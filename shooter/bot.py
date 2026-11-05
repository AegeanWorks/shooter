"""Headless bot scripts: move, shoot, kill. No window, deterministic."""

from __future__ import annotations

import math

from keystone.input import ActionState


def idle(n: int) -> list[ActionState]:
    return [ActionState() for _ in range(n)]


def move_forward(n: int, sprint: bool = False) -> list[ActionState]:
    held = frozenset({"sprint"}) if sprint else frozenset()
    return [ActionState(forward=1.0, held=held) for _ in range(n)]


def look_spin(n: int, yaw_per_frame: float = 0.02) -> list[ActionState]:
    return [ActionState(look_yaw=yaw_per_frame) for _ in range(n)]


def fire_hold(n: int) -> list[ActionState]:
    """Hold fire (keyboard path) so auto weapons keep firing headless."""
    return [ActionState(held=frozenset({"fire"})) for _ in range(n)]


def fire_clicks(n: int) -> list[ActionState]:
    return [ActionState(pressed=frozenset({"fire"}), mouse_clicked=True) for _ in range(n)]


def assault(n_move: int = 60, n_fire: int = 240) -> list[ActionState]:
    """Walk forward then hold fire: movement + determinism proof (see ADR-006)."""
    script = move_forward(n_move)
    script.extend(fire_hold(n_fire))
    return script


def _ammo_total(sim, wid: str) -> int:
    return int(sim.ammo.get(wid, 0)) + int(sim.reserve.get(wid, 0))


def _face(sim, tx: float, tz: float, turn: float = 0.12) -> tuple[float, float]:
    dx, dz = tx - sim.player_pos.x, tz - sim.player_pos.z
    dyaw = (math.atan2(dx, -dz) - sim.yaw + math.pi) % math.tau - math.pi
    return max(-turn, min(turn, dyaw)), 0.0


def kite_step(sim) -> ActionState:
    """One feedback tick: face the nearest live enemy, hold 6-12 m, fire when aimed.

    Pure function of sim state (no RNG, no wall-clock), so recorded logs replay
    deterministically. Uses the shipped ammo economy: pulse first, detours to the
    surge pickup when pulse runs dry, otherwise falls back to scatter/lance.
    """
    if not sim.alive:
        return ActionState()
    if _ammo_total(sim, sim.weapon) <= 0:
        if sim.pickup_active:
            look_yaw, look_pitch = _face(sim, 0.0, -6.0)
            return ActionState(forward=1.0, look_yaw=look_yaw, look_pitch=look_pitch)
        for wid, slot in (("scatter", "slot2"), ("lance", "slot3")):
            if _ammo_total(sim, wid) > 0:
                return ActionState(pressed=frozenset({slot}))
        # Dry on every gun: keep dodging (orbit strafe) instead of standing
        # still. No kills means no cache income, so this is survival-only —
        # but a moving target outlives a parked one until a wave clears.
        orbit = 1.0 if (sim.tick // 90) % 2 == 0 else -1.0
        return ActionState(forward=-0.5, right=0.7 * orbit)
    living = [e for e in sim.enemies if e.alive]
    if not living:
        return ActionState()
    px, pz = sim.player_pos.x, sim.player_pos.z
    target = min(living, key=lambda e: (e.pos.x - px) ** 2 + (e.pos.z - pz) ** 2)
    dx, dz = target.pos.x - px, target.pos.z - pz
    dist = math.hypot(dx, dz)
    desired_yaw = math.atan2(dx, -dz)
    dyaw = (desired_yaw - sim.yaw + math.pi) % math.tau - math.pi
    eye_y = sim.player_pos.y + 0.72
    desired_pitch = math.atan2((target.pos.y + 0.3) - eye_y, max(dist, 1e-6))
    dpitch = desired_pitch - sim.pitch
    turn = 0.12
    look_yaw = max(-turn, min(turn, dyaw))
    look_pitch = max(-turn, min(turn, dpitch))
    aimed = abs(dyaw) < 0.15 and abs(dpitch) < 0.15
    w = sim.weapons.get(sim.weapon, {})
    in_range = dist <= float(w.get("range", 60.0))
    if dist < 6.0:
        forward = -1.0
    elif dist > 12.0:
        forward = 1.0
    else:
        forward = 0.0
    orbit = 1.0 if (sim.tick // 90) % 2 == 0 else -1.0
    held = frozenset({"fire"}) if (aimed and in_range) else frozenset()
    return ActionState(
        forward=forward, right=0.7 * orbit,
        look_yaw=look_yaw, look_pitch=look_pitch, held=held,
    )


def strafe_fire(n: int = 300) -> list[ActionState]:
    script: list[ActionState] = []
    for i in range(n):
        right = 1.0 if (i // 30) % 2 == 0 else -1.0
        script.append(ActionState(forward=0.6, right=right, held=frozenset({"fire"})))
    return script


def overdrive_step(sim) -> ActionState:
    """Measurement policy: kite + voluntary overdrive when it is a real choice.

    Presses overdrive only when preview passes (pulse reserve covers cost)
    and streak >= 3, so uptake is measured, never forced. Otherwise identical
    to kite_step.
    """
    base = kite_step(sim)
    try:
        prev = sim.overdrive_preview()
    except AttributeError:
        return base
    if bool(prev.get("ok", False)) and int(getattr(sim, "streak", 0)) >= 3:
        pressed = set(getattr(base, "pressed", frozenset())) | {"overdrive"}
        return ActionState(
            forward=float(getattr(base, "forward", 0.0)),
            right=float(getattr(base, "right", 0.0)),
            up=float(getattr(base, "up", 0.0)),
            look_yaw=float(getattr(base, "look_yaw", 0.0)),
            look_pitch=float(getattr(base, "look_pitch", 0.0)),
            pressed=frozenset(pressed),
            held=getattr(base, "held", frozenset()),
            mouse_clicked=bool(getattr(base, "mouse_clicked", False)),
        )
    return base
