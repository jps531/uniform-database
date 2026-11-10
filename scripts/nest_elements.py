#!/usr/bin/env python3
"""
Nest flat staged files into element folders, driven by the token vocabulary.

Source:  temp/[{Sport}/]{Team}/{Slot} {Viewpoint}/{filename}.png
Dest:    {Sport}/{Team}/{Slot} {Viewpoint}/{Element}/{filename}.png

Filenames are NOT changed — only the folder they sit in.

THE RULE: the element folder is the filename minus everything that is not
part of the design.

    STRIPPED   tokens with scope `patch` or `variation`
               a form token: `kind` shell (helmet), cut (jersey), style (hat)
               the jersey number, WHEREVER it sits
               a sequence letter immediately following a stripped token
    KEPT       tokens with scope `design`
               a sequence letter otherwise — EMCC "2014 White A" and
               "2014 White B" are different helmets, not variants

Scope comes from configs/modifiers_{sport}.yaml, so adding a bowl patch or a
belt variation is a CONFIG change, not a code change. An unlisted token stays
in the element name — a loud failure (a wrong-looking folder in the dry run),
never a silent one.

Order matters: tokens match by LONGEST MATCH *before* any numeric or sequence
rule, because some design tokens end in a digit (DWS100) or a single capital
(Flying M, M over S).

The number is not assumed to be trailing. Baseball has "2015 White 85s 19
Grad" — element "2015 White 85s", number 19, patch Grad.

    pip install pyyaml

    python3 scripts/nest_elements.py --sport football
    python3 scripts/nest_elements.py --sport baseball --apply

COPIES, never moves.
"""

import argparse
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")


# Physical form variants that select a canvas: helmet shell, jersey cut, hat
# style. Different domain words, identical handling — all are file-level and
# stripped before the element name is taken.
FORM_KINDS = ("shell", "cut", "style")


def find_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "configs").is_dir() and (d / "scripts").is_dir():
            return d
    sys.exit(f"Could not find the project root above {start}. Pass --root.")


def read_vocab(root: Path, name: str, seen=None):
    """Load a vocabulary, following `extends:` so sports can share a base.

    A token defined in the extending file WINS over the same key in the base,
    so one sport can override a shared definition without copying the rest.
    """
    seen = seen or set()
    if name in seen:
        sys.exit(f"Circular `extends` reaching modifiers_{name}.yaml")
    seen.add(name)
    p = root / "configs" / f"modifiers_{name}.yaml"
    if not p.is_file():
        sys.exit(
            f"No vocabulary at configs/modifiers_{name}.yaml. Nesting needs one to tell design tokens from variations."
        )
    cfg = yaml.safe_load(p.open()) or {}
    tokens, colorways = {}, []
    if cfg.get("extends"):
        tokens, colorways = read_vocab(root, cfg["extends"], seen)
    return {**tokens, **(cfg.get("tokens") or {})}, (cfg.get("colorways") or colorways)


def load_vocab(root: Path, sport: str):
    tokens, cw = read_vocab(root, sport)
    colorways = {c.title() for c in cw}
    strip, design, shellcut, seq = [], [], [], []
    for v in tokens.values():
        # TOKEN is the string as it appears in filenames; `label` is the
        # display name and is often different (file: SBC, label: Sun Belt
        # Conference). Match on token, falling back to label.
        label = v.get("token") or v.get("label")
        kind, scope = v.get("kind"), v.get("scope")
        if not label:
            continue
        if kind in FORM_KINDS:
            shellcut.append(label)
        elif kind == "sequence":
            seq.append(label)
        elif scope in ("patch", "variation"):
            strip.append(label)
        else:
            # KEPT by default — scope: design, kind: finish, and anything
            # else. Only an explicit patch/variation/form/sequence is
            # stripped, so a token with an unexpected kind stays in the
            # element name rather than vanishing.
            design.append(label)

    def by(xs):
        """Distinct tokens, longest first, so matching prefers the longest token."""
        return sorted(set(xs), key=len, reverse=True)

    # Every WORD that appears in a design token or a colorway. A trailing
    # capitalised word outside this set is a player surname.
    known = {w for t in design for w in t.split()} | colorways
    return by(strip), by(design), by(shellcut), set(seq), known


