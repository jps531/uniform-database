"""Tests for scripts/golden/golden_plan.py: inventory, era resolution, greedy coverage, constraints and outputs."""

import argparse
import json
import sys

import common
import golden_plan as gp
import pytest
import yaml
from helpers import REPO, art, canvas_size, era, override_configs, scaled

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


# The known colorways, longest first, that the planning tests pass in.
COLORWAYS = ["vegas gold", "maroon", "white", "gold", "gray", "blue", "natural"]


def post(cfg, key, name):
    """The POST-scale [w, h] of one era of a profile."""
    return list(scaled(era(cfg, key, name)))


def rec(cfg, sport, slot, name, vps, numbers=None):
    """An inventory record for element `name` whose viewpoints have the given eras (None = unrecognised size)."""
    numbers = numbers or {}
    out = {"year": int(name[:4]) if name[:4].isdigit() else None, "keeper": "Keeper" in name.split(), "vps": {}}
    for vp, e in vps.items():
        size = post(cfg, f"{sport}-{slot}-{vp}", e) if e else [3, 3]
        out["vps"][vp] = {"era": e, "size": size, "numbers": list(numbers.get(vp, [])), "files": 1}
    return out


def tpl(templates, view):
    """One real template by view_kind."""
    return next(t for t in templates if t["view_kind"] == view)


def names(templates, sport):
    """Every real view_kind for a sport."""
    return {t["view_kind"] for t in templates if t["sport"] == sport}


def plan(templates, cfg, view, inv, pairings=None):
    """Run plan_template on a real template against a crafted inventory, with these known pairings (default none)."""
    t = tpl(templates, view)
    return gp.plan_template(t, names(templates, t["sport"]), inv, pairings or {}, COLORWAYS)


def picks(examples):
    """Each example as (team, {(u, slot): element})."""
    return [(team, dict(chosen)) for team, chosen, _ in examples]


def reduced_configs(project, templates, views, **files):
    """Keep only the named templates in the project's configs, and override any other `files` (helpers.override_configs)."""
    keep = [t for t in templates if t["view_kind"] in views]
    override_configs(project, {"view_templates.yaml": {"templates": keep}, **files})


def run_main(monkeypatch, *argv):
    """Call golden_plan.main() with the given arguments."""
    monkeypatch.setattr(sys, "argv", ["golden_plan.py", *argv])
    gp.main()


# --------------------------------------------------------------------------
# small functions
# --------------------------------------------------------------------------


def test_find_root_exits_without_configs(tmp_path, monkeypatch):
    """main() exits when no configs/canvas_definitions.yaml is above the cwd."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch)
    assert "No configs/canvas_definitions.yaml" in str(e.value)


def test_find_root_from_a_subdirectory(project, monkeypatch):
    """Without --root the project is found by walking up from a subdirectory."""
    (project / "a" / "b").mkdir(parents=True)
    monkeypatch.chdir(project / "a" / "b")
    assert common.root_from(argparse.Namespace(root=None)) == project


def test_era_for_uses_post_scale_size(cfg):
    """A standardized helmet is matched at its era's size AFTER scale, and its pre-scale size matches nothing."""
    a = era(cfg, "football-helmet-right", "F")
    assert gp.era_for(cfg, "football", "helmet", "right", post(cfg, "football-helmet-right", "F")) == "F"
    assert gp.era_for(cfg, "football", "helmet", "right", a["size"]) is None


def test_era_for_tolerance_and_nearest(cfg):
    """Within 5px matches, 6px does not, and the closest of two candidates wins (E vs E2 helmet backs)."""
    e = post(cfg, "football-helmet-back", "E")
    e2 = post(cfg, "football-helmet-back", "E2")
    assert gp.era_for(cfg, "football", "helmet", "back", [e[0] + 1, e[1]]) == "E"
    assert gp.era_for(cfg, "football", "helmet", "back", [e2[0] - 1, e2[1]]) == "E2"
    assert gp.era_for(cfg, "football", "helmet", "back", [e[0] + 3, e[1]]) == "E"
    w = post(cfg, "football-pants-left", "all")
    assert gp.era_for(cfg, "football", "pants", "left", [w[0] + 5, w[1]]) == "all"
    assert gp.era_for(cfg, "football", "pants", "left", [w[0] + 6, w[1]]) is None
    assert gp.era_for(cfg, "nosport", "pants", "left", w) is None


def test_content_size_bbox_and_transparent(tmp_path):
    """content_size() is the opaque bbox, or None when nothing is opaque."""
    p = art(tmp_path / "a.png", (40, 30), (10, 7), top=2)
    assert gp.content_size(p) == (10, 7)
    from PIL import Image

    q = tmp_path / "b.png"
    Image.new("RGBA", (12, 9), (0, 0, 0, 0)).save(q)
    assert gp.content_size(q) is None


def test_numbers_in_opaque_strings_sorted():
    """Numbers are strings after the element name, '03' distinct from '3', shortest then lexical."""
    stems = ["2015 White", "2015 White 03", "2015 White 3", "2015 White 19 Grad", "Other 7"]
    assert gp.numbers_in(stems, "2015 White", ["Grad"]) == ["3", "7", "03", "19"]
    assert gp.numbers_in(["2015 White 85s"], "2015 White 85s", []) == []


