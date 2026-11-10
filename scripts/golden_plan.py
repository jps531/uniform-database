#!/usr/bin/env python3
"""
Plan the GOLDEN EXAMPLE SUITE: one composition per template per era, drawn
from real elements, for review before anything is rendered.

    uv run scripts/golden_plan.py            # inventory + manifest + PLAN.md
    uv run scripts/golden_plan.py --rescan   # re-measure every element

Writes
    golden/inventory.json   every element, its era per viewpoint, its numbers
    golden/manifest.yaml    the examples — EDIT THIS, then run golden_run.py
    golden/PLAN.md          the same, readable, with a coverage matrix

COVERAGE RULE. For each template, every era of every (uniform, slot,
viewpoint) it places must appear in at least one example. Examples are
chosen greedily from REAL elements, preferring the same year across slots so
a combination looks like something actually worn, and preferring elements
that have a numbered file so number resolution gets exercised too.

Each example is single-team — compose works one team at a time — so an era
that only one program has (Nike N2 jerseys, say) is covered by that program.

Eras are measured from the STANDARDIZED files, which are post-correction, so
they are matched against each era's size AFTER its scale factor.

Some templates constrain which eras may appear. Those rules are in
CONSTRAINTS below and are printed in PLAN.md so you can check them.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

SLOT_DIR = {
    "helmet": "Helmets",
    "jersey": "Jerseys",
    "pants": "Pants",
    "hat": "Hats",
    "shorts": "Shorts",
}
TOL = 5


def slug(s):
    """Directory name -> config key: lowercase, apostrophes dropped, spaces to underscores."""
    return s.lower().replace("\u2019", "").replace("'", "").replace(" ", "_")


def find_root():
    """The nearest directory at or above the cwd holding configs/view_templates.yaml; exits if none."""
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / "configs" / "view_templates.yaml").is_file():
            return d
    sys.exit("No configs/view_templates.yaml above the current directory.")


# --------------------------------------------------------------------------
# Per-template era constraints. Anything not listed here may use any era.
#   cut:    jersey era the uniform must have
#   no_cut: jersey eras the uniform must NOT have (its variant covers them)
#   keeper: True = a Keeper element, False = a field element
# --------------------------------------------------------------------------
def constraints(view, sport, names):
    """Era rules a template imposes, as {uniform: {rule: value}} (see the table above).

    `names` is every template name for the sport: a view whose `-tq` or `-ls`
    sibling exists must leave that cut to the sibling.
    """
    c = defaultdict(dict)
    if sport in ("baseball", "softball"):
        if view.endswith("-tq"):
            c[1]["cut"] = {"tq"}
        elif f"{view}-tq" in names:
            c[1]["no_cut"] = {"tq"}
    if sport == "soccer":
        if "combo" in view:
            c[1].update(keeper=False, cut={"ss"})
            c[2]["keeper"] = True
            if view.endswith("-ls"):
                c[2]["cut"] = {"ls"}
            elif f"{view}-ls" in names:
                c[2]["cut"] = {"ss"}
        elif view.endswith("-ls"):
            c[1]["cut"] = {"ls"}
        elif f"{view}-ls" in names:
            c[1]["no_cut"] = {"ls"}
    if sport == "volleyball":
        m = re.search(r"-(ss|ls)-(ss|ls)$", view)
        if m:
            c[1]["cut"] = {m.group(1)}
            c[2]["cut"] = {m.group(2)}
    return c


def describe(c):
    """One readable line of a template's constraints, for PLAN.md; empty when there are none."""
    out = []
    for u in sorted(c):
        bits = []
        if "cut" in c[u]:
            bits.append("jersey " + "/".join(sorted(c[u]["cut"])) + " only")
        if "no_cut" in c[u]:
            bits.append("no " + "/".join(sorted(c[u]["no_cut"])) + " jerseys")
        if "keeper" in c[u]:
            bits.append("keeper jersey" if c[u]["keeper"] else "field jersey")
        if bits:
            out.append(f"uniform {u}: " + ", ".join(bits))
    return "; ".join(out)


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
def era_for(cfg, sport, slot, vp, size):
    """The era whose POST-scale size is closest to `size` within TOL, or None.

    Post-scale because the inventory measures standardized files, whose
    correction is already baked in.
    """
    best, dist = None, None
    for e in cfg["profiles"].get(f"{sport}-{slot}-{vp}", []):
        s = e.get("scale", 1)
        w, h = round(e["size"][0] * s), round(e["size"][1] * s)
        if abs(w - size[0]) <= TOL and abs(h - size[1]) <= TOL:
            d = abs(w - size[0]) + abs(h - size[1])
            if dist is None or d < dist:
                best, dist = e["era"], d
    return best


