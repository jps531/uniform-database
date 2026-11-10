#!/usr/bin/env python3
"""
Standardize element PNGs onto fixed canvases.

Reads canvas sizes and era corrections from configs/canvas_definitions.yaml,
so this script holds no per-era knowledge of its own.

    uv sync

    # inspect a slot before configuring it
    uv run scripts/pipeline/standardize.py survey "Football/Mississippi State/Helmets Right"

    # authored source: pad into a "… STD" sibling, check it, then replace
    uv run scripts/pipeline/standardize.py pad \\
        "Football/Mississippi State/Jerseys Front" \\
        "Football/Mississippi State/Jerseys Front STD"

    # generated helmets: pad the native-scale Marks into the .generated tree
    uv run scripts/pipeline/standardize.py pad \\
        "Marks/Football/Mississippi State/Helmets Right" \\
        "Football/Mississippi State/Helmets Right"

Paths may be absolute, or relative to the project root (the directory
containing configs/). The DESTINATION path determines which canvas and
profile apply: "Football/<Team>/Jerseys Front" -> sport=football,
slot=jersey, viewpoint=front.

Overrides for a slot not yet in the config (profiles are keyed
{sport}-{slot}-{viewpoint}):
    --canvas 1792x2044 --profile football-jersey-front

Content is matched to the CLOSEST era within the config's `tolerance`
(smallest |dw| + |dh|; ties to the first listed), as every script does.
Files are placed top-centre, the `--anchor` default, unless their era sets
an `anchor`.

`pad` exits 1 if ANY file was not written for a reason other than being
already standardized or fully transparent — a file matching no era, or one
falling outside its canvas — after writing the rest and reporting them all.
So `pad SRC DEST && rm -rf SRC` stops before deleting unwritten artwork.

`survey` suggests a canvas by the canvas rule: the largest POST-SCALE
content, plus 1px each side on a centred axis and none against an anchored
edge. Not headroom: padding exists to put every era at one placement.
"""

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

from common import (
    DPI,
    MARKER,
    add_root_arg,
    alpha_box,
    load_config,
    match_era,
    open_rgba,
    pngs,
    resolve,
    root_from,
    scaled_eras,
    sport_slug,
    standard_canvases,
    tolerance,
)

# ---------------------------------------------------------------- config


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
    view = parse_view(sport, parts[2], cfg)
    if view is None:
        return None
    return sport, parts[1], *view


def parse_view(sport: str, name: str, cfg: dict):
    """A viewpoint directory name -> (slot, viewpoint) for `sport`, or None if its first word is not a slot.

    'Jerseys Front' and 'Jerseys Front STD' both give (jersey, front): the
    viewpoint is the first later word declared for that sport+slot in
    `assignments`, not the last word.
    """
    words = name.split()
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
    return slot, viewpoint


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


def measure(img: Image.Image):
    """(bbox, (width, height)) of an open RGBA image's opaque content, or (None, None) if fully transparent."""
    box = alpha_box(img)
    if box is None:
        return None, None
    return box, (box[2] - box[0], box[3] - box[1])


def fit_extent(anchor: str, extent: int, offset: int):
    """Smallest canvas side that holds `extent` px of content at `anchor` ('start', 'end' or 'centre') plus `offset`.

    Mirrors pad's placement. An anchored axis needs no margin: content sits
    on that edge. A centred axis gets 1px each side, the canvas rule (largest
    post-scale content plus 1px each side). None when the offset pushes the
    content past the anchored edge, which no canvas size can fix.
    """
    if anchor == "start":
        return extent + offset if offset >= 0 else None
    if anchor == "end":
        return extent - offset if offset <= 0 else None
    side = extent + 2
    while (side - extent) // 2 + offset < 1 or (side - extent) // 2 + offset + extent > side - 1:
        side += 1
    return side


def placement(anchor: str, era: dict, width: int, height: int, w: int, h: int):
    """(x, y) of w x h content on a width x height canvas at `anchor`, plus the era's dx/dy."""
    if anchor.endswith("left"):
        x = 0
    elif anchor.endswith("right"):
        x = width - w
    else:
        x = (width - w) // 2
    y = 0 if anchor.startswith("top") else (height - h) // 2
    return x + int(era.get("dx", 0)), y + int(era.get("dy", 0))