def test_numbers_in_strips_patch_tokens_ending_in_digits():
    """CWS21 and SEC75 are patch tokens, not numbers: vocabulary tokens are stripped first, as compose does."""
    vocab = gp.load_vocab(REPO, "baseball")[0]
    assert {"CWS21", "SEC75"} <= set(vocab)
    assert gp.numbers_in(["2021 White", "2021 White CWS21"], "2021 White", vocab) == []
    assert gp.numbers_in(["2021 White 7 CWS21", "2021 White SEC75 18 Girodo"], "2021 White", vocab) == ["7", "18"]


def test_constraints_and_describe(templates):
    """Each template family gets the documented era rule, and describe() renders it."""
    bb, sc, vb = names(templates, "baseball"), names(templates, "soccer"), names(templates, "volleyball")
    c = gp.constraints("baseball-full-tq", "baseball", bb)
    assert c[1] == {"cut": {"tq"}}
    assert gp.describe(c) == "uniform 1: jersey tq only"
    c = gp.constraints("baseball-full", "baseball", bb)
    assert c[1] == {"no_cut": {"tq"}}
    assert gp.describe(c) == "uniform 1: no tq jerseys"
    assert gp.constraints("softball-full", "softball", names(templates, "softball")) == {}
    assert gp.constraints("soccer-jersey-ls", "soccer", sc)[1] == {"cut": {"ls"}}
    assert gp.constraints("soccer-jersey", "soccer", sc)[1] == {"no_cut": {"ls"}}
    assert gp.constraints("soccer-shorts", "soccer", sc) == {}
    c = gp.constraints("soccer-combo", "soccer", sc)
    assert c[1] == {"keeper": False, "cut": {"ss"}}
    assert c[2] == {"keeper": True, "cut": {"ss"}}
    assert gp.describe(c) == ("uniform 1: jersey ss only, field jersey; uniform 2: jersey ss only, keeper jersey")
    assert gp.constraints("soccer-combo-ls", "soccer", sc)[2] == {"keeper": True, "cut": {"ls"}}
    assert gp.constraints("soccer-condensed-combo", "soccer", sc)[2] == {"keeper": True}
    c = gp.constraints("volleyball-condensed-combo-ss-ls", "volleyball", vb)
    assert c[1] == {"cut": {"ss"}}
    assert c[2] == {"cut": {"ls"}}
    assert gp.constraints("volleyball-combo", "volleyball", vb) == {}
    assert gp.describe({}) == ""
    assert gp.describe({1: {}}) == ""


def test_colorway_longest_match():
    """colorway() takes the longest known colourway, falls back to the first word, and is empty for a bare year."""
    assert gp.colorway("2020 Vegas Gold Alt", COLORWAYS) == "vegas gold"
    assert gp.colorway("2020 Gold", COLORWAYS) == "gold"
    assert gp.colorway("2026 Teal Keeper", COLORWAYS) == "teal"
    assert gp.colorway("Generic Maroon", COLORWAYS) == "generic"
    assert gp.colorway("2020", COLORWAYS) == ""


def test_pick_number_prefers_back(cfg):
    """pick_number() takes the back view's first number, else a needed viewpoint's, else None."""
    r = rec(cfg, "football", "jersey", "2020 White", {"front": "N1", "back": "N2"}, {"front": ["1"], "back": ["7"]})
    assert gp.pick_number(r, ["front"]) == "7"
    r = rec(cfg, "football", "jersey", "2020 White", {"front": "N1", "back": "N2"}, {"front": ["1"]})
    assert gp.pick_number(r, ["front"]) == "1"
    r = rec(cfg, "football", "jersey", "2020 White", {"front": "N1"})
    assert gp.pick_number(r, ["front"]) is None


# --------------------------------------------------------------------------
# plan_template: coverage and constraints
# --------------------------------------------------------------------------


def test_every_era_covered_greedily(cfg, templates):
    """Each era of each placed viewpoint appears in an example; one element covering two eras saves an example."""
    J = lambda n, f, b: rec(cfg, "mens_basketball", "jersey", n, {"front": f, "back": b})  # noqa: E731
    inv = {
        "mens_basketball": {
            "Mississippi State": {
                "jersey": {
                    "2001 White": J("2001 White", "a", "a"),
                    "2010 White": J("2010 White", "b", "b"),
                    "2020 White": J("2020 White", "c", "c"),
                    "2021 Maroon": J("2021 Maroon", "c", "c"),
                }
            }
        }
    }
    examples, extras, targets, gaps, cons = plan(templates, cfg, "mbk-jersey", inv)
    assert len(targets) == 6
    assert not gaps
    assert not extras
    assert cons == {}
    covered = set().union(*(g for _, _, g in examples))
    assert covered == set(targets)
    assert len(examples) == 3
    # the newest of the two era-c elements is preferred
    assert {c[(1, "jersey")] for _, c, _ in examples} == {"2001 White", "2010 White", "2021 Maroon"}


def test_tq_constraint_splits_baseball_jerseys(cfg, templates):
    """A -tq template takes only three-quarter jerseys; its sibling never does, and neither reports the other's as a gap."""
    J = lambda n, e: rec(cfg, "baseball", "jersey", n, {"front": e, "back": e}, {"back": ["5"]})  # noqa: E731
    inv = {
        "baseball": {
            "Mississippi State": {"jersey": {"2020 White": J("2020 White", "std"), "2021 Gray": J("2021 Gray", "tq")}}
        }
    }
    ex, _, targets, gaps, _ = plan(templates, cfg, "diamond-jersey", inv)
    assert [c[(1, "jersey")] for _, c, _ in ex] == ["2020 White"]
    assert not gaps
    assert {t[3] for t in targets} == {"std"}
    ex, _, targets, gaps, _ = plan(templates, cfg, "diamond-jersey-tq", inv)
    assert [c[(1, "jersey")] for _, c, _ in ex] == ["2021 Gray"]
    assert not gaps