def content_size(path):
    """[width, height] of the file's opaque bounding box; the full image size if it is fully transparent."""
    with ImageOps.exif_transpose(Image.open(path)).convert("RGBA") as im:
        b = im.getchannel("A").getbbox()
        return [b[2] - b[0], b[3] - b[1]] if b else list(im.size)


def numbers_in(stems, element):
    """Every 1-2 digit number in the stems after the element name, as strings, shortest then lexical."""
    out = set()
    for s in stems:
        tail = s[len(element) :] if s.startswith(element) else s
        for m in re.finditer(r"(?<![\d])(\d{1,2})(?![\d])", tail):
            out.add(m.group(1))
    return sorted(out, key=lambda n: (len(n), n))


def build_inventory(root, cfg, sports):
    """Measure every element of the given sports: its year, whether it is a keeper, and per viewpoint
    the era, content size, numbers and file count.

    Reads one file per element per viewpoint (the unnumbered one when it
    exists). Returns {sport: {team: {slot: {element: record}}}}.
    """
    inv = {}
    dirs = {slug(d.name): d for d in root.iterdir() if d.is_dir()}
    for sport in sports:
        sd = dirs.get(sport)
        if not sd:
            continue
        for team_dir in sorted(p for p in sd.iterdir() if p.is_dir()):
            for slot, sdir in SLOT_DIR.items():
                for vp_dir in sorted(team_dir.glob(f"{sdir} *")):
                    vp = vp_dir.name.split()[-1].lower()
                    for el_dir in sorted(p for p in vp_dir.iterdir() if p.is_dir()):
                        files = sorted(f for f in el_dir.glob("*.png") if not f.name.startswith("."))
                        if not files:
                            continue
                        el = el_dir.name
                        stems = [f.stem for f in files]
                        nums = numbers_in(stems, el)
                        plain = [f for f in files if f.stem == el]
                        sample = (plain or files)[0]
                        size = content_size(sample)
                        rec = (
                            inv.setdefault(sport, {})
                            .setdefault(team_dir.name, {})
                            .setdefault(slot, {})
                            .setdefault(
                                el,
                                {
                                    "year": int(el[:4]) if el[:4].isdigit() else None,
                                    "keeper": "Keeper" in el.split(),
                                    "vps": {},
                                },
                            )
                        )
                        rec["vps"][vp] = {
                            "era": era_for(cfg, sport, slot, vp, size),
                            "size": size,
                            "numbers": nums,
                            "files": len(files),
                        }
    return inv


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------
COLORWAYS = []
PAIRINGS = {}  # (sport, team, element) -> {slot: element} worn together


def colorway(el):
    """'2026 Blue Keeper' -> 'blue'. Longest match first, so 'Vegas Gold'
    is not read as 'Gold'."""
    rest = el[5:] if el[:4].isdigit() else el
    for c in COLORWAYS:
        if rest.lower() == c or rest.lower().startswith(c + " "):
            return c
    return rest.split()[0].lower() if rest else ""


