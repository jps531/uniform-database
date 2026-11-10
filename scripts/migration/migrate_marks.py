#!/usr/bin/env python3
"""
Migrate helmet marks from Marks/Temp/<Shell>/ into Marks/Football/<Team>/.

Source:  Marks/Temp/<Shell>/{Team} {Year} {Color} [{Desc}] {1|2}.png
                                                    1 = right, 2 = left

Dest:    Marks/Football/{Team}/Helmets {Right|Left}/
             {Year} {Color} [{Desc}]/
                 {Year} {Color} [{Desc}] {Shell} [{Number}].png

The shell token is written on EVERY file, not only on collisions: 92 designs
exist in more than one shell, and omitting it on singletons would make naming
inconsistent inside the same folder. It also gives era a second, independent
signal alongside content size.

    uv run scripts/migration/migrate_marks.py            # dry run — prints the plan
    uv run scripts/migration/migrate_marks.py --apply    # copies files

COPIES, never moves. The source tree stays intact until you have verified.
Never overwrites either: a file already at its destination blocks --apply
unless it is byte-identical to the source, in which case it is reported and
left alone.

    uv sync
"""

import argparse
import filecmp
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

# The shared helpers, and path parsing and the sport-qualified profile key
# shared with `pad`, live in scripts/pipeline/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from common import (
    add_root_arg,
    content_size,
    known_colorways,
    load_config,
    load_vocabulary,
    longest_first,
    match_era,
    pngs,
    root_from,
    slot_dirs,
    tolerance,
)
from standardize import lookup, parse_dest

SIDE_TO_VIEWPOINT = {"1": "Right", "2": "Left"}

# Source directory name -> shell token label used in destination filenames.
SHELL_DIRS = {
    "Leather": "Leather",
    "Double Bar": "Double Bar",
    "Classic": "Classic",
    "Speed": "Speed",
    "Speedflex": "Speedflex",
}

# {Team} {Year} {rest...} {side}. Team is non-greedy so the FIRST 4-digit run
# terminates it — which is what separates multi-word team names from the rest.
NAME = re.compile(r"^(?P<team>.+?)\s(?P<year>\d{4})\s(?P<rest>.+)\s(?P<side>[12])$")

# A trailing 1-2 digit token in `rest` is a jersey number (rare — Alabama).
TRAILING_NUM = re.compile(r"^(?P<desc>.+?)\s(?P<number>\d{1,2})$")

# Problem kinds printed one by one and blocking --apply, across all three
# modes. "unknown colorway" (flat mode) is the one warning and is not here.
BLOCKING = (
    "unknown shell directory",
    "unparsed filename",
    "no profile",
    "filename does not match folder",
    "unrecognised trailing token",
    "no opaque content",
    "size matches no era",
    "era has no shell token",
    "no colorways",
    "no known colorway",
    "nothing before the colorway — team and colour may be reversed",
)


def plan_flat_noyear(
    src_root: Path,
    dest_root: Path,
    slot_dir: str,
    viewpoint: str,
    root: Path,
):
    """Flat `{Team} {Color} [{modifiers}].png`, no year and no side suffix.

    Baseball hat marks look like "Auburn Navy A" or "Ole Miss Navy Red Bill".
    Unlike football helmet marks there is no year (hat years are not
    researchable for 42 teams) and no 1/2 side suffix (a hat has one
    viewpoint). The TEAM is whatever precedes the first colorway token, which
    is why a reversed name like "Black Campbell" is reported rather than
    guessed at.
    """
    colorways = longest_first(known_colorways(root))
    if not colorways:
        return [], [("no colorways", "configs/slots_global.yaml", "")]
    moves, problems = [], []
    for f in pngs(src_root):
        stem = f.stem
        best = None
        for c in colorways:
            m = re.search(rf"(?:(?<=\s)|^){re.escape(c)}(?=\s|$)", stem, re.I)
            if m and (best is None or m.start() < best[1]):
                best = (stem[m.start() : m.end()], m.start(), m.end())
        if best is None:
            problems.append(("no known colorway", f.name, ""))
            continue
        colour, i, j = best
        team = stem[:i].strip()
        rest = stem[j:].strip()
        if not team:
            problems.append(
                (
                    "nothing before the colorway — team and colour may be reversed",
                    f.name,
                    "",
                )
            )
            continue
        element = f"{colour} {rest}".strip()
        dest = dest_root / team / f"{slot_dir} {viewpoint}" / element / f"{element}.png"
        moves.append((f, dest))
    return moves, problems


def shell_by_era(root: Path) -> dict:
    """era letter -> shell label, from the `shell` tokens in the football vocabulary, `extends` followed."""
    tokens = load_vocabulary(root, "football").tokens
    return {v["era"]: v["label"] for v in tokens.values() if v.get("kind") == "shell" and "era" in v}