def test_soccer_combo_keeper_and_cut(cfg, templates):
    """Combos put a field kit in uniform 1 and a keeper in uniform 2, the keeper's cut set by the -ls variant."""
    J = lambda n, e: rec(cfg, "soccer", "jersey", n, {"front": e, "back": e})  # noqa: E731
    S = lambda n: rec(cfg, "soccer", "shorts", n, {"front": "all", "back": "all"})  # noqa: E731
    inv = {
        "soccer": {
            "Mississippi State": {
                "jersey": {
                    "2024 Maroon": J("2024 Maroon", "ss"),
                    "2024 White LS": J("2024 White LS", "ls"),
                    "2024 Blue Keeper": J("2024 Blue Keeper", "ss"),
                    "2024 Green Keeper": J("2024 Green Keeper", "ls"),
                },
                "shorts": {"2024 Maroon": S("2024 Maroon"), "2024 Blue": S("2024 Blue")},
            }
        }
    }
    ex, *_ = plan(templates, cfg, "soccer-combo", inv)
    assert [(c[(1, "jersey")], c[(2, "jersey")]) for _, c, _ in ex] == [("2024 Maroon", "2024 Blue Keeper")]
    # uniform 2's shorts follow ITS OWN jersey's colourway, not uniform 1's
    assert ex[0][1][(2, "shorts")] == "2024 Blue"
    assert ex[0][1][(1, "shorts")] == "2024 Maroon"
    ex, *_ = plan(templates, cfg, "soccer-combo-ls", inv)
    assert [(c[(1, "jersey")], c[(2, "jersey")]) for _, c, _ in ex] == [("2024 Maroon", "2024 Green Keeper")]
    ex, *_ = plan(templates, cfg, "soccer-condensed-combo", inv)
    assert {c[(2, "jersey")] for _, c, _ in ex} == {"2024 Blue Keeper", "2024 Green Keeper"}
    assert {c[(1, "jersey")] for _, c, _ in ex} == {"2024 Maroon"}
    ex, *_ = plan(templates, cfg, "soccer-jersey-ls", inv)
    assert {c[(1, "jersey")] for _, c, _ in ex} <= {"2024 White LS", "2024 Green Keeper"}
    ex, *_ = plan(templates, cfg, "soccer-jersey", inv)
    assert all(
        inv["soccer"]["Mississippi State"]["jersey"][c[(1, "jersey")]]["vps"]["front"]["era"] == "ss" for _, c, _ in ex
    )


def test_volleyball_cuts_and_distinct_combo(cfg, templates):
    """Volleyball -a-b combos take cut a then cut b; a folded combo shows two different jerseys."""
    J = lambda n, e: rec(cfg, "volleyball", "jersey", n, {"front": e, "back": e})  # noqa: E731
    inv = {
        "volleyball": {
            "Mississippi State": {
                "jersey": {
                    "2022 Maroon": J("2022 Maroon", "ss"),
                    "2022 White": J("2022 White", "ss"),
                    "2022 Gray LS": J("2022 Gray LS", "ls"),
                }
            }
        }
    }
    ex, *_ = plan(templates, cfg, "volleyball-condensed-combo-ss-ls", inv)
    assert all(c[(2, "jersey")] == "2022 Gray LS" and c[(1, "jersey")] != "2022 Gray LS" for _, c, _ in ex)
    ex, *_ = plan(templates, cfg, "volleyball-combo", inv)
    assert ex
    assert all(c[(1, "jersey")] != c[(2, "jersey")] for _, c, _ in ex)


def test_same_year_and_numbered_preferred(cfg, templates):
    """Around an anchor, same-year elements are chosen, and among equals the one with numbered files."""
    B = "baseball"
    inv = {
        B: {
            "Mississippi State": {
                "jersey": {
                    "2015 White": rec(cfg, B, "jersey", "2015 White", {"front": "std"}),
                    "2015 White Pinstripes": rec(
                        cfg, B, "jersey", "2015 White Pinstripes", {"front": "std"}, {"front": ["22"]}
                    ),
                    "2019 White": rec(cfg, B, "jersey", "2019 White", {"front": "std"}, {"front": ["9"]}),
                },
                "pants": {
                    "2019 White": rec(cfg, B, "pants", "2019 White", {"left": "std"}),
                    "2015 Gray": rec(cfg, B, "pants", "2015 Gray", {"left": "std"}),
                    "2015 White Pinstripes": rec(cfg, B, "pants", "2015 White Pinstripes", {"left": "std"}),
                },
                "hat": {"2015 Maroon": rec(cfg, B, "hat", "2015 Maroon", {"front": "modern"})},
            }
        }
    }
    ex, *_ = plan(templates, cfg, "baseball-condensed", inv)
    assert len(ex) == 1
    c = ex[0][1]
    assert c[(1, "jersey")] == "2015 White Pinstripes"  # same year, and numbered
    assert c[(1, "pants")] == "2015 White Pinstripes"  # same name as the jersey


