"""Boltshooter: Keystone plug-in shooter. Engine owns loop/render/input.

Game owns state/rules/scene. Five ops + optional draw_ui. All tuning in
shooter/data/*.json, never hardcoded one-offs.
"""

from __future__ import annotations

import math
from dataclasses import replace

from keystone.assets import AssetRegistry
from keystone.audio import Mixer, noise, sine, square
from keystone.geometry import Material
from keystone.math3d import Quat, Vec3
from keystone.primitives import cone, cube, plane, sphere
from keystone.scene import DirectionalLight, Node, PointLight, Scene, Transform
from keystone.texture import TextureData

from .sim import Sim
from .ui import draw_shooter

MAX_ENEMIES = 24
MAX_TRACERS = 16


class ShooterGame:
    name = "shooter"

    def __init__(self) -> None:
        self.sim = Sim(seed=1)
        self.scene = Scene()
        self.assets = AssetRegistry()
        self.mixer = Mixer()
        self._clips: dict = {}
        self._enemy_nodes: list[Node] = []
        self._tracer_nodes: list[Node] = []
        self._flash: Node | None = None
        self._pickup: Node | None = None
        self._built = False

    # ---- five-operation contract --------------------------------------
    def build_scene(self) -> Scene:
        self.sim.reset()
        self.scene = Scene()
        self.assets = AssetRegistry()
        self.mixer = Mixer()
        self.particles = self.sim.particles

        self.assets.register("mesh.floor", plane(40.0))
        self.assets.register("mesh.wall", cube(1.0))
        self.assets.register("mesh.mite", sphere(0.5, segments=16, rings=10))
        self.assets.register("mesh.brute", cube(1.4))
        self.assets.register("mesh.wisp", cone(0.4, 0.9, segments=12))
        self.assets.register("mesh.tracer", cube(1.0))
        self.assets.register("mesh.flash", cube(1.0))
        self.assets.register("mesh.pickup", cube(0.6))
        checker = TextureData.checker(64, (0.10, 0.12, 0.16), (0.18, 0.20, 0.25), name="floor-checker")
        self.assets.register("texture.floor", checker)
        self.assets.register("material.floor", Material(color=Vec3(1, 1, 1), specular=0.08, shininess=8.0, texture=checker, checker_scale=0.5))
        self.assets.register("material.wall", Material(color=Vec3(0.42, 0.44, 0.50), specular=0.2, shininess=24.0))
        self.assets.register("material.cover", Material(color=Vec3(0.58, 0.46, 0.30), specular=0.15, shininess=18.0))
        self.assets.register("material.mite", Material(color=Vec3(0.95, 0.45, 0.15), specular=0.4, shininess=48.0, emissive=Vec3(0.55, 0.18, 0.02)))
        self.assets.register("material.brute", Material(color=Vec3(0.60, 0.40, 0.90), specular=0.4, shininess=48.0, metallic=0.2, roughness=0.5))
        self.assets.register("material.wisp", Material(color=Vec3(0.30, 0.85, 1.00), specular=0.6, shininess=64.0, emissive=Vec3(0.10, 0.45, 0.55)))
        self.assets.register("material.tracer", Material(color=Vec3(1.0, 0.85, 0.30), emissive=Vec3(0.9, 0.65, 0.15)))
        self.assets.register("material.flash", Material(color=Vec3(1.0, 1.0, 1.0), emissive=Vec3(1.0, 0.9, 0.6)))
        self.assets.register("material.pickup", Material(color=Vec3(0.25, 1.0, 0.45), emissive=Vec3(0.10, 0.55, 0.20)))

        self.scene.background = Vec3(0.035, 0.045, 0.07)
        self.scene.sky = Vec3(0.01, 0.015, 0.04)
        self.scene.ambient = Vec3(0.22, 0.24, 0.30)
        self.scene.fog_density = 0.008
        self.scene.camera.position = Vec3(0.0, 1.62, 8.0)
        self.scene.camera.fov_y = 75.0
        self.scene.camera.yaw = 0.0
        self.scene.camera.pitch = 0.0
        self.scene.camera.look_at(Vec3(0.0, 1.4, 0.0))
        self.scene.light = DirectionalLight(direction=Vec3(-0.45, -1.0, -0.35), color=Vec3(1.0, 0.93, 0.82), intensity=1.1)
        self.scene.point_light = PointLight(position=Vec3(0.0, 2.5, 8.0), color=Vec3(1.0, 0.8, 0.5), intensity=0.4, radius=14.0)

        floor = self.assets.require("mesh.floor").payload
        floor_mat = self.assets.require("material.floor").payload
        self.scene.add(Node("floor", id="floor", mesh=floor, material=floor_mat))
        wall_mesh = self.assets.require("mesh.wall").payload
        wall_mat = self.assets.require("material.wall").payload

        def wall(node_id: str, x: float, y: float, z: float, sx: float, sy: float, sz: float, mat=None) -> None:
            self.scene.add(Node(node_id, id=node_id, transform=Transform(position=Vec3(x, y, z), scale=Vec3(sx, sy, sz)), mesh=wall_mesh, material=mat if mat is not None else wall_mat))

        size = 20.0
        wall("wall-n", 0.0, 1.5, -20.0, 41.0, 3.0, 1.0)
        wall("wall-s", 0.0, 1.5, 20.0, 41.0, 3.0, 1.0)
        wall("wall-w", -20.0, 1.5, 0.0, 1.0, 3.0, 41.0)
        wall("wall-e", 20.0, 1.5, 0.0, 1.0, 3.0, 41.0)
        cover_mat = self.assets.require("material.cover").payload
        for i, c in enumerate(self.sim.levels["arena"]["covers"]):
            wall(f"cover-{i}", float(c["x"]), float(c["h"]) / 2.0, float(c["z"]), float(c["w"]), float(c["h"]), float(c["d"]), mat=cover_mat)

        # enemy pool (shared payloads -> auto-instancing)
        self._enemy_nodes = []
        for i in range(MAX_ENEMIES):
            node = Node(f"enemy-{i:02d}", id=f"enemy-{i:02d}", visible=False,
                        mesh=self.assets.require("mesh.mite").payload,
                        material=self.assets.require("material.mite").payload)
            self.scene.add(node)
            self._enemy_nodes.append(node)
        # tracer pool
        self._tracer_nodes = []
        tracer_mesh = self.assets.require("mesh.tracer").payload
        tracer_mat = self.assets.require("material.tracer").payload
        for i in range(MAX_TRACERS):
            node = Node(f"tracer-{i:02d}", id=f"tracer-{i:02d}", visible=False,
                        mesh=tracer_mesh, material=tracer_mat)
            self.scene.add(node)
            self._tracer_nodes.append(node)
        flash_mesh = self.assets.require("mesh.flash").payload
        flash_mat = self.assets.require("material.flash").payload
        self._flash = Node("muzzle", id="muzzle", visible=False, mesh=flash_mesh, material=flash_mat)
        self.scene.add(self._flash)
        pickup_mesh = self.assets.require("mesh.pickup").payload
        pickup_mat = self.assets.require("material.pickup").payload
        self._pickup_spot = self.sim.levels.get("pickup", {"x": 0.0, "y": 0.5, "z": -6.0})
        self._pickup = Node("surge-pickup", id="surge-pickup", visible=False,
                            transform=Transform(position=Vec3(
                                float(self._pickup_spot["x"]), float(self._pickup_spot["y"]), float(self._pickup_spot["z"]))),
                            mesh=pickup_mesh, material=pickup_mat)
        self.scene.add(self._pickup)

        # pre-synthesized deterministic SFX (no per-frame synth)
        self._clips = {
            "shoot": square(180.0, 0.08, name="shoot"),
            "scatter": noise(0.12, seed=5, name="scatter"),
            "lance": square(440.0, 0.12, name="lance"),
            "hit": noise(0.05, seed=9, name="hit"),
            "kill": sine(220.0, 0.15, name="kill"),
            "pickup": sine(880.0, 0.12, name="pickup"),
            "hurt": square(110.0, 0.15, name="hurt"),
            "wave": sine(660.0, 0.20, name="wave"),
        }
        self._built = True
        self._sync_scene()
        return self.scene

    def update(self, dt: float, actions) -> None:
        if not self._built:
            self.build_scene()
        events = self.sim.step(float(dt), actions)
        for e in events:
            if e == "shoot":
                w = self.sim.weapon
                clip = self._clips.get({"pulse": "shoot", "scatter": "scatter", "lance": "lance", "surge": "shoot"}.get(w, "shoot"), self._clips["shoot"])
                try:
                    self.mixer.play(clip, bus="sfx", gain=0.7)
                except ValueError:
                    pass
            elif e == "hit":
                try:
                    self.mixer.play(self._clips["hit"], bus="sfx", gain=0.5)
                except ValueError:
                    pass
            elif e == "kill":
                try:
                    self.mixer.play(self._clips["kill"], bus="sfx", gain=0.8)
                except ValueError:
                    pass
            elif e in ("pickup", "wave"):
                try:
                    self.mixer.play(self._clips["pickup" if e == "pickup" else "wave"], bus="sfx", gain=0.7)
                except ValueError:
                    pass
            elif e == "hurt":
                try:
                    self.mixer.play(self._clips["hurt"], bus="sfx", gain=0.8)
                except ValueError:
                    pass
        # cap voices: deterministic mixdown cost bounded (drop oldest beyond 8)
        while self.mixer.voice_count() > 8:
            self.mixer._voices.pop(0)
        self._sync_scene()

    def _sync_scene(self) -> None:
        sim = self.sim
        cam = self.scene.camera
        eye = sim.eye()
        cam.position = eye
        cam.yaw = sim.yaw
        cam.pitch = max(-1.55, min(1.55, sim.pitch + sim.kick))
        if self.scene.point_light is not None:
            base = Vec3(eye.x, eye.y + 0.4, eye.z)
            boost = 1.2 if sim.flash_t > 0.0 else 0.4
            self.scene.point_light = replace(self.scene.point_light, position=base, intensity=boost)
        mesh_by_type = {
            "mite": (self.assets.require("mesh.mite").payload, self.assets.require("material.mite").payload, Vec3(1, 1, 1)),
            "brute": (self.assets.require("mesh.brute").payload, self.assets.require("material.brute").payload, Vec3(1, 1, 1)),
            "wisp": (self.assets.require("mesh.wisp").payload, self.assets.require("material.wisp").payload, Vec3(1, 1, 1)),
        }
        ordered = sorted([e for e in sim.enemies if True], key=lambda e: (0 if e.alive else 1, e.etype))
        for i, node in enumerate(self._enemy_nodes):
            if i < len(ordered) and ordered[i].alive:
                e = ordered[i]
                mesh, mat, _ = mesh_by_type[e.etype]
                node.mesh = mesh
                node.material = mat
                node.visible = True
                # death squash: scale down when hp low (presentation from sim hp)
                frac = max(0.4, min(1.0, e.hp / max(1, self.sim.enemy_defs[e.etype]["hp"])))
                s = 0.6 + 0.4 * frac
                node.transform = Transform(position=Vec3(e.pos.x, e.pos.y, e.pos.z), scale=Vec3(s, s, s))
            else:
                node.visible = False
        for i, node in enumerate(self._tracer_nodes):
            if i < len(sim.tracers):
                t = sim.tracers[i]
                x0, y0, z0, x1, y1, z1 = t["x0"], t["y0"], t["z0"], t["x1"], t["y1"], t["z1"]
                dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
                length = max(0.3, math.sqrt(dx * dx + dy * dy + dz * dz))
                # Cube length axis is +/-z: yaw maps +z onto the beam
                # (atan2(dx,-dz) is the camera-forward convention and mirrors
                # the beam front-to-back through the viewer). Pitch included
                # so the beam visually connects muzzle to hit.
                yaw = math.atan2(dx, dz) if (abs(dx) + abs(dz)) > 1e-6 else 0.0
                pitch = -math.atan2(dy, math.hypot(dx, dz))
                node.visible = True
                node.transform = Transform(
                    position=Vec3((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0),
                    rotation=Quat.from_axis_angle(Vec3(0.0, 1.0, 0.0), yaw)
                    * Quat.from_axis_angle(Vec3(1.0, 0.0, 0.0), pitch),
                    scale=Vec3(0.02, 0.02, length),
                )
            else:
                node.visible = False
        if self._flash is not None:
            if sim.flash_t > 0.0:
                self._flash.visible = True
                self._flash.transform = Transform(position=sim.flash_pos, scale=Vec3(0.10, 0.10, 0.10))
            else:
                self._flash.visible = False
        if self._pickup is not None:
            self._pickup.visible = bool(sim.pickup_active)
            if sim.pickup_active:
                spin = (sim.time * 1.5) % math.tau
                self._pickup.transform = Transform(
                    position=Vec3(float(self._pickup_spot["x"]),
                                  float(self._pickup_spot["y"]) + 0.15 * math.sin(sim.time * 3.0),
                                  float(self._pickup_spot["z"])),
                    rotation=Quat.from_axis_angle(Vec3(0.0, 1.0, 0.0), spin),
                )

    def snapshot(self) -> dict:
        return self.sim.snapshot()

    def actions(self) -> dict:
        return {
            "axes": ["forward", "right", "up", "look_yaw", "look_pitch"],
            "buttons": ["fire", "reload", "slot1", "slot2", "slot3", "jump", "sprint", "quit"],
            "notes": "fire=mouse_clicked or pressed.fire; hold fire key for auto",
        }

    def status(self) -> str:
        # Short HP/ammo line only: "|" has no bitmap glyph (renders as "?"),
        # and WAVE/SCORE/KILLS already live in draw_shooter top-center.
        s = self.sim
        return f"HP {s.hp} - {s.weapon} {s.ammo.get(s.weapon,0)}/{s.reserve.get(s.weapon,0)}"

    def draw_ui(self, canvas, state) -> None:
        draw_shooter(canvas, state, self.sim)
