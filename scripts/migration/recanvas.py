#!/usr/bin/env python3
"""
Move ALREADY-STANDARDIZED files onto a different canvas. No era matching,
no scale correction, ever.

This exists because `standardize.py pad` resolves an era from CONTENT SIZE
and applies that era's scale. Run against output whose correction is already
baked in, it either re-applies the scale or — worse — finds no era at all and
silently drops the file. That is how era A football jerseys were lost: stored
post-correction at 1604x1862, they matched no entry in a profile that lists
era A as 1790x2078 pre-correction.

This script never looks at a profile. It crops to content, checks the content
FITS the destination canvas, and places it on the anchor. Pixels are untouched
apart from the crop and the new margin.

Use `pad` for authored source. Use this for anything a survey reports as
SCALED (see classify.py).

The canvas comes from DEST's path, parsed exactly as `pad` parses it, so the
recommended "… STD" sibling ("Jerseys Front STD") resolves the same canvas as
"Jerseys Front". `--canvas NAME` overrides it. Every file goes on that one
canvas, anchored top-centre; era `canvas:` overrides are not consulted, so a
cut larger than the slot canvas is reported as too big rather than placed.

    uv sync

    uv run scripts/migration/recanvas.py "temp/Mississippi State/Jerseys Front" \\
                                "Football/Mississippi State/Jerseys Front STD"
    uv run scripts/migration/recanvas.py SRC DEST --apply

COPIES, never moves. Refuses:
  - a DEST that resolves to SRC (it would rewrite the source in place);
  - a DEST holding PNGs without a .generated marker, which is treated as
    authored artwork, as `pad` does (an empty or new folder is fine);
  - --apply while any file's content is larger than the canvas.
On --apply it writes a .generated marker into DEST recording the source and
canvas. As with `pad`: recanvas into a "… STD" sibling, check it, delete its
marker, then copy the contents across.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

# Path parsing and the canvas lookup are `pad`'s, in scripts/pipeline/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from common import DPI, MARKER, add_root_arg, alpha_box, load_config, open_rgba, pngs, resolve, root_from  # noqa: E402
from standardize import lookup, parse_dest  # noqa: E402


def main():
    """Re-place standardized files from SRC onto DEST's canvas, top-centre; dry run unless --apply.

    The canvas comes from DEST's path (or --canvas). Refuses a DEST equal to
    SRC or holding PNGs without a .generated marker, and refuses to apply
    while any file's content is larger than the canvas.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dest")
    add_root_arg(ap)
    ap.add_argument("--canvas", help="override the canvas looked up from DEST")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = root_from(args)
    src, dest = resolve(args.src, root), resolve(args.dest, root)
    if not src.is_dir():
        sys.exit(f"Source not found: {src}")
    # Writing into the source rewrites every file in place: nothing would be
    # "left intact", whatever the last line printed.
    if dest == src:
        sys.exit("Destination must differ from source.")

    cfg = load_config(root)

    if args.canvas:
        cname = args.canvas
        cv = cfg["canvases"][cname]
    else:
        parsed = parse_dest(dest, root, cfg)
        if parsed is None:
            sys.exit(f"Cannot read sport/slot/viewpoint from {args.dest}")
        sport, _team, slot, viewpoint = parsed
        cv, _profile, (cname, _pn) = lookup(cfg, sport, slot, viewpoint)
        if not cv:
            sys.exit(f"No canvas assigned for {args.dest}")
    W, H = cv["width"], cv["height"]

    # Provenance guard, as in `pad`: a destination holding PNGs but no marker
    # is authored artwork, and re-placed copies must never overwrite it.
    # Checked before the dry run too, so the plan never looks safe.
    if dest.exists() and not (dest / MARKER).exists():
        held = pngs(dest)
        if held:
            sys.exit(
                f"REFUSING to write to {dest}\n"
                f"It holds {len(held)} PNGs but has no {MARKER} marker, so it looks like AUTHORED artwork.\n"
                "Recanvas into a new or empty folder (a … STD sibling) instead."
            )

    print(f"canvas {cname} = {W} x {H}, anchor top-center")
    print(f"{args.src}  ->  {args.dest}\n")

    jobs, too_big = [], []
    for f in pngs(src):
        with open_rgba(f) as im:
            b = alpha_box(im)
            cw, ch = (b[2] - b[0], b[3] - b[1]) if b else im.size
        if cw > W or ch > H:
            too_big.append((f.relative_to(src), f"{cw}x{ch}"))
            continue
        jobs.append((f, dest / f.relative_to(src), (cw, ch)))

    sizes = Counter(s for _, _, s in jobs)
    print(f"{len(jobs)} files, {len(sizes)} distinct content sizes:")
    for (cw, ch), n in sizes.most_common():
        print(f"   {cw:>6} x {ch:<6} {n:>4} files   -> placed at ({(W - cw) // 2}, 0)")
    if too_big:
        print(f"\n!! {len(too_big)} files are LARGER than the canvas:")
        for p, s in too_big[:10]:
            print(f"     {s:>12}  {p}")
        print("   These would be clipped. Check whether the canvas is right,")
        print("   or whether these still need a scale correction applied.")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to copy.")
        return
    if too_big:
        sys.exit("\nRefusing to apply while files exceed the canvas.")

    for s, d, _ in jobs:
        d.parent.mkdir(parents=True, exist_ok=True)
        with open_rgba(s) as im:
            b = alpha_box(im)
            art = im.crop(b) if b else im
            out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            out.paste(art, ((W - art.width) // 2, 0))
            out.save(d, dpi=(DPI, DPI))
    # The marker claims "generated from that source"; with nothing written
    # there is no such tree, so leave none.
    if jobs:
        (dest / MARKER).write_text(
            json.dumps(
                {
                    "generated_by": "scripts/migration/recanvas.py",
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "source": str(src),
                    "canvas": f"{W}x{H}",
                    "canvas_name": cname,
                    "anchor": "top-center",
                    "dpi": DPI,
                    "files_written": len(jobs),
                    "note": "Re-placed standardized output; scale untouched. Do not edit by hand.",
                },
                indent=2,
            )
            + "\n"
        )
    print(f"\nWrote {len(jobs)} files. Source left intact.")


if __name__ == "__main__":
    main()