def test_pairing_beats_heuristics(cfg, templates, monkeypatch):
    """A known pairing chooses the jersey and pants over a same-colourway, same-year match."""
    B = "baseball"
    inv = {
        B: {
            "Mississippi State": {
                "hat": {"2015 Maroon Fauxback": rec(cfg, B, "hat", "2015 Maroon Fauxback", {"front": "modern"})},
                "jersey": {
                    "2015 Maroon": rec(cfg, B, "jersey", "2015 Maroon", {"front": "std"}),
                    "2015 Natural Wool": rec(cfg, B, "jersey", "2015 Natural Wool", {"front": "std"}),
                },
                "pants": {
                    "2015 Maroon": rec(cfg, B, "pants", "2015 Maroon", {"left": "std"}),
                    "2015 Natural Wool": rec(cfg, B, "pants", "2015 Natural Wool", {"left": "std"}),
                },
            }
        }
    }
    ex, *_ = plan(templates, cfg, "baseball-condensed", inv)
    assert ex[0][1][(1, "jersey")] == "2015 Maroon"
    group = {"hat": "2015 Maroon Fauxback", "jersey": "2015 Natural Wool", "pants": "2015 Natural Wool"}
    pairings = {(B, "Mississippi State", e): {k: v for k, v in group.items() if k != s} for s, e in group.items()}
    ex, *_ = plan(templates, cfg, "baseball-condensed", inv, pairings)
    assert ex[0][1] == {
        (1, "hat"): "2015 Maroon Fauxback",
        (1, "jersey"): "2015 Natural Wool",
        (1, "pants"): "2015 Natural Wool",
    }


def test_gaps_reported(cfg, templates):
    """Unrecognised sizes, eras only on ineligible elements, and eras no team can complete are all 'not coverable'."""
    M = "mens_basketball"
    inv = {
        M: {
            "Mississippi State": {
                "jersey": {
                    "2001 White": rec(cfg, M, "jersey", "2001 White", {"front": "a", "back": "a"}),
                    "2002 Odd": rec(cfg, M, "jersey", "2002 Odd", {"front": None, "back": "a"}),
                    "2003 Front Only": rec(cfg, M, "jersey", "2003 Front Only", {"front": "c"}),
                },
                "shorts": {"2001 White": rec(cfg, M, "shorts", "2001 White", {"left": "a", "right": "a"})},
            },
            # a team with jerseys but no shorts: its era b is reachable but cannot be completed
            "Jones": {"jersey": {"2010 Gold": rec(cfg, M, "jersey", "2010 Gold", {"front": "b", "back": "b"})}},
        }
    }
    ex, _, targets, gaps, _ = plan(templates, cfg, "mbk-full", inv)
    assert (1, "jersey", "front", None) in gaps  # unrecognised size
    assert (1, "jersey", "front", "c") in gaps  # silent: element lacks a required view
    assert (1, "jersey", "front", "b") in gaps  # no Jones shorts
    assert [t for t, _, _ in ex] == ["Mississippi State"]


def test_no_team_fills_template(cfg, templates):
    """A template whose slots no team fills plans no examples and no explicit extras."""
    F = "football"
    inv = {
        F: {
            "Mississippi State": {
                "helmet": {"2020 Maroon": rec(cfg, F, "helmet", "2020 Maroon", {"right": "F", "left": "F"})}
            }
        }
    }
    ex, extras, _, gaps, _ = plan(templates, cfg, "condensed", inv)
    assert ex == []
    assert extras == []
    assert gaps == [(1, "helmet", "right", "F")]
    ex, *_ = plan(templates, cfg, "condensed", {})
    assert ex == []


def football_inv(cfg, left=True):
    """A small football team for the condensed template, with or without helmet-left artwork."""
    F = "football"
    hv = {"right": "F", "left": "F"} if left else {"right": "F"}
    return {
        F: {
            "Mississippi State": {
                "helmet": {"2020 Maroon": rec(cfg, F, "helmet", "2020 Maroon", hv)},
                "jersey": {
                    "2020 Maroon": rec(cfg, F, "jersey", "2020 Maroon", {"front": "N3", "back": "N3"}, {"back": ["4"]})
                },
                "pants": {"2020 Maroon": rec(cfg, F, "pants", "2020 Maroon", {"left": "all"})},
            }
        }
    }


def test_explicit_placement_gets_one_extra(cfg, templates):
    """The explicit helmet-left inset adds one extra example, only when the helmet has left artwork."""
    ex, extras, *_ = plan(templates, cfg, "condensed", football_inv(cfg))
    assert len(ex) == 1
    assert len(extras) == 1
    assert extras[0][2] == {"explicit": "helmet/left"}
    ex, extras, *_ = plan(templates, cfg, "condensed", football_inv(cfg, left=False))
    assert len(ex) == 1
    assert extras == []


def test_if_available_never_rules_out(cfg, templates):
    """An if_available viewpoint is covered when present but an element without it is still eligible."""
    F = "football"
    inv = {
        F: {
            "Jones": {
                "jersey": {
                    "2019 Gold": rec(cfg, F, "jersey", "2019 Gold", {"front": "N2", "back": "N2"}),
                    "2020 Gold": rec(cfg, F, "jersey", "2020 Gold", {"front": "N3", "back": "N3", "left": "all"}),
                }
            }
        }
    }
    ex, _, targets, gaps, _ = plan(templates, cfg, "jersey-full", inv)
    assert (1, "jersey", "left", "all") in targets
    assert (1, "jersey", "front", "N2") in targets
    assert {c[(1, "jersey")] for _, c, _ in ex} == {"2019 Gold", "2020 Gold"}
    assert not gaps


