#!/usr/bin/env python3
"""
Sync golden/fixture/: the copy of the artwork that CI runs the golden suite on.

The real artwork lives in iCloud and isn't in git. CI gets a COPY of just the
files the golden suite needs, at the same relative paths, under
golden/fixture/. This script builds that copy from a full golden run on the
Mac, so run the suite first:

    uv run scripts/golden/golden_run.py                  # full run, on the real tree
    uv run scripts/golden/golden_fixture.py              # dry run: what would change
    uv run scripts/golden/golden_fixture.py --apply      # copy, update, remove

What goes in:

  COMPOSITIONS  for every placement the last run placed, the files in its
                element folder that compose could have picked from: those
                carrying the requested number, plus the unnumbered ones (a
                file with another number never wins while one of those
                exists, so leaving it out changes nothing). If neither
                exists, the whole folder.
  HELMETS       for every Helmets Left|Right element used, the WHOLE generated
                folder and its source folder in Marks/, so CI can re-pad the
                marks and compare. Any helmet era (A-F, per side) not reached
                that way gets one more element that has it.
  VENUES        for every Fields|Courts Full folder with a Cropped sibling, its
                first and last file and their cropped copies.

Only ever writes or deletes inside golden/fixture/. The real tree is read,
never changed. `.generated` markers aren't copied (they record local paths).
Dry-runs until --apply.
"""

import argparse
import filecmp
import json
import shutil
import sys
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

# compose.py and standardize.py live in scripts/pipeline/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from compose import SLOT_DIR, load_vocab, split_tail  # noqa: E402
from standardize import match_era  # noqa: E402

FIXTURE = Path("golden") / "fixture"
SIDES = ("Left", "Right")
WARN_MB = 250


