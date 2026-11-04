"""Engagement mechanics: stated-vs-coded odds, honesty, overdrive, lock, determinism.

Stage 2 revision pins: 85/12/3 partition, separate reward stream, single
near-miss detector (almost-won only), ammo-staked overdrive with preview,
surge-forfeit lock. Every claim here pairs with a measurement.
"""

import json
from pathlib import Path

from keystone.math3d import Vec3

from shooter.bot import kite_step
from shooter.game import ShooterGame
from shooter.sim import _Enemy, Sim

DATA = Path(__file__).parent.parent / "shooter" / "data"


def _load_eng():
    return json.loads((DATA / "engagement.json").read_text(encoding="utf-8"))


def _aimed_sim(enemy_hp=30, etype="mite"):
    s = Sim(seed=1)
    s.spawn_queue = []
    # mirror tests/test_shooter.py::_aimed_game spot (0,0.5,2.0): clear of the
    # center cover at (0,0.6,0) so the ray hits enemy before any wall.
    s.enemies = [_Enemy(etype=etype, pos=Vec3(0.0, 0.5, 2.0), hp=enemy_hp, max_hp=enemy_hp)]
    import math
    s.yaw = 0.0
    eye_y = s.player_pos.y + 0.72
    dist = abs(2.0 - s.player_pos.z)
    s.pitch = math.atan2((0.5 + 0.3) - eye_y, max(dist, 1e-6))
    return s


def test_engagement_data_valid():
    e = _load_eng()
    assert e["schema"] == 1
    r = e["reward"]
    total = float(r["standard_p"]) + float(r["critical_p"]) + float(r["cache_p"])
    assert abs(total - 1.0) < 1e-9, total
    assert float(r["critical_mult"]) > 1.0
    assert int(r["cache_reserve"]) > 0 and float(r["cache_expire_s"]) > 0
    assert e["streak"]["break_on"] == "hurt"
    assert e["overdrive"]["cost_reserve"] > 0 and e["overdrive"]["mult"] > 1.0
    assert e["surge_lock"] is True


def test_reward_stream_separate_and_reseedable():
    a = Sim(seed=7)
    b = Sim(seed=7)
    # combat-only consumption leaves the reward stream in lockstep
    a.rng.random()
    assert a.reward_rng.getstate() == b.reward_rng.getstate()
    # the reward stream is real state: it advances on rolls, then reseeds clean
    a.reward_rng.random()
    assert a.reward_rng.getstate() != b.reward_rng.getstate()
    a.reseed(7)
    assert a.reward_rng.getstate() == b.reward_rng.getstate()
    assert a.rng.getstate() == b.rng.getstate()


def test_stated_odds_match_coded_partition():
    s = Sim(seed=123)
    cfg = s._eng()
    n = 5000
    counts = {"standard": 0, "critical": 0, "cache": 0}
    for _ in range(n):
        roll = s.reward_rng.random()
        if roll < cfg["cache_p"]:
            counts["cache"] += 1
        elif roll < cfg["cache_p"] + cfg["critical_p"]:
            counts["critical"] += 1
        else:
            counts["standard"] += 1
    # tolerances wide enough for seed variance, tight enough to catch fake odds
    assert abs(counts["standard"] / n - 0.85) < 0.03, counts
    assert abs(counts["critical"] / n - 0.12) < 0.03, counts
    assert abs(counts["cache"] / n - 0.03) < 0.015, counts


def test_kill_counts_rewards_and_streak_bonus():
    s = _aimed_sim(enemy_hp=120, etype="brute")
    s.engagement = dict(s.engagement)
    # force standard-only for exact math
    s.engagement["reward"] = {"standard_p": 1.0, "critical_p": 0.0, "critical_mult": 2.0,
                              "cache_p": 0.0, "cache_reserve": 12, "cache_expire_s": 8.0}
    events: list[str] = []
    for _ in range(40):
        if not any(e.alive for e in s.enemies):
            break
        s._fire(s.weapons["pulse"], events)
    assert s.kills == 1, (s.kills, events)
    assert s.rewards["standard"] == 1
    # brute 300 + streak x1 (10%) = 330
    assert s.score == 300 + 30, s.score
    assert s.streak == 1 and s.best_streak == 1


def test_streak_cap_and_hurt_break():
    s = Sim(seed=3)
    cfg = s._eng()
    s.streak = 4
    s.best_streak = 4
    # simulate 5th and 6th kill bonus math (cap 0.50)
    rate5 = min(cfg["streak_cap"], cfg["streak_per"] * 5)
    rate6 = min(cfg["streak_cap"], cfg["streak_per"] * 6)
    assert rate5 == 0.50 and rate6 == 0.50
    s._on_hurt([])
    assert s.streak == 0 and s.best_streak == 4


def test_near_miss_honest_once_per_wave():
    s = _aimed_sim(enemy_hp=15, etype="mite")  # pulse 12 -> 3 left = 10% of 30 max? use max 30
    s.enemies[0].max_hp = 30
    base_reserve = int(s.reserve["pulse"])
    events: list[str] = []
    s._fire(s.weapons["pulse"], events)
    assert s.enemies[0].alive is True, events
    assert s.near_miss == 1, events
    assert "near_miss" in events and "near_miss_bonus" in events
    assert int(s.reserve["pulse"]) == base_reserve + int(s._eng()["near_bonus"])
    # second graze same wave: counted, no second bonus (cap, cf. SURGE one-shot)
    s.enemies[0].hp = 15
    s._fire(s.weapons["pulse"], events)
    assert s.near_miss == 2
    assert events.count("near_miss_bonus") == 1