def plan_template(tpl, names, inv, cfg):
    """Choose the examples that cover every era of every viewpoint one template places.

    Greedy: each round anchors on the first uncovered target and builds the
    most realistic uniform around it from one team. Returns (examples,
    explicit extras, coverage targets, uncoverable targets, constraints).
    """
    sport, view = tpl["sport"], tpl["view_kind"]
    cons = constraints(view, sport, names)
    # (uniform, slot) -> viewpoints this template places. REQUIRED ones decide
    # whether an element is eligible; `if_available` ones are covered when an
    # element has them but never rule an element out. Treating them as
    # required silently dropped every team without a sleeve view — Jones's
    # Nike N2 jerseys never became a target at all.
    need, optional = defaultdict(list), defaultdict(list)
    explicit = []
    for p in tpl["placements"]:
        key = (p.get("uniform", 1), p["slot"])
        req = p.get("requirement", "required")
        if req == "explicit":
            explicit.append((key, p["viewpoint"]))
        elif req == "if_available":
            optional[key].append(p["viewpoint"])
        else:
            need[key].append(p["viewpoint"])
    for key in optional:
        need.setdefault(key, [])
    teams = inv.get(sport, {})

    def allowed(team, u, slot, el):
        """Whether an element may fill this (uniform, slot): it has every required viewpoint and meets the template's constraints."""
        rec = teams[team][slot][el]
        if any(vp not in rec["vps"] for vp in need[(u, slot)]):
            return False
        c = cons.get(u, {})
        if slot == "jersey":
            eras = {rec["vps"][vp]["era"] for vp in need[(u, slot)]}
            if "cut" in c and not eras <= c["cut"]:
                return False
            if "no_cut" in c and eras & c["no_cut"]:
                return False
        # KEEPER applies to the JERSEY only. Keepers wear the regular shorts —
        # there are no Keeper shorts elements at all — so applying it to shorts
        # made uniform 2 impossible and every soccer combo planned ZERO examples.
        if "keeper" in c and slot == "jersey" and rec["keeper"] != c["keeper"]:
            return False
        return True

    # every (u, slot, vp, era) reachable somewhere — the coverage target
    targets, reach = set(), defaultdict(list)
    for team in teams:
        for (u, slot), vps in need.items():
            for el in teams[team].get(slot, {}):
                if not allowed(team, u, slot, el):
                    continue
                for vp in vps + optional[(u, slot)]:
                    if vp not in teams[team][slot][el]["vps"]:
                        continue
                    era = teams[team][slot][el]["vps"][vp]["era"]
                    t = (u, slot, vp, era)
                    targets.add(t)
                    reach[t].append((team, el))

    # Every era present in the inventory for a slot this template uses, before
    # any eligibility filtering. Anything here that never becomes a target is
    # a SILENT gap — it must be reported, not quietly skipped.
    present = set()
    for team in teams:
        for (u, slot), vps in need.items():
            for el, rec in teams[team].get(slot, {}).items():
                c = cons.get(u, {})
                eras = {rec["vps"][v]["era"] for v in vps if v in rec["vps"]}
                if slot == "jersey" and (
                    ("cut" in c and not eras <= c["cut"]) or ("no_cut" in c and eras & c["no_cut"])
                ):
                    continue
                if "keeper" in c and slot == "jersey" and rec["keeper"] != c["keeper"]:
                    continue
                for v in vps:
                    if v in rec["vps"] and rec["vps"][v]["era"]:
                        present.add((u, slot, v, rec["vps"][v]["era"]))
    silent = sorted(present - targets)

    covered, examples = set(), []
    unmatched = sorted(t for t in targets if t[3] is None)
    targets = {t for t in targets if t[3] is not None}

    def covers(team, u, slot, el):
        """The (uniform, slot, viewpoint, era) targets this element would cover."""
        rec = teams[team][slot][el]
        return {
            (u, slot, vp, rec["vps"][vp]["era"]) for vp in need[(u, slot)] + optional[(u, slot)] if vp in rec["vps"]
        }

    def score(team, u, slot, el, year, chosen=None):
        """Sort key for an element in a slot, higher better: realism (known pairing, same name, same colour
        and year) before new coverage, then numbered files.
        """
        rec = teams[team][slot][el]
        new = len(covers(team, u, slot, el) - covered)
        # uniform 2 should differ from uniform 1, or a combo shows one kit twice
        same = 1 if (u == 2 and chosen and chosen.get((1, slot)) == el) else 0
        vps_here = need[(u, slot)] + optional[(u, slot)]
        probe = rec["vps"].get("back") or next((rec["vps"][v] for v in vps_here if v in rec["vps"]), None)
        numbered = 1 if probe and probe["numbers"] else 0
        # REALISM FIRST, coverage second. Ranking on coverage first built
        # uniforms nobody wore — a 1958 jersey under a 2025 helmet — which test
        # the geometry fine but make real defects harder to spot in review.
        # Every example still covers its anchor era, so nothing goes uncovered;
        # it just takes a few more examples.
        # The reference for this slot is the SAME UNIFORM's lead element: the
        # anchor if it belongs to this uniform, otherwise this uniform's
        # jersey. Comparing uniform 2 against uniform 1 gave a blue keeper
        # green shorts because the maroon field kit had already taken blue.
        ref = None
        if chosen:
            a_u, a_el = chosen.get("_anchor_u"), chosen.get("_anchor")
            # The JERSEY defines a uniform, so it leads. Following the anchor
            # instead paired the 2015 wool fauxback with 2026 pants, because
            # the anchor was a 2026 hat — while 2015 Natural Wool pants existed.
            ref = chosen.get((u, "jersey")) or (
                a_el
                if a_u == u
                else next(
                    (v for k, v in chosen.items() if isinstance(k, tuple) and k[0] == u),
                    None,
                )
            )
        same_name = 1 if ref and el == ref else 0
        # A KNOWN pairing beats every heuristic. Filenames cannot say that the
        # 2015 wool fauxback was worn with the "2015 Maroon Fauxback" hat —
        # different words, no shared token — so golden/pairings.yaml does.
        paired = 1 if ref and PAIRINGS.get((sport, team, ref), {}).get(slot) == el else 0
        ref_year = teams[team][slot].get(ref, {}).get("year") if ref and ref in teams[team][slot] else None
        if ref and ref_year is None:
            for sl in teams[team]:
                if ref in teams[team][sl]:
                    ref_year = teams[team][sl][ref]["year"]
                    break
        gap = abs((rec["year"] or 0) - (ref_year or year or 0)) if (ref_year or year) else 0
        # same colourway counts only within a few seasons — a 2026 jersey with
        # 1990 shorts of the same colour is still a costume, not a uniform
        hue = 1 if ref and colorway(el) == colorway(ref) and gap <= 3 else 0
        return (paired, same_name, -same, hue, -gap, new, numbered, rec["year"] or 0)

    while targets - covered:
        anchor = sorted(targets - covered)[0]
        best = None
        for team, el in reach[anchor]:
            u0, slot0 = anchor[0], anchor[1]
            year = teams[team][slot0][el]["year"]
            chosen, gained = {"_anchor": el, "_anchor_u": u0}, set()
            ok = True
            for u, slot in sorted(need, key=lambda k: (k[0], k[1] != "jersey", k[1])):
                if (u, slot) == (u0, slot0):
                    pick = el
                else:
                    cands = [e for e in teams[team].get(slot, {}) if allowed(team, u, slot, e)]
                    if not cands:
                        ok = False
                        break
                    pick = max(cands, key=lambda e: score(team, u, slot, e, year, chosen))
                chosen[(u, slot)] = pick
                gained |= covers(team, u, slot, pick)
            if not ok:
                continue
            picks = [v for k, v in chosen.items() if isinstance(k, tuple)]
            years = [int(v[:4]) for v in picks if v[:4].isdigit()]
            spread = (max(years) - min(years)) if years else 0
            lead = {u: chosen.get((u, "jersey")) for u, _ in need}
            same = sum(
                1
                for (u, sl), v in ((k, v) for k, v in chosen.items() if isinstance(k, tuple))
                if lead.get(u) and (v == lead[u] or PAIRINGS.get((sport, team, lead[u]), {}).get(sl) == v)
            )
            # every candidate covers the anchor, so choose the most REAL uniform
            # first and the most extra coverage second
            key = (
                same,
                -spread,
                len(gained - covered),
                team == "Mississippi State",
                year or 0,
            )
            if best is None or key > best[0]:
                best = (key, team, chosen, gained)
        if best is None:
            # nothing can host this target with all slots filled
            unmatched.append(anchor)
            targets.discard(anchor)
            continue
        _, team, chosen, gained = best
        chosen.pop("_anchor", None)
        chosen.pop("_anchor_u", None)
        covered |= gained
        examples.append((team, chosen, gained))

    # explicit placements (e.g. the helmet-left inset) — one example each
    extras = []
    for key, vp in explicit:
        if examples:
            team, chosen, _ = examples[0]
            el = chosen.get(key)
            if el and vp in teams[team][key[1]][el]["vps"]:
                extras.append((team, chosen, {"explicit": f"{key[1]}/{vp}"}))
    return examples, extras, sorted(targets), unmatched + silent, cons


