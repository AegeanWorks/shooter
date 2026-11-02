"""Emit a CommandLog for --replay determinism audits."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "keystone"))

from keystone.input import ActionState  # noqa: E402
from keystone.replay import CommandLog  # noqa: E402

from shooter.bot import assault  # noqa: E402


def main(out: str = "bot_log.json", frames: int = 600) -> None:
    script = assault(60, frames - 60)[:frames]
    log = CommandLog(seed=1)
    for action in script:
        log.record(action if isinstance(action, ActionState) else ActionState())
    log.save(Path(out))
    print(f"wrote {out} frames={len(log.frames)} seed={log.seed}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bot_log.json")