def canvas_hint(skipped) -> list:
    """Lines saying, per canvas, the smallest canvas that fits every skipped file at its anchor.

    `skipped` holds pad's (rel, cw, ch, w, h, x, y, anchor, era, canvas name,
    width, height) for each file that fell outside its canvas.
    """
    need, lines = {}, []
    for rel, _, _, w, h, _, _, anchor, era, name, width, height in skipped:
        if anchor.endswith("left"):
            hx = "start"
        elif anchor.endswith("right"):
            hx = "end"
        else:
            hx = "centre"
        hy = "start" if anchor.startswith("top") else "centre"
        fw = fit_extent(hx, w, int(era.get("dx", 0)))
        fh = fit_extent(hy, h, int(era.get("dy", 0)))
        if fw is None or fh is None:
            lines.append(f"   No canvas fits {rel}: its era's dx/dy pushes it past the anchored edge.")
            continue
        # "At least" the current canvas too: the files that fit still have to.
        nw, nh = need.get(name, (width, height))
        need[name] = (max(nw, fw), max(nh, fh))
    for name, (nw, nh) in sorted(need.items()):
        lines.append(f"   A canvas of at least {nw} x {nh} would fit them ({name}).")
    return lines


def sizes_text(sizes) -> str:
    """'40 x 30' or '40 x 30 or 60 x 30': canvas sizes for a message, smallest first."""
    return " or ".join(f"{w} x {h}" for w, h in sorted(sizes))


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
        with open_rgba(f) as img:
            box, cs = measure(img)
            if cs is None:
                continue
            sizes[cs] += 1
            if box != (0, 0, *img.size):
                margined.append((f.relative_to(src), img.size, box))

    print(f"{len(files)} PNGs under {src.name}")
    if not sizes:
        # Nothing to measure, so nothing below means anything — and the
        # largest-content line would call max() on an empty list.
        print(f"No file has opaque content: all {len(files)} PNGs are fully transparent.")
        return
    parsed = parse_dest(src, root, cfg)
    canvas, profile = None, None
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
    tol = tolerance(cfg)
    for (w, h), n in sizes.most_common():
        era = match_era(profile, (w, h), tol) if profile else None
        if era:
            tag = f"  -> era {era['era']}"
        elif profile:
            tag = "  -> UNMATCHED"
        else:
            tag = ""
        print(f"  {w:>5} x {h:<5}  {n:>4} files{tag}")

    if profile is None or args.elements:
        # Group elements by size so eras can be assigned by inspection.
        by_size = {}
        for f in files:
            with open_rgba(f) as img:
                _, cs = measure(img)
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
        std = 0
        for f in files:
            with Image.open(f) as im:
                std += im.size == (cw_, ch_)
        if std == len(files):
            print(f"\nNOTE: every file is already {cw_} x {ch_} — this is standardized OUTPUT, not source artwork.")
            print("Sizes above are post-correction, so era A will read as UNMATCHED (it lists pre-correction sizes).")
            print("Survey the original tree to check era coverage.")

    maxw = max(w for w, _ in sizes)
    maxh = max(h for _, h in sizes)
    print(f"\nLargest content: {maxw} x {maxh}")
    # The canvas rule: the largest POST-SCALE content plus 1px each side on a
    # centred axis, none against an anchored edge (fit_extent, as pad places
    # it). Padding puts every era at one placement; it is not headroom.
    # ~12% headroom was tried and reversed: it cost football_jersey 21% of
    # its area.
    post = []
    for w, h in sizes:
        e = (match_era(profile, (w, h), tol) if profile else None) or {}
        s = float(e.get("scale", 1.0))
        pw, ph = (round(w * s), round(h * s)) if not math.isclose(s, 1.0) else (w, h)
        anchor = e.get("anchor", "top-center")
        if anchor.endswith("left"):
            hx = "start"
        elif anchor.endswith("right"):
            hx = "end"
        else:
            hx = "centre"
        hy = "start" if anchor.startswith("top") else "centre"
        post.append((pw, ph, fit_extent(hx, pw, int(e.get("dx", 0))), fit_extent(hy, ph, int(e.get("dy", 0)))))
    print(f"Largest content after era scale: {max(p[0] for p in post)} x {max(p[1] for p in post)}")
    fits = [p for p in post if p[2] is not None and p[3] is not None]
    if fits:
        print(
            f"Suggested canvas: {max(p[2] for p in fits)} x {max(p[3] for p in fits)}"
            " (largest post-scale content, +1px each side on a centred axis)"
        )
    if len(fits) < len(post):
        print("   Some sizes fit no canvas: their era's dx/dy pushes them past the anchored edge.")
    if profile is None:
        print(
            "\nNo profile yet. Add one to configs/canvas_definitions.yaml "
            "under `profiles:`, declaring each era explicitly."
        )


