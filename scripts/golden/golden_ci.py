#!/usr/bin/env python3
"""
Run the golden suite on golden/fixture/, failing unless everything is ok.

This is what CI runs. It copies the fixture into a temporary project (the
fixture's artwork plus links to configs/ and scripts/) so nothing it does can
touch the repository or the real tree, then checks three things:

  COMPOSITIONS  golden_run.py --strict on the approved manifest: any defect,
                any note (1-2px clipping) or any missing result fails.
  HELMETS       every Marks/Football/*/Helmets Left|Right in the fixture is
                padded again with standardize.py, and each output must match
                the fixture's generated helmet pixel for pixel, file for
                file. Every helmet era (A-F) must be covered on both sides.
  VENUES        every "… Cropped" folder is derived again with
                derive_crops.py and must match pixel for pixel, file for
                file, for every sport whose canvases have `derived_from`.

Pixels are compared, not bytes, so a Pillow upgrade that compresses
differently doesn't fail it.

    uv run scripts/golden/golden_ci.py                 # all three checks
    uv run scripts/golden/golden_ci.py --keep          # keep the temporary project

Contact sheets and REPORT.md are copied to golden/run/ for review (CI uploads
them as an artifact).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
    from PIL import Image
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

# Sibling scripts live in scripts/pipeline/ and here in scripts/golden/.
SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS / "pipeline"), str(SCRIPTS / "golden")]
from derive_crops import jobs_for  # noqa: E402
from golden_fixture import SIDES, helmet_eras  # noqa: E402

REGEN = "REGEN"


def find_root(start: Path) -> Path:
    """The nearest directory at or above `start` holding configs/canvas_definitions.yaml; exits if none."""
    for d in [start, *start.parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            return d
    sys.exit(f"No configs/canvas_definitions.yaml above {start}")


def png_set(folder: Path) -> set:
    """Every visible PNG under `folder`, as paths relative to it."""
    if not folder.is_dir():
        return set()
    # Judge hidden-ness inside `folder` only: a dot-folder above it (a checkout
    # under .claude/, say) used to hide every file and read as an empty fixture.
    rels = (f.relative_to(folder) for f in folder.rglob("*.png"))
    return {r for r in rels if not any(p.startswith(".") for p in r.parts)}


def same_pixels(a: Path, b: Path) -> bool:
    """True when two images have the same size and identical RGBA pixels."""
    with Image.open(a) as x, Image.open(b) as y:
        return x.size == y.size and x.convert("RGBA").tobytes() == y.convert("RGBA").tobytes()


def compare(label: str, got: Path, want: Path) -> list[str]:
    """Failures from comparing a regenerated folder with the fixture's copy: missing, extra or different files."""
    g, w = png_set(got), png_set(want)
    out = [f"{label}: not regenerated: {r}" for r in sorted(w - g)]
    out += [f"{label}: regenerated but not in the fixture: {r}" for r in sorted(g - w)]
    out += [f"{label}: pixels differ: {r}" for r in sorted(g & w) if not same_pixels(got / r, want / r)]
    return out


def run(cmd, cwd: Path) -> subprocess.CompletedProcess:
    """Run a script, echoing its output indented, and return the result."""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    for line in (proc.stdout + proc.stderr).splitlines():
        print(f"    {line}")
    return proc


def build_project(root: Path, fixture: Path, tmp: Path) -> None:
    """A throwaway project: a copy of the fixture's artwork, links to configs/ and scripts/, the golden plan."""
    shutil.copytree(fixture, tmp, dirs_exist_ok=True)
    for name in ("configs", "scripts"):
        os.symlink(root / name, tmp / name)
    (tmp / "golden").mkdir(exist_ok=True)
    for name in ("manifest.yaml", "pairings.yaml"):
        if (root / "golden" / name).is_file():
            shutil.copy2(root / "golden" / name, tmp / "golden" / name)


def check_compositions(root: Path, tmp: Path) -> list[str]:
    """golden_run.py --strict in the throwaway project; copies its report and sheets back to golden/run/."""
    proc = run([sys.executable, str(tmp / "scripts" / "golden" / "golden_run.py"), "--strict"], tmp)
    out = root / "golden" / "run"
    if (tmp / "golden" / "run").is_dir():
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(tmp / "golden" / "run", out)
    return [] if proc.returncode == 0 else ["compositions: golden_run.py --strict failed (see REPORT.md)"]


