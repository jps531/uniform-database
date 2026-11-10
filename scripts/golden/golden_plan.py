#!/usr/bin/env python3
"""
Plan the GOLDEN EXAMPLE SUITE: one composition per template per era, drawn
from real elements, for review before anything is rendered.

    uv run scripts/golden/golden_plan.py                  # inventory + manifest + PLAN.md
    uv run scripts/golden/golden_plan.py --rescan         # re-measure every element
    uv run scripts/golden/golden_plan.py --sport soccer   # re-plan one sport, keep the rest

Writes
    golden/inventory.json   every element, its era per viewpoint, its numbers,
                            and which sports it covers
    golden/manifest.yaml    the examples, then run golden_run.py. Edits
                            here last until the next plan, which
                            OVERWRITES it; durable knowledge (uniforms worn
                            together) goes in golden/pairings.yaml
    golden/PLAN.md          the same, readable: per template, a table of
                            its examples and the eras each covers, then any
                            era targets it could not cover

--sport (repeatable) re-plans ONLY those sports: their entries in the
existing manifest.yaml and their sections of PLAN.md are replaced, and every
other sport's are kept as they are, hand edits included. (It used to write a
manifest of just those sports, and a later golden_fixture.py --apply then
deleted every other sport's fixture.) PLAN.md's header totals are recounted
across all of them.

The inventory is a cache. It records the sports it was measured for; a plan
that needs a sport it doesn't cover measures that sport and adds it, so an
inventory written by a --sport run is never reused as if it were complete.
--rescan re-measures the sports being planned (all, or the --sport ones)
and keeps the rest.

COVERAGE RULE. For each template, every era of every (uniform, slot,
viewpoint) it places must appear in at least one example. Examples are
chosen greedily from REAL elements, preferring the same year across slots so
a combination looks like something actually worn, and preferring elements
that have a numbered file so number resolution gets exercised too.

Each example is single-team — compose works one team at a time — so an era
that only one program has (Nike N2 jerseys, say) is covered by that program.

Eras are measured from the STANDARDIZED files, which are post-correction, so
they are matched against each era's size AFTER its scale factor: the
CLOSEST within the config's `tolerance`, as every script matches eras.

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
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

# Filenames are parsed exactly as compose parses them, so the planner never
# asks for a number compose would not find.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from common import (  # noqa: E402
    add_root_arg,
    content_size,
    known_colorways,
    load_config,
    load_yaml,
    longest_first,
    match_era,
    pngs,
    root_from,
    slot_dirs,
    sport_dir,
    tolerance,
)
from compose import load_vocab, split_tail  # noqa: E402

# The header golden/manifest.yaml is written with. A re-plan reproduces it,
# warning included.
MANIFEST_HEADER = """\
# Golden example suite. Set `approved: false` on any example to skip
# it, edit elements or numbers freely, or add your own entries.
# Then: uv run scripts/golden/golden_run.py
#
# WARNING: golden_plan.py OVERWRITES this file. Edits here last only until
# the next plan; uniforms known to be worn together belong in
# golden/pairings.yaml, which the planner reads.

