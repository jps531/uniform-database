#!/usr/bin/env python3
"""
Run the GOLDEN EXAMPLE SUITE planned by golden_plan.py.

    uv run scripts/golden_run.py                   # every approved example
    uv run scripts/golden_run.py --sport soccer
    uv run scripts/golden_run.py --only football--full--03
    uv run scripts/golden_run.py --strict           # exit 1 unless every example is ok (CI)

Writes, under golden/run/
    {sport}/{view}/{id}.png      every composition
    {sport}/{view}/{id}.json     compose's structured result
    sheets/{sport}--{view}.png   one contact sheet per template, defects
                                 outlined in red
    REPORT.md                    every defect, then a per-template summary
    index.html                   all contact sheets on one page

AUTOMATIC CHECKS, run before you look at anything:

  FAILED      compose could not resolve a required placement
  CLIPPED     opaque ARTWORK runs past the view canvas. Transparent padding
              hanging over the edge is not a defect. 1-2px is reported as a
              note, not a defect — that is rounding.
  WRONG ERA   the file placed is a different era from the one planned —
              e.g. a short-sleeve jersey in a -ls view
  NUMBER      a number was asked for and a file with that number exists,
              but a different file was placed
  EXTRA TOKEN the placed file carries tokens nobody asked for while a
              plainer file with the same number exists — a ranking bug
  EMPTY       the output has no opaque pixels

What these cannot see is anything that LOOKS wrong but measures right — an
element sitting awkwardly, z-order on overlapping pieces, a scale that is
technically within bounds but visibly off. That is what the contact sheets
are for.
"""

import argparse
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

CLIP_NOTE = 2  # px of clipping treated as rounding
TOL = 5


def find_root():
    """The nearest directory at or above the cwd holding configs/view_templates.yaml; exits if none."""
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / "configs" / "view_templates.yaml").is_file():
            return d
    sys.exit("No configs/view_templates.yaml above the current directory.")


def font(size, bold=False):
    """A TrueType font for contact-sheet labels (Arial on macOS, DejaVu on Linux), else Pillow's default."""
    for f in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def measure_era(cfg, sport, slot, vp, path):
    """The era of a placed file, by its content size against each era's POST-scale size; None if unmatched or empty."""
    with ImageOps.exif_transpose(Image.open(path)).convert("RGBA") as im:
        b = im.getchannel("A").getbbox()
    if not b:
        return None
    w, h = b[2] - b[0], b[3] - b[1]
    best, dist = None, None
    for e in cfg["profiles"].get(f"{sport}-{slot}-{vp}", []):
        s = e.get("scale", 1)
        ew, eh = round(e["size"][0] * s), round(e["size"][1] * s)
        if abs(ew - w) <= TOL and abs(eh - h) <= TOL:
            d = abs(ew - w) + abs(eh - h)
            if dist is None or d < dist:
                best, dist = e["era"], d
    return best


def plainer_exists(placed, vocab_tokens):
    """Is there a file in the same element folder with the same number and
    FEWER unrequested tokens than the one placed?"""
    folder = Path(placed["file"]).parent
    el = placed["element"]
    want = set(placed["tokens_requested"])
    num = placed["number_found"]

    def toks(stem):
        """(tokens, number) found in a stem after the element name."""
        tail = stem[len(el) :] if stem.startswith(el) else stem
        found = {t for t in vocab_tokens if re.search(rf"(?:^|\s){re.escape(t)}(?:\s|$)", tail)}
        n = re.search(r"(?<![\d])(\d{1,2})(?![\d])", tail)
        return found, (n.group(1) if n else None)

    mine = len(set(placed["tokens_found"]) - want)
    for f in folder.glob("*.png"):
        t, n = toks(f.stem)
        if n == num and want <= t and len(t - want) < mine:
            return f.name
    return None


def vocab_tokens(root, sport):
    """Every non-sequence token for a sport, following `extends`, longest first."""

    def read(name, seen=frozenset()):
        """Token dict for one vocabulary file, merged over the file it `extends`; a sport's own token wins."""
        p = root / "configs" / f"modifiers_{name}.yaml"
        if name in seen or not p.is_file():
            return {}
        c = yaml.safe_load(p.open()) or {}
        base = read(c["extends"], seen | {name}) if c.get("extends") else {}
        return {**base, **(c.get("tokens") or {})}

    return sorted(
        {
            v.get("token") or v.get("label")
            for v in read(sport).values()
            if v.get("kind") != "sequence" and (v.get("token") or v.get("label"))
        },
        key=len,
        reverse=True,
    )


