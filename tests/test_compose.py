"""Tests for scripts/pipeline/compose.py: candidate ranking, placement resolution, pasting, --json and --diff."""

import json
import os
import runpy
import sys

import compose
import numpy as np
import pytest
import yaml
from conftest import REPO, art, canvas_size
from PIL import Image

SCRIPT = str(REPO / "scripts" / "pipeline" / "compose.py")
MSU = "Mississippi State"


@pytest.fixture(scope="module")
def fvocab():
    """compose's view of the real football vocabulary."""
    return compose.load_vocab(REPO, "football")


@pytest.fixture(scope="module")
def bvocab():
    """compose's view of the real baseball vocabulary."""
    return compose.load_vocab(REPO, "baseball")


def put(root, slot, vp, element, name, size=(40, 30), content=None, sport="Football", team=MSU, seed=0, top=0):
    """Draw element artwork at {sport}/{team}/{Slot} {Viewpoint}/{element}/{name}.png."""
    path = root / sport / team / f"{compose.SLOT_DIR[slot]} {vp.title()}" / element / f"{name}.png"
    return art(path, size, content, top=top, seed=seed)


def touch(folder, *names):
    """Create empty-content PNG files with these names in folder; return the folder."""
    for n in names:
        art(folder / f"{n}.png", (2, 2))
    return folder


def rank(folder, element, vocab, number=None, want=(), player=None):
    """File names in candidate order."""
    return [f.name for f in compose.candidates(folder, element, number, want, vocab, player)]


def mini(project, *templates):
    """Replace the project's view templates with these, keeping every other real config file."""
    d = project / "configs"
    d.unlink()
    d.mkdir()
    for f in (REPO / "configs").iterdir():
        if f.name != "view_templates.yaml":
            os.symlink(f, d / f.name)
    (d / "view_templates.yaml").write_text(yaml.safe_dump({"templates": list(templates)}))


def tpl(view, placements, w=200, h=120, sport="football"):
    """A template dict."""
    return {"sport": sport, "view_kind": view, "output": {"width": w, "height": h}, "placements": placements}


def run(monkeypatch, *argv):
    """Call compose.main() with these arguments."""
    monkeypatch.setattr(sys, "argv", ["compose.py", *argv])
    compose.main()


def compose_json(project, monkeypatch, *argv, ok=True):
    """Run compose with --json and --out in the project; return (result dict, output path)."""
    out, jp = project / "out" / "c.png", project / "out" / "c.json"
    args = [*argv, "--out", str(out), "--json", str(jp)]
    if ok:
        run(monkeypatch, *args)
    else:
        with pytest.raises(SystemExit) as e:
            run(monkeypatch, *args)
        assert e.value.code == 1
    return json.loads(jp.read_text()), out


def by_label(result):
    """Placements of a --json result keyed by label."""
    return {p["label"]: p for p in result["placements"]}


def pixels(path):
    """An image's RGBA pixels as an array."""
    with Image.open(path) as im:
        return np.array(im.convert("RGBA"))


# --- vocabulary and tail parsing ----------------------------------------------


def test_vocab_excludes_sequences_and_marks_default_forms(fvocab, bvocab):
    """Sequence letters are not tokens; shells/styles are forms and Speedflex and Modern are the defaults."""
    allt, form, default = fvocab
    assert "A" not in allt
    assert "Grad" in allt
    assert "Flying M" in allt
    assert [len(t) for t in allt] == sorted((len(t) for t in allt), reverse=True)
    assert {"Speed", "Speedflex", "Leather"} <= form
    assert default == {"Speedflex"}
    assert {"Classic", "Modern", "Vest"} <= bvocab[1]
    assert bvocab[2] == {"Modern"}


def test_vocab_tolerates_loops_missing_files_and_unlabelled_tokens(project):
    """Circular extends stop, a missing base contributes nothing, and a token with no name is skipped."""
    mini(project)
    d = project / "configs"
    (d / "modifiers_a.yaml").write_text(yaml.safe_dump({"extends": "b", "tokens": {"x": {"label": "Xtra"}}}))
    (d / "modifiers_b.yaml").write_text(yaml.safe_dump({"extends": "a", "tokens": {"y": {"scope": "patch"}}}))
    (d / "modifiers_c.yaml").write_text(yaml.safe_dump({"extends": "nope", "tokens": {"z": {"label": "Zed"}}}))
    assert compose.load_vocab(project, "a") == (["Xtra"], set(), set())
    assert compose.load_vocab(project, "c") == (["Zed"], set(), set())
    assert compose.load_vocab(project, "curling") == ([], set(), set())


