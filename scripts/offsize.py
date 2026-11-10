#!/usr/bin/env python3
"""
List files whose content size is not an EXACT match for their profile entry.

`standardize.py` matches within a tolerance, so near-misses pass silently.
This reports them so the source artwork can be corrected instead.

    pip install pillow pyyaml

    python3 scripts/offsize.py "Football"
    python3 scripts/offsize.py "Football/Southern Miss/Pants Front"
    python3 scripts/offsize.py "Football" --csv offsize.csv

Walks any directory: a whole tree, one team, or one viewpoint. Read-only.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("pip install pillow pyyaml")

# Path -> (sport, team, slot, viewpoint) and the sport-qualified profile key
# live in standardize.py. Reuse them: a private copy here built the key
# without the sport, so every lookup missed and every file read as "exact".
from standardize import find_root, lookup, parse_dest


def content_size(path: Path):
    """Width and height of the non-transparent bbox, or None if empty."""
    with ImageOps.exif_transpose(Image.open(path)).convert("RGBA") as im:
        box = im.getchannel("A").getbbox()
    return None if box is None else (box[2] - box[0], box[3] - box[1])


def main():
    """Walk the target and report near-miss and unmatched content sizes."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path")
    ap.add_argument("--root")
    ap.add_argument("--csv", help="also write a machine-readable list")
    args = ap.parse_args()

    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else find_root(Path.cwd().resolve())
    )
    target = (root / args.path).resolve()
    if not target.is_dir():
        sys.exit(f"Not a directory: {target}")

    cfg = yaml.safe_load((root / "configs" / "canvas_definitions.yaml").open())
    tol = cfg.get("tolerance", 5)

    # Generated trees hold POST-standardization sizes, which will never match
    # the pre-correction sizes in the profiles. Skip anything under a
    # directory carrying a .generated marker.
    generated = {m.parent for m in target.rglob(".generated")}
    skipped_generated = 0
    skipped_standardized = 0
    # A miss here used to be silent, and with the key built wrong that made
    # the whole run report "exact". Count both kinds of miss and print them.
    unparsed = defaultdict(int)  # viewpoint dir -> files (not a sport tree)
    no_profile = defaultdict(int)  # profile key -> files

    rows, unmatched, checked = [], [], 0
    for f in sorted(target.rglob("*.png")):
        rel = f.relative_to(root)
        if any(p.startswith(".") for p in rel.parts):
            continue
        if any(g in f.parents for g in generated):
            skipped_generated += 1
            continue
        # {Sport}/{Team}/{Slot} {Viewpoint}/…, with Marks/ and Venues/
        # resolving like sport trees — the same parse `pad` uses.
        parsed = parse_dest(f.parent, root, cfg)
        if parsed is None:
            unparsed[Path(*rel.parts[:3])] += 1
            continue
        sport, _team, slot, viewpoint = parsed
        canvas, profile, (_canvas_name, key) = lookup(cfg, sport, slot, viewpoint)
        if not profile:
            no_profile[key] += 1
            continue

        # Files standardized IN PLACE carry no .generated marker but hold
        # post-standardization content. The tell is that their CANVAS equals
        # the configured padded canvas — the same signal standardize.py uses
        # for its idempotency guard.
        if canvas and canvas.get("fills") == "pad" and canvas.get("width"):
            with Image.open(f) as im:
                if im.size == (canvas["width"], canvas["height"]):
                    skipped_standardized += 1
                    continue

        cs = content_size(f)
        if cs is None:
            continue
        checked += 1
        entry = next(
            (
                e
                for e in profile
                if abs(e["size"][0] - cs[0]) <= tol and abs(e["size"][1] - cs[1]) <= tol
            ),
            None,
        )
        if entry is None:
            unmatched.append((rel, cs, key))
            continue
        want = tuple(entry["size"])
        if cs != want:
            rows.append(
                (
                    rel,
                    cs,
                    want,
                    cs[0] - want[0],
                    cs[1] - want[1],
                    key,
                    entry.get("era", "?"),
                )
            )

    print(f"checked {checked} files under {target.relative_to(root)}")
    if skipped_generated:
        print(
            f"skipped {skipped_generated} files in {len(generated)} "
            f"generated directories"
        )
    if skipped_standardized:
        print(
            f"skipped {skipped_standardized} files already on their standardized canvas"
        )
    if unparsed:
        print(
            f"!! skipped {sum(unparsed.values())} files whose path is not "
            f"{{Sport}}/{{Team}}/{{Slot}} {{Viewpoint}}:"
        )
        for d, n in sorted(unparsed.items()):
            print(f"     {d}  ({n} files)")
    if no_profile:
        print(
            f"!! skipped {sum(no_profile.values())} files whose profile "
            f"is not in canvas_definitions.yaml:"
        )
        for key, n in sorted(no_profile.items()):
            print(f"     {key}  ({n} files)")
    print()

    if not checked:
        # Nothing was measured, so nothing can be called exact.
        print("No files were checked against a profile.")
        return
    if not rows and not unmatched:
        print(f"All {checked} checked files are an exact match for their profile.")
        return

    if rows:
        print(f"{len(rows)} files are within tolerance but NOT exact:\n")
        groups = defaultdict(list)
        for rel, cs, want, dw, dh, key, era in rows:
            groups[(key, era, cs, want, dw, dh)].append(rel)
        for (key, era, cs, want, dw, dh), items in sorted(
            groups.items(), key=lambda kv: -len(kv[1])
        ):
            print(
                f"  {key} era {era}: {cs[0]}x{cs[1]} should be "
                f"{want[0]}x{want[1]}  ({dw:+d}, {dh:+d})  "
                f"— {len(items)} files"
            )
            for rel in items:
                print(f"       {rel}")
            print()

    if unmatched:
        print(
            f"{len(unmatched)} files match NO profile entry even within "
            f"tolerance {tol}:"
        )
        for rel, cs, key in unmatched:
            print(f"  {cs[0]}x{cs[1]}  [{key}]  {rel}")

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "path",
                    "width",
                    "height",
                    "want_w",
                    "want_h",
                    "dw",
                    "dh",
                    "profile",
                    "era",
                ]
            )
            for rel, cs, want, dw, dh, key, era in rows:
                w.writerow([rel, cs[0], cs[1], want[0], want[1], dw, dh, key, era])
            for rel, cs, key in unmatched:
                w.writerow([rel, cs[0], cs[1], "", "", "", "", key, "UNMATCHED"])
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()
