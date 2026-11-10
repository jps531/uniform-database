"""Fail unless every script in scripts/ has at least 95% coverage (lines and branches together).

coverage.py's own --fail-under checks only the total, which lets one
well-tested script hide an untested one. Run after a full, covered pytest
run, which writes the JSON report named by [tool.coverage.json] in
pyproject.toml:

    uv run pytest -n auto --cov
    uv run python tests/coverage_gate.py

A plain `pytest` (one file, say) collects no coverage, so it can't leave a
partial report behind; this gate still refuses a report that is missing or
older than any file under scripts/ or tests/, rather than judge stale data.
"""

import json
import sys
import tomllib
from pathlib import Path

THRESHOLD = 95.0
REPO = Path(__file__).resolve().parent.parent


def report_path() -> Path:
    """The JSON report coverage writes: [tool.coverage.json] output in pyproject.toml (coverage's default otherwise)."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text())
    return REPO / config.get("tool", {}).get("coverage", {}).get("json", {}).get("output", "coverage.json")


def stale_against(report: Path) -> Path | None:
    """The newest file under scripts/ or tests/ if it changed after `report` was written, else None."""
    files = [p for d in ("scripts", "tests") for p in (REPO / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    newest = max(files, key=lambda p: p.stat().st_mtime)
    return newest if newest.stat().st_mtime > report.stat().st_mtime else None


def main() -> int:
    """Print each script's coverage and return 1 if any is below the threshold or missing, or the report is unusable."""
    report = report_path()
    if not report.is_file():
        print(f"No coverage report at {report.relative_to(REPO)}: run `uv run pytest -n auto --cov` first.")
        return 1
    newer = stale_against(report)
    if newer:
        print(
            f"{report.relative_to(REPO)} is older than {newer.relative_to(REPO)}: "
            "re-run `uv run pytest -n auto --cov` before checking coverage."
        )
        return 1
    data = json.loads(report.read_text())
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
