import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
KEYSTONE = ROOT.parent / "keystone"
for candidate in (str(ROOT), str(KEYSTONE)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
