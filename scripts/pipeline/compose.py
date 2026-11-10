#!/usr/bin/env python3
"""
Compose a combination graphic from standardized elements.

A SPIKE, not the composition service. It reads a view template from
configs/view_templates.yaml, resolves each placement to a file on disk, and
pastes. No database, no caching, no deterministic URLs — the point is to
validate that the standardized assets, canvases and anchors actually compose.

    uv sync

    uv run scripts/pipeline/compose.py \\
        --team "Mississippi State" \\
        --helmet "2025 Black" --jersey "2025 Black" --pants "2025 Black" \\
        --number 0 \\
        --out out/2025-black.png

    # show the left helmet inset (only when the two sides differ)
    uv run scripts/pipeline/compose.py ... --helmet-left

    # compare against a hand-made composite
    uv run scripts/pipeline/compose.py ... --diff "path/to/existing.png"

RESOLUTION per placement, when a number is requested:
    1. {element}/{element} … {number} … .png   carrying exactly that number
    2. {element}/{element} … .png              else an unnumbered file
    3. otherwise FAIL — a file carrying ANOTHER number is never used
With no number requested, any file in the folder is a candidate, unnumbered
ones first. Within each tier, files rank as candidates() describes.
Failing: `required` errors (exit 1), `if_available` skips, `explicit` skips.

There is NO generic fallback. Generic pants were replaced by explicit
per-element duplicates, so an unresolved placement is a real gap.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

from common import (
    DPI,
    FORM_KINDS,
    add_root_arg,
    alpha_box,
    load_config,
    load_vocabulary,
    load_yaml,
    longest_first,
    open_rgba,
    pngs,
    root_from,
    slot_dirs,
    sport_dir,
    token_name,
)


def load_vocab(root: Path, sport: str):
    """Return (all_tokens_longest_first, form_tokens, default_form_tokens) for a sport, `extends` followed.

    Exits naming the file when the sport's vocabulary, or one it extends, is
    missing, or the chain loops.
    """
    allt, form, default = [], set(), set()
    for v in load_vocabulary(root, sport).tokens.values():
        t = token_name(v)
        if not t or v.get("kind") == "sequence":
            continue
        allt.append(t)
        if v.get("kind") in FORM_KINDS:
            form.add(t)
            if v.get("default"):
                default.add(t)
    return longest_first(allt), form, default


def split_tail(stem, element, vocab_tokens):
    """Tokens and number found after the element name."""
    tail = stem[len(element) :].strip() if stem.startswith(element) else stem
    found = []
    changed = True
    while changed:
        changed = False
        for t in vocab_tokens:
            m = re.match(rf"^(.*?)(?:^|\s){re.escape(t)}(\s.*)?$", tail)
            if m:
                tail = (m.group(1) + (m.group(2) or "")).strip()
                found.append(t)
                changed = True
                break
    num = None
    m = re.search(r"(?<![\d])(\d{1,2})(?![\d])", tail)
    if m:
        num = m.group(1)
        tail = (tail[: m.start()] + " " + tail[m.end() :]).strip()
    leftover = [w for w in tail.split() if w]
    return set(found), num, leftover


def load_template(root: Path, sport: str, view_kind: str):
    """The view template for this sport and view kind; exits if there is none."""
    cfg = load_yaml(root / "configs" / "view_templates.yaml")
    for t in cfg["templates"]:
        if t["sport"] == sport and t["view_kind"] == view_kind:
            return t
    sys.exit(f"No template for {sport}/{view_kind}")


def candidates(folder: Path, element: str, number, want, vocab, player=None):
    """Files in an element folder that may stand for this request, best match first.

    With a number requested, a file carrying a DIFFERENT number is not a
    candidate at all: resolution is that number, else an unnumbered file,
    else nothing. It used to rank such files last but keep them, so a
    folder with no #7 and no unnumbered file composed #3 for a request of
    #7. Numbers are OPAQUE STRINGS — "03" != "3", "00" != "0".

    Ranked by, in order:
      1. the requested number matches (with no number requested,
         unnumbered files first)
      2. every explicitly requested token is present
      3. the requested PLAYER matches, where one was asked for. Baseball has
         the same number on the same design worn by different players —
         "18 Girodo" and "18 Heck" are both number 18. Without --player they
         tie and fall through to filename order.
      4. FEWEST unrequested extra tokens — so "2026 White 85s.png" beats
         "2026 White 85s Grad NCAA.png" when no patch was asked for
      5. a default form token (e.g. the modern hat) beats a non-default one
      6. filename, for stability

    Before this, ranking ignored tokens entirely and fell back to alphabetical
    order, which quietly picked patched artwork nobody asked for.
    """
    files = pngs(folder, recursive=False)
    if not files:
        return []
    allt, form_tokens, default_form = vocab
    want = set(want or ())

    scored = []
    for f in files:
        toks, num, leftover = split_tail(f.stem, element, allt)
        if number is not None and num is not None and num != number:
            continue  # another number: never a stand-in for the one asked for
        missing = want - toks
        extras = toks - want - default_form
        has_default = bool(toks & default_form)
        non_default_form = bool((toks & form_tokens) - default_form)
        if number is not None and num == number:
            num_rank = 0
        elif num is None:
            num_rank = 1
        else:
            num_rank = 2  # only reachable with no number requested
        # leftover words after tokens and the number are the player surname
        who = " ".join(leftover) if leftover else None
        if not player:
            play_rank = 0 if who is None else 1
        elif who and who.lower() == player.lower():
            play_rank = 0
        elif who is None:
            play_rank = 1
        else:
            play_rank = 2
        scored.append(
            (
                (
                    num_rank,
                    len(missing),
                    play_rank,
                    len(extras),
                    0 if (has_default or not non_default_form) else 1,
                    f.name,
                ),
                f,
            )
        )
    scored.sort(key=lambda s: s[0])
    return [f for _, f in scored]


def resolve(
    root: Path,
    team: str,
    sport: str,
    slot: str,
    viewpoint: str,
    element: str,
    number,
    want,
    vocab,
    player=None,
):
    """Return (path, how) or (None, reason).

    The sport's directory is matched by slug (common.sport_dir), so
    mens_basketball finds "Men's Basketball"; the slot's directory word comes
    from `directory_slots`.
    """
    view_dir = f"{slot_dirs(load_config(root))[slot]} {viewpoint.title()}"
    sd = sport_dir(root, sport)
    if sd is None:
        return None, f"no file under {view_dir}/{element} (no directory for sport '{sport}')"
    base = sd / team / view_dir

    hits = candidates(base / element, element, number, want, vocab, player)
    if hits:
        toks, num, leftover = split_tail(hits[0].stem, element, vocab[0])
        bits = ["#" + num if num else "no number"]
        if leftover:
            bits.append(" ".join(leftover))
        if toks:
            bits.append("+".join(sorted(toks)))
        return hits[0], ", ".join(bits)

    folder = base / element
    if number is not None and folder.is_dir():
        others = sorted(
            {
                n
                for f in pngs(folder, recursive=False)
                for n in [split_tail(f.stem, element, vocab[0])[1]]
                if n is not None
            }
        )
        if others:
            has = ", ".join("#" + n for n in others)
            return None, f"no #{number} or unnumbered file under {base.name}/{element} (has {has})"

    # NOTE: there is no `Generic {colorway}` fallback any more. Generic pants
    # were eliminated in favour of explicit per-element duplicates, so every
    # element names its own artwork. A miss here is a real gap, not something
    # to paper over.
    return None, f"no file under {base.name}/{element}"


def main():
    """Resolve every placement the template asks for, paste them onto its canvas and save the result.

    With --json, also writes the structured result (placements, missing,
    clipping), including when nothing could be written.
    """
    # The project is found first: the slot flags come from its config.
    pre = argparse.ArgumentParser(add_help=False)
    add_root_arg(pre)
    root = root_from(pre.parse_known_args()[0])
    SLOTS = tuple(slot_dirs(load_config(root)))

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_root_arg(ap)
    ap.add_argument("--team", default="Mississippi State")
    ap.add_argument("--sport", default="football")
    ap.add_argument("--view", default="full")
    # One flag per slot. None is required at parse time: the TEMPLATE decides
    # which slots it needs, and a missing one is reported against the
    # placement that wanted it. Baseball needs --hat and no --helmet;
    # football the reverse.
    # One flag per slot, plus a `2` form for the SECOND uniform in a combo
    # view. A combo shows two kits side by side — soccer pairs a field kit
    # with a keeper kit, volleyball pairs two jerseys that may differ in
    # sleeve length. Placements carry `uniform: 2` to select the second set.
    # The slots are those of `directory_slots` in canvas_definitions.yaml.
    for slot in SLOTS:
        ap.add_argument(f"--{slot}")
        ap.add_argument(f"--{slot}2", dest=f"{slot}2")
    ap.add_argument(
        "--element",
        action="append",
        default=[],
        metavar="SLOT=NAME",
        help='any other slot, e.g. --element sock="2019 White"',
    )
    ap.add_argument(
        "--with",
        dest="want",
        action="append",
        default=[],
        metavar="TOKEN",
        help="require a token, e.g. --with Grad --with Classic. Without it the PLAINEST matching file wins.",
    )
    ap.add_argument("--number", help="jersey number, as a STRING ('03' != '3')")
    ap.add_argument("--number2", help="jersey number for the SECOND uniform")
    ap.add_argument(
        "--with2",
        dest="want2",
        action="append",
        default=[],
        metavar="TOKEN",
        help="require a token on the SECOND uniform",
    )
    ap.add_argument("--player2", metavar="SURNAME", help="surname for the SECOND uniform")
    ap.add_argument(
        "--player",
        metavar="SURNAME",
        help="pick between files sharing a number, e.g. baseball's "
        '"18 Girodo" and "18 Heck". A surname is a parsed '
        "FIELD, not a vocabulary token, so it is not "
        "validated — check the `how` column reports it.",
    )
    ap.add_argument(
        "--helmet-left",
        action="store_true",
        help="show the left-helmet inset (sides differ)",
    )
    ap.add_argument("--out", default="out/composed.png")
    ap.add_argument(
        "--json",
        metavar="PATH",
        help="also write a machine-readable result: every placement, "
        "the file chosen, the tokens and number it carries, and "
        "how far its ARTWORK runs past the canvas. Written even "
        "when a required placement is missing.",
    )
    ap.add_argument("--diff", help="hand-made composite to compare against")
    args = ap.parse_args()

    tpl = load_template(root, args.sport, args.view)
    vocab = load_vocab(root, args.sport)
    W, H = tpl["output"]["width"], tpl["output"]["height"]
    elements = {
        1: {s: getattr(args, s) for s in SLOTS if getattr(args, s)},
        2: {s: getattr(args, f"{s}2") for s in SLOTS if getattr(args, f"{s}2")},
    }
    for pair in args.element:
        if "=" not in pair:
            sys.exit(f"--element expects SLOT=NAME, got {pair!r}")
        k, v = pair.split("=", 1)
        k = k.strip()
        u = 1
        if k.endswith("2") and k[:-1] in SLOTS:
            k, u = k[:-1], 2
        elements[u][k] = v.strip()

    # Per-uniform number, tokens and player. Uniform 2 falls back to
    # uniform 1's where not given, so a combo of the same kit in two
    # colourways needs only the element names.
    number = {1: args.number, 2: args.number2 or args.number}
    want = {1: set(args.want), 2: set(args.want2) or set(args.want)}
    player = {1: args.player, 2: args.player2 or args.player}
    unknown = (want[1] | want[2]) - set(vocab[0])
    if unknown:
        sys.exit(f"Unknown token(s): {', '.join(sorted(unknown))}\nNot in configs/modifiers_{args.sport}.yaml")

    need = {
        (p.get("uniform", 1), p["slot"]) for p in tpl["placements"] if p.get("requirement", "required") == "required"
    }
    absent = sorted((u, s) for u, s in need if s not in elements[u])
    if absent:
        hint = ", ".join(f"--{s}{'2' if u == 2 else ''}" for u, s in absent)
        uniforms = sorted({u for u, _ in need})
        sys.exit(
            f"Template '{args.view}' needs "
            f"{'TWO uniforms' if 2 in uniforms else 'these slots'}: "
            + ", ".join(f"--{s}{'2' if u == 2 else ''}" for u, s in sorted(need))
            + f"\nNot supplied: {hint}"
        )

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    placements = sorted(tpl["placements"], key=lambda p: p.get("z", 0))

    two = any(p.get("uniform", 1) == 2 for p in tpl["placements"])
    print(
        f"{W} x {H}  team={args.team}  number={args.number or '-'}"
        + (f"  |  uniform 2 number={number[2] or '-'}" if two else "")
        + "\n"
    )
    print(f"{'placement':<22} {'source':<44} {'how':<20} at")
    print("-" * 108)

    missing = []
    record = []  # one entry per placement, for --json
    for p in placements:
        slot, vp = p["slot"], p["viewpoint"]
        u = p.get("uniform", 1)
        req = p.get("requirement", "required")
        label = f"{slot}/{vp}" + (f" #{u}" if u != 1 else "")

        if req == "explicit" and not (slot == "helmet" and vp == "left" and args.helmet_left):
            print(f"{label:<22} {'—':<44} {'not requested':<20}")
            continue

        if slot not in elements[u]:
            print(f"{label:<22} {'—':<44} {'no element given':<20}")
            continue
        path, how = resolve(
            root,
            args.team,
            args.sport,
            slot,
            vp,
            elements[u][slot],
            number[u],
            want[u],
            vocab,
            player[u],
        )
        if path is None:
            if req == "required":
                missing.append((label, how))
                print(f"{label:<22} {'—':<44} {'MISSING':<20} {how}")
            else:
                print(f"{label:<22} {'—':<44} {'skipped (absent)':<20}")
            record.append(
                {
                    "label": label,
                    "slot": slot,
                    "viewpoint": vp,
                    "uniform": u,
                    "requirement": req,
                    "element": elements[u][slot],
                    "file": None,
                    "status": "missing" if req == "required" else "skipped",
                    "reason": how,
                }
            )
            continue

        with open_rgba(path) as img:
            s = float(p.get("scale", 1.0))
            if not math.isclose(s, 1.0):
                img = img.resize((round(img.width * s), round(img.height * s)), Image.Resampling.LANCZOS)
            rot = float(p.get("rotation", p.get("rotate", 0)))
            if rot:
                # Rotate about the TOP-CENTRE ANCHOR, not the image centre.
                # Photoshop pivots on the transform reference point, so the
                # anchor coordinate keeps its meaning and the element swings
                # around it. Positive = clockwise (Photoshop); PIL rotates
                # counter-clockwise, hence the negation.
                h0 = img.height
                img = img.rotate(-rot, resample=Image.Resampling.BICUBIC, expand=True)
                th = math.radians(rot)
                # anchor offset (0, -h0/2) under a clockwise rotation, y-down
                ax = img.width / 2 + (h0 / 2) * math.sin(th)
                ay = img.height / 2 - (h0 / 2) * math.cos(th)
                x = int(round(p["x"] - ax))
                y = int(round(p["y"] - ay))
            else:
                x = int(p["x"] - img.width / 2)  # top-CENTRE anchor
                y = int(p["y"])
            canvas.alpha_composite(img, (x, y))
            # Clipping is judged on the ARTWORK, not the padded element canvas.
            # Transparent padding hanging past the edge is harmless; only opaque
            # pixels landing outside the view are a defect.
            ab = alpha_box(img)
            iw, ih = img.size
        extra = f" rot {rot:g}deg" if rot else ""
        if ab:
            ax0, ay0, ax1, ay1 = x + ab[0], y + ab[1], x + ab[2], y + ab[3]
        else:
            ax0 = ay0 = ax1 = ay1 = 0
        over = {k: v for k, v in (("L", -ax0), ("T", -ay0), ("R", ax1 - W), ("B", ay1 - H)) if v > 0}
        clip = "  CLIPPED " + ",".join(f"{k}{v}" for k, v in over.items()) if over else ""
        print(f"{label:<22} {path.name[:40]:<40} {how:<18} ({x}, {y}) {iw}x{ih}{extra}{clip}")
        toks, num, leftover = split_tail(path.stem, elements[u][slot], vocab[0])
        record.append(
            {
                "label": label,
                "slot": slot,
                "viewpoint": vp,
                "uniform": u,
                "requirement": req,
                "element": elements[u][slot],
                "file": str(path),
                "status": "placed",
                "number_requested": number[u],
                "number_found": num,
                "player_requested": player[u],
                "player_found": " ".join(leftover) or None,
                "tokens_requested": sorted(want[u]),
                "tokens_found": sorted(toks),
                "at": [x, y],
                "size": [iw, ih],
                "scale": float(p.get("scale", 1.0)),
                "rotation": rot,
                "artwork_bbox": [ax0, ay0, ax1, ay1],
                "clipped": over,
            }
        )

    def dump(written):
        """Write the --json result if one was asked for; `written` says whether the PNG was saved."""
        if not args.json:
            return
        jp = Path(args.json)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(
            json.dumps(
                {
                    "sport": args.sport,
                    "view": args.view,
                    "team": args.team,
                    "canvas": [W, H],
                    "output": str(args.out) if written else None,
                    "missing": [{"label": label, "reason": reason} for label, reason in missing],
                    "placements": record,
                },
                indent=2,
            )
        )

    if missing:
        print(f"\n!! {len(missing)} required placements unresolved:")
        for label, why in missing:
            print(f"   {label}: {why}")
        dump(False)
        sys.exit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, dpi=(DPI, DPI))
    dump(True)
    print(f"\nWrote {out}")

    if args.diff:
        ref_path = Path(args.diff)
        if not ref_path.is_file():
            sys.exit(f"Reference not found: {ref_path}")
        with Image.open(ref_path) as raw, raw.convert("RGBA") as ref:
            print(f"\nreference {ref.size}  composed {canvas.size}")
            if ref.size != canvas.size:
                print("  sizes differ — scaling reference to compare")
                ref = ref.resize(canvas.size, Image.Resampling.LANCZOS)
            import numpy as np

            a = np.array(canvas).astype(int)
            b = np.array(ref).astype(int)
            ink = (a[..., 3] > 20) | (b[..., 3] > 20)
            diff = (np.abs(a[..., :3] - b[..., :3]).sum(axis=2) > 40) & ink
            pct = 100 * diff.sum() / max(ink.sum(), 1)
            print(f"  differing pixels: {diff.sum():,} of {ink.sum():,} inked ({pct:.2f}%)")
            ys, xs = np.nonzero(diff)
            if len(xs):
                print(f"  differences span x {xs.min()}-{xs.max()}, y {ys.min()}-{ys.max()}")
                Image.fromarray((diff * 255).astype("uint8")).save(out.with_name(out.stem + "-diff.png"))
                print(f"  wrote {out.with_name(out.stem + '-diff.png')}")


if __name__ == "__main__":
    main()