def pick_number(rec, need_vps):
    """A number to request for this element: the first one on the back view, else on a needed viewpoint, else None."""
    for vp in ("back", *need_vps):
        if vp in rec["vps"] and rec["vps"][vp]["numbers"]:
            return rec["vps"][vp]["numbers"][0]
    return None


def main():
    """Build or reuse the inventory, plan every template, and write golden/manifest.yaml and golden/PLAN.md.

    Overwrites the manifest; durable choices belong in golden/pairings.yaml.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rescan", action="store_true")
    ap.add_argument("--sport", action="append", help="limit to these sports (repeatable)")
    args = ap.parse_args()

    root = find_root()
    cfg = yaml.safe_load((root / "configs/canvas_definitions.yaml").open())
    gp = root / "configs/slots_global.yaml"
    if gp.is_file():
        g = yaml.safe_load(gp.open()) or {}
        names_ = set()
        for k, v in (g.get("colorways") or {}).items():
            names_.add(str(k).replace("_", " ").lower())
            if isinstance(v, dict):
                for alt in (v.get("token"), v.get("label")):
                    if alt:
                        names_.add(alt.lower())
        COLORWAYS[:] = sorted(names_, key=len, reverse=True)

    pp = root / "golden" / "pairings.yaml"
    if pp.is_file():
        n = 0
        for sport_, teams_ in (yaml.safe_load(pp.open()) or {}).items():
            for team_, groups in (teams_ or {}).items():
                for g in groups or []:
                    for slot_, el_ in g.items():
                        PAIRINGS[(sport_, team_, el_)] = {k: v for k, v in g.items() if k != slot_}
                    n += 1
        print(f"pairings: {n} known uniform{'s' if n != 1 else ''} from golden/pairings.yaml")
    tpls = yaml.safe_load((root / "configs/view_templates.yaml").open())["templates"]
    if args.sport:
        tpls = [t for t in tpls if t["sport"] in args.sport]
    sports = sorted({t["sport"] for t in tpls})
    out = root / "golden"
    out.mkdir(exist_ok=True)

    invp = out / "inventory.json"
    if invp.is_file() and not args.rescan:
        inv = json.loads(invp.read_text())
        # Sizes are cached; eras are NOT trusted from the cache. Re-resolve
        # them against the profiles as they stand now, so a profile fix takes
        # effect without re-measuring every file.
        moved = 0
        for sport, teams in inv.items():
            for team in teams.values():
                for slot, els in team.items():
                    for rec in els.values():
                        for vp, v in rec["vps"].items():
                            era = era_for(cfg, sport, slot, vp, v["size"])
                            moved += era != v["era"]
                            v["era"] = era
        print(
            f"inventory: reusing {invp.relative_to(root)} (--rescan to refresh)"
            + (f" — {moved} eras re-resolved against current profiles" if moved else "")
        )
    else:
        print(
            "inventory: measuring every element — this reads one file per "
            "element per viewpoint, so it takes a minute or two..."
        )
        inv = build_inventory(root, cfg, sports)
        invp.write_text(json.dumps(inv, indent=1))
    n_el = sum(len(e) for s in inv.values() for t in s.values() for e in t.values())
    print(f"           {n_el} element-slots across {len(inv)} sports\n")

    by_sport = defaultdict(list)
    for t in tpls:
        by_sport[t["sport"]].append(t)

    manifest, plan_md = [], []
    gaps_total = 0
    empty = []
    for sport in sports:
        names = {t["view_kind"] for t in by_sport[sport]}
        plan_md.append(f"\n## {sport.replace('_', ' ').title()}\n")
        for tpl in by_sport[sport]:
            view = tpl["view_kind"]
            examples, extras, targets, unmatched, cons = plan_template(tpl, names, inv, cfg)
            teams = inv.get(sport, {})
            need_vps = defaultdict(list)
            for p in tpl["placements"]:
                need_vps[(p.get("uniform", 1), p["slot"])].append(p["viewpoint"])

            if not examples:
                empty.append(f"{sport} / {view}")
            plan_md.append(
                f"### `{view}` — {len(examples)} example"
                f"{'s' if len(examples) != 1 else ''}" + (f" + {len(extras)} explicit" if extras else "")
            )
            if describe(cons):
                plan_md.append(f"_Constraint: {describe(cons)}_\n")
            plan_md.append("| # | team | elements | eras covered |")
            plan_md.append("|---|---|---|---|")
            all_rows = [(e, False) for e in examples] + [(e, True) for e in extras]
            for i, ((team, chosen, gained), is_extra) in enumerate(all_rows, 1):
                ex_id = f"{sport}--{view}--{i:02d}"
                els, number = {1: {}, 2: {}}, {1: None, 2: None}
                expect = {}
                for (u, slot), el in chosen.items():
                    els[u][slot] = el
                    rec = teams[team][slot][el]
                    for vp in need_vps[(u, slot)]:
                        if vp in rec["vps"]:
                            expect[f"{u}/{slot}/{vp}"] = rec["vps"][vp]["era"]
                    if slot == "jersey" and number[u] is None:
                        number[u] = pick_number(rec, need_vps[(u, slot)])
                entry = {
                    "id": ex_id,
                    "approved": True,
                    "sport": sport,
                    "view": view,
                    "team": team,
                    "uniform1": els[1],
                    "number": number[1],
                    "expect_eras": expect,
                }
                if els[2]:
                    entry["uniform2"] = els[2]
                    entry["number2"] = number[2]
                if is_extra:
                    entry["helmet_left"] = True
                    entry["note"] = f"exercises the explicit {gained['explicit']} placement"
                else:
                    entry["covers"] = sorted(f"#{u} {s}/{v} {e}" for u, s, v, e in gained)
                manifest.append(entry)

                desc = "<br>".join(
                    f"{'#2 ' if u == 2 else ''}{s}: {el}" + (f" **{number[u]}**" if s == "jersey" and number[u] else "")
                    for (u, s), el in sorted(chosen.items())
                )
                cov = (
                    ("_explicit: " + gained["explicit"] + "_")
                    if is_extra
                    else ", ".join(f"{'#2 ' if u == 2 else ''}{s} {v} **{e}**" for u, s, v, e in sorted(gained))
                )
                plan_md.append(f"| {i} | {team} | {desc} | {cov} |")
            if unmatched:
                gaps_total += len(unmatched)
                plan_md.append("\n**Not coverable** — no team has an element that fits every slot of this template:")
                for u, s, v, e in unmatched:
                    plan_md.append(f"- {'#2 ' if u == 2 else ''}{s}/{v} era `{e or 'UNMATCHED SIZE'}`")
            plan_md.append("")

    (out / "manifest.yaml").write_text(
        "# Golden example suite. Set `approved: false` on any example to skip\n"
        "# it, edit elements or numbers freely, or add your own entries.\n"
        "# Then: python3 scripts/golden_run.py\n\n" + yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    )

    n_tpl = len(tpls)
    head = [
        "# Golden example suite — plan",
        "",
        f"**{len(manifest)} examples across {n_tpl} templates and "
        f"{len(sports)} sports.** Every era of every viewpoint each template "
        "places appears in at least one example, drawn from real elements.",
        "",
        "Review this, edit `golden/manifest.yaml` (set `approved: false` to "
        "skip an example, or change any element), then run:",
        "",
        "    python3 scripts/golden_run.py",
        "",
        "How examples are chosen: greedily, so each one covers as many "
        "uncovered eras as possible; within a team, elements from the same "
        "year are preferred so a combination looks like one actually worn; "
        "elements with numbered files are preferred so number resolution is "
        "exercised. Explicit placements (the football helmet-left inset) get "
        "one extra example each.",
    ]
    if empty:
        head += [
            "",
            f"## ⚠ {len(empty)} template{'s' if len(empty) != 1 else ''} have NO examples",
            "",
            "Nothing in these will be rendered or checked. Usually a template constraint no element satisfies:",
            "",
        ] + [f"- `{e}`" for e in empty]
    if gaps_total:
        head += [
            "",
            f"**{gaps_total} era targets could not be covered** — "
            "listed under each template. Usually a slot with no element "
            "on the same team, or a size no profile recognises.",
        ]
    (out / "PLAN.md").write_text("\n".join(head + plan_md) + "\n")

    per = defaultdict(int)
    for m in manifest:
        per[m["sport"]] += 1
    print(f"{len(manifest)} examples across {n_tpl} templates")
    for s in sports:
        print(f"   {s:<20} {per[s]:>4}")
    if empty:
        print(f"\n!! {len(empty)} templates have NO examples: " + ", ".join(empty))
    if gaps_total:
        print(f"\n!! {gaps_total} era targets not coverable — see golden/PLAN.md")
    print("\nWrote golden/manifest.yaml and golden/PLAN.md — review, then python3 scripts/golden_run.py")


if __name__ == "__main__":
    main()
