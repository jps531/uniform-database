#!/usr/bin/env python3
"""
List files whose content size is not an EXACT match for their profile entry.

`standardize.py` matches within a tolerance, so near-misses pass silently.
This reports them so the source artwork can be corrected instead.

    uv sync

    uv run scripts/migration/offsize.py "Football"
    uv run scripts/migration/offsize.py "Football/Southern Miss/Pants Front"
    uv run scripts/migration/offsize.py "Football" --csv offsize.csv

Walks any directory: a whole tree, one team, or one viewpoint. Read-only.
Each file is compared with the CLOSEST era within the config's `tolerance`
(smallest |dw| + |dh|), as every script matches eras.

Skips generated trees (a .generated marker) and files already sitting on a
standardized canvas — the slot canvas or any era's own `canvas:`, the set
`pad` refuses to re-pad from — since their content is post-correction. On a
`fills: fill` canvas that check can't tell source from output, so those
files are always measured. Run it on authored or raw source.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

# Path -> (sport, team, slot, viewpoint) and the sport-qualified profile key
# live in standardize.py. Reuse them: a private copy here built the key
# without the sport, so every lookup missed and every file read as "exact".
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from common import (
    add_root_arg,
    content_box,
    load_config,
    match_era,
    pngs,
    root_from,
    standard_canvases,
    tolerance,
)
from standardize import lookup, parse_dest


def main():
    """Walk the target and report near-miss and unmatched content sizes.

    Skips generated trees, and files already on a standardized canvas (the
    slot canvas or any era's own canvas, as `pad` does).
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    add_root_arg(ap)
    ap.add_argument("--csv", help="also write a machine-readable list")
    args = ap.parse_args()

    root = root_from(args)
    target = (root / args.path).resolve()
    if not target.is_dir():
        sys.exit(f"Not a directory: {target}")

    cfg = load_config(root)
    tol = tolerance(cfg)

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
    for f in pngs(target):
        rel = f.relative_to(root)
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
        # one a padded file of this slot can sit on — the slot canvas or an
        # era's own `canvas:` — the same set standardize.py's guard uses.
        # Checking the slot canvas alone measured every long-sleeve keeper
        # on its era canvas as if it were source.
        size, box = content_box(f)
        if size in standard_canvases(cfg, canvas, profile):
            skipped_standardized += 1
            continue

        if box is None:
            continue
        cs = (box[2] - box[0], box[3] - box[1])
        checked += 1
        entry = match_era(profile, cs, tol)
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
        print(f"skipped {skipped_generated} files in {len(generated)} generated directories")
    if skipped_standardized:
        print(f"skipped {skipped_standardized} files already on their standardized canvas")
    if unparsed:
        print(f"!! skipped {sum(unparsed.values())} files whose path is not {{Sport}}/{{Team}}/{{Slot}} {{Viewpoint}}:")
        for d, n in sorted(unparsed.items()):
            print(f"     {d}  ({n} files)")
    if no_profile:
        print(f"!! skipped {sum(no_profile.values())} files whose profile is not in canvas_definitions.yaml:")
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
        for (key, era, cs, want, dw, dh), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(
                f"  {key} era {era}: {cs[0]}x{cs[1]} should be "
                f"{want[0]}x{want[1]}  ({dw:+d}, {dh:+d})  "
                f"— {len(items)} files"
            )
            for rel in items:
                print(f"       {rel}")
            print()

    if unmatched:
        print(f"{len(unmatched)} files match NO profile entry even within tolerance {tol}:")
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