def test_reference_without_jersey_and_yearless(cfg):
    """With no jersey the reference is the uniform's chosen element; yearless elements still plan."""
    F = "football"
    t = {
        "sport": F,
        "view_kind": "custom",
        "placements": [
            {"slot": "helmet", "viewpoint": "right"},
            {"slot": "pants", "viewpoint": "left", "uniform": 2},
            {"slot": "helmet", "viewpoint": "right", "uniform": 2},
        ],
    }
    inv = {
        F: {
            "Mississippi State": {
                "helmet": {
                    "2020 Maroon": rec(cfg, F, "helmet", "2020 Maroon", {"right": "F"}),
                    "Generic White": rec(cfg, F, "helmet", "Generic White", {"right": "F"}),
                },
                "pants": {
                    "2020 Maroon": rec(cfg, F, "pants", "2020 Maroon", {"left": "all"}),
                    "Generic White": rec(cfg, F, "pants", "Generic White", {"left": "all"}),
                },
            }
        }
    }
    ex, *_ = gp.plan_template(t, {"custom"}, inv, {}, COLORWAYS)
    assert len(ex) == 1
    c = ex[0][1]
    # uniform 2's helmet follows uniform 2's pants (same name), and differs from uniform 1's
    assert c[(2, "helmet")] == c[(2, "pants")]
    assert c[(2, "helmet")] != c[(1, "helmet")]
    inv[F]["Mississippi State"]["helmet"].pop("2020 Maroon")
    inv[F]["Mississippi State"]["pants"].pop("2020 Maroon")
    ex, *_ = gp.plan_template(t, {"custom"}, inv, {}, COLORWAYS)
    assert ex[0][1] == {(1, "helmet"): "Generic White", (2, "pants"): "Generic White", (2, "helmet"): "Generic White"}


# --------------------------------------------------------------------------
# build_inventory on real files
# --------------------------------------------------------------------------


def draw_wbk(project, cfg, team="Mississippi State"):
    """Draw women's basketball shorts on their canvas: one era-a element (numbered too) and one era-b."""
    W = canvas_size(cfg, "wbk_shorts")
    base = project / "Women's Basketball" / team
    a, b = (
        era(cfg, "womens_basketball-shorts-front", "a")["size"],
        era(cfg, "womens_basketball-shorts-front", "b")["size"],
    )
    for vp in ("Front", "Back"):
        art(base / f"Shorts {vp}" / "2020 Maroon" / "2020 Maroon.png", W, a)
        art(base / f"Shorts {vp}" / "2021 White" / "2021 White 12.png", W, b)
    art(base / "Shorts Back" / "2020 Maroon" / "2020 Maroon 05.png", W, (10, 10))
    art(base / "Shorts Back" / "2020 Maroon" / ".hidden.png", W, (10, 10))
    (base / "Shorts Back" / "1999 Empty").mkdir()
    (base / "Shorts Back" / "notes.txt").write_text("not a folder")
    (base.parent / "notes.txt").write_text("not a team")
    return base


def test_build_inventory_measures_one_file_per_view(project, cfg):
    """The plain file is measured when present; numbers, file counts, year and keeper are recorded."""
    draw_wbk(project, cfg)
    inv = gp.build_inventory(project, cfg, ["womens_basketball", "volleyball"])
    assert set(inv) == {"womens_basketball"}
    els = inv["womens_basketball"]["Mississippi State"]["shorts"]
    assert set(els) == {"2020 Maroon", "2021 White"}
    m = els["2020 Maroon"]
    assert m["year"] == 2020
    assert m["keeper"] is False
    assert m["vps"]["back"] == {
        "era": "a",
        "size": era(cfg, "womens_basketball-shorts-back", "a")["size"],
        "numbers": ["05"],
        "files": 2,
    }
    w = els["2021 White"]["vps"]["front"]
    assert w["era"] == "b"
    assert w["numbers"] == ["12"]


def test_build_inventory_reads_numbers_past_patch_tokens(project, cfg):
    """A baseball jersey whose only patched file is CWS21 has no numbers, so the planner requests none."""
    d = project / "Baseball" / "Mississippi State" / "Jerseys Back" / "2021 White"
    art(d / "2021 White.png", (40, 40))
    art(d / "2021 White CWS21.png", (40, 40))
    inv = gp.build_inventory(project, cfg, ["baseball"])
    assert inv["baseball"]["Mississippi State"]["jersey"]["2021 White"]["vps"]["back"]["numbers"] == []


# --------------------------------------------------------------------------
# main(): outputs
# --------------------------------------------------------------------------


def test_main_rescan_writes_inventory_manifest_and_plan(project, cfg, templates, monkeypatch, capsys):
    """A first run measures artwork and writes inventory.json, manifest.yaml and PLAN.md covering every era."""
    reduced_configs(project, templates, {"wbk-shorts"})
    draw_wbk(project, cfg)
    run_main(monkeypatch)
    out = capsys.readouterr().out
    assert "inventory: measuring womens_basketball (not in golden/inventory.json)" in out
    assert "2 element-slots across 1 sports" in out
    assert "2 examples across 1 templates" in out
    inv = json.loads((project / "golden/inventory.json").read_text())
    assert inv["sports"] == ["womens_basketball"]
    assert set(inv["elements"]["womens_basketball"]["Mississippi State"]["shorts"]) == {"2020 Maroon", "2021 White"}
    man = yaml.safe_load((project / "golden/manifest.yaml").read_text())
    assert [m["id"] for m in man] == ["womens_basketball--wbk-shorts--01", "womens_basketball--wbk-shorts--02"]
    m = {x["uniform1"]["shorts"]: x for x in man}
    assert m["2020 Maroon"]["expect_eras"] == {"1/shorts/front": "a", "1/shorts/back": "a"}
    assert m["2021 White"]["covers"] == ["#1 shorts/back b", "#1 shorts/front b"]
    assert all(x["approved"] is True and x["number"] is None and "uniform2" not in x for x in man)
    md = (project / "golden/PLAN.md").read_text()
    assert "**2 examples across 1 templates and 1 sports.**" in md
    assert "### `wbk-shorts` — 2 examples" in md
    assert "Not coverable" not in md
    assert "NO examples" not in md


