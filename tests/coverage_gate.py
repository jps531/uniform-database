"""Fail unless every script in scripts/ has at least 95% coverage (lines and branches together).

coverage.py's own --fail-under checks only the total, which lets one
well-tested script hide an untested one. Run after pytest, which writes
coverage.json:

    uv run pytest -n auto
    uv run python tests/coverage_gate.py
"""

import json
import sys
from pathlib import Path

THRESHOLD = 95.0
REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    """Print each script's coverage and return 1 if any is below the threshold or missing from the report."""
    data = json.loads((REPO / "coverage.json").read_text())
    files = {Path(k).as_posix(): v["summary"]["percent_covered"] for k, v in data["files"].items()}
    scripts = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "scripts").rglob("*.py"))
    low = []
    for s in scripts:
        pct = files.get(s)
        ok = pct is not None and pct >= THRESHOLD
        print(f"{'ok ' if ok else 'LOW'} {s:<42} {'not measured' if pct is None else f'{pct:5.1f}%'}")
        if not ok:
            low.append(s)
    if low:
        print(f"\n{len(low)} below {THRESHOLD:g}%: " + ", ".join(low))
        return 1
    print(f"\nevery script is at {THRESHOLD:g}% or more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