def cmd_pad(args, root, cfg):
    """Standardize authored source into DEST: crop to content, apply the era's scale, pad onto the canvas.

    Writes immediately, and writes a .generated marker into DEST. Refuses a
    DEST of authored PNGs without a marker (unless --force), and refuses
    source that is already standardized: files on the slot canvas or on any
    canvas an era of the profile overrides it with, or whose content matches
    what an era's scale produces. The marker's `canvas` is the slot canvas;
    `era_canvases` lists any era canvas a written file sits on.

    Exits 1 if any file was left unwritten for any reason other than being
    already standardized or fully transparent (it matched no era, or fell
    outside its canvas), after reporting everything, so `pad && rm -rf SRC`
    cannot lose artwork.
    """
    src = resolve(args.src, root)
    dest = resolve(args.dest, root)
    if not src.is_dir():
        sys.exit(f"Not a directory: {src}")
    if dest == src:
        sys.exit("Destination must differ from source.")

    tol = tolerance(cfg)
    canvas = profile = cn = None
    parsed = parse_dest(dest, root, cfg)
    if parsed:
        sport, _team, slot, viewpoint = parsed
        canvas, profile, (cn, pn) = lookup(cfg, sport, slot, viewpoint)
        label = f"{sport}/{slot}/{viewpoint}  canvas={cn} profile={pn}"
    else:
        label = "(path not recognized — using overrides)"

    if args.canvas:
        w, h = (int(v) for v in args.canvas.lower().split("x"))
        canvas = {"width": w, "height": h}
        cn = "--canvas"
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
    # Every canvas this profile can place a file on: the slot canvas, plus
    # each one an era overrides it with. A file already sitting on ANY of them
    # has been through this pipeline. Checking only the canvas of the file's
    # own era would need the era to match first, and standardized content
    # need not match one (a profile re-measured after a restyle); checking
    # only the canvas the previous file used made the result depend on file
    # order, so a standard jersey sorted after a three-quarter one was padded
    # again. Erring this way can only skip a file and report it, never
    # re-pad one.
    #
    # `fills: fill` canvases are left out. There the canvas IS the content
    # size, so authored source cropped to its content is already canvas-sized
    # and the check can't tell source from output. Re-padding output there is
    # harmless unless an era scales, and scaled output is refused above by
    # the post-correction check, which runs first.
    on_canvas = standard_canvases(cfg, canvas, profile)
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
    corrected = scaled_eras(profile)

    # Two passes. Pass 1 measures and classifies EVERY file and decides where
    # each one goes; nothing is written. Pass 2 writes, and only runs once
    # the refusals below have had their say. Checking for post-correction
    # input after writing left a partially written destination behind a
    # message claiming "Nothing written".
    placed, unmatched, skipped = Counter(), [], []
    already_std = Counter()
    era_canvases = {}
    post_correction = []
    plan = []
    blank = 0  # fully transparent: nothing to measure, so never counted as source or output
    for f in files:
        rel = f.relative_to(src)
        with open_rgba(f) as img:
            iw, ih = img.size
            box, cs = measure(img)
        if cs is None:
            blank += 1
            continue

        hit = match_era(corrected, cs, tol, post_scale=True)
        if hit is not None:
            post_correction.append((rel, cs, hit["era"]))
            continue

        # A file whose CANVAS already equals a target has been through this
        # pipeline too, even if its era carries no scale correction.
        if (iw, ih) in on_canvas:
            already_std[(iw, ih)] += 1
            continue

        cw, ch = cs

        era = match_era(profile, cs, tol)
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
            name, width, height = ec, oc["width"], oc["height"]
        else:
            name, width, height = cn, base_width, base_height

        s = float(era.get("scale", 1.0))
        w, h = (round(cw * s), round(ch * s)) if not math.isclose(s, 1.0) else (cw, ch)
        anchor = era.get("anchor", args.anchor)
        x, y = placement(anchor, era, width, height, w, h)

        if x < 0 or y < 0 or x + w > width or y + h > height:
            skipped.append((rel, cw, ch, w, h, x, y, anchor, era, name, width, height))
            continue

        if ec:
            era_canvases[ec] = f"{width}x{height}"
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

    measured = len(files) - blank
    plural = "" if blank == 1 else "s"
    ignored = f" ({blank} fully transparent file{plural} ignored)" if blank else ""
    if not measured:
        sys.exit(f"{label}\nNo file has opaque content: all {len(files)} PNGs are fully transparent.\nNothing written.")
    # Judged on files with content: a blank file must not let standardized
    # output past this refusal.
    if already_std.total() == measured:
        sys.exit(
            f"{label}\n"
            f"All {measured} files are ALREADY {sizes_text(already_std)}{ignored}.\n"
            "This looks like standardized output, not source artwork. "
            "Re-padding would re-apply era scale corrections a second "
            "time.\nNothing written. Point `src` at the original tree."
        )

    # Pass 2: every refusal has passed, so write.
    for f, rel, box, era, s, cw, ch, w, h, x, y, cvw, cvh in plan:
        with open_rgba(f) as src_img:
            img = src_img.crop(box)
            if not math.isclose(s, 1.0):
                img = img.resize((w, h), Image.Resampling.LANCZOS)
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

    # The marker claims "this tree is generated from that source". With
    # nothing written there is no such tree, so leave no marker (or folder).
    if plan:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / MARKER).write_text(
            json.dumps(
                {
                    "generated_by": "scripts/pipeline/standardize.py",
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "source": str(src),
                    # The slot canvas, always; any era canvas a written file
                    # sits on instead is listed beside it.
                    "canvas": f"{base_width}x{base_height}",
                    "era_canvases": dict(sorted(era_canvases.items())),
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
    print(f"canvas {base_width} x {base_height}, anchor {args.anchor}")
    for ec, size in sorted(era_canvases.items()):
        print(f"era canvas {ec} {size.replace('x', ' x ')}")
    print(f"Wrote {sum(placed.values())} of {len(files)} files to {dest}\n")
    print(f"{'era':>8}  {'content':>14}  {'after scale':>14}  {'canvas':>13}  {'placed at':>13}  files")
    for (era, cw, ch, w, h, x, y, cvw, cvh), n in sorted(placed.items()):
        print(f"{str(era):>8}  {cw:>6} x {ch:<5}  {w:>6} x {h:<5}  {cvw:>5} x {cvh:<5}  ({x:>5}, {y:>4})  {n:>5}")

    if already_std:
        print(f"\n!! {already_std.total()} files were SKIPPED — already {sizes_text(already_std)}.")
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
        print(f"\n!! {len(skipped)} files fall outside the canvas:")
        for rel, cw, ch, w, h, x, y, *_ in skipped[:8]:
            print(f"   {cw}x{ch} -> {w}x{h} at ({x},{y})  {rel}")
        # Sized from the content and its anchor, not from x + w: centring
        # makes x negative for content wider than the canvas, so x + w came
        # out no bigger than the canvas that had just failed.
        for line in canvas_hint(skipped):
            print(line)

    if not unmatched and not skipped and not already_std:
        print("\nAll files matched an era and fit the canvas.")
        print("Spot-check one element per era against a hand-made composite.")

    if blank:
        print(
            f"\n{blank} fully transparent file{'s' if blank != 1 else ''} had nothing to pad and {'were' if blank != 1 else 'was'} skipped."
        )
    if not plan:
        sys.exit("\nNothing written: no file both matched an era and fit its canvas. No destination or marker created.")
    # Exit non-zero whenever authored source was left behind, so that
    # `pad SRC DEST && rm -rf SRC` can't lose it. Already-standardized and
    # blank files are not "left behind": they have nothing to pad.
    if unmatched or skipped:
        sys.exit(
            f"\n!! {len(unmatched) + len(skipped)} files were NOT written "
            f"({len(unmatched)} matched no era, {len(skipped)} fell outside the canvas). Keep the source."
        )


# ---------------------------------------------------------------- main


def main():
    """Parse the command line and run `survey` or `pad`."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_root_arg(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("survey", help="report content sizes for a slot")
    s.add_argument("path")
    s.add_argument("--profile", help="override profile name, e.g. football-helmet-right")
    s.add_argument(
        "--elements",
        action="store_true",
        help="list elements grouped by size (automatic when no profile is defined)",
    )

    p = sub.add_parser("pad", help="standardize onto the configured canvas")
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("--canvas", help="override, e.g. 1792x2044")
    p.add_argument("--profile", help="override profile name")
    p.add_argument(
        "--force",
        action="store_true",
        help="write even if the destination looks like authored artwork (no .generated marker)",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=DPI,
        help=f"DPI tag written to output PNGs (default {DPI}). Metadata only — does not resample.",
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
        help="default top-center, which every slot uses, helmets included (corner-anchored helmets were "
        "tried and reversed). An era's own `anchor` overrides it.",
    )

    args = ap.parse_args()
    root = root_from(args)
    cfg = load_config(root)

    if args.cmd == "survey":
        cmd_survey(args, root, cfg)
    else:
        cmd_pad(args, root, cfg)


if __name__ == "__main__":
    main()
