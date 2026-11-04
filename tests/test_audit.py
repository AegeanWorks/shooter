"""Wave-2 audit regression pins: cache pickup, surge forfeit, mixer cap,
overdrive policy, HUD smoke, and the documented live-input limits.

Each test pairs with a verified finding (see .aikit/decisions.md ADR-015/016):
repro first, pin after.
"""

from keystone.input import ActionState, InputMap

from shooter.bot import overdrive_step
from shooter.game import ShooterGame
from shooter.sim import Sim
from shooter.ui import draw_shooter


def _parked_sim(seed: int = 1) -> Sim:
    s = Sim(seed=seed)
    s.spawn_queue = ["mite"]  # non-empty queue blocks wave-clear during the probe
    s.spawn_t = 999.0
    s.enemies = []
    return s


def test_overlapping_caches_all_collected_same_frame():
    s = _parked_sim()
    per = int(s._eng()["cache_reserve"])
    before = int(s.reserve["pulse"])
    spot = {"x": 0.0, "y": 0.5, "z": 8.0, "ttl": 8.0}
    s.caches = [dict(spot), dict(spot)]
    events = s.step(1.0 / 60.0, ActionState())
    assert events.count("cache") == 2, events
    assert int(s.reserve["pulse"]) == before + 2 * per
    assert s.caches == []


def test_surge_forfeit_relinquishes_ammo():
    s = Sim(seed=1)
    s.weapon = "surge"
    s.surge_t = 5.0
    s.ammo["surge"] = 20
    s.pickup_taken = True
    events: list[str] = []
    s._switch("pulse", events)
    assert "surge_forfeit" in events
    assert float(s.surge_t) == 0.0
    assert int(s.ammo["surge"]) == 0
    # guard closed after forfeit: no re-select into a timer-less surge gun
    s._switch("surge", [])
    assert s.weapon == "pulse"
    # guard closed when never picked up either: no timer means no surge
    fresh = Sim(seed=1)
    fresh._switch("surge", [])
    assert fresh.weapon == "pulse"


def test_voice_cap_stays_bounded():
    g = ShooterGame()
    g.build_scene()
    for _ in range(12):
        g.mixer.play(g._clips["shoot"], bus="sfx", gain=0.7)
    assert g.mixer.voice_count() == 12
    g.update(1.0 / 60.0, ActionState())
    assert g.mixer.voice_count() <= 8


def test_overdrive_step_presses_only_when_ready():
    s = _parked_sim()
    s.streak = 3
    assert s.overdrive_preview()["ok"] is True
    assert "overdrive" in overdrive_step(s).pressed
    s.streak = 2
    assert "overdrive" not in overdrive_step(s).pressed
    s.streak = 3
    s.reserve["pulse"] = 0
    assert "overdrive" not in overdrive_step(s).pressed
    s.alive = False
    assert overdrive_step(s).pressed == frozenset()


class _Canvas:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def rect(self, *args) -> None:
        self.calls.append(("rect",) + tuple(args))

    def text(self, *args) -> None:
        self.calls.append(("text",) + tuple(args))


class _Hud:
    width = 960
    height = 540


def test_draw_shooter_smoke():
    s = Sim(seed=1)
    canvas = _Canvas()
    draw_shooter(canvas, _Hud(), s)  # must not raise on a fresh sim
    kinds = {call[0] for call in canvas.calls}
    assert "rect" in kinds and "text" in kinds
    assert any("HP" in str(call) for call in canvas.calls), canvas.calls
    s.hp = 10  # low-hp edge warning path
    s.alive = False  # death tint path
    draw_shooter(canvas, _Hud(), s)


def test_live_input_limits_documented():
    # The Engine samples InputMap() defaults only: no per-game bindings hook
    # exists, so shooter-only action names can never arrive live. Bots and
    # --replay drive them headless instead. If this fails, the engine grew a
    # bindings hook (or new defaults) — update README Controls + ADR-016.
    live_actions = set(InputMap().list_actions())
    shooter_only = {"fire", "reload", "slot1", "slot2", "slot3", "overdrive", "jump"}
    assert shooter_only & live_actions == set(), shooter_only & live_actions
