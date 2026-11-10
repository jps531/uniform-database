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


def sport_slug(name: str) -> str:
    """Directory name -> the key used in `assignments`."""
    return name.lower().replace("\u2019", "").replace("'", "").replace(" ", "_")


def find_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            return d
    sys.exit(f"No configs/canvas_definitions.yaml above {start}")


def content_size(path: Path):
    with ImageOps.exif_transpose(Image.open(path)).convert("RGBA") as im:
        box = im.getchannel("A").getbbox()
    return None if box is None else (box[2] - box[0], box[3] - box[1])


def main():
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
    dir_slots = cfg["directory_slots"]
    profiles = cfg["profiles"]
    canvases = cfg.get("canvases", {})
    assignments = cfg.get("assignments", {})
    tol = cfg.get("tolerance", 5)

    def padded_canvas(rel_parts, slot, viewpoint):
        """Configured canvas for this path, only if it is `fills: pad`."""
        parts = (
            rel_parts[1:]
            if rel_parts and rel_parts[0] in ("Marks", "Venues")
            else rel_parts
        )
        if not parts:
            return None
            # Apostrophes must go: "Men's Basketball" -> mens_basketball, the
        # key used in `assignments`. Keeping it gave men's_basketball, which
        # matched nothing and reported every canvas as (unassigned).
        sport = sport_slug(parts[0])
        name = assignments.get(sport, {}).get(slot, {}).get(viewpoint)
        c = canvases.get(name) if name else None
        if c and c.get("fills") == "pad" and c.get("width"):
            return (c["width"], c["height"])
        return None

    # Generated trees hold POST-standardization sizes, which will never match
    # the pre-correction sizes in the profiles. Skip anything under a
    # directory carrying a .generated marker.
    generated = {m.parent for m in target.rglob(".generated")}
    skipped_generated = 0
    skipped_standardized = 0

    rows, unmatched, checked = [], [], 0
    for f in sorted(target.rglob("*.png")):
        rel = f.relative_to(root)
        if any(p.startswith(".") for p in rel.parts):
            continue
        if any(g in f.parents for g in generated):
            skipped_generated += 1
            continue
        # find the "{Slot} {Viewpoint}" segment anywhere in the path
        seg = next(
            (
                p
                for p in rel.parts
                if p.split() and p.split()[0] in dir_slots and len(p.split()) >= 2
            ),
            None,
        )
        if seg is None:
            continue
        words = seg.split()
        key = f"{dir_slots[words[0]]}-{words[-1].lower()}"
        profile = profiles.get(key)
        if not profile:
            continue

        # Files standardized IN PLACE carry no .generated marker but hold
        # post-standardization content. The tell is that their CANVAS equals
        # the configured padded canvas — the same signal standardize.py uses
        # for its idempotency guard.
        want_canvas = padded_canvas(rel.parts, dir_slots[words[0]], words[-1].lower())
        if want_canvas:
            with Image.open(f) as im:
                if im.size == want_canvas:
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
    print()

    if not rows and not unmatched:
        print("Every file is an exact match for its profile size.")
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
