"""Seeded capture driver: step ShooterGame with a bot script, then headless Engine capture.

Routes (seed 1, FIXED_STEP):
  spawn   : 1 idle frame (empty arena baseline)
  combat  : kite 300 frames (aimed fight, tracers/particles live)
  pickup  : kite until wave>=2 and pickup visible, or 1200 frames max
  death   : hp=10 + brute at 1 m, 180 idle frames (YOU DIED)

Writes PNG + JSON report pairs for before/after comparison.
No balance changes; driver only.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "keystone"))

from keystone.input import ActionState  # noqa: E402
from keystone.math3d import Vec3  # noqa: E402
from keystone.replay import FIXED_STEP  # noqa: E402

from shooter.bot import fire_hold, kite_step  # noqa: E402
from shooter.game import ShooterGame  # noqa: E402
from shooter.sim import _Enemy  # noqa: E402


def _capture_stepped(game: ShooterGame, out_png: str, out_json: str, w: int = 960, h: int = 540) -> None:
    """Capture the already-stepped game without resetting it.

    Engine.__init__ calls game.build_scene(), so the game must be stepped
    AFTER the Engine exists (engine.game is the same object).
    """
    from keystone.app import Engine

    engine = Engine(game, w, h, visible=False, msaa=0, ui=True)
    try:
        engine.capture(out_png, out_json)
        print(f"wrote {out_png} + {out_json}")
    finally:
        engine.close()


def _capture(game: ShooterGame, out_png: str, out_json: str, w: int = 960, h: int = 540) -> None:
    _capture_stepped(game, out_png, out_json, w, h)


def _engine_with(game: ShooterGame, w: int = 960, h: int = 540):
    from keystone.app import Engine

    return Engine(game, w, h, visible=False, msaa=0, ui=True)


def route_spawn(prefix: str) -> None:
    from keystone.app import Engine

    game = ShooterGame()
    engine = Engine(game, 960, 540, visible=False, msaa=0, ui=True)
    try:
        engine.game.update(FIXED_STEP, ActionState())
        engine.capture(f"{prefix}_spawn.png", f"{prefix}_spawn.json")
        print(f"wrote {prefix}_spawn.png + {prefix}_spawn.json")
    finally:
        engine.close()


def route_combat(prefix: str, frames: int = 277) -> None:
    # 277 = 2 enemies alive + a shot fired this frame (kite scan);
    # frame 300 lands between waves with nothing alive.
    from keystone.app import Engine

    game = ShooterGame()
    engine = Engine(game, 960, 540, visible=False, msaa=0, ui=True)
    try:
        for _ in range(frames):
            engine.game.update(FIXED_STEP, kite_step(engine.game.sim))
        g = engine.game
        print(f"combat shots={g.sim.shots} hits={g.sim.hits} kills={g.sim.kills} wave={g.sim.wave} hp={g.sim.hp}")
        engine.capture(f"{prefix}_combat.png", f"{prefix}_combat.json")
        print(f"wrote {prefix}_combat.png + {prefix}_combat.json")
    finally:
        engine.close()


def route_fireburst(prefix: str) -> None:
    """Aimed burst at a static target: guarantees visible tracer + flash + hitmark."""
    from keystone.app import Engine
    from keystone.input import ActionState as AS

    game = ShooterGame()
    engine = Engine(game, 960, 540, visible=False, msaa=0, ui=True)
    try:
        g = engine.game
        g.sim.spawn_queue = []
        g.sim.enemies = [_Enemy(etype="mite", pos=Vec3(0.0, 0.5, 2.0), hp=30, max_hp=30)]
        # step until a shot fires, then capture on that exact frame
        fired = False
        for a in fire_hold(60):
            before = g.sim.shots
            g.update(FIXED_STEP, a)
            if g.sim.shots > before:
                fired = True
                break
        # keep stepping idle (no fire) at most 1 frame so flash/tracer stay alive
        print(f"burst shots={g.sim.shots} hits={g.sim.hits} flash={g.sim.flash_t:.3f} tracers={len(g.sim.tracers)} fired={fired}")
        engine.capture(f"{prefix}_burst.png", f"{prefix}_burst.json")
        print(f"wrote {prefix}_burst.png + {prefix}_burst.json")
    finally:
        engine.close()


def route_pickup(prefix: str) -> None:
    from keystone.app import Engine

    game = ShooterGame()
    engine = Engine(game, 960, 540, visible=False, msaa=0, ui=True)
    try:
        g = engine.game
        for i in range(1200):
            g.update(FIXED_STEP, kite_step(g.sim))
            if g.sim.pickup_active:
                break
        # Re-stage for the proof frame: the wave-2 surge spot (0, -6) sits
        # behind center cover from spawn, so stage the viewer at (3.5, 8)
        # facing it. Gameplay DATA is untouched; only the camera moves.
        import math
        from dataclasses import replace

        from keystone.math3d import Vec3 as _V

        g.sim.player_pos = _V(3.5, 0.9, 8.0)
        # physics body overwrites player_pos each step: re-stage it too
        g.sim.body = replace(g.sim.body, position=_V(3.5, 0.9, 8.0))
        g.sim.hvel = _V(0.0, 0.0, 0.0)
        g.sim.yaw = math.atan2(0.0 - 3.5, -(-6.0 - 8.0))
        g.sim.pitch = 0.0
        g.sim.kick = 0.0
        g.update(FIXED_STEP, ActionState())
        print(f"pickup wave={g.sim.wave} active={g.sim.pickup_active} frame={g.sim.tick}")
        engine.capture(f"{prefix}_pickup.png", f"{prefix}_pickup.json")
        print(f"wrote {prefix}_pickup.png + {prefix}_pickup.json")
    finally:
        engine.close()


def route_death(prefix: str) -> None:
    from keystone.app import Engine

    game = ShooterGame()
    engine = Engine(game, 960, 540, visible=False, msaa=0, ui=True)
    try:
        g = engine.game
        g.sim.spawn_queue = []
        g.sim.hp = 10
        g.sim.enemies = [_Enemy(etype="brute", pos=Vec3(0.0, 0.7, 7.0), hp=120, max_hp=120)]
        for _ in range(180):
            g.update(FIXED_STEP, ActionState())
        print(f"death hp={g.sim.hp} alive={g.sim.alive}")
        engine.capture(f"{prefix}_death.png", f"{prefix}_death.json")
        print(f"wrote {prefix}_death.png + {prefix}_death.json")
    finally:
        engine.close()


def main(which: str = "all", prefix: str = "shot_fix") -> None:
    if which in ("all", "spawn"):
        route_spawn(prefix)
    if which in ("all", "combat"):
        route_combat(prefix)
    if which in ("all", "burst"):
        route_fireburst(prefix)
    if which in ("all", "pickup"):
        route_pickup(prefix)
    if which in ("all", "death"):
        route_death(prefix)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all", sys.argv[2] if len(sys.argv) > 2 else "shot_fix")