def test_main_reuses_cache_and_reresolves_eras(project, cfg, templates, monkeypatch, capsys):
    """A cached inventory is reused without reading artwork, and its eras are re-resolved from cached sizes."""
    reduced_configs(project, templates, {"wbk-shorts"})
    M = "womens_basketball"
    r = rec(cfg, M, "shorts", "2020 Maroon", {"front": "a", "back": "a"})
    r["vps"]["front"]["era"] = "stale"
    inv = {M: {"Mississippi State": {"shorts": {"2020 Maroon": r}}}}
    (project / "golden/inventory.json").write_text(json.dumps(inv))
    run_main(monkeypatch)
    out = capsys.readouterr().out
    assert "reusing golden/inventory.json for womens_basketball (--rescan to refresh) — 1 eras re-resolved" in out
    man = yaml.safe_load((project / "golden/manifest.yaml").read_text())
    assert man[0]["expect_eras"]["1/shorts/front"] == "a"
    # --rescan ignores the cache: there is no artwork, so nothing is found
    run_main(monkeypatch, "--rescan")
    out = capsys.readouterr().out
    assert "inventory: measuring womens_basketball (--rescan)" in out
    assert "0 element-slots across 0 sports" in out
    assert "!! 1 templates have NO examples: womens_basketball / wbk-shorts" in out
    md = (project / "golden/PLAN.md").read_text()
    assert "## ⚠ 1 template have NO examples" in md
    assert "- `womens_basketball / wbk-shorts`" in md


def test_main_combo_explicit_constraints_gaps_and_pairings(project, cfg, templates, monkeypatch, capsys):
    """Combos write uniform2 and number2, the inset gets an extra entry, constraints and gaps reach PLAN.md, pairings load."""
    reduced_configs(project, templates, {"condensed", "volleyball-condensed-combo-ss-ls", "baseball-condensed"})
    V, B = "volleyball", "baseball"
    inv = football_inv(cfg)
    inv["football"]["Mississippi State"]["jersey"]["2021 Odd"] = rec(
        cfg, "football", "jersey", "2021 Odd", {"front": None}
    )
    inv[V] = {
        "Mississippi State": {
            "jersey": {
                "2022 Maroon": rec(cfg, V, "jersey", "2022 Maroon", {"front": "ss", "back": "ss"}, {"back": ["3"]}),
                "2022 Gray LS": rec(cfg, V, "jersey", "2022 Gray LS", {"front": "ls"}, {"front": ["11"]}),
            }
        }
    }
    inv[B] = {
        "Mississippi State": {
            "hat": {"2015 Maroon Fauxback": rec(cfg, B, "hat", "2015 Maroon Fauxback", {"front": "modern"})},
            "jersey": {
                "2015 Maroon": rec(cfg, B, "jersey", "2015 Maroon", {"front": "std"}),
                "2015 Natural Wool": rec(cfg, B, "jersey", "2015 Natural Wool", {"front": "std"}),
            },
            "pants": {
                "2015 Maroon": rec(cfg, B, "pants", "2015 Maroon", {"left": "std"}),
                "2015 Natural Wool": rec(cfg, B, "pants", "2015 Natural Wool", {"left": "std"}),
            },
        }
    }
    (project / "golden/inventory.json").write_text(json.dumps(inv))
    (project / "golden/pairings.yaml").write_text(
        yaml.safe_dump(
            {
                B: {
                    "Mississippi State": [
                        {"jersey": "2015 Natural Wool", "hat": "2015 Maroon Fauxback", "pants": "2015 Natural Wool"}
                    ]
                }
            }
        )
    )
    run_main(monkeypatch)
    out = capsys.readouterr().out
    assert "pairings: 1 known uniform from golden/pairings.yaml" in out
    assert "!! 1 era targets not coverable" in out
    man = {m["id"]: m for m in yaml.safe_load((project / "golden/manifest.yaml").read_text())}
    assert man["baseball--baseball-condensed--01"]["uniform1"]["jersey"] == "2015 Natural Wool"
    vb = man["volleyball--volleyball-condensed-combo-ss-ls--01"]
    assert vb["uniform1"] == {"jersey": "2022 Maroon"}
    assert vb["uniform2"] == {"jersey": "2022 Gray LS"}
    assert vb["number"] == "3"
    assert vb["number2"] == "11"
    assert vb["expect_eras"] == {"1/jersey/front": "ss", "2/jersey/front": "ls"}
    fb1, fb2 = man["football--condensed--01"], man["football--condensed--02"]
    assert "helmet_left" not in fb1
    assert fb1["number"] == "4"
    assert fb2["helmet_left"] is True
    assert fb2["note"] == "exercises the explicit helmet/left placement"
    assert fb2["expect_eras"]["1/helmet/left"] == "F"
    assert "covers" not in fb2
    md = (project / "golden/PLAN.md").read_text()
    assert "### `condensed` — 1 example + 1 explicit" in md
    assert "_Constraint: uniform 1: jersey ss only; uniform 2: jersey ls only_" in md
    assert "**Not coverable**" in md
    assert "- jersey/front era `UNMATCHED SIZE`" in md
    assert "**1 era targets could not be covered**" in md
    assert "jersey: 2022 Maroon **3**<br>#2 jersey: 2022 Gray LS **11**" in md
    assert "_explicit: helmet/left_" in md