def test_split_tail_finds_tokens_number_and_surname(fvocab, bvocab):
    """split_tail() separates tokens, the number (as an opaque string) and leftover surname words."""
    assert compose.split_tail("2025 Black 03 Grad NCAA", "2025 Black", fvocab[0]) == ({"Grad", "NCAA"}, "03", [])
    assert compose.split_tail("2014 White 85s 18 Heck", "2014 White 85s", bvocab[0]) == (set(), "18", ["Heck"])
    assert compose.split_tail("2025 Black", "2025 Black", fvocab[0]) == (set(), None, [])
    # A stem that doesn't start with the element is parsed whole.
    assert compose.split_tail("Other 7", "2025 Black", fvocab[0]) == (set(), "7", ["Other"])


# --- candidate ranking ----------------------------------------------------------


def test_requested_number_is_an_opaque_string(tmp_path, fvocab):
    """'03' and '3' are different numbers; a requested number never yields a file carrying another one."""
    f = touch(tmp_path / "2025 Black", "2025 Black", "2025 Black 3", "2025 Black 03")
    assert rank(f, "2025 Black", fvocab, "03") == ["2025 Black 03.png", "2025 Black.png"]
    assert rank(f, "2025 Black", fvocab, "3") == ["2025 Black 3.png", "2025 Black.png"]
    assert rank(f, "2025 Black", fvocab, "0") == ["2025 Black.png"]
    assert rank(f, "2025 Black", fvocab)[0] == "2025 Black.png"


def test_a_requested_number_never_falls_back_to_another_number(tmp_path, fvocab):
    """With a number requested and neither that number nor an unnumbered file present, there is no candidate."""
    f = touch(tmp_path / "e", "2025 Black 3", "2025 Black 12 Grad")
    assert rank(f, "2025 Black", fvocab, "7") == []
    assert rank(f, "2025 Black", fvocab, "7", {"Grad"}) == []


def test_without_a_number_any_file_is_a_candidate(tmp_path, fvocab):
    """With no number requested, numbered files remain candidates, unnumbered first."""
    f = touch(tmp_path / "e", "2025 Black 3", "2025 Black 12", "2025 Black")
    assert rank(f, "2025 Black", fvocab) == ["2025 Black.png", "2025 Black 12.png", "2025 Black 3.png"]
    only = touch(tmp_path / "n", "2025 Black 3")
    assert rank(only, "2025 Black", fvocab) == ["2025 Black 3.png"]


def test_resolve_names_the_missing_number(project, fvocab):
    """resolve() fails, naming the requested number and the ones that exist, rather than placing another number."""
    put(project, "jersey", "front", "2025 Black", "2025 Black 3")
    put(project, "jersey", "front", "2025 Black", "2025 Black 12")
    path, how = compose.resolve(project, MSU, "football", "jersey", "front", "2025 Black", "7", set(), fvocab)
    assert path is None
    assert how == "no #7 or unnumbered file under Jerseys Front/2025 Black (has #12, #3)"


def test_a_missing_number_fails_a_required_placement(project, monkeypatch):
    """End to end: a required jersey with only other numbers is MISSING, exit 1, nothing written."""
    mini(project, tpl("jf", [{"slot": "jersey", "viewpoint": "front", "x": 50, "y": 0}]))
    put(project, "jersey", "front", "2025 White", "2025 White 4")
    res, out = compose_json(project, monkeypatch, "--view", "jf", "--jersey", "2025 White", "--number", "15", ok=False)
    assert res["missing"] == [
        {"label": "jersey/front", "reason": "no #15 or unnumbered file under Jerseys Front/2025 White (has #4)"}
    ]
    assert res["output"] is None
    assert not out.exists()


def test_number_outranks_with_token(tmp_path, fvocab):
    """The requested number wins before a --with token is considered."""
    f = touch(tmp_path / "e", "2025 Black Grad", "2025 Black 12")
    assert rank(f, "2025 Black", fvocab, "12", {"Grad"})[0] == "2025 Black 12.png"


def test_with_token_is_required_over_plainness(tmp_path, fvocab):
    """--with picks the file carrying the token; without it the plain file wins."""
    f = touch(tmp_path / "e", "2025 Black 12", "2025 Black 12 Grad")
    assert rank(f, "2025 Black", fvocab, "12", {"Grad"})[0] == "2025 Black 12 Grad.png"
    assert rank(f, "2025 Black", fvocab, "12")[0] == "2025 Black 12.png"


def test_with_token_outranks_player(tmp_path, bvocab):
    """Every --with token must be present before the requested player is considered."""
    f = touch(tmp_path / "e", "2014 White 85s 18 Heck", "2014 White 85s 18 Girodo Grad")
    assert rank(f, "2014 White 85s", bvocab, "18", {"Grad"}, "Heck")[0] == "2014 White 85s 18 Girodo Grad.png"


