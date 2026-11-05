#!/usr/bin/env python3
"""One-click shooter launcher.

Double-click ``start-shooter.cmd`` (Windows) or run ``python play.py`` from
any working directory — this script resolves its own location, puts both
``projects/shooter`` and ``projects/keystone`` on ``sys.path`` (no manual
``PYTHONPATH`` setup), and starts the live windowed game::

    python -m keystone --game shooter.game:ShooterGame

Extra CLI args pass straight through to Keystone, so headless proofs keep
working without extra setup::

    python play.py --simulate --frames 600
    python play.py --describe
    python play.py --headless --frames 1 --size 960x540 --ui --out shot.png --report shot.json

Exit codes mirror ``keystone.__main__.main`` (0 ok, 1 failure, 2 usage).
"""

from __future__ import annotations

import sys
from pathlib import Path

SHOOTER_DIR = Path(__file__).resolve().parent
KEYSTONE_DIR = SHOOTER_DIR.parent / "keystone"
GAME_SPEC = "shooter.game:ShooterGame"


def build_argv(extra: list[str]) -> list[str]:
    """Return the Keystone argv, defaulting ``--game`` to the shooter."""
    if any(a == "--game" or a.startswith("--game=") for a in extra):
        return list(extra)
    return ["--game", GAME_SPEC, *extra]


def ensure_paths() -> None:
    for candidate in (str(SHOOTER_DIR), str(KEYSTONE_DIR)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


def check_prerequisites() -> str | None:
    if sys.version_info < (3, 10):
        return (
            f"Why: Python {sys.version.split()[0]} is too old (shooter needs 3.10+).\n"
            "Fix: install Python 3.10 or newer from https://www.python.org/downloads/ "
            "and re-run start-shooter.cmd."
        )
    if not KEYSTONE_DIR.is_dir():
        return (
            f"Why: Keystone engine not found at {KEYSTONE_DIR}.\n"
            "Fix: keep the 'shooter' and 'keystone' folders side by side under "
            "'projects/' (fresh clone of both repos) and try again."
        )
    if not (SHOOTER_DIR / "shooter" / "game.py").is_file():
        return (
            f"Why: shooter package not found under {SHOOTER_DIR}.\n"
            "Fix: run this launcher from its own folder (don't move play.py "
            "away from the shooter checkout)."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    problem = check_prerequisites()
    if problem is not None:
        print(f"Shooter could not start.\n{problem}", file=sys.stderr)
        return 1
    ensure_paths()
    try:
        from keystone.__main__ import main as keystone_main
    except ImportError as exc:
        print(
            "Shooter could not start.\n"
            f"Why: could not import the Keystone engine ({exc}).\n"
            "Fix: install the pinned stack with "
            f"`python -m pip install -r \"{KEYSTONE_DIR / 'requirements.txt'}\"` "
            "then re-run start-shooter.cmd.",
            file=sys.stderr,
        )
        return 1
    return keystone_main(build_argv(list(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
