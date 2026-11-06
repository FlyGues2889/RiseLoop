import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "health-data-mcp", ROOT / "action-library-mcp"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))