def test_player_picks_between_same_number_files(tmp_path, bvocab):
    """--player chooses between files sharing a number; without it they fall to filename order."""
    f = touch(tmp_path / "e", "2014 White 85s 18 Heck", "2014 White 85s 18 Girodo")
    assert rank(f, "2014 White 85s", bvocab, "18", player="heck")[0] == "2014 White 85s 18 Heck.png"
    assert rank(f, "2014 White 85s", bvocab, "18")[0] == "2014 White 85s 18 Girodo.png"


def test_player_outranks_fewest_extra_tokens(tmp_path, bvocab):
    """The requested player wins even when that file carries an unrequested patch."""
    f = touch(tmp_path / "e", "2014 White 85s 18 Grad Heck", "2014 White 85s 18 Girodo")
    assert rank(f, "2014 White 85s", bvocab, "18", player="Heck")[0] == "2014 White 85s 18 Grad Heck.png"


def test_a_player_file_ranks_below_an_unnamed_one_unless_asked(tmp_path, bvocab):
    """With no --player the unnamed file wins; asking for an absent player still prefers unnamed over another."""
    f = touch(tmp_path / "e", "2014 White 85s 18 Aaron", "2014 White 85s 18")
    assert rank(f, "2014 White 85s", bvocab, "18")[0] == "2014 White 85s 18.png"
    assert rank(f, "2014 White 85s", bvocab, "18", player="Heck")[0] == "2014 White 85s 18.png"


def test_fewest_unrequested_tokens_beats_filename_order(tmp_path, fvocab):
    """The plain file wins over patched ones even though ' ' sorts before '.'."""
    f = touch(tmp_path / "e", "2025 Black Grad NCAA", "2025 Black Grad", "2025 Black")
    assert rank(f, "2025 Black", fvocab) == ["2025 Black.png", "2025 Black Grad.png", "2025 Black Grad NCAA.png"]


def test_default_form_breaks_a_tie_on_extras(tmp_path, fvocab, bvocab):
    """With equal unrequested tokens, a file in the default form beats one in a non-default form."""
    f = touch(tmp_path / "h", "2015 Maroon Speed", "2015 Maroon Speedflex Grad")
    assert rank(f, "2015 Maroon", fvocab)[0] == "2015 Maroon Speedflex Grad.png"
    hats = touch(tmp_path / "hat", "1968 Maroon Classic", "1968 Maroon Modern")
    assert rank(hats, "1968 Maroon", bvocab)[0] == "1968 Maroon Modern.png"
    assert rank(hats, "1968 Maroon", bvocab, want={"Classic"})[0] == "1968 Maroon Classic.png"


def test_filename_is_the_last_tie_break(tmp_path, fvocab):
    """Files equal on every rank come back in filename order."""
    f = touch(tmp_path / "e", "2025 Black Grad", "2025 Black NCAA", "2025 Black SEC")
    assert rank(f, "2025 Black", fvocab) == ["2025 Black Grad.png", "2025 Black NCAA.png", "2025 Black SEC.png"]


def test_missing_or_empty_folder_has_no_candidates(tmp_path, fvocab):
    """A missing folder, or one holding only hidden files, has no candidates."""
    assert rank(tmp_path / "absent", "x", fvocab) == []
    f = touch(tmp_path / "e", ".2025 Black")
    assert rank(f, "2025 Black", fvocab) == []


# --- sport directories and resolution ---------------------------------------------


def test_sport_dir_matches_slug_including_apostrophes(tmp_path):
    """Slugs find "Men's Basketball" and "Women’s Basketball"; with no match the title-cased path is returned."""
    (tmp_path / "Men's Basketball").mkdir()
    (tmp_path / "Women’s Basketball").mkdir()
    (tmp_path / "notes.txt").write_text("")
    assert compose.sport_dir(tmp_path, "mens_basketball") == tmp_path / "Men's Basketball"
    assert compose.sport_dir(tmp_path, "womens_basketball") == tmp_path / "Women’s Basketball"
    assert compose.sport_dir(tmp_path, "field_hockey") == tmp_path / "Field Hockey"


def test_resolve_reports_how_and_has_no_generic_fallback(project, fvocab):
    """resolve() describes the file it chose, and a missing element fails even when a Generic folder exists."""
    put(project, "pants", "front", "2025 Black", "2025 Black 3 Grad")
    put(project, "pants", "front", "Generic Black", "Generic Black")
    path, how = compose.resolve(project, MSU, "football", "pants", "front", "2025 Black", "3", set(), fvocab)
    assert path is not None
    assert path.name == "2025 Black 3 Grad.png"
    assert how == "#3, Grad"
    path, how = compose.resolve(project, MSU, "football", "pants", "front", "2024 Black", None, set(), fvocab)
    assert path is None
    assert how == "no file under Pants Front/2024 Black"