def test_main_sport_filter_and_plural_pairings(project, cfg, templates, monkeypatch, capsys):
    """--sport limits the plan, an empty pairings file counts zero, and missing slots_global is tolerated."""
    reduced_configs(project, templates, {"wbk-shorts", "condensed", "jersey-full"}, **{"slots_global.yaml": None})
    (project / "golden/pairings.yaml").write_text("")
    (project / "golden/inventory.json").write_text(json.dumps(football_inv(cfg)))
    run_main(monkeypatch, "--sport", "football")
    out = capsys.readouterr().out
    assert "pairings: 0 known uniforms" in out
    assert "3 examples across 2 templates" in out
    assert "womens_basketball" not in out
    man = yaml.safe_load((project / "golden/manifest.yaml").read_text())
    assert {m["sport"] for m in man} == {"football"}
    jf = next(m for m in man if m["view"] == "jersey-full")
    assert jf["expect_eras"] == {"1/jersey/front": "N3", "1/jersey/back": "N3"}


def test_main_reads_colorway_tokens_and_labels(project, templates, monkeypatch, capsys):
    """Colourways are read from slots_global.yaml keys, tokens and labels, longest first."""
    colorways = {
        "vegas_gold": {"token": "Vegas Gold", "label": "Old Gold"},
        "red": None,
        "powder": {"label": "Powder Blue"},
    }
    reduced_configs(project, templates, {"wbk-shorts"}, **{"slots_global.yaml": {"colorways": colorways}})
    (project / "golden/inventory.json").write_text("{}")
    seen, real = [], gp.plan_template
    monkeypatch.setattr(gp, "plan_template", lambda *a: seen.append(a[4]) or real(*a))
    run_main(monkeypatch)
    assert seen[0][:2] == ["powder blue", "vegas gold"]
    assert set(seen[0]) == {
        "powder blue",
        "vegas gold",
        "old gold",
        "red",
        "powder",
    }
    assert "NO examples" in capsys.readouterr().out


def test_runs_as_a_script(project, monkeypatch, capsys):
    """Executed as __main__, the script plans from the project it is run in."""
    import runpy

    (project / "golden/inventory.json").write_text("{}")
    monkeypatch.setattr(sys, "argv", ["golden_plan.py", "--sport", "womens_basketball"])
    runpy.run_path(str(REPO / "scripts/golden/golden_plan.py"), run_name="__main__")
    assert "Wrote golden/manifest.yaml and golden/PLAN.md" in capsys.readouterr().out


# --------------------------------------------------------------------------
# main(): --sport keeps the other sports
# --------------------------------------------------------------------------


def two_sport_inv(cfg) -> dict:
    """football_inv plus one women's basketball shorts element."""
    inv = football_inv(cfg)
    M = "womens_basketball"
    inv[M] = {
        "Mississippi State": {
            "shorts": {"2020 Maroon": rec(cfg, M, "shorts", "2020 Maroon", {"front": "a", "back": "a"})}
        }
    }
    return inv


def test_main_sport_replaces_only_that_sport_in_manifest_and_plan(project, cfg, templates, monkeypatch, capsys):
    """--sport replaces the selected sport's manifest entries and PLAN.md section, keeping every other sport's, edits included."""
    reduced_configs(project, templates, {"wbk-shorts", "condensed", "jersey-full"})
    (project / "golden/inventory.json").write_text(json.dumps(two_sport_inv(cfg)))
    run_main(monkeypatch)
    full_man = yaml.safe_load((project / "golden/manifest.yaml").read_text())
    full_md = (project / "golden/PLAN.md").read_text()
    assert {m["sport"] for m in full_man} == {"football", "womens_basketball"}
    # a hand edit on the other sport survives a re-plan of football
    edited = [dict(m, approved=False) if m["sport"] == "womens_basketball" else m for m in full_man]
    (project / "golden/manifest.yaml").write_text(yaml.safe_dump(edited, sort_keys=False))
    capsys.readouterr()
    run_main(monkeypatch, "--sport", "football")
    out = capsys.readouterr().out
    assert "kept 1 example for other sports: womens_basketball" in out
    assert yaml.safe_load((project / "golden/manifest.yaml").read_text()) == edited
    assert (project / "golden/PLAN.md").read_text() == full_md
    # and the selected sport really is re-planned: drop its section and entries, re-plan, both come back
    (project / "golden/manifest.yaml").write_text(
        yaml.safe_dump([m for m in edited if m["sport"] != "football"], sort_keys=False)
    )
    (project / "golden/PLAN.md").write_text(
        full_md.split("\n## Football\n")[0] + "\n## Womens Basketball\n" + full_md.split("\n## Womens Basketball\n")[1]
    )
    run_main(monkeypatch, "--sport", "football")
    assert yaml.safe_load((project / "golden/manifest.yaml").read_text()) == edited
    assert (project / "golden/PLAN.md").read_text() == full_md


def test_main_sport_header_counts_kept_sections(project, cfg, templates, monkeypatch, capsys):
    """PLAN.md's header totals examples, templates, empty templates and gaps across kept and re-planned sports."""
    reduced_configs(project, templates, {"wbk-shorts", "condensed", "jersey-full", "volleyball-condensed-combo-ss-ls"})
    inv = two_sport_inv(cfg)
    inv["football"]["Mississippi State"]["jersey"]["2021 Odd"] = rec(
        cfg, "football", "jersey", "2021 Odd", {"front": None}
    )
    (project / "golden/inventory.json").write_text(json.dumps(inv))
    run_main(monkeypatch)
    full_md = (project / "golden/PLAN.md").read_text()
    assert "## ⚠ 1 template have NO examples" in full_md
    assert "era targets could not be covered" in full_md
    run_main(monkeypatch, "--sport", "womens_basketball")
    assert (project / "golden/PLAN.md").read_text() == full_md