def find_root(start: Path) -> Path:
    """The nearest directory at or above `start` holding configs/canvas_definitions.yaml; exits if none."""
    for d in [start, *start.parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            return d
    sys.exit(f"No configs/canvas_definitions.yaml above {start}")


def pngs(folder: Path):
    """Visible PNGs directly in `folder`, sorted."""
    return sorted(f for f in folder.glob("*.png") if not f.name.startswith("."))


def evicted(path: Path) -> bool:
    """True when iCloud has swapped the file for a `.name.icloud` placeholder."""
    return (path.parent / f".{path.name}.icloud").exists()


def composition_files(placement, _root: Path, vocab) -> list[Path]:
    """The files in a placed element's folder that compose could have chosen between.

    Mirrors compose.candidates(): a file whose number is neither the requested
    one nor absent ranks below every file that is, so it can only win when
    no such file exists, and then the whole folder is kept.
    """
    folder = Path(placement["file"]).parent
    element, req = placement["element"], placement.get("number_requested")
    files = pngs(folder)
    keep = [f for f in files if split_tail(f.stem, element, vocab[0])[1] in (req, None)]
    return keep or files


def content_size(path: Path):
    """Width and height of the opaque content, or None if the file is empty."""
    with ImageOps.exif_transpose(Image.open(path)).convert("RGBA") as im:
        box = im.getchannel("A").getbbox()
    return None if box is None else (box[2] - box[0], box[3] - box[1])


def helmet_eras(folder: Path, profile, tol) -> set:
    """The profile eras (pre-scale, as authored in Marks) that a Marks element folder's files match."""
    found = set()
    for f in pngs(folder):
        cs = content_size(f)
        era = match_era(profile, *cs, tol) if cs else None
        if era:
            found.add(era["era"])
    return found


def plan(root: Path) -> tuple[set, list]:
    """Every source file the fixture needs, as paths relative to the root, and any errors."""
    cfg = yaml.safe_load((root / "configs" / "canvas_definitions.yaml").open())
    tol = cfg.get("tolerance", 5)
    manifest = yaml.safe_load((root / "golden" / "manifest.yaml").open()) or []
    run = root / "golden" / "run"
    mtime = (root / "golden" / "manifest.yaml").stat().st_mtime
    need, errors, vocab = set(), [], {}
    helmet_dirs = set()  # (team, side, element)

    for ex in manifest:
        if not ex.get("approved", True):
            continue
        js = run / ex["sport"] / ex["view"] / f"{ex['id']}.json"
        if not js.is_file():
            errors.append(f"no result for {ex['id']}: run scripts/golden/golden_run.py first")
            continue
        if js.stat().st_mtime < mtime:
            errors.append(f"{ex['id']}: result is older than manifest.yaml, re-run scripts/golden/golden_run.py")
            continue
        result = json.loads(js.read_text())
        if ex["sport"] not in vocab:
            vocab[ex["sport"]] = load_vocab(root, ex["sport"])
        for p in result.get("placements", []):
            if p.get("status") != "placed":
                continue
            file = Path(p["file"])
            try:
                rel = file.relative_to(root)
            except ValueError:
                errors.append(f"{ex['id']}: {file} is outside the project")
                continue
            if p["slot"] == "helmet" and p["viewpoint"] in ("left", "right") and ex["sport"] == "football":
                helmet_dirs.add((rel.parts[1], p["viewpoint"].title(), p["element"]))
            else:
                need.update(f.relative_to(root) for f in composition_files(p, root, vocab[ex["sport"]]))

    # Helmets: every generated folder used, whole, plus its Marks source.
    covered = {s: set() for s in SIDES}
    for team, side, element in sorted(helmet_dirs):
        gen = Path("Football") / team / f"{SLOT_DIR['helmet']} {side}" / element
        src = Path("Marks") / gen
        if not (root / src).is_dir():
            errors.append(f"{gen} has no source in Marks ({src})")
            continue
        need.update(f.relative_to(root) for f in pngs(root / gen))
        need.update(f.relative_to(root) for f in pngs(root / src))
        covered[side] |= helmet_eras(root / src, cfg["profiles"][f"football-helmet-{side.lower()}"], tol)

    # Any helmet era no example reached: add one element that has it.
    for side in SIDES:
        profile = cfg["profiles"][f"football-helmet-{side.lower()}"]
        missing = {e["era"] for e in profile} - covered[side]
        teams = sorted(d.name for d in (root / "Football").iterdir() if d.is_dir()) if missing else []
        for team in teams:
            if not missing:
                break
            marks = root / "Marks" / "Football" / team / f"Helmets {side}"
            for el in sorted(d for d in marks.iterdir() if d.is_dir()) if marks.is_dir() else []:
                got = helmet_eras(el, profile, tol) & missing
                gen = root / "Football" / team / f"Helmets {side}" / el.name
                if got and gen.is_dir():
                    need.update(f.relative_to(root) for f in pngs(el) + pngs(gen))
                    missing -= got
                    if not missing:
                        break
        for era in sorted(missing):
            errors.append(f"no tracked team has a {side.lower()} helmet mark of era {era}")

    # Venues: first and last of every Full folder that has a Cropped sibling.
    venues = root / "Venues"
    for full in sorted(venues.glob("*/*/* Full")) if venues.is_dir() else []:
        cropped = full.with_name(full.name.removesuffix(" Full") + " Cropped")
        files = sorted(f for f in full.rglob("*.png") if not f.name.startswith("."))
        if not cropped.is_dir() or not files:
            continue
        for f in {files[0], files[-1]}:
            c = cropped / f.relative_to(full)
            if not c.is_file():
                errors.append(f"{f.relative_to(root)} has no cropped copy at {c.relative_to(root)}")
                continue
            need.update({f.relative_to(root), c.relative_to(root)})

    for rel in sorted(need):
        if evicted(root / rel):
            errors.append(f"{rel} is in iCloud only: run brctl download on it first")
    return need, errors


def main():
    """Plan the fixture from the last golden run, report the changes, and apply them with --apply."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())
    dest = (root / FIXTURE).resolve()
    if not dest.is_relative_to(root / "golden"):
        sys.exit(f"Refusing: fixture path {dest} is outside golden/")

    need, errors = plan(root)
    if errors:
        print(f"!! {len(errors)} problems:")
        for e in errors[:30]:
            print(f"     {e}")
        sys.exit("Fix these before syncing the fixture.")

    have = {f.relative_to(dest) for f in dest.rglob("*") if f.is_file()} if dest.is_dir() else set()
    add = sorted(need - have)
    update = sorted(r for r in need & have if not filecmp.cmp(root / r, dest / r, shallow=False))
    remove = sorted(have - need)
    size = sum((root / r).stat().st_size for r in need)

    by_tree = {}
    for r in need:
        by_tree[r.parts[0]] = by_tree.get(r.parts[0], 0) + 1
    print(f"fixture: {len(need)} files, {size / 1e6:.1f} MB")
    for tree, n in sorted(by_tree.items()):
        print(f"   {tree:<22} {n} files")
    print(f"\n   add {len(add)}, update {len(update)}, remove {len(remove)}")
    for label, rels in (("+", add), ("~", update), ("-", remove)):
        for r in rels[:10]:
            print(f"     {label} {r}")
        if len(rels) > 10:
            print(f"     {label} … {len(rels) - 10} more")
    if size > WARN_MB * 1e6:
        print(f"\n!! over {WARN_MB} MB: every change to these files grows the repository's history for good.")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return
    for r in add + update:
        (dest / r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / r, dest / r)
    for r in remove:
        (dest / r).unlink()
    for d in sorted((p for p in dest.rglob("*") if p.is_dir()), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    print(f"\nWrote {len(add) + len(update)} files, removed {len(remove)}. Commit golden/fixture/.")


if __name__ == "__main__":
    main()