# --- main: placements -------------------------------------------------------------

MINI = tpl(
    "mini",
    [
        {"slot": "helmet", "viewpoint": "front", "x": 50, "y": 0, "z": 10, "requirement": "required"},
        {"slot": "helmet", "viewpoint": "left", "x": 150, "y": 0, "scale": 0.5, "z": 40, "requirement": "explicit"},
        {"slot": "jersey", "viewpoint": "left", "x": 150, "y": 60, "z": 20, "requirement": "if_available"},
    ],
)


def test_places_artwork_top_centre_and_reports_it(project, monkeypatch, capsys):
    """An element is pasted with its top-centre at the placement point, pixel for pixel, and written at 300 DPI."""
    mini(project, MINI)
    src = put(project, "helmet", "front", "2025 Black", "2025 Black", size=(40, 30), seed=3)
    res, out = compose_json(project, monkeypatch, "--view", "mini", "--helmet", "2025 Black")
    got = pixels(out)
    assert got.shape == (120, 200, 4)
    assert np.array_equal(got[0:30, 30:70], pixels(src))
    assert got[30:, :, 3].sum() == 0
    assert got[:, 70:, 3].sum() == 0
    with Image.open(out) as im:
        assert round(im.info["dpi"][0]) == 300
    p = by_label(res)["helmet/front"]
    assert p["status"] == "placed"
    assert p["at"] == [30, 0]
    assert p["size"] == [40, 30]
    assert p["artwork_bbox"] == [30, 0, 70, 30]
    assert p["clipped"] == {}
    assert res["output"] == str(out)
    assert res["missing"] == []
    assert res["canvas"] == [200, 120]
    text = capsys.readouterr().out
    assert "helmet/left" in text
    assert "not requested" in text
    assert "jersey/left" in text
    assert "no element given" in text
    assert f"Wrote {out}" in text


def test_explicit_placement_only_with_helmet_left(project, monkeypatch):
    """The explicit left-helmet inset is placed, at its scale, only when --helmet-left is passed."""
    mini(project, MINI)
    put(project, "helmet", "front", "2025 Black", "2025 Black")
    put(project, "helmet", "left", "2025 Black", "2025 Black", size=(40, 30))
    res, _ = compose_json(project, monkeypatch, "--view", "mini", "--helmet", "2025 Black")
    assert "helmet/left" not in by_label(res)
    res, out = compose_json(project, monkeypatch, "--view", "mini", "--helmet", "2025 Black", "--helmet-left")
    p = by_label(res)["helmet/left"]
    assert p["size"] == [20, 15]
    assert p["at"] == [140, 0]
    assert p["scale"] == 0.5
    assert pixels(out)[0:15, 140:160, 3].min() == 255


def test_if_available_skips_silently_and_is_placed_when_present(project, monkeypatch, capsys):
    """An if_available placement with no file is recorded as skipped without failing; with a file it is placed."""
    mini(project, MINI)
    put(project, "helmet", "front", "1990 White", "1990 White")
    put(project, "jersey", "front", "1990 White", "1990 White")
    res, out = compose_json(project, monkeypatch, "--view", "mini", "--helmet", "1990 White", "--jersey", "1990 White")
    p = by_label(res)["jersey/left"]
    assert p["status"] == "skipped"
    assert p["file"] is None
    assert p["reason"] == "no file under Jerseys Left/1990 White"
    assert out.is_file()
    assert "skipped (absent)" in capsys.readouterr().out
    put(project, "jersey", "left", "1990 White", "1990 White")
    res, _ = compose_json(project, monkeypatch, "--view", "mini", "--helmet", "1990 White", "--jersey", "1990 White")
    assert by_label(res)["jersey/left"]["status"] == "placed"


def test_missing_required_fails_writes_json_but_no_png(project, monkeypatch, capsys):
    """A required placement with no file exits 1, lists the gap, and --json records it with no output."""
    mini(project, MINI)
    put(project, "helmet", "front", "Generic Black", "Generic Black")
    res, out = compose_json(project, monkeypatch, "--view", "mini", "--helmet", "2025 Black", ok=False)
    assert not out.exists()
    assert res["output"] is None
    assert res["missing"] == [{"label": "helmet/front", "reason": "no file under Helmets Front/2025 Black"}]
    assert by_label(res)["helmet/front"]["status"] == "missing"
    text = capsys.readouterr().out
    assert "MISSING" in text
    assert "!! 1 required placements unresolved" in text