"""


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
    """The era whose POST-scale size is closest to `size` within the config's tolerance, or None.

    Post-scale because the inventory measures standardized files, whose
    correction is already baked in. A fully transparent file has no size
    (None) and no era.
    """
    if size is None:
        return None
    e = match_era(cfg["profiles"].get(f"{sport}-{slot}-{vp}"), size, tolerance(cfg), post_scale=True)
    return e["era"] if e else None


def numbers_in(stems, element, vocab_tokens):
    """The number in each stem, parsed as compose does, as strings, shortest then lexical.

    Vocabulary tokens are stripped before the number is read, so a patch
    token ending in digits (CWS21, SEC75) is not taken for number 21 or 75.
    """
    nums = {split_tail(s, element, vocab_tokens)[1] for s in stems}
    return sorted((n for n in nums if n is not None), key=lambda n: (len(n), n))


def build_inventory(root, cfg, sports):
    """Measure every element of the given sports: its year, whether it is a keeper, and per viewpoint
    the era, content size, numbers and file count.

    Reads one file per element per viewpoint (the unnumbered one when it
    exists). Returns {sport: {team: {slot: {element: record}}}}.
    """
    inv = {}
    for sport in sports:
        sd = sport_dir(root, sport)
        if not sd:
            continue
        vocab = load_vocab(root, sport)[0]
        for team_dir in sorted(p for p in sd.iterdir() if p.is_dir()):
            for slot, sdir in slot_dirs(cfg).items():
                for vp_dir in sorted(team_dir.glob(f"{sdir} *")):
                    vp = vp_dir.name.split()[-1].lower()
                    for el_dir in sorted(p for p in vp_dir.iterdir() if p.is_dir()):
                        files = pngs(el_dir, recursive=False)
                        if not files:
                            continue
                        el = el_dir.name
                        stems = [f.stem for f in files]
                        nums = numbers_in(stems, el, vocab)
                        plain = [f for f in files if f.stem == el]
                        sample = (plain or files)[0]
                        size = content_size(sample)
                        size = list(size) if size else None  # as JSON stores it
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


def load_pairings(root):
    """golden/pairings.yaml as {(sport, team, element): {slot: element}}: what each element was worn with.

    Empty when the file is missing. Prints how many uniforms it holds.
    """
    pairings = {}
    pp = root / "golden" / "pairings.yaml"
    if pp.is_file():
        n = 0
        for sport_, teams_ in (load_yaml(pp) or {}).items():
            for team_, groups in (teams_ or {}).items():
                for g in groups or []:
                    for slot_, el_ in g.items():
                        pairings[(sport_, team_, el_)] = {k: v for k, v in g.items() if k != slot_}
                    n += 1
        print(f"pairings: {n} known uniform{'s' if n != 1 else ''} from golden/pairings.yaml")
    return pairings


def colorway(el, colorways):
    """'2026 Blue Keeper' -> 'blue', given the known colorways longest first, so 'Vegas Gold'
    is not read as 'Gold'."""
    rest = el[5:] if el[:4].isdigit() else el
    for c in colorways:
        if rest.lower() == c or rest.lower().startswith(c + " "):
            return c
    return rest.split()[0].lower() if rest else ""


def plan_template(tpl, names, inv, pairings, colorways):
    """Choose the examples that cover every era of every viewpoint one template places.

    Greedy: each round anchors on the first uncovered target and builds the
    most realistic uniform around it from one team. `pairings` is
    load_pairings()'s, `colorways` the known colorways longest first. Returns
    (examples, explicit extras, coverage targets, uncoverable targets,
    constraints).
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
        paired = 1 if ref and pairings.get((sport, team, ref), {}).get(slot) == el else 0
        ref_year = teams[team][slot].get(ref, {}).get("year") if ref and ref in teams[team][slot] else None
        if ref and ref_year is None:
            for sl in teams[team]:
                if ref in teams[team][sl]:
                    ref_year = teams[team][sl][ref]["year"]
                    break
        gap = abs((rec["year"] or 0) - (ref_year or year or 0)) if (ref_year or year) else 0
        # same colourway counts only within a few seasons — a 2026 jersey with
        # 1990 shorts of the same colour is still a costume, not a uniform
        hue = 1 if ref and colorway(el, colorways) == colorway(ref, colorways) and gap <= 3 else 0
        return (paired, same_name, -same, hue, -gap, new, numbered, rec["year"] or 0)

    while targets - covered:
        anchor = min(targets - covered)
        best = None
        for team, el in reach[anchor]:
            u0, slot0 = anchor[0], anchor[1]
            year = teams[team][slot0][el]["year"]
            chosen: dict = {"_anchor": el, "_anchor_u": u0}
            gained = set()
            ok = True
            for u, slot in sorted(need, key=lambda k: (k[0], k[1] != "jersey", k[1])):
                if (u, slot) == (u0, slot0):
                    pick = el
                else:
                    cands = [e for e in teams[team].get(slot, {}) if allowed(team, u, slot, e)]
                    if not cands:
                        ok = False
                        break
                    pick = max(cands, key=lambda e, u=u, slot=slot: score(team, u, slot, e, year, chosen))
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
                if lead.get(u) and (v == lead[u] or pairings.get((sport, team, lead[u]), {}).get(sl) == v)
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


