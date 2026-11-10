#!/usr/bin/env python3
"""
Normalize PNG DPI metadata. Does NOT resample — pixel dimensions are
unchanged; only the pHYs chunk that Photoshop reads when placing a file.

A 965px-tall PNG tagged 72 DPI places into a 300 DPI PSD at 4020px
(965 / 72 * 300), which makes transform percentages meaningless across
files. Tagging everything 300 DPI makes placement 1:1.

    uv sync

    uv run scripts/migration/fix_dpi.py check "Football/Mississippi State"
    uv run scripts/migration/fix_dpi.py set   "Football/Mississippi State" 300
    uv run scripts/migration/fix_dpi.py set   "Football/Mississippi State" 300 --apply

`check` is read-only. Run it first. `set` is a DRY RUN until `--apply`: it
reports how many files it would retag, and from which tags.

With `--apply`, each file not already at the target is re-saved to a hidden
temp file in its own folder, verified, then moved over the original with
os.replace (atomic, so an interrupted run never leaves a half-written PNG).
Everything but the DPI tag is carried across: the EXIF block (Pillow drops
it unless passed explicitly, and with it the Orientation tag Finder's
"rotate" writes, which would silently turn the image), the ICC profile and
the PNG text chunks. Permission bits are kept. It ABORTS, leaving that file
untouched, if the copy's size, pixels, EXIF orientation or DPI are not what
was intended. Bad arguments are a usage error (exit 2).
"""

import argparse
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    from PIL import Image, PngImagePlugin
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

ORIENTATION = 0x0112  # the EXIF tag Finder's "rotate" writes instead of rotating pixels


def pngs(root: Path):
    """Yield every PNG under root, sorted, skipping anything inside a hidden directory or hidden itself."""
    for p in sorted(root.rglob("*.png")):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        yield p


def read_dpi(path: Path):
    """The file's horizontal DPI tag, rounded, or None if it has no tag."""
    with Image.open(path) as im:
        d = im.info.get("dpi")
        return round(d[0]) if d else None


def cmd_check(root: Path):
    """Report how many PNGs under root carry each DPI tag. Read-only."""
    files = list(pngs(root))
    if not files:
        sys.exit(f"No PNGs under {root}")
    counts = Counter()
    examples = {}
    for f in files:
        d = read_dpi(f)
        counts[d] += 1
        examples.setdefault(d, f.relative_to(root))
    print(f"{len(files)} PNGs under {root.name}\n")
    for d, n in counts.most_common():
        print(f"  {label(d):<14} {n:>5} files   e.g. {examples[d]}")
    if len(counts) > 1:
        print(
            "\nMixed DPI. Photoshop places by physical size, so files with "
            "different tags\nland at different scales even when their pixel "
            "dimensions are comparable."
        )
    elif None in counts:
        print("\nUntagged files default to 72 DPI in most tools.")


def label(d):
    """A DPI tag as printed: "72 DPI", or "no DPI tag" for None."""
    return f"{d} DPI" if d else "no DPI tag"


def retag(f: Path, target: int):
    """Re-save one PNG at `target` DPI, keeping its EXIF, ICC profile and text chunks.

    Writes a hidden temp file beside it, checks size, pixels, EXIF
    orientation and DPI against the original, then os.replace()s it over the
    original. On any mismatch it exits naming the file; on any error it
    removes the temp file. Either way the original is untouched.
    """
    with Image.open(f) as im:
        im.load()
        size0, mode0, data0 = im.size, im.mode, im.tobytes()
        orient0 = im.getexif().get(ORIENTATION)
        kw = {"format": "PNG", "dpi": (target, target)}
        if exif := im.info.get("exif"):
            kw["exif"] = exif
        if icc := im.info.get("icc_profile"):
            kw["icc_profile"] = icc
        if text := getattr(im, "text", None):
            info = PngImagePlugin.PngInfo()
            for k, v in text.items():
                info.add_text(k, v)
            kw["pnginfo"] = info
        fd, tmp_name = tempfile.mkstemp(dir=f.parent, prefix=f".{f.name}.", suffix=".tmp")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            im.save(tmp, **kw)
            with Image.open(tmp) as im2:
                im2.load()
                size, mode, data = im2.size, im2.mode, im2.tobytes()
                orient = im2.getexif().get(ORIENTATION)
                dpi = im2.info.get("dpi")
            if size != size0:
                sys.exit(f"ABORT: {f} changed size {size0} -> {size}; original left untouched")
            if (mode, data) != (mode0, data0):
                sys.exit(f"ABORT: {f} pixels changed on re-save; original left untouched")
            if orient != orient0:
                sys.exit(f"ABORT: {f} orientation changed {orient0} -> {orient}; original left untouched")
            if not dpi or round(dpi[0]) != target:
                sys.exit(f"ABORT: {f} re-saved without the {target} DPI tag; original left untouched")
            os.chmod(tmp, f.stat().st_mode & 0o7777)
            os.replace(tmp, f)
        finally:
            tmp.unlink(missing_ok=True)


def cmd_set(root: Path, target: int, apply: bool = False):
    """Retag every PNG under root not already at `target` DPI; a dry run unless `apply`.

    Files already at the target are never opened for writing. See retag()
    for how each file is written and verified.
    """
    files = list(pngs(root))
    if not files:
        sys.exit(f"No PNGs under {root}")
    todo = []
    skipped = 0
    for f in files:
        d = read_dpi(f)
        if d == target:
            skipped += 1
        else:
            todo.append((f, d))
    if not apply:
        print(f"Dry run: would set {target} DPI on {len(todo)} files ({skipped} already correct).")
        for d, n in Counter(d for _, d in todo).most_common():
            print(f"  {label(d)} -> {target}: {n:>5} files")
        print("\nNothing written. Re-run with --apply to write.")
        return
    for f, _ in todo:
        retag(f, target)
    print(f"Set {target} DPI on {len(todo)} files ({skipped} already correct).")
    print("Pixel dimensions, pixels and EXIF orientation verified unchanged on every file written.")
    print(
        "\nNote: files are re-encoded, so content hashes change. Harmless "
        "for PNG (lossless),\nbut re-run any hash-based inventory."
    )


def positive_int(s: str) -> int:
    """argparse type: a DPI must be a whole number above zero."""
    try:
        n = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {s!r}") from None
    if n <= 0:
        raise argparse.ArgumentTypeError(f"must be above zero: {n}")
    return n


def main(argv=None):
    """Parse `check PATH` or `set PATH DPI [--apply]` and run it."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="report DPI tags (read-only)")
    c.add_argument("path")
    s = sub.add_parser("set", help="retag to DPI; dry run until --apply")
    s.add_argument("path")
    s.add_argument("dpi", type=positive_int)
    s.add_argument("--apply", action="store_true", help="write the files (default: report only)")
    args = ap.parse_args(argv)
    root = Path(args.path).expanduser().resolve()
    if args.cmd == "check":
        cmd_check(root)
    else:
        cmd_set(root, args.dpi, args.apply)


if __name__ == "__main__":
    main()