def test_missing_required_without_json_still_exits(project, monkeypatch):
    """Without --json a missing required placement still exits 1."""
    mini(project, MINI)
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "--view", "mini", "--helmet", "2025 Black", "--out", str(project / "o.png"))
    assert e.value.code == 1
    assert not (project / "o.png").exists()


def test_required_slot_not_supplied_names_the_flag(project, monkeypatch):
    """A template needing a slot the caller didn't give exits listing what it needs and what's missing."""
    mini(project, MINI)
    with pytest.raises(SystemExit, match=r"Template 'mini' needs these slots: --helmet\nNot supplied: --helmet"):
        run(monkeypatch, "--view", "mini")


def test_unknown_with_token_exits(project, monkeypatch):
    """--with a token not in the sport's vocabulary exits naming it."""
    mini(project, MINI)
    with pytest.raises(SystemExit, match=r"Unknown token\(s\): Glitter\nNot in configs/modifiers_football.yaml"):
        run(monkeypatch, "--view", "mini", "--helmet", "x", "--with", "Glitter")


def test_ranking_flags_pick_the_file_end_to_end(project, monkeypatch):
    """--number, --with and the plainest-file rule decide which file is composed, reported in --json."""
    mini(project, MINI)
    for n in ("2025 Black", "2025 Black 3", "2025 Black 03", "2025 Black 03 Grad"):
        put(project, "helmet", "front", "2025 Black", n)
    cases = {
        (): ("2025 Black.png", None),
        ("--number", "03"): ("2025 Black 03.png", "03"),
        ("--number", "3"): ("2025 Black 3.png", "3"),
        ("--number", "03", "--with", "Grad"): ("2025 Black 03 Grad.png", "03"),
    }
    placed = {}
    for flags, (name, num) in cases.items():
        res, _ = compose_json(project, monkeypatch, "--view", "mini", "--helmet", "2025 Black", *flags)
        p = by_label(res)["helmet/front"]
        assert (p["file"].rsplit("/", 1)[-1], p["number_found"]) == (name, num)
        placed[flags] = p
    # Only the one case passes --with, so name it rather than relying on it being last.
    grad = placed[("--number", "03", "--with", "Grad")]
    assert grad["tokens_requested"] == ["Grad"]
    assert grad["tokens_found"] == ["Grad"]


def test_numbers_resolve_per_viewpoint(project, monkeypatch):
    """A numbered front and an unnumbered back both resolve for the same requested number."""
    mini(
        project,
        tpl(
            "jf",
            [
                {"slot": "jersey", "viewpoint": "front", "x": 50, "y": 0},
                {"slot": "jersey", "viewpoint": "back", "x": 150, "y": 0},
            ],
        ),
    )
    put(project, "jersey", "front", "2025 White", "2025 White 15")
    put(project, "jersey", "front", "2025 White", "2025 White 4")
    put(project, "jersey", "back", "2025 White", "2025 White")
    res, _ = compose_json(project, monkeypatch, "--view", "jf", "--jersey", "2025 White", "--number", "15")
    got = by_label(res)
    assert got["jersey/front"]["number_found"] == "15"
    assert got["jersey/back"]["number_found"] is None
    assert got["jersey/back"]["status"] == "placed"


def test_player_flag_reported_in_json(project, monkeypatch):
    """--player chooses the surname's file and --json reports the player requested and found."""
    mini(project, tpl("bj", [{"slot": "jersey", "viewpoint": "front", "x": 50, "y": 0}], sport="baseball"))
    for n in ("2014 White 85s 18 Girodo", "2014 White 85s 18 Heck"):
        put(project, "jersey", "front", "2014 White 85s", n, sport="Baseball")
    res, _ = compose_json(
        project, monkeypatch, "--sport", "baseball", "--view", "bj", "--jersey", "2014 White 85s", "--number", "18"
    )
    assert by_label(res)["jersey/front"]["player_found"] == "Girodo"
    res, _ = compose_json(
        project,
        monkeypatch,
        "--sport",
        "baseball",
        "--view",
        "bj",
        "--jersey",
        "2014 White 85s",
        "--number",
        "18",
        "--player",
        "Heck",
    )
    p = by_label(res)["jersey/front"]
    assert (p["player_requested"], p["player_found"]) == ("Heck", "Heck")


# --- combos -----------------------------------------------------------------------

COMBO = tpl(
    "combo",
    [
        {"slot": "jersey", "viewpoint": "front", "x": 50, "y": 0, "z": 20},
        {"slot": "jersey", "viewpoint": "front", "x": 150, "y": 0, "z": 120, "uniform": 2},
    ],
)