def test_main_sport_warns_when_a_kept_sport_has_no_plan_section(project, cfg, templates, monkeypatch, capsys):
    """A kept sport with manifest entries but no PLAN.md section is kept and named, so a full re-plan can restore it."""
    reduced_configs(project, templates, {"wbk-shorts", "condensed"})
    (project / "golden/inventory.json").write_text(json.dumps(two_sport_inv(cfg)))
    run_main(monkeypatch)
    (project / "golden/PLAN.md").unlink()
    capsys.readouterr()
    run_main(monkeypatch, "--sport", "womens_basketball")
    out = capsys.readouterr().out
    assert "PLAN.md had no section for football" in out
    assert {m["sport"] for m in yaml.safe_load((project / "golden/manifest.yaml").read_text())} == {
        "football",
        "womens_basketball",
    }


def test_main_sport_unknown_exits(project, monkeypatch):
    """--sport naming a sport with no template exits before writing anything."""
    with pytest.raises(SystemExit, match="No templates for sport: curling"):
        run_main(monkeypatch, "--sport", "curling")
    assert not (project / "golden/manifest.yaml").exists()


def draw_football_jerseys(project, cfg):
    """One football jersey element, front and back, at era N3 on the jersey canvas."""
    W = canvas_size(cfg, "football_jersey")
    for vp in ("front", "back"):
        size = era(cfg, f"football-jersey-{vp}", "N3")["size"]
        art(
            project / "Football" / "Mississippi State" / f"Jerseys {vp.title()}" / "2016 White" / "2016 White.png",
            W,
            size,
        )


def test_inventory_records_its_sports_and_extends_when_one_is_missing(project, cfg, templates, monkeypatch, capsys):
    """An inventory measured for one sport is extended, not reused as is, when a later plan needs another."""
    reduced_configs(project, templates, {"wbk-shorts", "jersey-full"})
    draw_wbk(project, cfg)
    draw_football_jerseys(project, cfg)
    run_main(monkeypatch, "--sport", "womens_basketball")
    saved = json.loads((project / "golden/inventory.json").read_text())
    assert saved["sports"] == ["womens_basketball"]
    assert set(saved["elements"]) == {"womens_basketball"}
    capsys.readouterr()
    run_main(monkeypatch)
    out = capsys.readouterr().out
    assert "inventory: measuring football (not in golden/inventory.json)" in out
    saved = json.loads((project / "golden/inventory.json").read_text())
    assert saved["sports"] == ["football", "womens_basketball"]
    man = yaml.safe_load((project / "golden/manifest.yaml").read_text())
    assert [m["uniform1"] for m in man if m["view"] == "jersey-full"] == [{"jersey": "2016 White"}]
    # now everything needed is cached: reused, nothing measured
    run_main(monkeypatch)
    assert "inventory: reusing golden/inventory.json" in capsys.readouterr().out


def test_rescan_with_sport_keeps_other_sports_inventory(project, cfg, templates, monkeypatch, capsys):
    """--rescan --sport re-measures only the selected sport and keeps the rest of the cached inventory."""
    reduced_configs(project, templates, {"wbk-shorts", "condensed"})
    (project / "golden/inventory.json").write_text(
        json.dumps({"sports": ["football", "womens_basketball"], "elements": two_sport_inv(cfg)})
    )
    draw_wbk(project, cfg)
    run_main(monkeypatch, "--rescan", "--sport", "womens_basketball")
    saved = json.loads((project / "golden/inventory.json").read_text())
    assert saved["sports"] == ["football", "womens_basketball"]
    assert saved["elements"]["football"] == football_inv(cfg)["football"]
    assert set(saved["elements"]["womens_basketball"]["Mississippi State"]["shorts"]) == {"2020 Maroon", "2021 White"}


def test_legacy_inventory_covers_the_sports_it_holds(project, cfg, templates, monkeypatch, capsys):
    """An inventory.json from before coverage was recorded counts as covering exactly the sports it holds."""
    reduced_configs(project, templates, {"wbk-shorts", "jersey-full"})
    draw_football_jerseys(project, cfg)
    M = "womens_basketball"
    legacy = {
        M: {"Mississippi State": {"shorts": {"2020 Maroon": rec(cfg, M, "shorts", "2020 Maroon", {"front": "a"})}}}
    }
    (project / "golden/inventory.json").write_text(json.dumps(legacy))
    run_main(monkeypatch)
    out = capsys.readouterr().out
    assert "inventory: measuring football (not in golden/inventory.json)" in out
    saved = json.loads((project / "golden/inventory.json").read_text())
    assert saved["sports"] == ["football", "womens_basketball"]
    assert saved["elements"][M] == legacy[M]


def test_root_flag_and_manifest_header(project, tmp_path, monkeypatch, capsys):
    """--root plans a project from elsewhere, and the manifest it writes warns that a re-plan overwrites it."""
    (project / "golden/inventory.json").write_text("{}")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    run_main(monkeypatch, "--root", str(project), "--sport", "womens_basketball")
    text = (project / "golden/manifest.yaml").read_text()
    assert text.startswith(gp.MANIFEST_HEADER)
    assert "WARNING: golden_plan.py OVERWRITES this file." in text
    assert "golden/pairings.yaml" in text
    assert not (elsewhere / "golden").exists()
