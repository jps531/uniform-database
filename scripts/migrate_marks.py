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

    uv run scripts/migrate_marks.py            # dry run — prints the plan
    uv run scripts/migrate_marks.py --apply    # copies files

COPIES, never moves. The source tree stays intact until you have verified.

    uv sync
"""

import argparse
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import yaml
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

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


def find_root(start: Path) -> Path:
    """The nearest directory at or above `start` holding configs/canvas_definitions.yaml; exits if none."""
    for d in [start, *start.parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            return d
    sys.exit(f"No configs/canvas_definitions.yaml above {start}. Pass --root.")


def plan_flat_noyear(
    src_root: Path,
    dest_root: Path,
    sport: str,
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
    colorways = sorted(known_colorways(root), key=len, reverse=True)
    if not colorways:
        return [], [("no colorways", "configs/slots_global.yaml", "")]
    moves, problems = [], []
    for f in sorted(src_root.rglob("*.png")):
        if f.name.startswith("."):
            continue
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
    """era letter -> shell label, from the `shell` tokens in the vocabulary."""
    p = root / "configs" / "modifiers_football.yaml"
    if not p.is_file():
        return {}
    cfg = yaml.safe_load(p.open()) or {}
    return {v["era"]: v["label"] for v in (cfg.get("tokens") or {}).values() if v.get("kind") == "shell" and "era" in v}


def load_profile(root: Path, name: str):
    """(profile entries or None, tolerance) for a profile name in canvas_definitions.yaml."""
    cfg = yaml.safe_load((root / "configs" / "canvas_definitions.yaml").open())
    return cfg.get("profiles", {}).get(name), cfg.get("tolerance", 3)


def content_size(path: Path):
    """(width, height) of the file's opaque bounding box, or None if it is fully transparent."""
    with Image.open(path).convert("RGBA") as im:
        box = im.getchannel("A").getbbox()
    if box is None:
        return None
    return box[2] - box[0], box[3] - box[1]


def plan_nested(src_root: Path, dest_root: Path, team: str, root: Path):
    """Source already in element-folder shape; derive the shell token from
    content size where the filename does not already carry one."""
    if Image is None:
        sys.exit("Missing dependencies: run `uv sync` (nested mode reads image sizes)")
    era_shell = shell_by_era(root)
    shell_names = sorted(era_shell.values(), key=len, reverse=True)
    moves, problems = [], []

    skipped_dirs = []
    for view_dir in sorted(src_root.iterdir()):
        if not view_dir.is_dir() or not view_dir.name.startswith("Helmets"):
            continue
        # Generated trees are outputs, not sources.
        if (view_dir / ".generated").exists():
            skipped_dirs.append((view_dir.name, "generated output"))
            continue
        viewpoint = view_dir.name.split()[-1]
        profile, tol = load_profile(root, f"helmet-{viewpoint.lower()}")
        if not profile:
            # Only left/right are stored as marks. Front/back stay in place,
            # and any suffixed directory (e.g. "... STD") is not a source.
            skipped_dirs.append((view_dir.name, "no profile — not a mark viewpoint"))
            continue

        for element_dir in sorted(d for d in view_dir.iterdir() if d.is_dir()):
            element = element_dir.name
            for f in sorted(element_dir.glob("*.png")):
                if f.name.startswith("."):
                    continue
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
                    entry = next(
                        (e for e in profile if abs(e["size"][0] - cs[0]) <= tol and abs(e["size"][1] - cs[1]) <= tol),
                        None,
                    )
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
                dest = dest_root / team / f"Helmets {viewpoint}" / element / (" ".join(parts) + ".png")
                moves.append((f, dest))

    if skipped_dirs:
        print("Skipped directories:")
        for name, why in skipped_dirs:
            print(f"  {name:<24} {why}")
        print()
    return moves, problems