def test_combo_needs_two_uniforms(project, monkeypatch):
    """A combo template without the `2` flags exits saying it needs two uniforms."""
    mini(project, COMBO)
    with pytest.raises(SystemExit, match=r"needs TWO uniforms: --jersey, --jersey2\nNot supplied: --jersey2"):
        run(monkeypatch, "--view", "combo", "--jersey", "2025 White")


def test_combo_second_uniform_inherits_number_tokens_and_player(project, monkeypatch, capsys):
    """Uniform 2 uses uniform 1's number, --with and --player unless its own are given."""
    mini(project, COMBO)
    for n in ("2025 White 7", "2025 White 7 Grad"):
        put(project, "jersey", "front", "2025 White", n)
    for n in ("2025 Maroon 7 Grad", "2025 Maroon 9", "2025 Maroon 7"):
        put(project, "jersey", "front", "2025 Maroon", n)
    res, _ = compose_json(
        project, monkeypatch, "--view", "combo", "--jersey", "2025 White", "--jersey2", "2025 Maroon", "--number", "7"
    )
    assert "uniform 2 number=7" in capsys.readouterr().out
    got = by_label(res)
    assert got["jersey/front"]["file"].endswith("2025 White 7.png")
    assert got["jersey/front #2"]["file"].endswith("2025 Maroon 7.png")
    assert got["jersey/front #2"]["uniform"] == 2
    res, _ = compose_json(
        project,
        monkeypatch,
        "--view",
        "combo",
        "--jersey",
        "2025 White",
        "--jersey2",
        "2025 Maroon",
        "--number",
        "7",
        "--with",
        "Grad",
    )
    assert by_label(res)["jersey/front #2"]["file"].endswith("2025 Maroon 7 Grad.png")
    res, _ = compose_json(
        project,
        monkeypatch,
        "--view",
        "combo",
        "--jersey",
        "2025 White",
        "--jersey2",
        "2025 Maroon",
        "--number",
        "7",
        "--with",
        "Grad",
        "--number2",
        "9",
        "--with2",
        "SEC",
        "--player2",
        "Nobody",
    )
    got = by_label(res)
    assert got["jersey/front"]["file"].endswith("2025 White 7 Grad.png")
    p2 = got["jersey/front #2"]
    assert p2["file"].endswith("2025 Maroon 9.png")
    assert (p2["number_requested"], p2["tokens_requested"], p2["player_requested"]) == ("9", ["SEC"], "Nobody")


def test_element_flag_sets_slots_for_either_uniform(project, monkeypatch):
    """--element SLOT=NAME and SLOT2=NAME fill uniform 1 and 2 like the per-slot flags."""
    mini(project, COMBO)
    put(project, "jersey", "front", "2025 White", "2025 White")
    put(project, "jersey", "front", "2025 Maroon", "2025 Maroon")
    res, _ = compose_json(
        project,
        monkeypatch,
        "--view",
        "combo",
        "--element",
        " jersey = 2025 White ",
        "--element",
        "jersey2=2025 Maroon",
    )
    got = by_label(res)
    assert got["jersey/front"]["element"] == "2025 White"
    assert got["jersey/front #2"]["element"] == "2025 Maroon"


def test_element_flag_without_equals_exits(project, monkeypatch):
    """--element without SLOT=NAME exits quoting what it got."""
    mini(project, COMBO)
    with pytest.raises(SystemExit, match="--element expects SLOT=NAME, got 'jersey'"):
        run(monkeypatch, "--view", "combo", "--element", "jersey")


# --- clipping, blank artwork, rotation -----------------------------------------------


def test_clipping_is_judged_on_artwork_not_padding(project, monkeypatch, capsys):
    """Transparent padding past the edge is not clipping; opaque artwork past it is reported per side."""
    mini(project, tpl("edge", [{"slot": "helmet", "viewpoint": "front", "x": 50, "y": 0}], w=200, h=40))
    put(project, "helmet", "front", "Padded", "Padded", size=(120, 30), content=(80, 30))
    put(project, "helmet", "front", "Wide", "Wide", size=(120, 50), content=(120, 50))
    res, _ = compose_json(project, monkeypatch, "--view", "edge", "--helmet", "Padded")
    p = by_label(res)["helmet/front"]
    assert p["at"] == [-10, 0]
    assert p["artwork_bbox"] == [10, 0, 90, 30]
    assert p["clipped"] == {}
    capsys.readouterr()
    res, _ = compose_json(project, monkeypatch, "--view", "edge", "--helmet", "Wide")
    assert by_label(res)["helmet/front"]["clipped"] == {"L": 10, "B": 10}
    assert "CLIPPED L10,B10" in capsys.readouterr().out


