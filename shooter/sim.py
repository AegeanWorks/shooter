"""Deterministic shooter simulation: movement, hitscan weapons, enemies, waves.

No window, GL, or wall-clock. Own RNG (random.Random) seeded fixed for
--verify-determinism stability. Scene sync lives in game.py; this module
is headless-testable via keystone.testing.run_script.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from keystone.broadphase import SpatialGrid
from keystone.character import CharacterBody, CharacterController
from keystone.math3d import Vec3
from keystone.particles import Emitter, ParticleSystem
from keystone.physics import AABB, Ray, aabb_overlap, ray_aabb
from keystone.triggers import TriggerTracker, TriggerVolume

DATA_DIR = Path(__file__).parent / "data"

WALK_SPEED = 6.5
SPRINT_SPEED = 9.0
ACCEL_GROUND = 40.0
ACCEL_AIR = 14.0
FRICTION = 12.0
JUMP_SPEED = 7.2
COYOTE_S = 0.12
BUFFER_S = 0.12
PITCH_LIMIT = 1.45


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@dataclass
class _Enemy:
    etype: str
    pos: Vec3
    hp: int
    max_hp: int
    alive: bool = True
    attack_cd: float = 0.0
    state_t: float = 0.0
    pause_t: float = 0.0


class Sim:
    """Owns all deterministic shooter state. Game.py mirrors it into a Scene."""

    def __init__(self, seed: int = 1) -> None:
        self.weapons = {w["id"]: w for w in _load("weapons.json")["weapons"]}
        self.enemy_defs = {e["id"]: e for e in _load("enemies.json")["enemies"]}
        self.levels = _load("levels.json")
        self.juice = _load("juice.json")
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.controller = CharacterController(gravity=24.0)
        self.grid = SpatialGrid(cell_size=4.0)
        self.particles = ParticleSystem(
            emitters={
                "impact": Emitter(
                    name="impact", rate=0.0, lifetime=0.4, speed=4.0,
                    spread=1.0, direction=Vec3(0.0, 1.0, 0.0),
                    gravity=Vec3(0.0, -9.0, 0.0), drag=2.0, size=1.0, seed=11,
                ),
                "kill": Emitter(
                    name="kill", rate=0.0, lifetime=0.6, speed=6.0,
                    spread=1.0, direction=Vec3(0.0, 1.0, 0.0),
                    gravity=Vec3(0.0, -7.0, 0.0), drag=1.5, size=1.4, seed=23,
                ),
            },
            max_particles=int(self.juice.get("max_particles", 256)),
        )
        self.tracker = TriggerTracker()
        self.reset()

    def reseed(self, seed: int) -> None:
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.reset()

    # ---- setup ---------------------------------------------------------
    def _colliders(self) -> list[AABB]:
        size = float(self.levels["arena"]["size"])
        half = size / 2.0
        h = float(self.levels["arena"]["wall_height"])
        boxes = [AABB(Vec3(0.0, -0.5, 0.0), Vec3(half, 0.5, half))]  # floor
        wall_t = 0.5
        boxes.append(AABB(Vec3(0.0, h / 2.0, -half), Vec3(half + wall_t, h / 2.0 + 0.5, wall_t)))
        boxes.append(AABB(Vec3(0.0, h / 2.0, half), Vec3(half + wall_t, h / 2.0 + 0.5, wall_t)))
        boxes.append(AABB(Vec3(-half, h / 2.0, 0.0), Vec3(wall_t, h / 2.0 + 0.5, half + wall_t)))
        boxes.append(AABB(Vec3(half, h / 2.0, 0.0), Vec3(wall_t, h / 2.0 + 0.5, half + wall_t)))
        for c in self.levels["arena"]["covers"]:
            boxes.append(
                AABB(
                    Vec3(float(c["x"]), float(c["h"]) / 2.0, float(c["z"])),
                    Vec3(float(c["w"]) / 2.0, float(c["h"]) / 2.0, float(c["d"]) / 2.0),
                )
            )
        return boxes

    def reset(self) -> None:
        self.rng = random.Random(self.seed)
        spawn = self.levels["player"]["spawn"]
        # rest on floor with skin gap so the floor never blocks horizontal moves
        self.player_pos = Vec3(float(spawn[0]), float(spawn[1]) + 0.0002, float(spawn[2]))
        self.body = CharacterBody(position=self.player_pos)
        self.yaw = math.pi  # face -Z? spawn z=8 looking to center: yaw=pi faces +Z? corrected below
        self.yaw = 0.0  # forward -Z looks toward origin from z=8
        self.pitch = 0.0
        self.hp = int(self.levels["player"]["hp"])
        self.alive = True
        self.hvel = Vec3()
        self.coyote = 0.0
        self.buffer = 0.0
        self.weapon = "pulse"
        self.ammo = {wid: int(w["mag"]) for wid, w in self.weapons.items()}
        self.reserve = {wid: int(w["reserve"]) for wid, w in self.weapons.items()}
        self.cooldown = 0.0
        self.reload_t = 0.0
        self.surge_t = 0.0
        self.kick = 0.0
        self.hitstop = 0
        self.hitmark_t = 0.0
        self.flash_t = 0.0
        self.flash_pos = Vec3()
        self.tracers: list[dict] = []
        self.enemies: list[_Enemy] = []
        self._next_enemy = 1
        self.shots = 0
        self.hits = 0
        self.kills = 0
        self.score = 0
        self.time = 0.0
        self.tick = 0
        self.wave = 1
        self.spawn_queue: list[str] = []
        self.spawn_t = 0.0
        self.pickup_active = False
        self.pickup_taken = False
        self._build_wave()
        self.colliders = self._colliders()
        self.grid.clear()
        for i, b in enumerate(self.colliders):
            self.grid.insert(f"wall:{i}", b)
        self.particles.clear()
        self.tracker = TriggerTracker()

    def _build_wave(self) -> None:
        waves = self.levels["waves"]
        spec = waves[(self.wave - 1) % len(waves)]
        queue: list[str] = []
        for etype in ("mite", "brute", "wisp"):
            queue.extend([etype] * int(spec.get(etype, 0)))
        # deterministic shuffle
        self.rng.shuffle(queue)
        self.spawn_queue = queue
        self.spawn_t = 0.5
        if int(self.wave) >= int(self.levels.get("pickup_wave", 2)) and not self.pickup_taken:
            self.pickup_active = True
        else:
            self.pickup_active = self.pickup_active and not self.pickup_taken

    def _spawn_enemy(self, etype: str) -> None:
        edef = self.enemy_defs[etype]
        px, _, pz = self.player_pos.x, self.player_pos.y, self.player_pos.z
        x, z = 0.0, -18.0
        for _ in range(5):
            x = self.rng.uniform(-18.0, 18.0)
            z = self.rng.uniform(-18.0, 18.0)
            if math.hypot(x - px, z - pz) >= 10.0:
                break
        y = float(edef["height"]) / 2.0
        self.enemies.append(
            _Enemy(
                etype=etype, pos=Vec3(x, y, z),
                hp=int(edef["hp"]), max_hp=int(edef["hp"]),
            )
        )
        self._next_enemy += 1

    # ---- helpers -------------------------------------------------------
    def eye(self) -> Vec3:
        return Vec3(self.player_pos.x, self.player_pos.y + 0.72, self.player_pos.z)

    def forward(self) -> Vec3:
        cp = math.cos(self.pitch)
        return Vec3(math.sin(self.yaw) * cp, math.sin(self.pitch), -math.cos(self.yaw) * cp)

    def _enemy_box(self, e: _Enemy) -> AABB:
        # Generous hitbox (aim assist): tall enough that hip-fire from eye
        # level hits grounded enemies without pixel-perfect pitch.
        edef = self.enemy_defs[e.etype]
        r = float(edef["radius"]) + 0.15
        hy = float(edef["height"]) / 2.0 + 0.45
        center = Vec3(e.pos.x, e.pos.y + 0.3, e.pos.z)
        return AABB(center, Vec3(r, hy, r))

    # ---- main step -----------------------------------------------------
    def step(self, dt: float, actions) -> list[str]:
        events: list[str] = []
        if dt <= 0.0:
            raise ValueError("dt must be positive")
        fwd_in = float(getattr(actions, "forward", 0.0))
        right_in = float(getattr(actions, "right", 0.0))
        up_in = float(getattr(actions, "up", 0.0))
        look_yaw = float(getattr(actions, "look_yaw", 0.0))
        look_pitch = float(getattr(actions, "look_pitch", 0.0))
        pressed = set(getattr(actions, "pressed", frozenset()))
        held = set(getattr(actions, "held", frozenset()))
        clicked = bool(getattr(actions, "mouse_clicked", False))

        frozen = self.hitstop > 0
        if self.hitstop > 0:
            self.hitstop -= 1

        # look (skipped during hitstop freeze for punch)
        if self.alive and not frozen:
            self.yaw = (self.yaw + look_yaw) % math.tau
            self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, self.pitch + look_pitch))

        # weapon switch
        if self.alive and not frozen:
            if "slot1" in pressed:
                self._switch("pulse", events)
            elif "slot2" in pressed:
                self._switch("scatter", events)
            elif "slot3" in pressed:
                self._switch("lance", events)

        # movement with accel/friction smoothing, then engine collision
        if self.alive and not frozen:
            sprint = "sprint" in held
            speed = SPRINT_SPEED if sprint else WALK_SPEED
            fx, fz = math.sin(self.yaw), -math.cos(self.yaw)
            rx, rz = math.cos(self.yaw), math.sin(self.yaw)
            wish_x = fx * fwd_in * speed + rx * right_in * speed
            wish_z = fz * fwd_in * speed + rz * right_in * speed
            wish = Vec3(wish_x, 0.0, wish_z)
            cur = self.hvel
            rate = FRICTION if (abs(fwd_in) < 1e-6 and abs(right_in) < 1e-6) else (
                ACCEL_GROUND if self.body.on_ground else ACCEL_AIR
            )
            blend = min(1.0, rate * dt)
            self.hvel = Vec3(
                cur.x + (wish.x - cur.x) * blend, 0.0, cur.z + (wish.z - cur.z) * blend
            )
            jump_intent = up_in > 0.5 or "jump" in pressed
            if jump_intent:
                self.buffer = BUFFER_S
            else:
                self.buffer = max(0.0, self.buffer - dt)
            if self.body.on_ground:
                self.coyote = COYOTE_S
            else:
                self.coyote = max(0.0, self.coyote - dt)
            vy = self.body.velocity.y
            if self.buffer > 0.0 and (self.body.on_ground or self.coyote > 0.0):
                vy = JUMP_SPEED
                self.buffer = 0.0
                self.coyote = 0.0
            self.body = CharacterBody(
                position=self.body.position, half_extents=self.body.half_extents,
                velocity=Vec3(self.hvel.x, vy, self.hvel.z), on_ground=self.body.on_ground,
            )
            self.body = self.controller.step(self.body, self.hvel, dt, self.colliders)
            self.player_pos = self.body.position
            self.hvel = Vec3(self.body.velocity.x, 0.0, self.body.velocity.z)
        else:
            # still apply gravity settle when dead/frozen? keep deterministic no-op
            pass

        # timers
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.reload_t > 0.0:
            self.reload_t = max(0.0, self.reload_t - dt)
            if self.reload_t <= 0.0:
                w = self.weapons[self.weapon]
                need = int(w["mag"]) - int(self.ammo.get(self.weapon, 0))
                take = min(need, int(self.reserve.get(self.weapon, 0)))
                self.ammo[self.weapon] = int(self.ammo.get(self.weapon, 0)) + take
                self.reserve[self.weapon] = int(self.reserve.get(self.weapon, 0)) - take
                events.append("reloaded")
        if self.surge_t > 0.0:
            self.surge_t = max(0.0, self.surge_t - dt)
            if self.surge_t <= 0.0 and self.weapon == "surge":
                self._switch("pulse", events)
        self.kick *= max(0.0, 1.0 - 8.0 * dt)
        if abs(self.kick) < 1e-6:
            self.kick = 0.0
        self.hitmark_t = max(0.0, self.hitmark_t - dt)
        self.flash_t = max(0.0, self.flash_t - dt)
        for t in self.tracers:
            t["life"] = max(0.0, float(t["life"]) - dt)
        self.tracers = [t for t in self.tracers if t["life"] > 0.0][:16]

        # firing
        if self.alive and not frozen and self.reload_t <= 0.0:
            w = self.weapons[self.weapon]
            want_edge = clicked or ("fire" in pressed)
            want_hold = ("fire" in held) and bool(w.get("auto", False))
            if (want_edge or want_hold) and self.cooldown <= 0.0:
                if int(self.ammo.get(self.weapon, 0)) > 0:
                    self._fire(w, events)
                elif int(self.reserve.get(self.weapon, 0)) > 0 and float(w.get("reload_s", 0.0)) > 0.0:
                    self.reload_t = float(w["reload_s"])
                    events.append("reload")
                elif "reload" in pressed and int(self.reserve.get(self.weapon, 0)) > 0:
                    self.reload_t = float(w.get("reload_s", 1.0))
                    events.append("reload")
        if "reload" in pressed and self.reload_t <= 0.0 and self.alive:
            w = self.weapons[self.weapon]
            if int(self.ammo.get(self.weapon, 0)) < int(w["mag"]) and int(
                self.reserve.get(self.weapon, 0)
            ) > 0:
                self.reload_t = float(w.get("reload_s", 1.0))
                events.append("reload")

        # spawns
        if not frozen:
            self.spawn_t -= dt
            alive_count = sum(1 for e in self.enemies if e.alive)
            if self.spawn_queue and self.spawn_t <= 0.0 and alive_count < int(
                self.levels.get("max_alive", 24)
            ):
                self._spawn_enemy(self.spawn_queue.pop(0))
                self.spawn_t = float(self.levels.get("spawn_interval_s", 0.8))
                events.append("spawn")
            if not self.spawn_queue and alive_count == 0 and self.alive:
                # wave clear bonus then next wave
                self.score += 250
                self.wave += 1
                events.append("wave")
                self._build_wave()

        # enemies (frozen during hitstop)
        if not frozen:
            self._step_enemies(dt, events)

        # surge pickup via trigger volume (spot from levels.json DATA)
        if self.pickup_active and self.alive:
            box = AABB(self.player_pos, Vec3(0.35, 0.9, 0.35))
            spot = self.levels.get("pickup", {"x": 0.0, "y": 0.5, "z": -6.0})
            vol = TriggerVolume("surge", AABB(
                Vec3(float(spot["x"]), float(spot["y"]), float(spot["z"])),
                Vec3(1.0, 0.5, 1.0)))
            trig = self.tracker.update(box, [vol])
            if "surge" in trig.entered:
                self.pickup_active = False
                self.pickup_taken = True
                self.weapon = "surge"
                self.ammo["surge"] = int(self.weapons["surge"]["mag"])
                self.surge_t = float(self.weapons["surge"].get("duration_s", 10.0))
                self.reload_t = 0.0
                events.append("pickup")

        self.particles.step(dt)
        self.time += dt
        self.tick += 1
        return events

    def _switch(self, wid: str, events: list[str]) -> None:
        if wid not in self.weapons or wid == self.weapon:
            return
        if wid == "surge" and self.surge_t <= 0.0 and self.pickup_taken and self.ammo.get("surge", 0) <= 0:
            return
        self.weapon = wid
        self.reload_t = 0.0
        self.cooldown = max(self.cooldown, 0.08)
        events.append(f"switch:{wid}")

    def _fire(self, w: dict, events: list[str]) -> None:
        self.ammo[self.weapon] = int(self.ammo.get(self.weapon, 0)) - 1
        self.cooldown = 1.0 / float(w["rof"])
        self.shots += 1
        events.append("shoot")
        origin = self.eye()
        base = self.forward()
        rx, _, rz = math.cos(self.yaw), 0.0, math.sin(self.yaw)
        spread = math.radians(float(w.get("spread_hip_deg", 1.0)))
        pellets = int(w.get("pellets", 1))
        pierce = int(w.get("pierce", 1))
        wall_dists: list[float] = []
        for b in self.colliders:
            d = ray_aabb(Ray(origin, base), b)
            if d is not None:
                wall_dists.append(d)
        wall_best = min(wall_dists) if wall_dists else float("inf")
        for _ in range(pellets):
            ox = self.rng.uniform(-spread, spread) if spread > 0 else 0.0
            oy = self.rng.uniform(-spread, spread) if spread > 0 else 0.0
            direction = Vec3(base.x + rx * ox, base.y + oy, base.z + rz * ox).normalized()
            if direction.length_squared() < 1e-9:
                direction = base
            # gather enemy hits sorted
            scored: list[tuple[float, _Enemy]] = []
            for e in self.enemies:
                if not e.alive:
                    continue
                d = ray_aabb(Ray(origin, direction), self._enemy_box(e))
                if d is not None and d <= float(w["range"]):
                    scored.append((d, e))
            scored.sort(key=lambda item: item[0])
            end_dist = min(wall_best, float(w["range"]))
            impacted = False
            for d, e in scored[: max(1, pierce)]:
                if d > wall_best:
                    break
                fall = float(w.get("falloff_start", float(w["range"])))
                dmg = float(w["dmg"])
                if d > fall:
                    span = max(1e-6, float(w["range"]) - fall)
                    dmg *= max(0.3, 1.0 - (d - fall) / span * 0.7)
                e.hp -= int(round(dmg))
                self.hits += 1
                self.hitmark_t = float(self.juice.get("crosshair_hit_s", 0.12))
                hit_pos = Vec3(
                    origin.x + direction.x * d,
                    origin.y + direction.y * d,
                    origin.z + direction.z * d,
                )
                self.particles.burst("impact", int(self.juice.get("impact_burst", 12)), hit_pos)
                events.append("hit")
                impacted = True
                end_dist = min(end_dist, d)
                if e.hp <= 0 and e.alive:
                    e.alive = False
                    self.kills += 1
                    edef = self.enemy_defs[e.etype]
                    self.score += int(edef["score"])
                    self.particles.burst("kill", int(self.juice.get("kill_burst", 20)), e.pos)
                    self.hitstop = int(self.juice.get("hitstop_ticks", 2))
                    events.append("kill")
            if not impacted:
                # wall / ground puff at wall distance when within range
                if wall_best <= float(w["range"]):
                    hit_pos = Vec3(
                        origin.x + base.x * wall_best,
                        origin.y + base.y * wall_best,
                        origin.z + base.z * wall_best,
                    )
                    self.particles.burst("impact", 4, hit_pos)
            self.tracers.append(
                {
                    "x0": origin.x, "y0": origin.y, "z0": origin.z,
                    "x1": origin.x + direction.x * end_dist,
                    "y1": origin.y + direction.y * end_dist,
                    "z1": origin.z + direction.z * end_dist,
                    "life": float(self.juice.get("tracer_life_s", 0.08)),
                }
            )
            self.tracers = self.tracers[:16]
        self.flash_t = float(self.juice.get("flash_life_s", 0.06))
        self.flash_pos = Vec3(origin.x + base.x * 0.7, origin.y + base.y * 0.7 - 0.1, origin.z + base.z * 0.7)
        self.kick += math.radians(float(w.get("kick_deg", 0.6)))
        self.kick = min(self.kick, math.radians(4.0))

    def _step_enemies(self, dt: float, events: list[str]) -> None:
        eye = self.eye()
        wall_boxes = self.colliders
        for e in self.enemies:
            if not e.alive:
                continue
            edef = self.enemy_defs[e.etype]
            e.attack_cd = max(0.0, e.attack_cd - dt)
            e.state_t += dt
            to_p = Vec3(self.player_pos.x - e.pos.x, 0.0, self.player_pos.z - e.pos.z)
            dist = math.sqrt(to_p.x * to_p.x + to_p.z * to_p.z)
            direction = to_p.normalized() if dist > 1e-6 else Vec3()
            speed = float(edef["speed"])
            if e.etype == "mite":
                strafe = math.sin(self.time * 2.2 + e.state_t) * 0.8
                side = Vec3(-direction.z, 0.0, direction.x)
                vel = direction * speed + side * strafe
                if dist > 1.2:
                    e.pos = Vec3(e.pos.x + vel.x * dt, e.pos.y, e.pos.z + vel.z * dt)
                if dist <= float(edef["range"]) and e.attack_cd <= 0.0 and self.alive:
                    self.hp -= int(edef["dmg"])
                    e.attack_cd = 1.0
                    events.append("hurt")
                    if self.hp <= 0:
                        self.hp = 0
                        self.alive = False
                        events.append("died")
            elif e.etype == "brute":
                if e.pause_t > 0.0:
                    e.pause_t = max(0.0, e.pause_t - dt)
                elif dist > 3.0:
                    e.pos = Vec3(
                        e.pos.x + direction.x * speed * dt, e.pos.y,
                        e.pos.z + direction.z * speed * dt,
                    )
                    if dist < 6.0:
                        e.pause_t = 0.4
                if dist <= float(edef["range"]) and e.attack_cd <= 0.0 and self.alive:
                    self.hp -= int(edef["dmg"])
                    e.attack_cd = 2.0
                    events.append("hurt")
                    if self.hp <= 0:
                        self.hp = 0
                        self.alive = False
                        events.append("died")
            else:  # wisp
                side = Vec3(-direction.z, 0.0, direction.x)
                flank = 1.0 if math.sin(self.time * 1.3 + e.state_t * 0.7) >= 0.0 else -1.0
                if dist > 8.0:
                    vel = direction * speed + side * (flank * 2.0)
                elif dist < 5.0:
                    vel = direction * (-speed * 0.7) + side * (flank * 2.5)
                else:
                    vel = side * (flank * speed * 0.8)
                # dart every 2.1s
                if int((self.time + e.state_t) / 2.1) != int((self.time + e.state_t - dt) / 2.1):
                    vel = direction * (speed * 1.6)
                e.pos = Vec3(e.pos.x + vel.x * dt, e.pos.y, e.pos.z + vel.z * dt)
                if dist <= float(edef["range"]) and e.attack_cd <= 0.0 and self.alive:
                    # LOS check enemy->player against walls
                    src = Vec3(e.pos.x, e.pos.y + 0.3, e.pos.z)
                    vec = Vec3(eye.x - src.x, eye.y - src.y, eye.z - src.z)
                    length = vec.length()
                    blocked = False
                    if length > 1e-6:
                        ray = Ray(src, vec.normalized(), t_max=length)
                        for b in wall_boxes:
                            d = ray_aabb(ray, b)
                            if d is not None and d < length - 0.3:
                                blocked = True
                                break
                    if not blocked:
                        self.hp -= int(edef["dmg"])
                        e.attack_cd = 1.5
                        events.append("hurt")
                        if self.hp <= 0:
                            self.hp = 0
                            self.alive = False
                            events.append("died")
            # clamp arena
            e.pos = Vec3(max(-19.0, min(19.0, e.pos.x)), e.pos.y, max(-19.0, min(19.0, e.pos.z)))

    # ---- snapshot ------------------------------------------------------
    def snapshot(self) -> dict:
        def r(v: float) -> float:
            return round(float(v), 4)

        return {
            "time": r(self.time),
            "tick": int(self.tick),
            "seed": int(self.seed),
            "wave": int(self.wave),
            "shots": int(self.shots),
            "hits": int(self.hits),
            "kills": int(self.kills),
            "score": int(self.score),
            "weapon": str(self.weapon),
            "ammo": {k: int(v) for k, v in self.ammo.items()},
            "reserve": {k: int(v) for k, v in self.reserve.items()},
            "reloading": round(float(self.reload_t), 4),
            "player": {
                "x": r(self.player_pos.x),
                "y": r(self.player_pos.y),
                "z": r(self.player_pos.z),
                "yaw": r(self.yaw),
                "pitch": r(self.pitch),
                "kick": r(self.kick),
                "hp": int(self.hp),
                "alive": bool(self.alive),
            },
            "enemies": [
                {
                    "type": e.etype, "x": r(e.pos.x), "y": r(e.pos.y), "z": r(e.pos.z),
                    "hp": int(e.hp), "alive": bool(e.alive),
                }
                for e in sorted(self.enemies, key=lambda item: (item.etype, item.pos.x, item.pos.z))
            ],
            "alive_enemies": int(sum(1 for e in self.enemies if e.alive)),
            "hitstop": int(self.hitstop),
        }
