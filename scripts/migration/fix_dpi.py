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

`check` is read-only. Run it first.
"""

import sys
from collections import Counter
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")


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
        label = f"{d} DPI" if d else "no DPI tag"
        print(f"  {label:<14} {n:>5} files   e.g. {examples[d]}")
    if len(counts) > 1:
        print(
            "\nMixed DPI. Photoshop places by physical size, so files with "
            "different tags\nland at different scales even when their pixel "
            "dimensions are comparable."
        )
    elif None in counts:
        print("\nUntagged files default to 72 DPI in most tools.")


def cmd_set(root: Path, target: int):
    """Re-save every PNG under root not already at `target` DPI with that tag.

    Rewrites files in place. Aborts if any file's pixel dimensions change,
    which would mean the save did more than retag it.
    """
    files = list(pngs(root))
    if not files:
        sys.exit(f"No PNGs under {root}")
    changed = skipped = 0
    for f in files:
        if read_dpi(f) == target:
            skipped += 1
            continue
        with Image.open(f) as im:
            size_before = im.size
            im.load()
            im.save(f, dpi=(target, target))
        with Image.open(f) as im2:
            if im2.size != size_before:
                sys.exit(f"ABORT: {f} changed size {size_before} -> {im2.size}")
        changed += 1
    print(f"Set {target} DPI on {changed} files ({skipped} already correct).")
    print("Pixel dimensions verified unchanged on every file written.")
    print(
        "\nNote: files are re-encoded, so content hashes change. Harmless "
        "for PNG (lossless),\nbut re-run any hash-based inventory."
    )


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "check":
        cmd_check(Path(a[1]).expanduser().resolve())
    elif len(a) == 3 and a[0] == "set":
        cmd_set(Path(a[1]).expanduser().resolve(), int(a[2]))
    else:
        print(__doc__)
        sys.exit(1)
