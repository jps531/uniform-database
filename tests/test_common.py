"""Tests for scripts/pipeline/common.py: the project root, config, sport directories, vocabulary, eras, artwork and the PNG walker."""

import argparse
import io
import runpy
import sys

import common
import pytest
import yaml
from conftest import REPO, art, era
from PIL import Image

# --- the project -------------------------------------------------------------


def test_find_root_walks_up_and_exits_naming_the_marker(project, tmp_path):
    """find_root() finds configs/canvas_definitions.yaml above a subdirectory, and exits naming it when there is none."""
    sub = project / "a" / "b"
    sub.mkdir(parents=True)
    assert common.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(SystemExit, match="No configs/canvas_definitions.yaml in .*lone or any directory above it"):
        common.find_root(lone)


def test_root_from_uses_root_flag_else_the_cwd(project, tmp_path, monkeypatch):
    """root_from() takes --root (user-expanded, resolved) when given, else finds the project above the cwd."""
    ap = argparse.ArgumentParser()
    common.add_root_arg(ap)
    assert common.root_from(ap.parse_args([])) == project
    monkeypatch.chdir(tmp_path)
    assert common.root_from(ap.parse_args(["--root", str(project / "x" / "..")])) == project
    assert "canvas_definitions.yaml" in ap.format_help()


def test_resolve_takes_relative_paths_from_the_root(project, tmp_path, monkeypatch):
    """A relative path argument is read from the project root, not the cwd; an absolute one is kept."""
    monkeypatch.chdir(tmp_path)
    assert common.resolve("Football/T", project) == project / "Football" / "T"
    assert common.resolve(str(tmp_path / "x"), project) == tmp_path / "x"


def test_load_yaml_and_config(tmp_path):
    """load_yaml() parses a file (an empty one is None); load_config() is the real canvas config."""
    (tmp_path / "a.yaml").write_text("k: [1, 2]\n")
    (tmp_path / "e.yaml").write_text("")
    assert common.load_yaml(tmp_path / "a.yaml") == {"k": [1, 2]}
    assert common.load_yaml(tmp_path / "e.yaml") is None
    assert "profiles" in common.load_config(REPO)


def test_tolerance_comes_from_config_and_is_never_guessed(cfg):
    """tolerance() returns the config's value, and exits clearly when the config has none rather than defaulting."""
    assert common.tolerance(cfg) == cfg["tolerance"] == 5
    with pytest.raises(SystemExit, match="No `tolerance` in configs/canvas_definitions.yaml"):
        common.tolerance({k: v for k, v in cfg.items() if k != "tolerance"})


def test_slot_dirs_inverts_directory_slots(cfg):
    """slot_dirs() maps each slot to its directory word, from `directory_slots`."""
    dirs = common.slot_dirs(cfg)
    assert dirs["helmet"] == "Helmets"
    assert dirs["jersey"] == "Jerseys"
    assert dirs["court"] == "Courts"
    assert set(dirs) == set(cfg["directory_slots"].values())


# --- sports ------------------------------------------------------------------


def test_sport_slug_drops_straight_and_curly_apostrophes():
    """Directory names slug to config keys: lowercase, apostrophes of either kind dropped, spaces to underscores."""
    assert common.sport_slug("Men's Basketball") == "mens_basketball"
    assert common.sport_slug("Women’s Basketball") == "womens_basketball"
    assert common.sport_slug("Football") == "football"


def test_sport_dir_matches_by_slug_under_any_parent(tmp_path):
    """sport_dir() finds "Men's Basketball" and Venues/Basketball by slug, and is None when nothing matches."""
    (tmp_path / "Men's Basketball").mkdir()
    (tmp_path / "Venues" / "Basketball").mkdir(parents=True)
    (tmp_path / "football").write_text("a file, not a directory")
    assert common.sport_dir(tmp_path, "mens_basketball") == tmp_path / "Men's Basketball"
    assert common.sport_dir(tmp_path / "Venues", "basketball") == tmp_path / "Venues" / "Basketball"
    assert common.sport_dir(tmp_path, "football") is None
    assert common.sport_dir(tmp_path, "field_hockey") is None
    assert common.sport_dir(tmp_path / "nowhere", "basketball") is None


# --- vocabulary --------------------------------------------------------------


def vocab_files(project, files: dict):
    """Replace the project's configs link with a directory holding only these modifiers files (name -> dict)."""
    d = project / "configs"
    d.unlink()
    d.mkdir()
    for name, data in files.items():
        (d / f"modifiers_{name}.yaml").write_text(yaml.safe_dump(data) if data is not None else "")