def load_inventory(root, cfg, sports, rescan):
    """The inventory for `sports`: cached where golden/inventory.json covers them, measured where it doesn't.

    The file is {"sports": [...], "elements": {sport: ...}}. One written
    before coverage was recorded is a bare {sport: ...} and counts as
    covering exactly the sports it holds. With `rescan`, `sports` are
    measured again; any other cached sport is kept. Writes the file back
    whenever anything was measured.
    """
    invp = root / "golden" / "inventory.json"
    inv, covered = {}, set()
    if invp.is_file():
        raw = json.loads(invp.read_text())
        if isinstance(raw.get("sports"), list) and isinstance(raw.get("elements"), dict):
            inv, covered = raw["elements"], set(raw["sports"])
        else:
            inv, covered = raw, set(raw)
    todo = sorted(set(sports) if rescan else set(sports) - covered)
    reused = sorted(set(sports) - set(todo))
    if reused:
        # Sizes are cached; eras are NOT trusted from the cache. Re-resolve
        # them against the profiles as they stand now, so a profile fix takes
        # effect without re-measuring every file.
        moved = 0
        for sport in reused:
            for team in inv.get(sport, {}).values():
                for slot, els in team.items():
                    for rec in els.values():
                        for vp, v in rec["vps"].items():
                            era = era_for(cfg, sport, slot, vp, v["size"])
                            moved += era != v["era"]
                            v["era"] = era
        print(
            f"inventory: reusing {invp.relative_to(root)} for {', '.join(reused)} (--rescan to refresh)"
            + (f" — {moved} eras re-resolved against current profiles" if moved else "")
        )
    if todo:
        why = "--rescan" if rescan else f"not in {invp.relative_to(root)}"
        print(
            f"inventory: measuring {', '.join(todo)} ({why}) — this reads one file per "
            "element per viewpoint, so it takes a minute or two..."
        )
        for sport in todo:
            inv.pop(sport, None)
        inv.update(build_inventory(root, cfg, todo))
        covered |= set(todo)
        invp.write_text(json.dumps({"sports": sorted(covered), "elements": inv}, indent=1))
    return {sport: inv[sport] for sport in sports if sport in inv}


def sport_title(sport):
    """A sport slug as PLAN.md heads its section: mens_basketball -> Mens Basketball."""
    return sport.replace("_", " ").title()


def plan_sections(text, sports):
    """Split an existing PLAN.md into its per-sport sections, keyed by slug, each as PLAN.md holds it.

    A section runs from its `## {Sport}` heading to the next sport's heading
    or the end. Anything before the first is the header, which is rebuilt.
    """
    titles = {f"## {sport_title(sp)}": sp for sp in sports}
    lines = text.removesuffix("\n").split("\n")  # the one newline main() adds after the last section
    starts = [i for i, line in enumerate(lines) if line in titles and i > 0 and lines[i - 1] == ""]
    out = {}
    for a, b in zip(starts, [*starts[1:], len(lines) + 1], strict=True):
        out[titles[lines[a]]] = "\n".join(lines[a - 1 : b - 1])
    return out


def section_stats(sport, section):
    """(templates, empty templates, uncoverable era targets) read back from one PLAN.md section."""
    tpl = empty = gaps = 0
    names = []
    for line in section.split("\n"):
        if line.startswith("### `"):
            tpl += 1
            if " — 0 examples" in line:
                empty += 1
                names.append(f"{sport} / {line.split('`')[1]}")
        elif line.startswith("- "):
            gaps += 1
    return tpl, names if empty else [], gaps