def check(example, result, png, cfg, vocab):
    """Run the automatic checks on one composed example.

    Returns (issues, notes): issues are defects (FAILED, EMPTY, CLIPPED, WRONG
    ERA, NUMBER, EXTRA TOKEN); notes are clipping within rounding.
    """
    issues, notes = [], []
    if result.get("missing"):
        for m in result["missing"]:
            issues.append(f"FAILED {m['label']}: {m['reason']}")
        return issues, notes
    if png and png.is_file():
        with Image.open(png) as im:
            if im.getchannel("A").getbbox() is None:
                issues.append("EMPTY output")
    expect = example.get("expect_eras", {})
    for p in result["placements"]:
        if p["status"] != "placed":
            continue
        lab = p["label"]
        over = p.get("clipped") or {}
        if over:
            worst = max(over.values())
            txt = ",".join(f"{k}{v}" for k, v in over.items())
            (issues if worst > CLIP_NOTE else notes).append(
                f"{'CLIPPED' if worst > CLIP_NOTE else 'clip (rounding)'} {lab} {txt}px"
            )
        key = f"{p['uniform']}/{p['slot']}/{p['viewpoint']}"
        if key in expect and expect[key]:
            got = measure_era(cfg, example["sport"], p["slot"], p["viewpoint"], p["file"])
            if got != expect[key]:
                issues.append(f"WRONG ERA {lab}: planned {expect[key]}, placed {got or 'unrecognised size'}")
        req = p.get("number_requested")
        if req and p["number_found"] != req:
            folder = Path(p["file"]).parent
            pat = re.compile(rf"(?<![\d]){re.escape(req)}(?![\d])")
            if any(pat.search(f.stem[len(p["element"]) :]) for f in folder.glob("*.png")):
                issues.append(
                    f"NUMBER {lab}: asked for {req}, a file exists, placed {p['number_found'] or 'unnumbered'}"
                )
        if set(p["tokens_found"]) - set(p["tokens_requested"]):
            better = plainer_exists(p, vocab)
            if better:
                issues.append(f"EXTRA TOKEN {lab}: placed {Path(p['file']).name} but plainer {better} exists")
    return issues, notes