def known_colorways(root: Path) -> set:
    """Colorway strings AS THEY APPEAR IN FILENAMES.

    Both the KEY and the token/label are accepted, because filenames use
    either: "Dark Gray" matches the token where the key is dark_gray, while
    "Kansas Powder" matches the key where the label is "Powder Blue".
    Reading keys alone missed every multi-word colorway; reading labels alone
    missed the shortened ones.
    """
    p = root / "configs" / "slots_global.yaml"
    if not p.is_file():
        return set()
    cfg = yaml.safe_load(p.open()) or {}
    out = set()
    for key, v in (cfg.get("colorways") or {}).items():
        out.add(str(key).replace("_", " ").lower())
        if isinstance(v, dict):
            for alt in (v.get("token"), v.get("label")):
                if alt:
                    out.add(alt.lower())
    return out


def plan(src_root: Path, dest_root: Path, colorways: set):
    """Return (moves, problems). Each move is (source, destination)."""
    moves, problems = [], []
    for shell_dir in sorted(src_root.iterdir()):
        if not shell_dir.is_dir():
            continue
        shell = SHELL_DIRS.get(shell_dir.name)
        if shell is None:
            problems.append(("unknown shell directory", shell_dir.name, ""))
            continue
        for f in sorted(shell_dir.glob("*.png")):
            if f.name.startswith("."):
                continue
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

            dest = dest_root / g["team"] / f"Helmets {viewpoint}" / element / filename
            moves.append((f, dest))

            colour = rest.split()[0].lower() if rest else ""
            if colorways and colour not in colorways:
                problems.append(("unknown colorway", colour, f"{shell_dir.name}/{f.name}"))
    return moves, problems


def main():
    """Plan a marks migration in the chosen --mode, report problems, and copy the files with --apply.

    Unknown colorways are a warning; unparsed names, unmatched sizes and
    destination collisions block --apply.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="project root (default: auto-detect)")
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

    root = Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())
    src_root, dest_root = root / args.src, root / args.dest
    if not src_root.is_dir():
        sys.exit(f"Source not found: {src_root}")

    if args.mode == "flat-noyear":
        moves, problems = plan_flat_noyear(
            src_root,
            dest_root,
            args.sport if hasattr(args, "sport") else "",
            args.slot_dir,
            args.viewpoint,
            root,
        )
    elif args.mode == "nested":
        if not args.team:
            sys.exit("--team is required in nested mode")
        moves, problems = plan_nested(src_root, dest_root, args.team, root)
    else:
        moves, problems = plan(src_root, dest_root, known_colorways(root))

    # --- report -------------------------------------------------------
    teams = {m[1].relative_to(dest_root).parts[0] for m in moves}
    elements = {m[1].parent for m in moves}
    print(f"{len(moves)} files -> {len(teams)} teams, {len(elements)} element folders")
    print(f"source: {src_root}\ndest:   {dest_root}\n")

    by_kind = defaultdict(list)
    for kind, a, b in problems:
        by_kind[kind].append((a, b))

    for kind in (
        "unknown shell directory",
        "unparsed filename",
        "no profile",
        "filename does not match folder",
        "unrecognised trailing token",
        "size matches no era",
        "era has no shell token",
    ):
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

    print("Sample of the plan:")
    for s, d in moves[:6]:
        print(f"  {s.relative_to(src_root)}")
        print(f"    -> {d.relative_to(dest_root)}")

    blocking = (
        any(
            by_kind.get(k)
            for k in (
                "unparsed filename",
                "unknown shell directory",
                "no profile",
                "filename does not match folder",
                "unrecognised trailing token",
                "size matches no era",
                "era has no shell token",
            )
        )
        or dupes
    )
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to copy.")
        if blocking:
            print("Resolve the flagged items first; unknown colorways are a warning, not a blocker.")
        return

    if blocking:
        sys.exit(
            "\nRefusing to apply while unparsed files, unknown shell directories, or destination collisions remain."
        )

    written = 0
    for s, d in moves:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        written += 1
    print(f"\nCopied {written} files. Source tree left intact.")


if __name__ == "__main__":
    main()