def plan_nested(src_root: Path, dest_root: Path, team: str, root: Path):
    """Source already in element-folder shape; derive the shell token from
    content size where the filename does not already carry one.

    The era is the CLOSEST within the config's `tolerance`, as every script
    matches eras.
    """
    cfg = load_config(root)
    tol = tolerance(cfg)
    helmets = slot_dirs(cfg)["helmet"]
    era_shell = shell_by_era(root)
    shell_names = longest_first(era_shell.values())
    moves, problems = [], []

    skipped_dirs = []
    for view_dir in sorted(src_root.iterdir()):
        if not view_dir.is_dir() or not view_dir.name.startswith(helmets):
            continue
        # Generated trees are outputs, not sources.
        if (view_dir / ".generated").exists():
            skipped_dirs.append((view_dir.name, "generated output"))
            continue
        viewpoint = view_dir.name.split()[-1]
        # Only left/right are stored as marks. Front/back stay in place, and
        # any suffixed directory (e.g. "... STD") is not a source. This used
        # to fall out of the profile lookup missing; front and back DO have
        # profiles, so it has to be said explicitly.
        if viewpoint not in SIDE_TO_VIEWPOINT.values():
            skipped_dirs.append((view_dir.name, "not a mark viewpoint"))
            continue
        # Profiles are keyed {sport}-{slot}-{viewpoint}. Resolve the key from
        # the DESTINATION directory (Marks/Football/<Team>/Helmets <View>),
        # the same parse `pad` uses, so the sport comes from the path rather
        # than being assumed. Leaving it out gave `helmet-left`, which is not
        # a key, and every viewpoint was skipped as having no profile.
        parsed = parse_dest(dest_root / team / view_dir.name, root, cfg)
        if parsed is None:
            skipped_dirs.append((view_dir.name, f"dest {dest_root} is not a sport tree"))
            continue
        sport, _team, slot, vp = parsed
        _canvas, profile, (_canvas_name, key) = lookup(cfg, sport, slot, vp)
        if not profile:
            skipped_dirs.append((view_dir.name, f"no profile {key}"))
            continue

        for element_dir in sorted(d for d in view_dir.iterdir() if d.is_dir()):
            element = element_dir.name
            for f in pngs(element_dir, recursive=False):
                stem = f.stem
                if not stem.startswith(element):
                    problems.append(
                        (
                            "filename does not match folder",
                            f"{view_dir.name}/{element}/{f.name}",
                            "",
                        )
                    )
                    continue
                rest = stem[len(element) :].strip()

                shell = next(
                    (s for s in shell_names if rest == s or rest.startswith(s + " ")),
                    None,
                )
                if shell:
                    rest = rest[len(shell) :].strip()
                number = rest if re.fullmatch(r"\d{1,2}", rest) else None
                if rest and number is None:
                    problems.append(("unrecognised trailing token", f"{element}/{f.name}", rest))
                    continue

                if shell is None:
                    cs = content_size(f)
                    if cs is None:
                        problems.append(("no opaque content", f"{element}/{f.name}", ""))
                        continue
                    entry = match_era(profile, cs, tol)
                    if entry is None:
                        problems.append(
                            (
                                "size matches no era",
                                f"{element}/{f.name}",
                                f"{cs[0]}x{cs[1]}",
                            )
                        )
                        continue
                    shell = era_shell.get(entry["era"])
                    if shell is None:
                        problems.append(
                            (
                                "era has no shell token",
                                f"{element}/{f.name}",
                                entry["era"],
                            )
                        )
                        continue

                parts = [element, shell] + ([number] if number else [])
                dest = dest_root / team / f"{helmets} {viewpoint}" / element / (" ".join(parts) + ".png")
                moves.append((f, dest))

    if skipped_dirs:
        print("Skipped directories:")
        for name, why in skipped_dirs:
            print(f"  {name:<24} {why}")
        print()
    return moves, problems


def plan(src_root: Path, dest_root: Path, colorways: set, helmets: str):
    """Return (moves, problems). Each move is (source, destination).

    `colorways` are common.known_colorways(); `helmets` is the helmet slot's
    directory word from `directory_slots` ("Helmets").
    """
    moves, problems = [], []
    for shell_dir in sorted(src_root.iterdir()):
        if not shell_dir.is_dir():
            continue
        shell = SHELL_DIRS.get(shell_dir.name)
        if shell is None:
            problems.append(("unknown shell directory", shell_dir.name, ""))
            continue
        for f in pngs(shell_dir, recursive=False):
            m = NAME.match(f.stem)
            if not m:
                problems.append(("unparsed filename", f"{shell_dir.name}/{f.name}", ""))
                continue
            g = m.groupdict()
            rest = g["rest"].strip()

            number = None
            nm = TRAILING_NUM.match(rest)
            if nm:
                number, rest = nm.group("number"), nm.group("desc").strip()

            element = f"{g['year']} {rest}"
            viewpoint = SIDE_TO_VIEWPOINT[g["side"]]
            parts = [element, shell] + ([number] if number else [])
            filename = " ".join(parts) + ".png"

            dest = dest_root / g["team"] / f"{helmets} {viewpoint}" / element / filename
            moves.append((f, dest))

            colour = rest.split()[0].lower() if rest else ""
            if colorways and colour not in colorways:
                problems.append(("unknown colorway", colour, f"{shell_dir.name}/{f.name}"))
    return moves, problems


