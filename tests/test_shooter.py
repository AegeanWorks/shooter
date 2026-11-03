"""Shooter headless proofs: move, shoot, hit, kill, die, score, determinism."""

import json
from pathlib import Path

from keystone.batch import plan_batches
from keystone.gpu.instancing import plan_instanced
from keystone.headless import run_simulation
from keystone.input import ActionState
from keystone.replay import FIXED_STEP
from keystone.testing import assert_deterministic

from shooter.bot import assault, fire_hold, move_forward
from shooter.game import ShooterGame
from shooter.sim import _Enemy, Sim

DATA = Path(__file__).parent.parent / "shooter" / "data"


def _aimed_game() -> ShooterGame:
    from keystone.math3d import Vec3

    g = ShooterGame()
    g.build_scene()
    sim = g.sim
    sim.spawn_queue = []
    sim.enemies = [_Enemy(etype="mite", pos=Vec3(0.0, 0.5, 2.0), hp=30, max_hp=30)]
    return g


def _run_manual(g: ShooterGame, actions: list, dt: float = 1.0 / 60.0) -> dict:
    from keystone.replay import stable_hash

    for a in actions:
        g.update(dt, a)
    final = g.snapshot()
    return {"final": final, "hash": stable_hash(final)}


def test_contract():
    g = ShooterGame()
    assert g.name == "shooter"
    for op in ("build_scene", "update", "snapshot", "actions", "status"):
        assert callable(getattr(g, op)), op
    assert callable(getattr(g, "draw_ui", None))
    scene = g.build_scene()
    assert scene is not None
    snap = g.snapshot()
    for key in ("time", "tick", "wave", "shots", "hits", "kills", "score", "weapon", "player", "enemies"):
        assert key in snap, key
    acts = g.actions()
    assert "forward" in acts["axes"] and "look_yaw" in acts["axes"]
    assert "fire" in acts["buttons"]
    assert isinstance(g.status(), str)


def test_data_tables():
    weapons = json.loads((DATA / "weapons.json").read_text(encoding="utf-8"))["weapons"]
    enemies = json.loads((DATA / "enemies.json").read_text(encoding="utf-8"))["enemies"]
    levels = json.loads((DATA / "levels.json").read_text(encoding="utf-8"))
    juice = json.loads((DATA / "juice.json").read_text(encoding="utf-8"))
    assert len(weapons) >= 4
    assert len(enemies) == 3
    assert len(levels["waves"]) >= 5
    assert int(juice["max_particles"]) <= 256


def test_movement():
    g = ShooterGame()
    start = run_simulation(g, frames=1, actions=[ActionState()])["final"]["player"]
    result = run_simulation(ShooterGame(), frames=60, actions=move_forward(60))
    end = result["final"]["player"]
    assert end["z"] < start["z"] - 3.0, (start, end)
    assert abs(end["x"] - start["x"]) < 0.5
    assert end["hp"] == 100


def test_sprint_faster():
    # 30 frames: both clear of the center cover, sprint must separate
    walk = run_simulation(ShooterGame(), frames=30, actions=move_forward(30))["final"]["player"]
    sprinted = run_simulation(
        ShooterGame(), frames=30,
        actions=[ActionState(forward=1.0, held=frozenset({"sprint"})) for _ in range(30)],
    )["final"]["player"]
    assert (8.0 - sprinted["z"]) > (8.0 - walk["z"]) * 1.2


def test_first_gun_fires_hits():
    g = _aimed_game()
    result = _run_manual(g, fire_hold(60))
    final = result["final"]
    assert final["shots"] > 0, final
    assert final["hits"] > 0, final


def test_kill_scores():
    g = _aimed_game()
    result = _run_manual(g, fire_hold(300))
    final = result["final"]
    assert final["kills"] >= 1, final
    assert final["score"] >= 100, final


def _run_kite(g: ShooterGame, frames: int) -> dict:
    from keystone.replay import stable_hash

    from shooter.bot import kite_step

    for _ in range(frames):
        g.update(1.0 / 60.0, kite_step(g.sim))
    final = g.snapshot()
    return {"final": final, "hash": stable_hash(final)}


def test_kite_bot_clears_wave_one():
    g = ShooterGame()
    g.build_scene()
    result = _run_kite(g, 600)
    final = result["final"]
    assert final["wave"] >= 2, final
    assert final["kills"] >= 5, final
    assert final["player"]["alive"] is True, final
    again = _run_kite(ShooterGame(), 600)
    assert again["hash"] == result["hash"]


def test_kite_holds_distance_600():
    import math

    from shooter.bot import kite_step

    g = ShooterGame()
    g.build_scene()
    min_dist = 99.0
    for _ in range(600):
        g.update(1.0 / 60.0, kite_step(g.sim))
        px, pz = g.sim.player_pos.x, g.sim.player_pos.z
        for e in g.sim.enemies:
            if e.alive:
                min_dist = min(min_dist, math.hypot(e.pos.x - px, e.pos.z - pz))
    final = g.snapshot()
    assert final["player"]["alive"] is True, final
    assert min_dist > 1.5, min_dist


def test_strafe_baseline_locked():
    from shooter.bot import strafe_fire

    g = ShooterGame()
    result = run_simulation(g, frames=300, actions=strafe_fire(300))
    final = result["final"]
    assert final["player"]["alive"] is True, final
    assert final["shots"] == 30, final
    assert final["hits"] == 2, final
    assert final["player"]["hp"] == 84, final


def test_player_can_die():
    from keystone.math3d import Vec3

    g = ShooterGame()
    g.build_scene()
    g.sim.spawn_queue = []
    g.sim.hp = 10
    g.sim.enemies = [_Enemy(etype="brute", pos=Vec3(0.0, 0.7, 7.0), hp=120, max_hp=120)]
    result = _run_manual(g, [ActionState() for _ in range(180)])
    final = result["final"]
    assert final["player"]["hp"] <= 10, final
    # brute at 1m deals 20: after 3s at least one slam lands
    assert final["player"]["hp"] < 10 or final["player"]["alive"] is False, final


def test_determinism():
    script = assault(30, 120)
    assert_deterministic(lambda: ShooterGame(), script, frames=len(script))
    first = run_simulation(ShooterGame(), frames=len(script), actions=script)
    second = run_simulation(ShooterGame(), frames=len(script), actions=script)
    assert first["hash"] == second["hash"]


def test_frame_budget():
    g = ShooterGame()
    scene = g.build_scene()
    # simulate 120 frames of combat to populate tracers/enemies, then re-check
    run_simulation(g, frames=120, actions=assault(30, 90))
    plan = plan_batches(g.scene)
    inst = plan_instanced(g.scene)
    assert plan["draw_calls"] <= 40, plan
    assert plan["triangles"] <= 80000, plan
    assert inst["instanced_calls"] <= 40, inst


def test_fixed_step():
    assert abs(FIXED_STEP - 1.0 / 60.0) < 1e-9