def contact_sheet(rows, out, title):
    """rows: [(png, label_lines, has_issue)]"""
    TH, PADX, LH = 520, 40, 32
    thumbs = []
    for png, lines, bad in rows:
        if png and png.is_file():
            im = Image.open(png).convert("RGBA")
            im.thumbnail((TH, TH))
        else:
            im = Image.new("RGBA", (TH, int(TH * 0.6)), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((20, 20), "NOT RENDERED", font=font(36, True), fill=(180, 30, 30, 255))
        thumbs.append((im, lines, bad))
    cols = min(4, len(thumbs)) or 1
    cw = TH + PADX
    ch = TH + LH * 6 + PADX
    rows_n = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw + PADX, rows_n * ch + 130), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    d.text((PADX, 30), title, font=font(46, True), fill=(30, 30, 30))
    for i, (im, lines, bad) in enumerate(thumbs):
        x = PADX + (i % cols) * cw
        y = 110 + (i // cols) * ch
        bg = Image.new("RGB", (TH, TH), (238, 234, 228))
        bg.paste(im, ((TH - im.width) // 2, (TH - im.height) // 2), im)
        sheet.paste(bg, (x, y))
        d.rectangle(
            [x - 4, y - 4, x + TH + 3, y + TH + 3],
            outline=(200, 30, 30) if bad else (210, 210, 210),
            width=8 if bad else 2,
        )
        for j, ln in enumerate(lines[:6]):
            d.text(
                (x, y + TH + 10 + j * LH),
                ln[:40],
                font=font(24, j == 0),
                fill=(180, 30, 30) if (bad and j == 0) else (40, 40, 40),
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main():
    """Compose every approved manifest example, check each, and write the sheets, REPORT.md and index.html under golden/run/."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sport", action="append")
    ap.add_argument("--only", action="append", metavar="ID")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if any example has a defect OR a note, or has no result: for CI",
    )
    args = ap.parse_args()

    root = find_root()
    gold = root / "golden"
    mf = gold / "manifest.yaml"
    if not mf.is_file():
        sys.exit("No golden/manifest.yaml — run scripts/golden_plan.py first.")
    manifest = yaml.safe_load(mf.open()) or []
    cfg = yaml.safe_load((root / "configs/canvas_definitions.yaml").open())
    run = gold / "run"

    todo = [
        m
        for m in manifest
        if m.get("approved", True)
        and (not args.sport or m["sport"] in args.sport)
        and (not args.only or m["id"] in args.only)
    ]
    skipped = sum(1 for m in manifest if not m.get("approved", True))
    print(f"{len(todo)} examples to render" + (f" ({skipped} not approved, skipped)" if skipped else "") + "\n")

    vocab_cache, results = {}, []
    rendered = set()
    for i, ex in enumerate(todo, 1):
        sport, view = ex["sport"], ex["view"]
        d = run / sport / view
        png, js = d / f"{ex['id']}.png", d / f"{ex['id']}.json"
        cmd = [
            sys.executable,
            str(root / "scripts/compose.py"),
            "--root",
            str(root),
            "--sport",
            sport,
            "--view",
            view,
            "--team",
            ex["team"],
            "--out",
            str(png),
            "--json",
            str(js),
        ]
        for slot, el in (ex.get("uniform1") or {}).items():
            cmd += [f"--{slot}", el]
        for slot, el in (ex.get("uniform2") or {}).items():
            cmd += [f"--{slot}2", el]
        if ex.get("number"):
            cmd += ["--number", str(ex["number"])]
        if ex.get("number2"):
            cmd += ["--number2", str(ex["number2"])]
        for t in ex.get("with") or []:
            cmd += ["--with", t]
        if ex.get("helmet_left"):
            cmd += ["--helmet-left"]
        if png.exists():
            png.unlink()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        try:
            result = json.loads(js.read_text())
        except (OSError, ValueError):
            result = {
                "missing": [
                    {
                        "label": "compose",
                        "reason": (proc.stderr or proc.stdout).strip().splitlines()[-1]
                        if (proc.stderr or proc.stdout)
                        else "no output",
                    }
                ],
                "placements": [],
            }
        if sport not in vocab_cache:
            vocab_cache[sport] = vocab_tokens(root, sport)
        issues, notes = check(ex, result, png, cfg, vocab_cache[sport])
        rendered.add(ex["id"])
        flag = "DEFECT" if issues else ("note  " if notes else "ok    ")
        print(f"  [{i:>3}/{len(todo)}] {flag} {ex['id']}")
        for x in issues:
            print(f"                 - {x}")

    # The report and sheets cover EVERY approved example with a result on
    # disk, not just this run — so `--only` refreshes one example without
    # throwing away the other hundred.
    for ex in manifest:
        if not ex.get("approved", True):
            continue
        d = run / ex["sport"] / ex["view"]
        png, js = d / f"{ex['id']}.png", d / f"{ex['id']}.json"
        if not js.is_file():
            continue
        try:
            result = json.loads(js.read_text())
        except ValueError:
            continue
        if ex["sport"] not in vocab_cache:
            vocab_cache[ex["sport"]] = vocab_tokens(root, ex["sport"])
        issues, notes = check(ex, result, png, cfg, vocab_cache[ex["sport"]])
        results.append((ex, png, issues, notes))

    # contact sheets, one per template
    by_tpl = defaultdict(list)
    for ex, png, issues, notes in results:
        by_tpl[(ex["sport"], ex["view"])].append((ex, png, issues, notes))
    sheets = []
    for (sport, view), items in sorted(by_tpl.items()):
        rows = []
        for ex, png, issues, notes in items:
            ee = ex.get("expect_eras") or {}

            def eras(u, slot):
                """The planned eras for one slot of uniform `u`, joined with '/', for a contact-sheet label."""
                got = []
                for k, v in ee.items():
                    ku, ks, _ = k.split("/")
                    if int(ku) == u and ks == slot and v and v not in got:
                        got.append(v)
                return "/".join(got)

            num = f" {ex['number']}" if ex.get("number") else ""
            lines = [f"#{ex['id'].rsplit('--', 1)[-1]}  {ex['team']}{num}"]
            for slot, el in (ex.get("uniform1") or {}).items():
                lines.append(f"{slot} {el} [{eras(1, slot)}]")
            for slot, el in (ex.get("uniform2") or {}).items():
                lines.append(f"#2 {slot} {el} [{eras(2, slot)}]")
            if ex.get("helmet_left"):
                lines.append("+ helmet-left inset")
            if issues:
                lines[0] = "DEFECT  " + lines[0]
            rows.append((png, lines, bool(issues)))
        sp = run / "sheets" / f"{sport}--{view}.png"
        contact_sheet(rows, sp, f"{sport.replace('_', ' ')} / {view}")
        sheets.append(
            (
                sport,
                view,
                sp,
                sum(1 for *_, i, _ in [(None, None, x[2], x[3]) for x in items] if i),
            )
        )

    # report
    n_bad = sum(1 for *_, i, _ in results if i)
    lines = [
        "# Golden example suite — results",
        "",
        f"**{len(results)} examples, {n_bad} with defects.**",
        "",
        "Automatic checks cover failures, clipping, wrong eras, number "
        "resolution and token ranking. They cannot judge how a layout "
        "LOOKS — review every contact sheet below regardless of the "
        "counts.",
        "",
    ]
    if n_bad:
        lines += ["## Defects", ""]
        for ex, png, issues, notes in results:
            if issues:
                lines.append(f"### `{ex['id']}` — {ex['team']}")
                lines += [f"- {x}" for x in issues]
                lines.append("")
    noted = [(ex, n) for ex, _, i, n in results if n and not i]
    if noted:
        lines += ["## Notes (not defects)", ""]
        for ex, n in noted:
            lines.append(f"- `{ex['id']}`: " + "; ".join(n))
        lines.append("")
    lines += [
        "## By template",
        "",
        "| sport | template | examples | defects | sheet |",
        "|---|---|---|---|---|",
    ]
    for sport, view, sp, bad in sheets:
        n = len(by_tpl[(sport, view)])
        lines.append(f"| {sport} | `{view}` | {n} | {bad or ''} | [sheet](sheets/{sp.name}) |")
    (run / "REPORT.md").write_text("\n".join(lines) + "\n")

    page = [
        "<!doctype html><meta charset=utf-8><title>Golden suite</title>",
        "<style>body{font:15px -apple-system,Arial,sans-serif;margin:24px;"
        "color:#222;background:#fafafa}h2{margin-top:40px}img{max-width:100%;"
        "border:1px solid #ddd;background:#fff}.bad{color:#b22}</style>",
        f"<h1>Golden suite</h1><p>{len(results)} rendered, "
        f"<b class=bad>{n_bad} with defects</b>. Defects are outlined in red. "
        f"See <a href=REPORT.md>REPORT.md</a> for details.</p>",
    ]
    for sport, view, sp, bad in sheets:
        cls = " class=bad" if bad else ""
        page.append(
            f"<h2{cls}>{html.escape(sport)} / {html.escape(view)}"
            + (f" — {bad} defect{'s' if bad != 1 else ''}" if bad else "")
            + f"</h2><img src='sheets/{html.escape(sp.name)}' loading=lazy>"
        )
    (run / "index.html").write_text("\n".join(page))

    print(f"\n{len(rendered)} rendered this run; report covers {len(results)}, {n_bad} with defects")
    print("Review: golden/run/index.html   Details: golden/run/REPORT.md")

    if args.strict:
        # Everything must be clean: a note (1-2px clipping) fails too, and so
        # does an approved example that produced no result at all.
        n_noted = sum(1 for _, _, i, n in results if n and not i)
        have = {ex["id"] for ex, *_ in results}
        absent = [m["id"] for m in todo if m["id"] not in have]
        for x in absent:
            print(f"!! no result for {x}")
        if n_bad or n_noted or absent:
            sys.exit(f"STRICT: {n_bad} with defects, {n_noted} with notes, {len(absent)} without a result")
        print("STRICT: every example is ok")


if __name__ == "__main__":
    main()
