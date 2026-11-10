#!/usr/bin/env python3
"""
Derive cropped renditions from their authored source, driven by config.

Any canvas in canvas_definitions.yaml carrying a `derived_from` block is
built by this script:

    football_field_cropped:
      width: 3432
      height: 1597
      derived_from:
        canvas: football_field_full
        crop_at: [108, 287]

The source VIEWPOINT is resolved from `assignments` by finding which
viewpoint of the same sport+slot uses the source canvas. So adding
basketball_court_cropped or baseball_field_cropped needs no code change.

    pip install pillow pyyaml

    python3 scripts/derive_crops.py                 # dry run, all sports
    python3 scripts/derive_crops.py --apply
    python3 scripts/derive_crops.py --sport football --apply

Reads from the AUTHORED tree (e.g. Fields Full) and writes the derived one
(Fields Cropped) with a .generated marker. Never reads from temp/ — staging
gets cleared, and this must stay re-runnable.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("pip install pillow pyyaml")

DPI = 300


def find_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            return d
    sys.exit(f"No configs/canvas_definitions.yaml above {start}")


def jobs_for(cfg, sport_filter):
    """Yield (sport, slot, src_viewpoint, dst_viewpoint, canvas_src, canvas_dst)."""
    canvases, assignments = cfg["canvases"], cfg.get("assignments", {})
    for sport, slots in assignments.items():
        if sport_filter and sport != sport_filter:
            continue
        for slot, views in slots.items():
            for vp, cname in views.items():
                c = canvases.get(cname) or {}
                d = c.get("derived_from")
                if not d:
                    continue
                src_canvas = d["canvas"]
                src_vp = next((v for v, n in views.items() if n == src_canvas), None)
                if src_vp is None:
                    yield (
                        "ERROR",
                        sport,
                        slot,
                        vp,
                        f"no viewpoint of {sport}/{slot} uses {src_canvas}",
                    )
                    continue
                yield (
                    "OK",
                    sport,
                    slot,
                    src_vp,
                    vp,
                    canvases[src_canvas],
                    c,
                    tuple(d["crop_at"]),
                )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--sport")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())
    cfg = yaml.safe_load((root / "configs" / "canvas_definitions.yaml").open())
    dir_for_slot = {v: k for k, v in cfg["directory_slots"].items()}

    rules = list(jobs_for(cfg, args.sport))
    errs = [r for r in rules if r[0] == "ERROR"]
    rules = [r for r in rules if r[0] == "OK"]
    for _, sport, slot, vp, why in errs:
        print(f"!! {sport}/{slot}/{vp}: {why}")
    if not rules:
        sys.exit(
            "No canvases carry a `derived_from` block" + (f" for sport '{args.sport}'" if args.sport else "") + "."
        )

    total, problems, per_rule = [], [], []
    for _, sport, slot, src_vp, dst_vp, csrc, cdst, (cx, cy) in rules:
        sdir = dir_for_slot.get(slot)
        if not sdir:
            problems.append((f"{sport}/{slot}", "slot missing from directory_slots"))
            continue
        # Playing surfaces live under Venues/; uniforms under the sport root.
        cand = [
            root / "Venues" / sport.replace("_", " ").title(),
            root / sport.replace("_", " ").title(),
        ]
        sport_dir = next((d for d in cand if d.is_dir()), cand[0])
        cw, ch = cdst["width"], cdst["height"]
        sw, sh = csrc["width"], csrc["height"]
        if cx + cw > sw or cy + ch > sh:
            problems.append((f"{sport}/{slot}/{dst_vp}", "crop box falls outside the source canvas"))
            continue
        print(f"{sport}/{slot}: {sdir} {src_vp.title()} -> {sdir} {dst_vp.title()}")
        print(
            f"   crop {cw}x{ch} from ({cx}, {cy}) of {sw}x{sh}"
            f"   margins {cx}/{sw - cx - cw} horizontal, {cy}/{sh - cy - ch} vertical"
        )

        found = []
        if sport_dir.is_dir():
            for team_dir in sorted(d for d in sport_dir.iterdir() if d.is_dir()):
                src = team_dir / f"{sdir} {src_vp.title()}"
                if not src.is_dir():
                    continue
                dst = team_dir / f"{sdir} {dst_vp.title()}"
                for f in sorted(src.rglob("*.png")):
                    if f.name.startswith("."):
                        continue
                    with Image.open(f) as im:
                        size = im.size
                    if size != (sw, sh):
                        problems.append(
                            (
                                str(f.relative_to(root)),
                                f"{size[0]}x{size[1]}, expected {sw}x{sh}",
                            )
                        )
                        continue
                    found.append((f, dst / f.relative_to(src), (cx, cy, cw, ch)))
                per_rule.append((dst, len(found)))
        print(f"   {len(found)} files\n")
        total += found

    if problems:
        print(f"!! {len(problems)} problems:")
        for a, b in problems[:15]:
            print(f"     {a}  ({b})")
        print()

    if not args.apply:
        print(f"DRY RUN — {len(total)} files would be written. Re-run with --apply.")
        return
    if problems:
        sys.exit("Refusing to apply while problems remain.")

    for s, d, (cx, cy, cw, ch) in total:
        d.parent.mkdir(parents=True, exist_ok=True)
        with ImageOps.exif_transpose(Image.open(s)).convert("RGBA") as im:
            im.crop((cx, cy, cx + cw, cy + ch)).save(d, dpi=(DPI, DPI))
    for dst, n in per_rule:
        if not n:
            continue
        dst.mkdir(parents=True, exist_ok=True)
        (dst / ".generated").write_text(
            json.dumps(
                {
                    "generated_by": "scripts/derive_crops.py",
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "files_written": n,
                    "note": "Generated output. Regenerate from the source viewpoint rather than editing by hand.",
                },
                indent=2,
            )
            + "\n"
        )
    print(f"Wrote {len(total)} files.")


if __name__ == "__main__":
    main()
