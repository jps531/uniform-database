#!/usr/bin/env python3
"""
Standardize element PNGs onto fixed canvases.

Reads canvas sizes and era corrections from configs/canvas_definitions.yaml,
so this script holds no per-era knowledge of its own.

    uv sync

    # inspect a slot before configuring it
    uv run scripts/pipeline/standardize.py survey "Football/Mississippi State/Helmets Right"

    # standardize into place (canvas + profile looked up from the path)
    uv run scripts/pipeline/standardize.py pad \\
        "~/.../MSU Uniforms/Football/Helmets Right" \\
        "Football/Mississippi State/Helmets Right"

Paths may be absolute, or relative to the project root (the directory
containing configs/). The DESTINATION path determines which canvas and
profile apply: "Football/<Team>/Jerseys Front" -> sport=football,
slot=jersey, viewpoint=front.

Overrides for a slot not yet in the config:
    --canvas 2000x2300 --profile jersey-front
"""

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

MARKER = ".generated"

try:
    import yaml
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")
try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")


# ---------------------------------------------------------------- config


def sport_slug(name: str) -> str:
    """Directory name -> the key used in `assignments`."""
    return name.lower().replace("\u2019", "").replace("'", "").replace(" ", "_")


def find_root(start: Path) -> Path:
    """Walk up for the directory containing configs/canvas_definitions.yaml."""
    for d in [start, *start.parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            return d
    sys.exit(
        "Could not find configs/canvas_definitions.yaml in any parent "
        f"of {start}. Run from inside the project, or pass --root."
    )


def load_config(root: Path) -> dict:
    """Parsed configs/canvas_definitions.yaml."""
    with (root / "configs" / "canvas_definitions.yaml").open() as fh:
        return yaml.safe_load(fh)


def resolve(path_arg: str, root: Path) -> Path:
    """A path argument as an absolute path; relative ones are taken from the project root, not the cwd."""
    p = Path(path_arg).expanduser()
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def parse_dest(dest: Path, root: Path, cfg: dict):
    """'Football/<Team>/Jerseys Front' -> (sport, team, slot, viewpoint).

    Trailing words are ignored, so 'Jerseys Front STD' still resolves to
    (jersey, front). The viewpoint is matched against the viewpoints declared
    for that sport+slot in `assignments`, not taken positionally.
    """
    try:
        parts = dest.relative_to(root).parts
    except ValueError:
        return None
    # Marks/ and Venues/ carry an extra leading segment before the usual
    # {Sport}/{Team}/{Slot} {Viewpoint}. Drop it so those trees resolve the
    # same canvas and profile as the uniform tree. Venues/ holds playing
    # surfaces, which are NOT uniform elements — Venues/Basketball is
    # deliberately ungendered because Humphrey Coliseum is shared by the
    # men's and women's programs.
    if parts and parts[0] in ("Marks", "Venues"):
        parts = parts[1:]
    if len(parts) < 3:
        return None
    # Apostrophes must go: "Men's Basketball" -> mens_basketball, the key
    # used in `assignments`. Keeping it gave men's_basketball, which matched
    # nothing and reported every canvas as (unassigned).
    sport = sport_slug(parts[0])
    team = parts[1]
    words = parts[2].split()
    if len(words) < 2:
        return None
    slot = cfg["directory_slots"].get(words[0])
    if not slot:
        return None

    known = set(cfg.get("assignments", {}).get(sport, {}).get(slot, {}))
    rest = [w.lower() for w in words[1:]]
    viewpoint = next((w for w in rest if w in known), None)
    if viewpoint is None:
        # slot known but viewpoint not declared yet — fall back to the first
        # word after the slot so the error message is useful
        viewpoint = rest[0]
    return sport, team, slot, viewpoint


def lookup(cfg, sport, slot, viewpoint):
    """Return (canvas dict or None, profile list or None, names)."""
    canvas_name = cfg.get("assignments", {}).get(sport, {}).get(slot, {}).get(viewpoint)
    canvas = cfg["canvases"].get(canvas_name) if canvas_name else None
    # Keyed by SPORT too: `jersey-front` alone matched baseball jerseys
    # against football's profile and reported every size as UNMATCHED.
    profile_name = f"{sport}-{slot}-{viewpoint}"
    profile = cfg.get("profiles", {}).get(profile_name)
    return canvas, profile, (canvas_name, profile_name)


# ---------------------------------------------------------------- imaging


def pngs(root: Path):
    """Yield every PNG under root, sorted, skipping anything inside a hidden directory or hidden itself."""
    for p in sorted(root.rglob("*.png")):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        yield p


def content_size(img: Image.Image):
    """(bbox, (width, height)) of the image's opaque content, or (None, None) if fully transparent."""
    box = img.getchannel("A").getbbox()
    if box is None:
        return None, None
    return box, (box[2] - box[0], box[3] - box[1])


def match_era(profile, w, h, tol):
    """The first profile entry whose size is within `tol` of (w, h), or None."""
    for entry in profile:
        ew, eh = entry["size"]
        if abs(ew - w) <= tol and abs(eh - h) <= tol:
            return entry
    return None


# ---------------------------------------------------------------- commands


def cmd_survey(args, root, cfg):
    """Print the distinct content sizes under a path and the era each matches. Read-only.

    Use it to write or check a profile; with --elements, or when no profile
    exists yet, it also lists which elements sit at each size.
    """
    src = resolve(args.path, root)
    if not src.is_dir():
        sys.exit(f"Not a directory: {src}")
    files = list(pngs(src))
    if not files:
        sys.exit(
            f"No PNGs under {src}\n"
            "If files show an iCloud arrow:\n"
            f'  find "{src}" -name "*.icloud" -exec brctl download {{}} \\;'
        )

    sizes, margined = Counter(), []
    for f in files:
        with ImageOps.exif_transpose(Image.open(f)).convert("RGBA") as img:
            box, cs = content_size(img)
            if cs is None:
                continue
            sizes[cs] += 1
            if box != (0, 0, *img.size):
                margined.append((f.relative_to(src), img.size, box))

    print(f"{len(files)} PNGs under {src.name}")
    parsed = parse_dest(src, root, cfg)
    profile = None
    if getattr(args, "profile", None):
        profile = cfg.get("profiles", {}).get(args.profile)
        if profile is None:
            sys.exit(f"No profile '{args.profile}' in config.")
        print(f"  profile={args.profile} (override)")
    elif parsed:
        sport, team, slot, viewpoint = parsed
        canvas, profile, (cn, pn) = lookup(cfg, sport, slot, viewpoint)
        print(f"  sport={sport} team={team} slot={slot} viewpoint={viewpoint}")
        print(f"  canvas={cn or '(unassigned)'}  profile={pn}{'' if profile else ' (not yet defined)'}")

    print(f"\n{len(sizes)} distinct CONTENT sizes:")
    tol = cfg.get("tolerance", 3)
    for (w, h), n in sizes.most_common():
        era = match_era(profile, w, h, tol) if profile else None
        tag = f"  -> era {era['era']}" if era else ("  -> UNMATCHED" if profile else "")
        print(f"  {w:>5} x {h:<5}  {n:>4} files{tag}")

    if profile is None or args.elements:
        # Group elements by size so eras can be assigned by inspection.
        by_size = {}
        for f in files:
            with ImageOps.exif_transpose(Image.open(f)).convert("RGBA") as img:
                _, cs = content_size(img)
            if cs is None:
                continue
            el = f.relative_to(src).parts[0]
            by_size.setdefault(cs, set()).add(el)
        print("\nElements at each size (assign eras from this):")
        for cs, els in sorted(by_size.items(), key=lambda kv: -len(kv[1])):
            names = sorted(els)
            print(f"\n  {cs[0]} x {cs[1]}  ({len(names)} elements)")
            head = names if len(names) <= 8 else names[:4] + ["..."] + names[-3:]
            for nm in head:
                print(f"      {nm}")

    if margined:
        print(f"\n{len(margined)} files carry transparent margin (cropped automatically on pad)")

    # Only meaningful for PADDED canvases. For `fills: fill` the canvas IS
    # the content size, so every source file matches it and this would fire
    # on unstandardized artwork.
    if parsed and canvas and canvas.get("width") and canvas.get("fills") == "pad":
        cw_, ch_ = canvas["width"], canvas["height"]
        std = sum(1 for f in files if Image.open(f).size == (cw_, ch_))
        if std == len(files):
            print(f"\nNOTE: every file is already {cw_} x {ch_} — this is standardized OUTPUT, not source artwork.")
            print("Sizes above are post-correction, so era A will read as UNMATCHED (it lists pre-correction sizes).")
            print("Survey the original tree to check era coverage.")

    maxw = max(w for w, _ in sizes)
    maxh = max(h for _, h in sizes)
    print(f"\nLargest content: {maxw} x {maxh}")
    print(f"Suggested canvas (~12% headroom): {round(maxw * 1.12 / 100) * 100} x {round(maxh * 1.11 / 100) * 100}")
    if profile is None:
        print(
            "\nNo profile yet. Add one to configs/canvas_definitions.yaml "
            "under `profiles:`, declaring each era explicitly."
        )


def cmd_pad(args, root, cfg):
    """Standardize authored source into DEST: crop to content, apply the era's scale, pad onto the canvas.

    Writes immediately, and writes a .generated marker into DEST. Refuses a
    DEST of authored PNGs without a marker (unless --force), and refuses
    source that is already standardized: files on the target canvas, or whose
    content matches what an era's scale produces.
    """
    src = resolve(args.src, root)
    dest = resolve(args.dest, root)
    if not src.is_dir():
        sys.exit(f"Not a directory: {src}")
    if dest == src:
        sys.exit("Destination must differ from source.")

    tol = cfg.get("tolerance", 3)
    canvas = profile = None
    parsed = parse_dest(dest, root, cfg)
    if parsed:
        sport, team, slot, viewpoint = parsed
        canvas, profile, (cn, pn) = lookup(cfg, sport, slot, viewpoint)
        label = f"{sport}/{slot}/{viewpoint}  canvas={cn} profile={pn}"
    else:
        label = "(path not recognized — using overrides)"

    if args.canvas:
        w, h = (int(v) for v in args.canvas.lower().split("x"))
        canvas = {"width": w, "height": h}
    if args.profile:
        profile = cfg.get("profiles", {}).get(args.profile)
        if profile is None:
            sys.exit(f"No profile '{args.profile}' in config.")

    if not canvas or not canvas.get("width"):
        sys.exit(f"No canvas size for this path ({label}).\nFill it in under `canvases:` or pass --canvas WxH.")
    if not profile:
        sys.exit(
            f"No profile for this path ({label}).\n"
            "Add one under `profiles:` or pass --profile NAME.\n"
            "Run `survey` first to see the era sizes."
        )

    base_width, base_height = canvas["width"], canvas["height"]
    width, height = base_width, base_height
    # Provenance guard. A destination holding authored artwork must never be
    # overwritten by a generated run. Generated trees carry a .generated
    # marker; anything else with content in it is treated as authored.
    marker = dest / MARKER
    if dest.exists() and not marker.exists():
        existing = list(pngs(dest))
        if existing and not args.force:
            sys.exit(
                f"REFUSING to write to {dest}\n"
                f"It holds {len(existing)} PNGs but has no {MARKER} marker, so "
                f"it looks like AUTHORED artwork.\n"
                f"Generated output would overwrite it.\n\n"
                f"If this really is a generated tree, pass --force once and "
                f"the marker will be written."
            )

    files = list(pngs(src))
    if not files:
        sys.exit(f"No PNGs under {src}")

    # Sizes an era would produce AFTER its scale correction. A file whose
    # content matches one of these has already been through this pipeline,
    # whatever canvas it is sitting on.
    #
    # The old guard only compared the CANVAS against the target, which is
    # too narrow: resizing football_jersey from 2000x2300 to 1792x2044 made
    # every already-scaled era A jersey sail past it. They then matched no
    # era (stored at 1604x1862 against a profile listing 1790x2078) and were
    # silently not written — and a following `rm -rf` of the source lost
    # them. Use scripts/migration/recanvas.py to move standardized files to a new
    # canvas; it never touches scale.
    corrected = {}
    for e in profile:
        s = e.get("scale", 1)
        if s != 1:
            corrected[(round(e["size"][0] * s), round(e["size"][1] * s))] = e["era"]

    # Two passes. Pass 1 measures and classifies EVERY file and decides where
    # each one goes; nothing is written. Pass 2 writes, and only runs once
    # the refusals below have had their say. Checking for post-correction
    # input after writing left a partially written destination behind a
    # message claiming "Nothing written".
    placed, unmatched, skipped = Counter(), [], []
    already_std = 0
    post_correction = []
    plan = []
    for f in files:
        rel = f.relative_to(src)
        with ImageOps.exif_transpose(Image.open(f)).convert("RGBA") as img:
            iw, ih = img.size
            box, cs = content_size(img)
        if cs is None:
            continue

        hit = next(
            (era for size, era in corrected.items() if abs(size[0] - cs[0]) <= tol and abs(size[1] - cs[1]) <= tol),
            None,
        )
        if hit is not None:
            post_correction.append((rel, cs, hit))
            continue

        # A file whose CANVAS already equals the target has been through
        # this pipeline too, even if its era carries no scale correction.
        if (iw, ih) == (width, height):
            already_std += 1
            continue

        cw, ch = cs

        era = match_era(profile, cw, ch, tol)
        if era is None:
            unmatched.append((rel, cw, ch))
            continue

        # An era may override the slot canvas. Without this, one canvas
        # has to be wide enough for every era — which would pad 1,000+
        # standard baseball jerseys to accommodate 14 three-quarter ones.
        ec = era.get("canvas")
        if ec:
            oc = cfg["canvases"].get(ec)
            if not oc or not oc.get("width"):
                unmatched.append((rel, cw, ch))
                continue
            width, height = oc["width"], oc["height"]
        else:
            width, height = base_width, base_height

        s = float(era.get("scale", 1.0))
        w, h = (round(cw * s), round(ch * s)) if s != 1.0 else (cw, ch)
        anchor = era.get("anchor", args.anchor)
        x = 0 if anchor.endswith("left") else (width - w if anchor.endswith("right") else (width - w) // 2)
        y = 0 if anchor.startswith("top") else (height - h) // 2
        x += int(era.get("dx", 0))
        y += int(era.get("dy", 0))

        if x < 0 or y < 0 or x + w > width or y + h > height:
            skipped.append((rel, cw, ch, w, h, x, y))
            continue

        plan.append((f, rel, box, era, s, cw, ch, w, h, x, y, width, height))

    if post_correction:
        eras = sorted({e for _, _, e in post_correction})
        lines = "\n".join(f"     {c[0]}x{c[1]}  era {e}  {r}" for r, c, e in post_correction[:8])
        sys.exit(
            f"{label}\n"
            f"REFUSING: {len(post_correction)} of {len(files)} files are "
            f"ALREADY POST-CORRECTION (era {', '.join(eras)}).\n"
            f"{lines}\n"
            "Their content matches what the era's scale factor PRODUCES, not "
            "what it consumes, so this is standardized output. Padding it "
            "again would re-apply the scale — or, if the sizes no longer "
            "match any era, drop the files entirely.\n\n"
            "Nothing written. Point `src` at the authored tree, or use\n"
            "  uv run scripts/migration/recanvas.py SRC DEST\n"
            "to move standardized files to a different canvas without "
            "touching scale."
        )

    if already_std == len(files):
        sys.exit(
            f"{label}\n"
            f"All {len(files)} files are ALREADY {width} x {height}.\n"
            "This looks like standardized output, not source artwork. "
            "Re-padding would re-apply era scale corrections a second "
            "time.\nNothing written. Point `src` at the original tree."
        )

    # Pass 2: every refusal has passed, so write.
    for f, rel, box, era, s, cw, ch, w, h, x, y, cvw, cvh in plan:
        with ImageOps.exif_transpose(Image.open(f)).convert("RGBA") as img:
            img = img.crop(box)
            if s != 1.0:
                img = img.resize((w, h), Image.LANCZOS)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            cv = Image.new("RGBA", (cvw, cvh), (0, 0, 0, 0))
            # No mask: the canvas is empty, so a plain paste copies RGBA as
            # is. Pasting with the image as its own mask applied alpha twice
            # and squared every anti-aliased edge (128 -> 64, 64 -> 16).
            cv.paste(img, (x, y))
            # Tag DPI explicitly. Untagged PNGs default to 72 in most tools,
            # so they place into a 300 DPI PSD at 4.17x and make transform
            # percentages meaningless across files.
            cv.save(out, dpi=(args.dpi, args.dpi))
        placed[(era["era"], cw, ch, w, h, x, y, cvw, cvh)] += 1

    dest.mkdir(parents=True, exist_ok=True)
    (dest / MARKER).write_text(
        json.dumps(
            {
                "generated_by": "scripts/pipeline/standardize.py",
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "source": str(src),
                "canvas": f"{width}x{height}",
                "profile": label,
                "anchor": args.anchor,
                "dpi": args.dpi,
                "files_written": sum(placed.values()),
                "note": "Generated output. Do not edit by hand — the next run "
                "overwrites this directory. Edit the source instead.",
            },
            indent=2,
        )
        + "\n"
    )

    print(f"{label}")
    print(f"canvas {width} x {height}, anchor {args.anchor}")
    print(f"Wrote {sum(placed.values())} of {len(files)} files to {dest}\n")
    print(f"{'era':>8}  {'content':>14}  {'after scale':>14}  {'canvas':>13}  {'placed at':>13}  files")
    for (era, cw, ch, w, h, x, y, cvw, cvh), n in sorted(placed.items()):
        print(f"{str(era):>8}  {cw:>6} x {ch:<5}  {w:>6} x {h:<5}  {cvw:>5} x {cvh:<5}  ({x:>5}, {y:>4})  {n:>5}")

    if already_std:
        print(f"\n!! {already_std} files were SKIPPED — already {width} x {height}.")
        print("   Mixed source: some artwork here has already been standardized.")

    if unmatched:
        print(f"\n!! {len(unmatched)} files matched NO era and were NOT written:")
        for (w, h), n in Counter((w, h) for _, w, h in unmatched).most_common():
            print(f"   {w} x {h}  ({n} files)")
        for rel, w, h in unmatched[:8]:
            print(f"     {w}x{h}  {rel}")
        print("   Add an era to the profile, or widen `tolerance` if these")
        print("   are rounding variants of an existing entry.")

    if skipped:
        need_w = max(x + w for _, _, _, w, _, x, _ in skipped)
        need_h = max(y + h for _, _, _, _, h, _, y in skipped)
        print(f"\n!! {len(skipped)} files fall outside the canvas:")
        for rel, cw, ch, w, h, x, y in skipped[:8]:
            print(f"   {cw}x{ch} -> {w}x{h} at ({x},{y})  {rel}")
        print(f"   A canvas of at least {need_w} x {need_h} would fit them.")

    if not unmatched and not skipped and not already_std:
        print("\nAll files matched an era and fit the canvas.")
        print("Spot-check one element per era against a hand-made composite.")


# ---------------------------------------------------------------- main


def main():
    """Parse the command line and run `survey` or `pad`."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="project root (default: auto-detect)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("survey", help="report content sizes for a slot")
    s.add_argument("path")
    s.add_argument("--profile", help="override profile name, e.g. helmet-right")
    s.add_argument(
        "--elements",
        action="store_true",
        help="list elements grouped by size (automatic when no profile is defined)",
    )

    p = sub.add_parser("pad", help="standardize onto the configured canvas")
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("--canvas", help="override, e.g. 2000x2300")
    p.add_argument("--profile", help="override profile name")
    p.add_argument(
        "--force",
        action="store_true",
        help="write even if the destination looks like authored artwork (no .generated marker)",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI tag written to output PNGs (default 300). Metadata only — does not resample.",
    )
    p.add_argument(
        "--anchor",
        default="top-center",
        choices=[
            "top-left",
            "top-center",
            "top-right",
            "middle-left",
            "middle-center",
            "middle-right",
        ],
        help="default top-center (jerseys, pants). Use top-left for right-facing helmets, top-right for left-facing.",
    )

    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())
    cfg = load_config(root)

    if args.cmd == "survey":
        cmd_survey(args, root, cfg)
    else:
        cmd_pad(args, root, cfg)


if __name__ == "__main__":
    main()