def test_vocabulary_follows_the_extends_chain_and_merges_colorways(project):
    """Tokens merge down the chain with the nearest file winning; colorways merge base first, without repeats."""
    vocab_files(
        project,
        {
            "base": {"tokens": {"a": {"token": "A1"}, "b": {"token": "B1"}}, "colorways": ["maroon", "purple"]},
            "mid": {"extends": "base", "tokens": {"b": {"token": "B2"}}, "colorways": ["white", "maroon"]},
            "top": {"extends": "mid", "tokens": {"c": {"token": "C3"}}},
        },
    )
    v = common.load_vocabulary(project, "top")
    assert v.tokens == {"a": {"token": "A1"}, "b": {"token": "B2"}, "c": {"token": "C3"}}
    assert v.colorways == ["maroon", "purple", "white"]


def test_real_baseball_keeps_shared_colorways():
    """Baseball lists its own colorways and still has shared's purple; softball reaches both through baseball."""
    for sport in ("baseball", "softball"):
        colorways = common.load_vocabulary(REPO, sport).colorways
        assert {"purple", "teal", "maroon"} <= set(colorways)
        assert len(colorways) == len(set(colorways))
    assert "NCAA" in {common.token_name(t) for t in common.load_vocabulary(REPO, "softball").tokens.values()}


def test_vocabulary_cycle_and_missing_files_exit(project):
    """A loop in `extends` exits naming where it closes; a missing file exits naming it and what extended it."""
    vocab_files(project, {"a": {"extends": "b"}, "b": {"extends": "a"}, "c": {"extends": "gone"}, "blank": None})
    with pytest.raises(SystemExit, match="Circular `extends` reaching modifiers_a.yaml"):
        common.load_vocabulary(project, "a")
    with pytest.raises(SystemExit, match=r"No vocabulary at configs/modifiers_gone.yaml \(extended by modifiers_c"):
        common.load_vocabulary(project, "c")
    with pytest.raises(SystemExit, match=r"No vocabulary at configs/modifiers_curling.yaml$"):
        common.load_vocabulary(project, "curling")
    assert common.load_vocabulary(project, "blank") == common.Vocabulary({}, [])


def test_token_name_and_longest_first_order():
    """A token's name is its token, else its label; longest_first is longest first, alphabetical within a length."""
    assert common.token_name({"token": "SBC", "label": "Sun Belt"}) == "SBC"
    assert common.token_name({"label": "Grad"}) == "Grad"
    assert common.token_name({"scope": "patch"}) is None
    assert common.longest_first({"NCAA", "Grad", "Egg Bowl", "SEC", "Bowl", "Grad"}) == [
        "Egg Bowl",
        "Bowl",
        "Grad",
        "NCAA",
        "SEC",
    ]


def test_known_colorways_reads_keys_tokens_and_labels(project):
    """known_colorways() holds every key (underscores as spaces), token and label, lowercased; empty with no file."""
    c = common.known_colorways(project)
    assert {"maroon", "dark gray", "powder", "powder blue"} <= c
    (project / "configs").unlink()
    (project / "configs").mkdir()
    assert common.known_colorways(project) == set()
    (project / "configs" / "slots_global.yaml").write_text("colorways:\n  red:\n  vegas_gold: {label: Old Gold}\n")
    assert common.known_colorways(project) == {"red", "vegas gold", "old gold"}


# --- eras --------------------------------------------------------------------


def test_closest_era_wins_inside_overlapping_windows(cfg):
    """Helmet backs E (667) and E2 (674) overlap at tolerance 5: 670 takes E (3px), 671 takes E2 (3px vs 4px)."""
    profile = cfg["profiles"]["football-helmet-back"]
    tol = common.tolerance(cfg)
    h = era(cfg, "football-helmet-back", "E")["size"][1]
    assert common.match_era(profile, (670, h), tol)["era"] == "E"
    assert common.match_era(profile, (671, h), tol)["era"] == "E2"
    assert common.match_era(profile, (674 + tol, h), tol)["era"] == "E2"
    assert common.match_era(profile, (674 + tol + 1, h), tol) is None


def test_ties_go_to_the_first_listed_era():
    """Two eras equally close to a size: the one listed first wins."""
    profile = [{"era": "x", "size": [10, 10]}, {"era": "y", "size": [14, 10]}, {"era": "z", "size": [12, 12]}]
    assert common.match_era(profile, (12, 10), 3)["era"] == "x"
    assert common.match_era(profile, (12, 11), 3)["era"] == "z"
    assert common.match_era(None, (12, 10), 3) is None


