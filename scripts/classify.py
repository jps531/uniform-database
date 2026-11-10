#!/usr/bin/env python3
"""
Classify files as RAW, OLD-STANDARDIZED or NEW-STANDARDIZED.

Two independent signals:

  CANVAS size  — which standardization pass wrote the file, if any.
  CONTENT size — whether an era's scale correction has been APPLIED. This is
                 the one that matters: a correction baked in once cannot be
                 detected later except by comparing against the profile, and
                 applying it twice is what destroyed era A.

    RAW          content matches an era's PRE-scale size; canvas hugs content
    OLD-STD      canvas matches a previous canvas size (see WAS below)
    NEW-STD      canvas matches the current canvas
    SCALED       content matches an era's POST-scale size — correction applied
    UNSCALED     content matches an era's PRE-scale size — correction pending

    python3 scripts/classify.py Football temp
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("pip install pillow pyyaml")

# Canvas sizes BEFORE the minimal-padding pass. Anything still at one of
# these was written by the earlier standardization.
WAS = {
    "football_jersey": (2000, 2300),
    "football_helmet_face": (750, 900),
    "baseball_hat": (3030, 2460),
    "diamond_jersey": (1800, 1960),
    "diamond_jersey_tq": (2140, 1960),
    "diamond_pants": (950, 1960),
    "mbk_jersey": (1280, 1950),
    "mbk_shorts": (920, 1790),
    "wbk_jersey": (1265, 1940),
    "wbk_shorts": (865, 775),
    "soccer_jersey": (2290, 2880),
    "soccer_jersey_ls": (2800, 3010),
    "soccer_shorts": (800, 560),
    "volleyball_jersey": (2290, 2770),
    "volleyball_jersey_ls": (2810, 3010),
}
TOL = 5


def slug(s):
    return s.lower().replace("\u2019", "").replace("'", "").replace(" ", "_")


def near(a, b):
    return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL


def main():
    root = Path(".")
    for d in [root, *Path.cwd().parents]:
        if (d / "configs" / "canvas_definitions.yaml").is_file():
            root = d
            break
    cfg = yaml.safe_load((root / "configs/canvas_definitions.yaml").open())
    C, A, P = cfg["canvases"], cfg["assignments"], cfg["profiles"]
    dir_slot = cfg["directory_slots"]
    args = sys.argv[1:]
    # temp/{Team}/{Viewpoint} has no sport segment, so allow an explicit one.
    fallback = None
    if "--sport" in args:
        i = args.index("--sport")
        fallback = slug(args[i + 1])
        del args[i : i + 2]
    targets = args or ["."]

    groups = defaultdict(Counter)
    for base in targets:
        for f in sorted((root / base).rglob("*.png")):
            if f.name.startswith("."):
                continue
            parts = f.relative_to(root).parts
            # temp/{Sport}/... and temp/{Team}/... both occur; find the
            # viewpoint directory by looking for a known slot word.
            vp_i = next(
                (i for i, x in enumerate(parts) if x.split() and x.split()[0] in dir_slot),
                None,
            )
            if vp_i is None:
                continue
            view = parts[vp_i]
            words = view.split()
            slot, vp = dir_slot[words[0]], words[-1].lower()
            sport = next((slug(x) for x in parts[:vp_i] if slug(x) in A), None)
            if sport is None:
                sport = fallback
            if sport is None:
                continue
            cname = (A.get(sport) or {}).get(slot, {}).get(vp)
            if not cname:
                continue

            with ImageOps.exif_transpose(Image.open(f)).convert("RGBA") as im:
                canvas = im.size
                b = im.getchannel("A").getbbox()
            content = (b[2] - b[0], b[3] - b[1]) if b else (0, 0)

            # which canvas is this sitting on
            now = (C[cname]["width"], C[cname]["height"])
            alts = {e["canvas"] for e in P.get(f"{sport}-{slot}-{vp}", []) if e.get("canvas")}
            new_sizes = [now] + [(C[a]["width"], C[a]["height"]) for a in alts]
            old_sizes = [WAS[k] for k in [cname, *alts] if k in WAS]
            if any(near(canvas, s) for s in new_sizes):
                where = "NEW-STD"
            elif any(near(canvas, s) for s in old_sizes):
                where = "OLD-STD"
            elif near(canvas, content):
                where = "RAW"
            else:
                where = f"? {canvas[0]}x{canvas[1]}"

            # has the era scale been applied to the pixels
            pre = post = None
            for e in P.get(f"{sport}-{slot}-{vp}", []):
                s = e.get("scale", 1)
                if near(content, tuple(e["size"])):
                    pre = e["era"]
                if s != 1 and near(content, (round(e["size"][0] * s), round(e["size"][1] * s))):
                    post = e["era"]
            if post:
                how = f"SCALED (era {post})"
            elif pre:
                e = next(x for x in P[f"{sport}-{slot}-{vp}"] if x["era"] == pre)
                how = (
                    f"UNSCALED (era {pre}, needs x{e['scale']})"
                    if e.get("scale", 1) != 1
                    else f"era {pre}, no correction"
                )
            else:
                how = "NO ERA MATCH"

            groups[(base, sport, parts[vp_i - 1], view)][(where, how, f"{content[0]}x{content[1]}")] += 1

    for key in sorted(groups):
        base, sport, team, view = key
        print(f"\n{base}  {team} / {view}")
        for (where, how, content), n in sorted(groups[key].items(), key=lambda x: -x[1]):
            flag = "  <-- CANNOT RE-PAD" if how.startswith("SCALED") else ""
            print(f"   {n:>4}  {where:<9} content {content:<12} {how}{flag}")


if __name__ == "__main__":
    main()