def main():
    """Build or reuse the inventory, plan every template, and write golden/manifest.yaml and golden/PLAN.md.

    Overwrites the manifest; durable choices belong in golden/pairings.yaml.
    With --sport, only those sports' entries and PLAN.md sections are
    replaced; every other sport's are kept.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_root_arg(ap)
    ap.add_argument("--rescan", action="store_true")
    ap.add_argument("--sport", action="append", help="limit to these sports (repeatable)")
    args = ap.parse_args()

    root = root_from(args)
    cfg = load_config(root)
    colorways = longest_first(known_colorways(root))
    pairings = load_pairings(root)
    tpls = load_yaml(root / "configs/view_templates.yaml")["templates"]
    all_sports = sorted({t["sport"] for t in tpls})
    if args.sport:
        unknown = sorted(set(args.sport) - set(all_sports))
        if unknown:
            sys.exit(f"No templates for sport: {', '.join(unknown)}\nSports with templates: {', '.join(all_sports)}")
        tpls = [t for t in tpls if t["sport"] in args.sport]
    sports = sorted({t["sport"] for t in tpls})
    out = root / "golden"
    out.mkdir(exist_ok=True)

    inv = load_inventory(root, cfg, sports, args.rescan)
    n_el = sum(len(e) for s in inv.values() for t in s.values() for e in t.values())
    print(f"           {n_el} element-slots across {len(inv)} sports\n")

    by_sport = defaultdict(list)
    for t in tpls:
        by_sport[t["sport"]].append(t)

    manifest, sections = [], {}
    for sport in sports:
        names = {t["view_kind"] for t in by_sport[sport]}
        plan_md = sections[sport] = []
        plan_md.append(f"\n## {sport_title(sport)}\n")
        for tpl in by_sport[sport]:
            view = tpl["view_kind"]
            examples, extras, _targets, unmatched, cons = plan_template(tpl, names, inv, pairings, colorways)
            teams = inv.get(sport, {})
            need_vps = defaultdict(list)
            for p in tpl["placements"]:
                need_vps[(p.get("uniform", 1), p["slot"])].append(p["viewpoint"])

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
                plan_md.append("\n**Not coverable** — no team has an element that fits every slot of this template:")
                for u, s, v, e in unmatched:
                    plan_md.append(f"- {'#2 ' if u == 2 else ''}{s}/{v} era `{e or 'UNMATCHED SIZE'}`")
            plan_md.append("")

    # Join each sport's section; with --sport, keep the others' from the
    # existing manifest and PLAN.md. Order is by sport, as a full plan writes.
    text = {sp: "\n".join(lines) for sp, lines in sections.items()}
    selected = len(manifest)
    kept_examples = []
    if args.sport:
        mp, pp_ = out / "manifest.yaml", out / "PLAN.md"
        old = (load_yaml(mp) or []) if mp.is_file() else []
        kept_examples = [m for m in old if m.get("sport") not in sports]
        others = set(all_sports) - set(sports)
        # Split on EVERY sport's heading, so a kept section never swallows
        # the stale section of a sport being re-planned.
        old_sections = plan_sections(pp_.read_text(), all_sports) if pp_.is_file() else {}
        old_sections = {sp: t for sp, t in old_sections.items() if sp in others}
        text.update(old_sections)
        manifest = sorted(kept_examples + manifest, key=lambda m: m.get("sport", ""))
        if kept_examples:
            kept_sports = sorted({m.get("sport", "") for m in kept_examples})
            print(
                f"kept {len(kept_examples)} example{'s' if len(kept_examples) != 1 else ''} "
                f"for other sports: {', '.join(kept_sports)}"
            )
            missing = [sp for sp in kept_sports if sp not in old_sections]
            if missing:
                print(f"!! PLAN.md had no section for {', '.join(missing)}: re-plan without --sport to restore it")
    order = sorted(text)
    n_tpl, empty, gaps_total = 0, [], 0
    for sp in order:
        t, e, g = section_stats(sp, text[sp])
        n_tpl += t
        empty += e
        gaps_total += g

    (out / "manifest.yaml").write_text(MANIFEST_HEADER + yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))

    head = [
        "# Golden example suite — plan",
        "",
        f"**{len(manifest)} examples across {n_tpl} templates and "
        f"{len(order)} sports.** Every era of every viewpoint each template "
        "places appears in at least one example, drawn from real elements.",
        "",
        "Review this, edit `golden/manifest.yaml` (set `approved: false` to "
        "skip an example, or change any element), then run:",
        "",
        "    uv run scripts/golden/golden_run.py",
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
    (out / "PLAN.md").write_text("\n".join(head + [text[sp] for sp in order]) + "\n")

    # The summary covers the sports planned in this run.
    per = defaultdict(int)
    for m in manifest:
        per[m["sport"]] += 1
    mine = [section_stats(sp, text[sp]) for sp in sports]
    print(f"{selected} examples across {len(tpls)} templates")
    for sp in sports:
        print(f"   {sp:<20} {per[sp]:>4}")
    my_empty = [n for _, e, _ in mine for n in e]
    my_gaps = sum(g for *_, g in mine)
    if my_empty:
        print(f"\n!! {len(my_empty)} templates have NO examples: " + ", ".join(my_empty))
    if my_gaps:
        print(f"\n!! {my_gaps} era targets not coverable — see golden/PLAN.md")
    print("\nWrote golden/manifest.yaml and golden/PLAN.md — review, then uv run scripts/golden/golden_run.py")


if __name__ == "__main__":
    main()