def test_fully_transparent_artwork_is_placed_without_bbox(project, monkeypatch):
    """An element with no opaque pixels is placed with an empty artwork bbox and no clipping."""
    mini(project, tpl("edge", [{"slot": "helmet", "viewpoint": "front", "x": 50, "y": 0}]))
    path = project / "Football" / MSU / "Helmets Front" / "Blank" / "Blank.png"
    path.parent.mkdir(parents=True)
    Image.new("RGBA", (30, 30), (0, 0, 0, 0)).save(path)
    res, _ = compose_json(project, monkeypatch, "--view", "edge", "--helmet", "Blank")
    p = by_label(res)["helmet/front"]
    assert p["status"] == "placed"
    assert p["artwork_bbox"] == [0, 0, 0, 0]
    assert p["clipped"] == {}


@pytest.mark.parametrize("key", ["rotation", "rotate"])
def test_rotation_pivots_on_the_top_centre_anchor(project, monkeypatch, capsys, key):
    """A clockwise rotation swings the element about its top-centre anchor, which stays on the placement point."""
    mini(project, tpl("spin", [{"slot": "pants", "viewpoint": "left", "x": 100, "y": 60, key: 90}], w=200, h=200))
    path = project / "Football" / MSU / "Pants Left" / "2025 Black" / "2025 Black.png"
    path.parent.mkdir(parents=True)
    a = np.zeros((60, 30, 4), np.uint8)
    a[:, :] = (0, 0, 255, 255)
    a[0:6, 12:18] = (255, 0, 0, 255)  # marker at the top-centre anchor
    Image.fromarray(a).save(path)
    res, out = compose_json(project, monkeypatch, "--view", "spin", "--pants", "2025 Black")
    p = by_label(res)["pants/left"]
    assert p["rotation"] == 90
    assert p["size"] == [60, 30]
    got = pixels(out)
    red = (got[..., 0] > 200) & (got[..., 2] < 50) & (got[..., 3] > 200)
    ys, xs = np.where(red)
    # Turned 90deg clockwise, the top edge faces right: the marker ends at x=100, centred on y=60.
    assert abs(xs.max() + 1 - 100) <= 1
    assert abs(ys.mean() + 0.5 - 60) <= 1
    blue = (got[..., 2] > 200) & (got[..., 3] > 200)
    assert np.where(blue)[1].min() >= 38  # body extends left of the anchor, 60px long
    assert "rot 90deg" in capsys.readouterr().out


# --- --diff -------------------------------------------------------------------------


def test_diff_against_identical_reference(project, monkeypatch, capsys):
    """A reference equal to the composite reports zero differing pixels and writes no diff image."""
    mini(project, MINI)
    put(project, "helmet", "front", "2025 Black", "2025 Black")
    out = project / "out" / "c.png"
    run(monkeypatch, "--view", "mini", "--helmet", "2025 Black", "--out", str(out))
    ref = project / "ref.png"
    ref.write_bytes(out.read_bytes())
    capsys.readouterr()
    run(monkeypatch, "--view", "mini", "--helmet", "2025 Black", "--out", str(out), "--diff", str(ref))
    text = capsys.readouterr().out
    assert "reference (200, 120)  composed (200, 120)" in text
    assert "differing pixels: 0 of 1,200 inked (0.00%)" in text
    assert not (project / "out" / "c-diff.png").exists()


def test_diff_writes_a_mask_of_differences(project, monkeypatch, capsys):
    """A reference that differs gets its differing span reported and a diff mask written next to the output."""
    mini(project, MINI)
    put(project, "helmet", "front", "2025 Black", "2025 Black", seed=1)
    ref = project / "ref.png"
    Image.new("RGBA", (200, 120), (0, 0, 0, 0)).save(ref)
    out = project / "out" / "c.png"
    run(monkeypatch, "--view", "mini", "--helmet", "2025 Black", "--out", str(out), "--diff", str(ref))
    text = capsys.readouterr().out
    assert "differing pixels:" in text
    assert "differences span x 30-69, y 0-29" in text
    mask = pixels(project / "out" / "c-diff.png")
    assert mask.shape[:2] == (120, 200)


def test_diff_scales_a_reference_of_another_size(project, monkeypatch, capsys):
    """A reference of a different size is scaled to the composite before comparing."""
    mini(project, MINI)
    put(project, "helmet", "front", "2025 Black", "2025 Black")
    ref = project / "ref.png"
    Image.new("RGBA", (100, 60), (0, 0, 0, 0)).save(ref)
    run(monkeypatch, "--view", "mini", "--helmet", "2025 Black", "--out", str(project / "c.png"), "--diff", str(ref))
    assert "sizes differ — scaling reference to compare" in capsys.readouterr().out