def element_for(stem, strip, design, shellcut, seq, known_words=frozenset()):
    s, notes = stem, []

    for tok in shellcut:
        m = re.match(rf"^(.*?)\s{re.escape(tok)}(?:\s([A-Z]))?(\s.*)?$", s)
        if m:
            s = (m.group(1) + (m.group(3) or "")).strip()
            notes.append(tok + (f" {m.group(2)}" if m.group(2) else ""))
            break

    changed = True
    while changed:
        changed = False
        for tok in strip:
            m = re.match(rf"^(.*?)\s{re.escape(tok)}(?:\s([A-Z]))?(\s.*)?$", s)
            if m:
                s = (m.group(1) + (m.group(3) or "")).strip()
                notes.append(tok + (f" {m.group(2)}" if m.group(2) else ""))
                changed = True
                break

    # The number, wherever it sits — plus a sequence letter immediately after
    # it. A letter following a NUMBER is a variant of that number
    # ("34 A", "34 B"); a letter following the colorway is part of the design
    # ("2014 White A" and "2014 White B" are different EMCC helmets).
    m = re.search(r"(?<=\s)(\d{1,2})(?:\s([A-Z]))?(?=\s|$)", s)
    if m:
        s = (s[: m.start()] + " " + s[m.end() :]).strip()
        notes.append(f"#{m.group(1)}" + (f" {m.group(2)}" if m.group(2) else ""))

    s = re.sub(r"\s{2,}", " ", s).strip()

    # PLAYER SURNAME: a trailing capitalised word that belongs to no design
    # token and is not a colorway. Baseball has the same number on the same
    # design worn by different players ("18 Girodo" vs "18 Heck").
    parts = s.split()
    if len(parts) > 2:
        last = parts[-1]
        if re.fullmatch(r"[A-Z][a-z']+", last) and last not in known_words:
            s = " ".join(parts[:-1])
            notes.append(f"player {last}")

    return (s, notes) if s else (None, ["nothing left"])


def build_plan(src_root, dest_root, vocab, only_team):
    strip, design, shellcut, seq, known = vocab
    moves, problems = [], []
    for team_dir in sorted(d for d in src_root.iterdir() if d.is_dir()):
        if only_team and team_dir.name != only_team:
            continue
        for view_dir in sorted(d for d in team_dir.iterdir() if d.is_dir()):
            for f in sorted(view_dir.glob("*.png")):
                if f.name.startswith("."):
                    continue
                el, notes = element_for(f.stem, strip, design, shellcut, seq, known)
                if el is None:
                    problems.append((f"{team_dir.name}/{view_dir.name}/{f.name}", ", ".join(notes)))
                    continue
                moves.append((f, dest_root / team_dir.name / view_dir.name / el / f.name, notes))
    return moves, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--sport", default="football")
    ap.add_argument("--src")
    ap.add_argument("--dest")
    ap.add_argument("--team")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())
    sport_dir = args.sport.replace("_", " ").title()
    src_root = root / (
        args.src if args.src else (f"temp/{sport_dir}" if (root / "temp" / sport_dir).is_dir() else "temp")
    )
    dest_root = root / (args.dest or sport_dir)
    if not src_root.is_dir():
        sys.exit(f"Source not found: {src_root}")

    vocab = load_vocab(root, args.sport)
    print(
        f"vocabulary: {len(vocab[0])} strippable, {len(vocab[1])} design, "
        f"{len(vocab[2])} shell/cut, {len(vocab[3])} sequence"
    )
    print(f"source: {src_root.relative_to(root)}  ->  dest: {dest_root.relative_to(root)}\n")

    moves, problems = build_plan(src_root, dest_root, vocab, args.team)
    if not moves and not problems:
        sys.exit(f"No PNGs under {src_root}")

    folders = {d.parent for _, d, _ in moves}
    print(f"{len(moves)} files -> {len(folders)} element folders\n")
    per = defaultdict(lambda: [0, set()])
    for _, d, _ in moves:
        p = d.relative_to(dest_root).parts
        per[(p[0], p[1])][0] += 1
        per[(p[0], p[1])][1].add(p[2])
    print(f"{'team':<22}{'viewpoint':<18}{'files':>7}{'elements':>10}")
    for (t, v), (n, els) in sorted(per.items()):
        print(f"{t:<22}{v:<18}{n:>7}{len(els):>10}")

    coll = {d: n for d, n in Counter(d for _, d, _ in moves).items() if n > 1}
    if coll:
        print(f"\n!! {len(coll)} destination collisions:")
        for d, n in list(coll.items())[:10]:
            print(f"   {d.relative_to(dest_root)} ({n} sources)")
    if problems:
        print(f"\n!! {len(problems)} files could not be assigned:")
        for p, why in problems[:20]:
            print(f"   {p}  ({why})")

    print("\nSample (what was stripped):")
    for s, d, notes in moves[:8]:
        print(f"  {s.stem}")
        print(f"      -> {d.parent.name}/   [{', '.join(notes) or '—'}]")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return
    if problems or coll:
        sys.exit("\nRefusing to apply while problems or collisions remain.")
    for s, d, _ in moves:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    print(f"\nCopied {len(moves)} files. Source tree left intact.")


if __name__ == "__main__":
    main()