def test_post_scale_matches_what_the_scale_produces(cfg):
    """With post_scale a size is compared with each era's size after its scale; scaled_eras lists only scaled ones."""
    profile = cfg["profiles"]["football-helmet-right"]
    tol = common.tolerance(cfg)
    f = era(cfg, "football-helmet-right", "F")
    post = common.era_size(f, post_scale=True)
    assert post == (round(f["size"][0] * f["scale"]), round(f["size"][1] * f["scale"]))
    assert common.era_size(f) == tuple(f["size"])
    assert common.match_era(profile, post, tol, post_scale=True)["era"] == "F"
    assert common.match_era(profile, tuple(f["size"]), tol, post_scale=True) is None
    assert common.match_era(profile, tuple(f["size"]), tol)["era"] == "F"
    plain = [{"era": "p", "size": [5, 5]}, {"era": "s", "size": [10, 10], "scale": 0.5}]
    assert common.scaled_eras(plain) == [plain[1]]
    assert common.scaled_eras(None) == []
    assert common.era_size(plain[0], post_scale=True) == (5, 5)


def test_standard_canvases_are_the_slot_and_era_canvases_but_not_fill(cfg):
    """standard_canvases() is the padded slot canvas plus every era canvas override, never a `fills: fill` one."""
    slot = cfg["assignments"]["soccer"]["jersey"]["front"]
    got = common.standard_canvases(cfg, cfg["canvases"][slot], cfg["profiles"]["soccer-jersey-front"])
    ls = cfg["canvases"]["soccer_jersey_ls"]
    assert got == {(cfg["canvases"][slot]["width"], cfg["canvases"][slot]["height"]), (ls["width"], ls["height"])}
    sleeve = cfg["canvases"]["football_jersey_sleeve"]
    assert (
        common.standard_canvases(cfg, sleeve, [{"era": "x", "size": [1, 1], "canvas": "football_jersey_sleeve"}])
        == set()
    )
    assert common.standard_canvases(cfg, None, None) == set()


# --- artwork -----------------------------------------------------------------


def rotated(path, size, content):
    """Save a PNG of `size` whose EXIF says to rotate it 90 degrees (orientation 6), as Finder's "rotate" does."""
    buf = io.BytesIO()
    art(path, size, content)
    with Image.open(path) as im:
        exif = im.getexif()
        exif[0x0112] = 6
        im.save(buf, format="PNG", exif=exif.tobytes())
    path.write_bytes(buf.getvalue())
    return path


def test_open_rgba_applies_orientation_and_closes(tmp_path):
    """open_rgba() yields an RGBA image turned by its EXIF orientation, and the measuring helpers see it turned."""
    p = rotated(tmp_path / "r.png", (30, 10), (20, 4))
    with common.open_rgba(p) as im:
        assert im.mode == "RGBA"
        assert im.size == (10, 30)
    assert common.content_box(p) == ((10, 30), (6, 5, 10, 25))
    assert common.content_size(p) == (4, 20)


def test_blank_file_has_no_content(tmp_path):
    """A fully transparent file has no box and no content size, not the whole image's."""
    p = art(tmp_path / "b.png", (9, 7), (0, 0))
    assert common.content_box(p) == ((9, 7), None)
    assert common.content_size(p) is None
    with common.open_rgba(p) as im:
        assert common.alpha_box(im) is None


def test_pngs_skips_hidden_parts_below_the_root_only(tmp_path):
    """pngs() skips dot-files (AppleDouble ._x.png too) and dot-folders below its root, never the root's own path."""
    root = tmp_path / ".claude" / "worktree"
    for rel in ("b/2.png", "a/1.png", "a/._1.png", ".hidden/3.png", "a/.x/4.png", "top.png", "a/n.txt"):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"")
    assert [p.relative_to(root).as_posix() for p in common.pngs(root)] == ["a/1.png", "b/2.png", "top.png"]
    assert [p.name for p in common.pngs(root / "a", recursive=False)] == ["1.png"]
    assert common.pngs(tmp_path / "missing") == []


def test_missing_dependencies_exit_with_a_hint(monkeypatch):
    """Without PyYAML the module exits telling the user to run `uv sync`, before any script uses it."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(SystemExit, match="uv sync"):
        runpy.run_path(str(REPO / "scripts" / "pipeline" / "common.py"), run_name="common_noimport")
