#!/usr/bin/env python3
"""
Replace `Generic {colorway}` pants with explicit per-element duplicates.

Generic artwork was a legitimate fallback — a 1939 pant has a side stripe but
looks like plain maroon from the front, so one shared front served many
elements. Eliminating it trades a resolver branch for a handful of duplicate
files, so every element names its own artwork and nothing has to fall back.

For each element missing a viewpoint, copies the matching Generic file in,
renamed to the element. Then deletes the Generic folders.

    python3 scripts/expand_generics.py            # dry run
    python3 scripts/expand_generics.py --apply

Only touches the three teams below. Southern Miss's 1987/1988/1997 pants are
missing BOTH Front and Left with no generic to copy from — a genuine coverage
gap, not a fallback case, and deliberately out of scope here.
"""

import argparse
import shutil
import sys
from pathlib import Path

# team -> list of (element needing a viewpoint, generic to copy from)
PLAN = {
    "Mississippi State": [
        ("1939 Maroon", "Generic Maroon"),
        ("1951 Maroon", "Generic Maroon"),
        ("1953 Maroon", "Generic Maroon"),
        ("1949 White", "Generic White"),
        ("1953 White", "Generic White"),
        ("1987 White", "Generic White"),
    ],
    "Raleigh": [
        ("1995 Maroon", "Generic Maroon"),
    ],
    "Taylorsville": [
        ("1990 Gold", "Generic Gold"),
        ("2008 Gold", "Generic Gold"),
        ("2015 Gold", "Generic Gold"),
        ("2004 Green", "Generic Green"),
        ("2014 Green", "Generic Green"),
        ("2000 White", "Generic White"),
        ("2004 White", "Generic White"),
        ("2011 White", "Generic White"),
        ("2013 White", "Generic White"),
    ],
}

VIEWPOINTS = ["Pants Front", "Pants Left", "Pants Icon"]


def find_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "configs").is_dir() and (d / "Football").is_dir():
            return d
    sys.exit(f"Could not find the project root above {start}. Pass --root.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else find_root(Path.cwd().resolve())
    )
    fb = root / "Football"

    copies, skipped, problems = [], [], []
    generics = set()

    for team, pairs in PLAN.items():
        for element, generic in pairs:
            for vp in VIEWPOINTS:
                src_dir = fb / team / vp / generic
                dst_dir = fb / team / vp / element

                if src_dir.is_dir():
                    generics.add(src_dir)

                # already has its own artwork for this viewpoint
                if dst_dir.is_dir() and any(dst_dir.glob("*.png")):
                    skipped.append(f"{team}/{vp}/{element}")
                    continue

                srcs = (
                    sorted(
                        f for f in src_dir.glob("*.png") if not f.name.startswith(".")
                    )
                    if src_dir.is_dir()
                    else []
                )
                if not srcs:
                    problems.append(f"{team}/{vp}/{element}: no source at {generic}")
                    continue
                if len(srcs) > 1:
                    problems.append(
                        f"{team}/{vp}/{generic}: {len(srcs)} files, expected 1"
                    )
                    continue

                copies.append((srcs[0], dst_dir / f"{element}.png"))

    print(f"{len(copies)} files to create, {len(generics)} generic folders to remove\n")

    by_team = {}
    for s, d in copies:
        rel = d.relative_to(fb)
        by_team.setdefault(rel.parts[0], []).append((s, d))
    for team, items in sorted(by_team.items()):
        print(f"  {team}")
        for s, d in items:
            print(f"     {s.parent.name:<16} -> {d.relative_to(fb / team)}")
        print()

    if skipped:
        print(f"{len(skipped)} already had their own artwork (left alone):")
        for s in skipped[:10]:
            print(f"     {s}")
        print()

    if problems:
        print(f"!! {len(problems)} problems:")
        for p in problems:
            print(f"     {p}")
        print()

    print("Generic folders to delete:")
    for g in sorted(generics):
        print(f"     {g.relative_to(fb)}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return
    if problems:
        sys.exit("\nRefusing to apply while problems remain.")

    for s, d in copies:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    for g in generics:
        shutil.rmtree(g)
    print(f"\nCreated {len(copies)} files, removed {len(generics)} generic folders.")


if __name__ == "__main__":
    main()