def test_diff_missing_reference_exits_after_writing(project, monkeypatch):
    """A missing reference exits naming it, after the composite itself has been written."""
    mini(project, MINI)
    put(project, "helmet", "front", "2025 Black", "2025 Black")
    with pytest.raises(SystemExit, match="Reference not found"):
        run(monkeypatch, "--view", "mini", "--helmet", "2025 Black", "--out", "c.png", "--diff", "nope.png")
    assert (project / "c.png").is_file()


# --- real templates ------------------------------------------------------------------


def test_real_football_full_template(project, monkeypatch, cfg, templates):
    """The real football `full` view places every element at its template point, the inset at its scale."""
    tp = next(t for t in templates if t["sport"] == "football" and t["view_kind"] == "full")
    sizes = {
        ("helmet", "front"): canvas_size(cfg, "football_helmet_face"),
        ("helmet", "back"): canvas_size(cfg, "football_helmet_face"),
        ("helmet", "right"): canvas_size(cfg, "football_helmet_profile"),
        ("helmet", "left"): canvas_size(cfg, "football_helmet_profile"),
        ("jersey", "front"): canvas_size(cfg, "football_jersey"),
        ("jersey", "back"): canvas_size(cfg, "football_jersey"),
        ("jersey", "left"): canvas_size(cfg, "football_jersey_sleeve"),
        ("pants", "front"): canvas_size(cfg, "football_pants_front"),
        ("pants", "left"): canvas_size(cfg, "football_pants_side"),
    }
    for i, ((slot, vp), size) in enumerate(sizes.items()):
        put(project, slot, vp, "2025 Black", "2025 Black", size=size, content=(50, 40), top=5, seed=i)
    res, out = compose_json(
        project,
        monkeypatch,
        "--view",
        "full",
        "--helmet",
        "2025 Black",
        "--jersey",
        "2025 Black",
        "--pants",
        "2025 Black",
        "--helmet-left",
    )
    assert res["canvas"] == [tp["output"]["width"], tp["output"]["height"]]
    got = by_label(res)
    assert len(got) == len(tp["placements"])
    for p in tp["placements"]:
        r = got[f"{p['slot']}/{p['viewpoint']}"]
        w, h = sizes[(p["slot"], p["viewpoint"])]
        s = p.get("scale", 1.0)
        assert r["size"] == [round(w * s), round(h * s)]
        assert r["at"] == [int(p["x"] - round(w * s) / 2), int(p["y"])]
        assert r["clipped"] == {}
    with Image.open(out) as im:
        assert im.size == (tp["output"]["width"], tp["output"]["height"])


def test_mens_basketball_finds_the_apostrophe_directory(project, monkeypatch, cfg):
    """`--sport mens_basketball` composes from "Men's Basketball/", which title-casing would never find."""
    w, h = canvas_size(cfg, "mbk_jersey")
    for vp in ("front", "back"):
        put(
            project, "jersey", vp, "2025 Maroon", "2025 Maroon", size=(w, h), content=(30, 30), sport="Men's Basketball"
        )
    res, out = compose_json(
        project, monkeypatch, "--sport", "mens_basketball", "--view", "mbk-jersey", "--jersey", "2025 Maroon"
    )
    assert out.is_file()
    assert all("/Men's Basketball/" in p["file"] for p in res["placements"])


# --- entry points ------------------------------------------------------------------------


def test_unknown_view_exits(project, monkeypatch):
    """A sport/view with no template exits naming both."""
    with pytest.raises(SystemExit, match="No template for football/nope"):
        run(monkeypatch, "--view", "nope")


def test_find_root_walks_up_and_fails_cleanly(project, tmp_path, monkeypatch):
    """Without --root the project is found above cwd; with none above, compose exits."""
    sub = project / "a" / "b"
    sub.mkdir(parents=True)
    assert compose.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    monkeypatch.chdir(lone)
    with pytest.raises(SystemExit, match="No configs/view_templates.yaml above"):
        run(monkeypatch, "--view", "mini")


def test_root_flag_and_script_entry_point(project, tmp_path, monkeypatch):
    """Run as `__main__` from elsewhere with --root, compose reads that project's templates."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["compose.py", "--root", str(project), "--view", "nope"])
    with pytest.raises(SystemExit, match="No template for football/nope"):
        runpy.run_path(SCRIPT, run_name="__main__")


def test_missing_dependencies_exit_with_a_hint(monkeypatch):
    """Without PyYAML or Pillow the script exits telling the user to run `uv sync`."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(SystemExit, match="uv sync"):
        runpy.run_path(SCRIPT, run_name="compose_noimport")