def existing(moves):
    """Split planned copies whose destination already exists into (identical, different) destination lists.

    An identical file (same bytes as its source) needs no copy; a different
    one would be silently overwritten by shutil.copy2, so it blocks --apply.
    """
    same, differ = [], []
    for s, d in moves:
        if d.exists():
            (same if d.is_file() and filecmp.cmp(s, d, shallow=False) else differ).append(d)
    return same, differ


def main():
    """Plan the migration for the chosen mode, report it, and copy on --apply.

    Refuses to apply while a blocking problem or a destination collision
    remains, or a destination file already exists with different contents;
    an identical existing file is reported and skipped.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_root_arg(ap)
    ap.add_argument("--src", default="Marks/Temp")
    ap.add_argument("--dest", default="Marks/Football")
    ap.add_argument(
        "--slot-dir",
        default="Hats",
        help="flat-noyear: directory name for the slot (Hats)",
    )
    ap.add_argument("--viewpoint", default="Front", help="flat-noyear: viewpoint directory suffix")
    ap.add_argument(
        "--mode",
        choices=["flat", "nested", "flat-noyear"],
        default="flat",
        help="flat: Marks/Temp/<Shell>/{Team} {Year} ... {1|2}.png. "
        "nested: source already in element-folder shape; the "
        "shell token is derived from content size. "
        "flat-noyear: {Team} {Color} [{mods}].png with no "
        "year and no side suffix — baseball hat marks.",
    )
    ap.add_argument("--team", help="team name for nested mode")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually copy files (default is a dry run)",
    )
    args = ap.parse_args()

    root = root_from(args)
    src_root, dest_root = root / args.src, root / args.dest
    if not src_root.is_dir():
        sys.exit(f"Source not found: {src_root}")

    if args.mode == "flat-noyear":
        moves, problems = plan_flat_noyear(
            src_root,
            dest_root,
            args.slot_dir,
            args.viewpoint,
            root,
        )
    elif args.mode == "nested":
        if not args.team:
            sys.exit("--team is required in nested mode")
        moves, problems = plan_nested(src_root, dest_root, args.team, root)
    else:
        moves, problems = plan(src_root, dest_root, known_colorways(root), slot_dirs(load_config(root))["helmet"])

    # --- report -------------------------------------------------------
    teams = {m[1].relative_to(dest_root).parts[0] for m in moves}
    elements = {m[1].parent for m in moves}
    print(f"{len(moves)} files -> {len(teams)} teams, {len(elements)} element folders")
    print(f"source: {src_root}\ndest:   {dest_root}\n")

    by_kind = defaultdict(list)
    for kind, a, b in problems:
        by_kind[kind].append((a, b))

    for kind in BLOCKING:
        if by_kind.get(kind):
            print(f"!! {len(by_kind[kind])} {kind}:")
            for a, b in by_kind[kind][:20]:
                print(f"     {a}")
            print()

    if by_kind.get("unknown colorway"):
        counts = Counter(a for a, _ in by_kind["unknown colorway"])
        print(f"!! {len(counts)} colorways not in slots_global.yaml ({sum(counts.values())} files):")
        for c, n in counts.most_common():
            example = next(b for a, b in by_kind["unknown colorway"] if a == c)
            print(f"     {c:<14} {n:>4} files   e.g. {example}")
        print("   Add them to configs/slots_global.yaml, or correct the names.\n")

    collisions = Counter(d for _, d in moves)
    dupes = {d: n for d, n in collisions.items() if n > 1}
    if dupes:
        print(f"!! {len(dupes)} destination collisions — two sources would write the same file:")
        for d, n in list(dupes.items())[:10]:
            print(f"     {d.relative_to(dest_root)} ({n} sources)")
        print()

    same, differ = existing(moves)
    if differ:
        print(f"!! {len(differ)} files already exist at the destination with different contents:")
        for d in differ[:10]:
            print(f"     {d.relative_to(dest_root)}")
        print()
    if same:
        print(f"{len(same)} files already at the destination, identical: nothing to copy for them.\n")

    print("Sample of the plan:")
    for s, d in moves[:6]:
        print(f"  {s.relative_to(src_root)}")
        print(f"    -> {d.relative_to(dest_root)}")

    blocking = any(by_kind.get(k) for k in BLOCKING) or dupes or differ
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to copy.")
        if blocking:
            print("Resolve the flagged items first; unknown colorways are a warning, not a blocker.")
        return

    if blocking:
        sys.exit(
            "\nRefusing to apply while flagged problems, destination collisions or differing existing files remain."
        )

    skip = set(same)
    written = 0
    for s, d in moves:
        if d in skip:
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        written += 1
    kept = f" ({len(same)} already in place)" if same else ""
    print(f"\nCopied {written} files{kept}. Source tree left intact.")


if __name__ == "__main__":
    main()