def check_helmets(tmp: Path, cfg: dict) -> list[str]:
    """Pad every fixture Marks helmet side again and compare with the generated copy; check era coverage."""
    fails, covered = [], {s: set() for s in SIDES}
    tol = cfg.get("tolerance", 5)
    sources = sorted(p for s in SIDES for p in (tmp / "Marks" / "Football").glob(f"*/Helmets {s}"))
    if not sources:
        return ["helmets: the fixture has no Marks/Football/*/Helmets Left|Right"]
    for src in sources:
        team, side = src.parent.name, src.name.split()[-1]
        gen = tmp / "Football" / team / src.name
        out = gen.with_name(f"{src.name} {REGEN}")
        print(f"  {team} / {src.name}")
        proc = run(
            [
                sys.executable,
                str(tmp / "scripts" / "pipeline" / "standardize.py"),
                "--root",
                str(tmp),
                "pad",
                str(src),
                str(out),
            ],
            tmp,
        )
        if proc.returncode:
            fails.append(f"helmets: pad refused {team} / {src.name}")
            continue
        fails += compare(f"helmets {team} {side}", out, gen)
        profile = cfg["profiles"][f"football-helmet-{side.lower()}"]
        for el in (d for d in src.iterdir() if d.is_dir()):
            covered[side] |= helmet_eras(el, profile, tol)
    for side in SIDES:
        want = {e["era"] for e in cfg["profiles"][f"football-helmet-{side.lower()}"]}
        fails += [f"helmets: no {side.lower()} mark of era {e} in the fixture" for e in sorted(want - covered[side])]
    return fails


def check_venues(tmp: Path, cfg: dict) -> list[str]:
    """Derive every cropped venue again and compare with the fixture's cropped copies, for every derived sport."""
    expected = tmp.parent / f"{tmp.name}-expected"
    venues = tmp / "Venues"
    crops = sorted(venues.glob("*/*/* Cropped")) if venues.is_dir() else []
    for c in crops:
        target = expected / c.relative_to(tmp)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(c), str(target))
    proc = run(
        [sys.executable, str(tmp / "scripts" / "pipeline" / "derive_crops.py"), "--root", str(tmp), "--apply"], tmp
    )
    if proc.returncode:
        return ["venues: derive_crops.py refused"]
    fails = []
    for c in crops:
        fails += compare(f"venues {c.relative_to(venues)}", c, expected / c.relative_to(tmp))
    sports = {r[1] for r in jobs_for(cfg, None) if r[0] == "OK"}
    for sport in sorted(sports):
        if not any(c.relative_to(venues).parts[0] == sport.replace("_", " ").title() for c in crops):
            fails.append(f"venues: the fixture has no cropped venue for {sport}")
    return fails


def summary(fails: list[str]) -> None:
    """Print the result, and add it to the GitHub Actions job summary when there is one."""
    text = "\n".join(f"- {f}" for f in fails) if fails else "Every composition, helmet and venue is ok."
    print(("\nFAILED:\n" if fails else "\n") + text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(f"## Golden suite\n\n{text}\n")


def main():
    """Build the throwaway project, run the three checks, report, and exit 1 on any failure."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--keep", action="store_true", help="keep the temporary project and print where it is")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())
    fixture = root / "golden" / "fixture"
    if not png_set(fixture):
        summary(["golden/fixture/ is empty: run scripts/golden/golden_fixture.py --apply on the Mac and commit it"])
        sys.exit(1)
    cfg = yaml.safe_load((root / "configs" / "canvas_definitions.yaml").open())

    base = Path(tempfile.mkdtemp(prefix="golden-"))
    tmp = base / "project"
    try:
        build_project(root, fixture, tmp)
        fails = []
        print("== compositions")
        fails += check_compositions(root, tmp)
        print("== helmets: Marks -> Helmets Left|Right")
        fails += check_helmets(tmp, cfg)
        print("== venues: Full -> Cropped")
        fails += check_venues(tmp, cfg)
    finally:
        if args.keep:
            print(f"\nkept {tmp}")
        else:
            shutil.rmtree(base, ignore_errors=True)
    summary(fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
