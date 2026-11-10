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

    uv sync

    uv run scripts/migration/recanvas.py "temp/Mississippi State/Jerseys Front" \\
                                "Football/Mississippi State/Jerseys Front"
    uv run scripts/migration/recanvas.py SRC DEST --apply

COPIES, never moves.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

DPI = 300


def find_root(start: Path) -> Path:
    """The nearest directory at or above `start` holding configs/canvas_definitions.yaml; exits if none."""
    for d in [start, *start.parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            return d
    sys.exit(f"No configs/canvas_definitions.yaml above {start}")


def slug(s):
    """Directory name -> config key: lowercase, apostrophes dropped, spaces to underscores."""
    return s.lower().replace("\u2019", "").replace("'", "").replace(" ", "_")


def main():
    """Re-place standardized files from SRC onto DEST's canvas, top-centre; dry run unless --apply.

    The canvas comes from DEST's path (or --canvas). Refuses to apply while any
    file's content is larger than the canvas.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dest")
    ap.add_argument("--root")
    ap.add_argument("--canvas", help="override the canvas looked up from DEST")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())
    src, dest = root / args.src, root / args.dest
    if not src.is_dir():
        sys.exit(f"Source not found: {src}")

    cfg = yaml.safe_load((root / "configs/canvas_definitions.yaml").open())
    C, A, dir_slot = cfg["canvases"], cfg["assignments"], cfg["directory_slots"]

    if args.canvas:
        cname = args.canvas
    else:
        parts = dest.relative_to(root).parts
        parts = parts[1:] if parts[0] in ("Marks", "Venues") else parts
        if len(parts) < 3:
            sys.exit(f"Cannot read sport/slot/viewpoint from {args.dest}")
        words = parts[2].split()
        cname = (A.get(slug(parts[0])) or {}).get(dir_slot.get(words[0]), {}).get(words[-1].lower())
        if not cname:
            sys.exit(f"No canvas assigned for {args.dest}")
    cv = C[cname]
    W, H = cv["width"], cv["height"]
    print(f"canvas {cname} = {W} x {H}, anchor top-center")
    print(f"{args.src}  ->  {args.dest}\n")

    jobs, too_big = [], []
    for f in sorted(src.rglob("*.png")):
        if f.name.startswith("."):
            continue
        with ImageOps.exif_transpose(Image.open(f)).convert("RGBA") as im:
            b = im.getchannel("A").getbbox()
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
        with ImageOps.exif_transpose(Image.open(s)).convert("RGBA") as im:
            b = im.getchannel("A").getbbox()
            art = im.crop(b) if b else im
            out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            out.paste(art, ((W - art.width) // 2, 0))
            out.save(d, dpi=(DPI, DPI))
    print(f"\nWrote {len(jobs)} files. Source left intact.")


if __name__ == "__main__":
    main()
