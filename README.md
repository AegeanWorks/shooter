# Shooter (Keystone plug-in)

Fast arena shooter on the Keystone engine. Engine owns render/loop/input/serialization (`projects/keystone`); this package owns state/rules/scene and loads via `--game shooter.game:ShooterGame`.

## Prerequisites

- Python 3.10+, Keystone pinned stack (numpy 2.5.3, PyOpenGL 3.1.10, glfw 2.11.0, pytest 9.1.1)
- OpenGL 3.3-capable GPU driver for rendered runs (headless sim needs no GPU)

## Test

```powershell
# from projects/shooter
python -m pytest -q
# engine gate (from projects/keystone)
python -m pytest -q
# headless bot proofs (no GPU)
$env:PYTHONPATH="C:\Users\Yunus-Emre\Desktop\portable_agent_kit\projects\keystone;C:\Users\Yunus-Emre\Desktop\portable_agent_kit\projects\shooter"
python -m keystone --game shooter.game:ShooterGame --describe
python -m keystone --game shooter.game:ShooterGame --simulate --frames 600 --trace
python -m keystone --game shooter.game:ShooterGame --verify-determinism --frames 1800
python -m keystone --game shooter.game:ShooterGame --headless --frames 1 --size 960x540 --ui --out shot.png --report shot.json
```

## Tree

```text
projects/shooter/
├── shooter/
│   ├── __init__.py      <- plug-in exports
│   ├── game.py          <- ShooterGame: five ops + draw_ui, Scene sync, mixer
│   ├── sim.py           <- deterministic sim: move/weapons/enemies/waves/particles
│   ├── bot.py           <- headless bot scripts (move/fire/assault)
│   ├── ui.py            <- crosshair/HP/ammo/score overlay
│   └── data/
│       ├── weapons.json <- 4 guns (pulse/scatter/lance/surge)
│       ├── enemies.json <- mite/brute/wisp
│       ├── levels.json  <- arena + 5 waves
│       └── juice.json   <- tracer/flash/particle caps, hitstop
├── tests/
│   ├── conftest.py      <- adds keystone + shooter to sys.path
│   └── test_shooter.py  <- move/shoot/hit/kill/die/score/determinism/budget
├── scripts/
│   └── record_bot.py    <- emit CommandLog for --replay
└── .aikit/
    └── decisions.md     <- append-only ADRs
```

## Controls

W/S forward/back, A/D strafe, Space jump, mouse look, left-click fire (hold F for auto), R reload, 1/2/3 pulse/scatter/lance, Shift sprint, P pause, H hide UI, F1 cursor, Esc quit.