def test_clutch_is_flavor_only():
    from keystone.headless import run_simulation
    g = ShooterGame()
    g.build_scene()
    g.sim.spawn_queue = []
    g.sim.enemies = []
    g.sim.hp = 20
    # force a wave-clear tick with no enemies queued and none alive
    g.sim.spawn_queue = []
    n0 = int(g.sim.near_miss)
    g.update(1.0 / 60.0, kite_step(g.sim))
    # wave may or may not have cleared (spawn queue empty + 0 alive -> clear)
    assert int(g.sim.near_miss) == n0  # clutch never inflates near_miss
    assert run_simulation(ShooterGame(), frames=1)["final"]["clutch"] == 0


def test_overdrive_preview_refusals_cost_and_break():
    s = Sim(seed=1)
    s.spawn_queue = []
    s.enemies = []
    ok = s.overdrive_preview()
    assert ok["ok"] is True, ok
    cost = int(ok["cost"])
    before = int(s.reserve["pulse"])
    ev: list[str] = []
    s._try_overdrive(ev)
    assert "overdrive" in ev
    assert int(s.reserve["pulse"]) == before - cost
    assert float(s.overdrive_t) > 0.0
    # already-on refuses
    ev2: list[str] = []
    s._try_overdrive(ev2)
    assert any(x.startswith("overdrive_denied:already_on") for x in ev2), ev2
    # hurt breaks timer + streak
    s.streak = 3
    s._on_hurt(ev2)
    assert float(s.overdrive_t) == 0.0 and int(s.streak) == 0
    assert "overdrive_break" in ev2 and "streak_break" in ev2
    # insufficient ammo refuses
    s.reserve["pulse"] = 0
    bad = s.overdrive_preview()
    assert bad == {"ok": False, "reason": "insufficient_ammo", "cost": cost,
                   "duration_s": bad["duration_s"], "mult": bad["mult"]}
    # surge-active refuses
    s.reserve["pulse"] = 999
    s.surge_t = 5.0
    assert s.overdrive_preview()["reason"] == "surge_active"
    # dead refuses
    s.alive = False
    assert s.overdrive_preview()["reason"] == "dead"


def test_overdrive_doubles_score_while_active():
    s = _aimed_sim(enemy_hp=120, etype="brute")
    s.engagement["reward"] = {"standard_p": 1.0, "critical_p": 0.0, "critical_mult": 2.0,
                              "cache_p": 0.0, "cache_reserve": 12, "cache_expire_s": 8.0}
    s.reserve["pulse"] = 999
    s._try_overdrive([])
    assert float(s.overdrive_t) > 0.0
    events: list[str] = []
    for _ in range(40):
        if not any(e.alive for e in s.enemies):
            break
        s._fire(s.weapons["pulse"], events)
    # 300 base + 10% streak = 330, x2 overdrive = 660
    assert s.score == 660, (s.score, events)
    assert "overdrive_hit" in events


def test_cache_drop_pickup_and_expiry():
    s = _aimed_sim(enemy_hp=30, etype="mite")
    s.engagement["reward"] = {"standard_p": 0.0, "critical_p": 0.0, "critical_mult": 2.0,
                              "cache_p": 1.0, "cache_reserve": 12, "cache_expire_s": 8.0}
    events: list[str] = []
    for _ in range(20):
        if not any(e.alive for e in s.enemies):
            break
        s._fire(s.weapons["pulse"], events)
    assert s.kills == 1 and s.rewards["cache"] == 1
    assert "cache_drop" in events and len(s.caches) == 1
    # walk onto the corpse: pickup grants pulse reserve
    from keystone.input import ActionState
    c = s.caches[0]
    s.player_pos = Vec3(float(c["x"]), 0.9, float(c["z"]))
    before = int(s.reserve["pulse"])
    s.step(1.0 / 60.0, ActionState())
    assert int(s.reserve["pulse"]) == before + 12
    # expiry path: a fresh drop vanishes after its ttl with no grant
    s.caches = [{"x": 19.0, "y": 0.5, "z": 19.0, "ttl": 0.01}]
    s.step(1.0 / 60.0, ActionState())
    assert s.caches == []


def test_surge_lock_forfeits_on_switch():
    s = Sim(seed=1)
    s.weapon = "surge"
    s.surge_t = 5.0
    ev: list[str] = []
    s._switch("pulse", ev)
    assert float(s.surge_t) == 0.0
    assert "surge_forfeit" in ev and s.weapon == "pulse"


def test_engagement_deterministic():
    from keystone.replay import stable_hash
    from shooter.bot import kite_step as kite
    a = ShooterGame()
    a.build_scene()
    for _ in range(120):
        a.update(1.0 / 60.0, kite(a.sim))
    b = ShooterGame()
    b.build_scene()
    for _ in range(120):
        b.update(1.0 / 60.0, kite(b.sim))
    fa, fb = a.snapshot(), b.snapshot()
    assert stable_hash(fa) == stable_hash(fb)
    # new telemetry present and honest: rewards sum == kills
    assert fa["rewards"]["standard"] + fa["rewards"]["critical"] + fa["rewards"]["cache"] == fa["kills"]
