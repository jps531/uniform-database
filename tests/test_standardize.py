"""Tests for scripts/pipeline/standardize.py: path parsing, era matching, survey, and pad's writes and refusals."""

import copy
import json
import re
from pathlib import Path

import common
import numpy as np
import pytest
import standardize
from helpers import art, bbox, blank, canvas_size, era, main, override_configs, pixels, scaled, small_configs
from PIL import Image

HELMET_FRONT = "Football/T/Helmets Front"


def size_line(size, n, tag) -> str:
    """One line of survey's size table, formatted as survey prints it."""
    return f"  {size[0]:>5} x {size[1]:<5}  {n:>4} files{tag}"


def custom_config(project: Path, cfg: dict, mutate) -> dict:
    """Write mutate(copy of cfg) as the project's canvas_definitions.yaml; returns the new cfg."""
    new = copy.deepcopy(cfg)
    mutate(new)
    override_configs(project, {"canvas_definitions.yaml": new})
    return new


def tiny_sport(c: dict) -> None:
    """Add a small synthetic sport `test` whose jersey-front eras exercise canvas overrides, offsets and anchors."""
    c["canvases"]["tiny"] = {"width": 40, "height": 30, "fills": "pad"}
    c["canvases"]["tiny_wide"] = {"width": 60, "height": 30, "fills": "pad"}
    c["canvases"]["tiny_blank"] = {"fills": "pad"}
    c["assignments"]["test"] = {"jersey": {"front": "tiny"}}
    c["profiles"]["test-jersey-front"] = [
        {"era": "std", "size": [38, 28]},
        {"era": "wide", "size": [58, 28], "canvas": "tiny_wide"},
        {"era": "nocanvas", "size": [20, 20], "canvas": "missing"},
        {"era": "blank", "size": [26, 26], "canvas": "tiny_blank"},
        {"era": "shift", "size": [10, 10], "anchor": "top-left", "dx": 3, "dy": 2},
    ]


# ---------------------------------------------------------------- helpers


def test_sport_slug_drops_apostrophes_and_underscores_spaces():
    """Sport directory names slug to the assignments key, straight or curly apostrophe."""
    assert standardize.sport_slug("Men's Basketball") == "mens_basketball"
    assert standardize.sport_slug("Women’s Basketball") == "womens_basketball"


def test_find_root_walks_up_and_exits_when_absent(project, tmp_path):
    """find_root finds the project from a subdirectory and exits when no config is above."""
    sub = project / "a" / "b"
    sub.mkdir(parents=True)
    assert common.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(SystemExit, match=r"No configs/canvas_definitions\.yaml in"):
        common.find_root(lone)


def test_resolve_takes_relative_paths_from_root(project, tmp_path):
    """Relative arguments resolve against the root, absolute ones stay put."""
    assert standardize.resolve("Football/x", project) == (project / "Football/x").resolve()
    assert standardize.resolve(str(tmp_path / "abs"), project) == (tmp_path / "abs").resolve()


def test_parse_dest_variants(project, cfg):
    """parse_dest reads sport/team/slot/viewpoint, matches the viewpoint anywhere, and rejects non-trees."""
    p = standardize.parse_dest
    assert p(project / "Men's Basketball/MSU/Shorts Left", project, cfg) == ("mens_basketball", "MSU", "shorts", "left")
    assert p(project / "Football/T/Jerseys Old Front STD", project, cfg) == ("football", "T", "jersey", "front")
    assert p(project / "Marks/Football/T/Helmets Left", project, cfg) == ("football", "T", "helmet", "left")
    assert p(project / "Venues/Basketball/MSU/Courts Full", project, cfg) == ("basketball", "MSU", "court", "full")
    # undeclared viewpoint falls back to the first word after the slot
    assert p(project / "Football/T/Helmets Side X", project, cfg) == ("football", "T", "helmet", "side")
    assert p(Path("/elsewhere/Football/T/Helmets Front"), project, cfg) is None
    assert p(project / "Football/T", project, cfg) is None
    assert p(project / "Football/T/Helmets", project, cfg) is None
    assert p(project / "Football/T/Gloves Front", project, cfg) is None


def test_lookup_is_keyed_by_sport(cfg):
    """lookup returns the sport-qualified canvas and profile, or None for either when absent."""
    canvas, profile, names = standardize.lookup(cfg, "football", "helmet", "front")
    assert names == ("football_helmet_face", "football-helmet-front")
    assert canvas is not None
    assert (canvas["width"], canvas["height"]) == canvas_size(cfg, "football_helmet_face")
    assert profile == cfg["profiles"]["football-helmet-front"]
    canvas, profile, names = standardize.lookup(cfg, "football", "helmet", "side")
    assert canvas is None
    assert profile is None
    assert names == (None, "football-helmet-side")


def test_pngs_skips_hidden_files_and_directories(tmp_path):
    """pngs yields visible PNGs only, sorted."""
    for rel in ("b/x.png", "a/y.png", ".hidden/z.png", "a/.w.png", "a/n.txt"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"")
    assert [p.relative_to(tmp_path).as_posix() for p in standardize.pngs(tmp_path)] == ["a/y.png", "b/x.png"]


def test_measure_of_opaque_and_empty_images(tmp_path):
    """measure returns an open image's alpha bbox and its size, or (None, None) for a blank image."""
    with Image.open(art(tmp_path / "a.png", (20, 10), (6, 4), top=2)) as im:
        assert standardize.measure(im.convert("RGBA")) == ((7, 2, 13, 6), (6, 4))
    assert standardize.measure(Image.new("RGBA", (5, 5))) == (None, None)


def test_match_era_within_tolerance_only(cfg):
    """match_era accepts a size up to `tolerance` off on each axis and rejects one pixel beyond."""
    tol = cfg["tolerance"]
    profile = cfg["profiles"]["football-helmet-front"]
    w, h = era(cfg, "football-helmet-front", "B")["size"]
    matched = standardize.match_era(profile, (w + tol, h - tol), tol)
    assert matched is not None
    assert matched["era"] == "B"
    assert standardize.match_era(profile, (w + tol + 1, h), tol) is None
    assert standardize.match_era(profile, (w, h - tol - 1), tol) is None


# ---------------------------------------------------------------- survey


def test_survey_reports_sizes_eras_and_margins(project, cfg, monkeypatch, capsys):
    """survey lists each content size with its era, flags UNMATCHED and counts margined files."""
    a = era(cfg, "football-helmet-front", "A")["size"]
    b = era(cfg, "football-helmet-front", "B")["size"]
    src = project / HELMET_FRONT
    art(src / "1990 White" / "helmet.png", a)
    art(src / "2000 White" / "helmet.png", (b[0] + 10, b[1] + 6), b, top=3)
    art(src / "2001 White" / "helmet.png", b, seed=1)
    art(src / "2002 White" / "helmet.png", (50, 50))
    blank(src / "2003 White" / "blank.png", (40, 40))
    main(monkeypatch, standardize, "survey", HELMET_FRONT)
    out = capsys.readouterr().out
    assert "5 PNGs under Helmets Front" in out
    assert "sport=football team=T slot=helmet viewpoint=front" in out
    assert "canvas=football_helmet_face  profile=football-helmet-front" in out
    assert "3 distinct CONTENT sizes" in out
    assert size_line(b, 2, "  -> era B") in out
    assert size_line(a, 1, "  -> era A") in out
    assert size_line((50, 50), 1, "  -> UNMATCHED") in out
    assert "1 files carry transparent margin" in out
    assert f"Largest content: {a[0]} x {a[1]}" in out
    assert "Elements at each size" not in out
    assert "NOTE" not in out


def test_survey_suggests_largest_post_scale_content_plus_the_margin(project, cfg, monkeypatch, capsys):
    """survey suggests a canvas sized by the 1px rule from post-scale content, not one with ~12% headroom."""
    a = era(cfg, "football-jersey-front", "A")
    b = era(cfg, "football-jersey-front", "B")["size"]
    src = project / "Football/T/Jerseys Front"
    art(src / "1950 White" / "j.png", a["size"])
    art(src / "1970 White" / "j.png", b, seed=1)
    main(monkeypatch, standardize, "survey", "Football/T/Jerseys Front")
    out = capsys.readouterr().out
    post_w = max(scaled(a)[0], b[0])
    post_h = max(scaled(a)[1], b[1])
    assert f"Largest content after era scale: {post_w} x {post_h}" in out
    assert f"Suggested canvas: {post_w + 2} x {post_h}" in out
    assert "headroom" not in out


def test_survey_suggestion_honours_era_anchor_and_offsets(project, cfg, monkeypatch, capsys):
    """survey's suggestion places each size at its era's anchor and dx/dy, and says when an offset fits no canvas."""

    def mutate(c):
        """tiny_sport, plus an era whose negative dx pushes left-anchored content off the canvas."""
        tiny_sport(c)
        c["profiles"]["test-jersey-front"].append({"era": "off", "size": [16, 3], "anchor": "top-left", "dx": -1})
        c["profiles"]["test-jersey-front"].append({"era": "mid", "size": [50, 50], "anchor": "middle-right"})

    custom_config(project, cfg, mutate)
    src = project / "Test/T/Jerseys Front"
    art(src / "a" / "j.png", (10, 10))  # era shift: top-left, dx 3, dy 2
    art(src / "b" / "j.png", (16, 3))  # era off
    art(src / "c" / "j.png", (50, 50))  # era mid: right edge, centred vertically
    main(monkeypatch, standardize, "survey", "Test/T/Jerseys Front")
    out = capsys.readouterr().out
    assert "Suggested canvas: 50 x 52" in out
    assert "fit no canvas" in out


def test_survey_elements_and_profile_override(project, cfg, monkeypatch, capsys):
    """--profile overrides the path's profile and --elements lists the elements at each size."""
    b = era(cfg, "football-helmet-back", "BCD")["size"]
    src = project / "temp" / "helmets"
    art(src / "2010 White" / "h.png", b)
    art(src / "2011 Black" / "h.png", b)
    blank(src / "2012 Black" / "blank.png", (9, 9))
    main(monkeypatch, standardize, "survey", "temp/helmets", "--profile", "football-helmet-back", "--elements")
    out = capsys.readouterr().out
    assert "profile=football-helmet-back (override)" in out
    assert "-> era BCD" in out
    assert f"{b[0]} x {b[1]}  (2 elements)" in out
    assert "      2010 White" in out
    assert "      2011 Black" in out
    assert "2012 Black" not in out


def test_survey_profile_override_inside_a_sport_tree(project, cfg, monkeypatch, capsys):
    """--profile on a path that also parses surveys it: the canvas check below must not read an unset canvas.

    The override skips the branch that looks the canvas up, so the
    standardized-output note has no canvas to compare against and is left out.
    """
    b = era(cfg, "football-helmet-back", "BCD")["size"]
    src = project / HELMET_FRONT
    art(src / "2010 White" / "h.png", b)
    main(monkeypatch, standardize, "survey", HELMET_FRONT, "--profile", "football-helmet-back")
    out = capsys.readouterr().out
    assert "profile=football-helmet-back (override)" in out
    assert "-> era BCD" in out
    assert "NOTE" not in out


def test_survey_rejects_unknown_profile(project, monkeypatch):
    """survey exits naming a --profile that isn't in the config."""
    art(project / "src" / "x.png", (5, 5))
    with pytest.raises(SystemExit, match=r"No profile 'nope' in config\."):
        main(monkeypatch, standardize, "survey", "src", "--profile", "nope")


def test_survey_without_profile_groups_and_truncates_elements(project, monkeypatch, capsys):
    """With no profile, survey lists elements per size, eliding the middle of long lists, and asks for a profile."""
    src = project / "Football/T/Helmets Side"
    for i in range(10):
        art(src / f"20{i:02d} White" / "h.png", (12, 8))
    main(monkeypatch, standardize, "survey", "Football/T/Helmets Side")
    out = capsys.readouterr().out
    assert "canvas=(unassigned)  profile=football-helmet-side (not yet defined)" in out
    assert "12 x 8  (10 elements)" in out
    shown = [ln.strip() for ln in out.splitlines() if ln.startswith("      ")]
    assert shown == [
        "2000 White",
        "2001 White",
        "2002 White",
        "2003 White",
        "...",
        "2007 White",
        "2008 White",
        "2009 White",
    ]
    assert "No profile yet." in out
    assert "UNMATCHED" not in out


def test_survey_notes_standardized_output(project, cfg, monkeypatch, capsys):
    """survey warns when every file is already on the padded canvas."""
    cv = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / HELMET_FRONT / "2000 White" / "h.png", cv, b)
    main(monkeypatch, standardize, "survey", HELMET_FRONT)
    out = capsys.readouterr().out
    assert f"every file is already {cv[0]} x {cv[1]}" in out


def test_survey_no_note_for_fill_canvas(project, cfg, monkeypatch, capsys):
    """A `fills: fill` canvas never triggers the standardized-output note, even when files equal it."""
    cv = canvas_size(cfg, "football_jersey_sleeve")
    art(project / "Football/T/Jerseys Left" / "2000 White" / "s.png", cv)
    main(monkeypatch, standardize, "survey", "Football/T/Jerseys Left")
    out = capsys.readouterr().out
    assert "-> era all" in out
    assert "NOTE" not in out


def test_survey_mixed_canvas_sizes_no_note(project, cfg, monkeypatch, capsys):
    """The standardized-output note needs EVERY file on the canvas."""
    cv = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / HELMET_FRONT / "a" / "h.png", cv, b)
    art(project / HELMET_FRONT / "b" / "h.png", b)
    main(monkeypatch, standardize, "survey", HELMET_FRONT)
    assert "NOTE" not in capsys.readouterr().out


def test_survey_refuses_missing_or_empty_dirs(project, monkeypatch):
    """survey exits on a path that isn't a directory, and on one with no PNGs."""
    with pytest.raises(SystemExit, match="Not a directory"):
        main(monkeypatch, standardize, "survey", "nothing")
    (project / "empty").mkdir()
    with pytest.raises(SystemExit, match="No PNGs under") as e:
        main(monkeypatch, standardize, "survey", "empty")
    assert "brctl download" in str(e.value)


# ---------------------------------------------------------------- pad: writes


def test_pad_bakes_scale_and_places_top_centre(project, cfg, monkeypatch, capsys):
    """pad crops to content, applies a scaled era's factor and places it top-centre on the slot canvas."""
    a = era(cfg, "football-helmet-front", "A")
    cv = canvas_size(cfg, "football_helmet_face")
    art(project / "src" / "1960 White" / "helmet.png", (a["size"][0] + 20, a["size"][1] + 9), a["size"], top=4)
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    out_file = project / HELMET_FRONT / "1960 White" / "helmet.png"
    w, h = scaled(a)
    size, box = bbox(out_file)
    assert size == cv
    assert box == ((cv[0] - w) // 2, 0, (cv[0] - w) // 2 + w, h)
    with Image.open(out_file) as im:
        assert im.info["dpi"] == pytest.approx((300, 300), abs=0.01)
    out = capsys.readouterr().out
    assert "Wrote 1 of 1 files" in out
    assert "All files matched an era and fit the canvas." in out


def test_pad_unscaled_era_copies_pixels_exactly(project, cfg, monkeypatch):
    """An era with no scale is placed pixel-for-pixel, and the source is left untouched."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    cv = canvas_size(cfg, "football_helmet_face")
    src = art(project / "src" / "2000 White" / "helmet.png", (b[0] + 4, b[1] + 4), b, top=2, seed=7)
    before = src.read_bytes()
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT, "--dpi", "144")
    with Image.open(src) as s, Image.open(project / HELMET_FRONT / "2000 White" / "helmet.png") as o:
        s_px = np.asarray(s.convert("RGBA"))[2 : 2 + b[1], 2 : 2 + b[0]]
        x = (cv[0] - b[0]) // 2
        o_px = np.asarray(o.convert("RGBA"))
        assert o.size == cv
        assert o.info["dpi"] == pytest.approx((144, 144), abs=0.01)
    assert np.array_equal(o_px[0 : b[1], x : x + b[0]], s_px)
    assert o_px[b[1] :, :, 3].max() == 0
    assert src.read_bytes() == before


def test_pad_writes_generated_marker(project, cfg, monkeypatch):
    """pad writes a .generated marker recording source, canvas, profile and file count."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    cv = canvas_size(cfg, "football_helmet_face")
    art(project / "src" / "x" / "h.png", b)
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    marker = json.loads((project / HELMET_FRONT / ".generated").read_text())
    assert marker["generated_by"] == "scripts/pipeline/standardize.py"
    assert marker["source"] == str((project / "src").resolve())
    assert marker["canvas"] == f"{cv[0]}x{cv[1]}"
    assert marker["files_written"] == 1
    assert "profile=football-helmet-front" in marker["profile"]
    assert marker["anchor"] == "top-center"
    assert marker["dpi"] == 300


def test_pad_rewrites_a_marked_destination(project, cfg, monkeypatch):
    """A destination that carries a marker is treated as generated and overwritten."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    dest = project / HELMET_FRONT
    art(dest / "x" / "h.png", (3, 3))
    (dest / ".generated").write_text("{}")
    art(project / "src" / "x" / "h.png", b)
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert bbox(dest / "x" / "h.png")[0] == canvas_size(cfg, "football_helmet_face")


@pytest.mark.parametrize(
    "anchor, expect_x, expect_y",
    [
        ("top-left", lambda W, w: 0, lambda H, h: 0),
        ("top-right", lambda W, w: W - w, lambda H, h: 0),
        ("middle-center", lambda W, w: (W - w) // 2, lambda H, h: (H - h) // 2),
    ],
)
def test_pad_anchor_positions(project, cfg, monkeypatch, anchor, expect_x, expect_y):
    """--anchor places content left, right or centred, at top or middle."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    W, H = canvas_size(cfg, "football_helmet_face")
    art(project / "src" / "x" / "h.png", b)
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT, "--anchor", anchor)
    x, y = expect_x(W, b[0]), expect_y(H, b[1])
    assert bbox(project / HELMET_FRONT / "x" / "h.png")[1] == (x, y, x + b[0], y + b[1])


def test_pad_reports_unmatched_skipped_and_mixed(project, cfg, monkeypatch, capsys):
    """Files matching no era, falling off the canvas, or already standardized are reported and not written."""
    e = era(cfg, "soccer-shorts-front", "all")["size"]
    cv = canvas_size(cfg, "soccer_shorts")
    tol = cfg["tolerance"]
    dest = "Soccer/MSU/Shorts Front"
    art(project / "src" / "good" / "s.png", e)
    wide = (cv[0] + 1, e[1])  # within tolerance of the era, one px wider than the canvas
    assert wide[0] - e[0] <= tol
    art(project / "src" / "wide" / "s.png", wide)
    art(project / "src" / "odd" / "s.png", (40, 40))
    art(project / "src" / "std" / "s.png", cv, e)
    blank(project / "src" / "blank" / "s.png", (9, 9))
    with pytest.raises(
        SystemExit,
        match=r"^\n!! 2 files were NOT written \(1 matched no era, 1 fell outside the canvas\)\. Keep the source\.$",
    ):
        main(monkeypatch, standardize, "pad", "src", dest)
    out = capsys.readouterr().out
    written = sorted(p.relative_to(project / dest).as_posix() for p in (project / dest).rglob("*.png"))
    assert written == ["good/s.png"]
    assert "Wrote 1 of 5 files" in out
    assert f"!! 1 files were SKIPPED — already {cv[0]} x {cv[1]}." in out
    assert "!! 1 files matched NO era and were NOT written:" in out
    assert "40x40  odd/s.png" in out
    assert "!! 1 files fall outside the canvas:" in out
    assert f"A canvas of at least {wide[0] + 2} x {e[1]} would fit them (soccer_shorts)." in out
    assert "All files matched" not in out


def test_pad_era_canvas_override_and_offsets(project, cfg, monkeypatch, capsys):
    """An era's own canvas, anchor and dx/dy are honoured; an era whose canvas is missing or sizeless is unmatched."""
    custom_config(project, cfg, tiny_sport)
    src = project / "src"
    art(src / "std" / "j.png", (38, 28))
    art(src / "wide" / "j.png", (58, 28))
    art(src / "shift" / "j.png", (10, 10))
    art(src / "nocanvas" / "j.png", (20, 20))
    art(src / "blank" / "j.png", (26, 26))
    with pytest.raises(SystemExit, match="2 files were NOT written"):
        main(monkeypatch, standardize, "pad", "src", "Test/T/Jerseys Front")
    dest = project / "Test/T/Jerseys Front"
    assert bbox(dest / "std" / "j.png") == ((40, 30), (1, 0, 39, 28))
    assert bbox(dest / "wide" / "j.png") == ((60, 30), (1, 0, 59, 28))
    assert bbox(dest / "shift" / "j.png") == ((40, 30), (3, 2, 13, 12))
    assert not (dest / "nocanvas").exists()
    assert not (dest / "blank").exists()
    out = capsys.readouterr().out
    assert "!! 2 files matched NO era" in out
    assert "20x20  nocanvas/j.png" in out


def test_pad_canvas_and_profile_overrides(project, cfg, monkeypatch, capsys):
    """--canvas and --profile let pad run on a path the config doesn't recognise."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "src" / "x" / "h.png", b)
    main(
        monkeypatch,
        standardize,
        "pad",
        "src",
        "out/anything",
        "--canvas",
        "700X900",
        "--profile",
        "football-helmet-front",
    )
    assert bbox(project / "out/anything/x/h.png") == (
        (700, 900),
        ((700 - b[0]) // 2, 0, (700 - b[0]) // 2 + b[0], b[1]),
    )
    assert "(path not recognized — using overrides)" in capsys.readouterr().out


# ---------------------------------------------------------------- pad: refusals


def test_pad_refuses_unmarked_authored_destination(project, cfg, monkeypatch):
    """pad refuses a destination of PNGs with no marker and writes nothing into it."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    dest = project / HELMET_FRONT
    authored = art(dest / "x" / "h.png", b, seed=3)
    before = authored.read_bytes()
    art(project / "src" / "x" / "h.png", b, seed=4)
    art(project / "src" / "y" / "h.png", b, seed=5)
    with pytest.raises(SystemExit, match="REFUSING to write") as e:
        main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert "holds 1 PNGs" in str(e.value)
    assert authored.read_bytes() == before
    assert not (dest / "y").exists()
    assert not (dest / ".generated").exists()


def test_pad_force_writes_marker_into_unmarked_destination(project, cfg, monkeypatch):
    """--force overrides the provenance guard and labels the destination generated."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    dest = project / HELMET_FRONT
    art(dest / "old" / "h.png", b)
    art(project / "src" / "x" / "h.png", b)
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT, "--force")
    assert (dest / ".generated").is_file()
    assert (dest / "x" / "h.png").is_file()


def test_pad_allows_unmarked_destination_without_pngs(project, cfg, monkeypatch):
    """An existing destination with no PNGs in it is not authored artwork, so pad writes."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    (project / HELMET_FRONT).mkdir(parents=True)
    art(project / "src" / "x" / "h.png", b)
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert (project / HELMET_FRONT / ".generated").is_file()


def test_pad_refuses_post_correction_input(project, cfg, monkeypatch):
    """Content matching what a scaled era PRODUCES is refused, and none of the batch is written."""
    a = era(cfg, "football-helmet-front", "A")
    b = era(cfg, "football-helmet-front", "B")["size"]
    tol = cfg["tolerance"]
    w, h = scaled(a)
    art(project / "src" / "1960 White" / "h.png", (w + tol, h - tol))
    art(project / "src" / "2000 White" / "h.png", b)
    with pytest.raises(SystemExit, match=r"REFUSING: 1 of 2 files are ALREADY POST-CORRECTION \(era A\)") as e:
        main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert f"{w + tol}x{h - tol}  era A  1960 White/h.png" in str(e.value)
    assert "Nothing written" in str(e.value)
    assert not (project / HELMET_FRONT).exists()


def test_pad_refuses_input_already_on_canvas(project, cfg, monkeypatch):
    """Source whose every file already sits on the target canvas is refused and nothing is written."""
    cv = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "src" / "x" / "h.png", cv, b)
    art(project / "src" / "y" / "h.png", cv, b)
    with pytest.raises(SystemExit, match=f"All 2 files are ALREADY {cv[0]} x {cv[1]}"):
        main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert not (project / HELMET_FRONT).exists()


@pytest.mark.parametrize(
    "argv, msg",
    [
        (("pad", "missing", HELMET_FRONT), "Not a directory"),
        (("pad", "src", "src"), "Destination must differ from source."),
        (("pad", "empty", HELMET_FRONT), "No PNGs under"),
        (("pad", "src", "out/x"), "No canvas size for this path ((path not recognized"),
        (("pad", "src", "Football/T/Helmets Side"), "No canvas size for this path (football/helmet/side"),
        (("pad", "src", "out/x", "--canvas", "10x10"), "No profile for this path"),
        (("pad", "src", HELMET_FRONT, "--profile", "nope"), "No profile 'nope' in config."),
    ],
)
def test_pad_refuses_bad_arguments(project, monkeypatch, argv, msg):
    """pad exits on a missing source, dest == src, an empty source, and unknown canvas or profile, writing nothing."""
    art(project / "src" / "x.png", (5, 5))
    (project / "empty").mkdir()
    with pytest.raises(SystemExit, match=re.escape(msg)):
        main(monkeypatch, standardize, *argv)
    assert not (project / HELMET_FRONT).exists()
    assert not (project / "out").exists()


def test_main_accepts_explicit_root(project, cfg, monkeypatch, tmp_path, capsys):
    """--root lets the script run from outside the project."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / HELMET_FRONT / "x" / "h.png", b)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    main(monkeypatch, standardize, "--root", str(project), "survey", HELMET_FRONT)
    assert "-> era B" in capsys.readouterr().out


def test_survey_of_unrecognised_path_lists_elements(project, monkeypatch, capsys):
    """A path outside any sport tree, with no --profile, is surveyed with no era matching."""
    art(project / "temp" / "loose" / "2000 White" / "h.png", (14, 9))
    main(monkeypatch, standardize, "survey", "temp/loose")
    out = capsys.readouterr().out
    assert "sport=" not in out
    assert size_line((14, 9), 1, "") in out
    assert "14 x 9  (1 elements)" in out
    assert "No profile yet." in out


def test_pad_keeps_partial_alpha_exactly(project, cfg, monkeypatch):
    """Anti-aliased edges survive pad unchanged: partly transparent pixels keep their alpha and colour."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    cv = canvas_size(cfg, "football_helmet_face")
    src = project / "src" / "2000 White" / "helmet.png"
    a = np.zeros((b[1], b[0], 4), np.uint8)
    a[..., :3] = np.random.default_rng(3).integers(0, 255, (b[1], b[0], 3), dtype=np.uint8)
    a[..., 3] = np.tile(np.linspace(1, 255, b[0]).astype(np.uint8), (b[1], 1))  # every alpha from 1 to 255
    src.parent.mkdir(parents=True)
    Image.fromarray(a).save(src)
    main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    with Image.open(project / HELMET_FRONT / "2000 White" / "helmet.png") as o:
        x = (cv[0] - b[0]) // 2
        out = np.asarray(o.convert("RGBA"))[0 : b[1], x : x + b[0]]
    assert np.array_equal(out[..., 3], a[..., 3])
    assert np.array_equal(out, a)


# ---------------------------------------------------------------- fixed bugs


def test_survey_of_only_transparent_files_reports_and_exits_cleanly(project, monkeypatch, capsys):
    """survey of a tree whose every PNG is fully transparent says so instead of crashing."""
    blank(project / HELMET_FRONT / "x" / "blank.png", (9, 9))
    blank(project / HELMET_FRONT / "y" / "blank.png", (4, 4))
    main(monkeypatch, standardize, "survey", HELMET_FRONT)
    out = capsys.readouterr().out
    assert "2 PNGs under Helmets Front" in out
    assert "No file has opaque content: all 2 PNGs are fully transparent." in out
    assert "Largest content" not in out


def test_pad_already_on_canvas_check_does_not_depend_on_file_order(project, cfg, monkeypatch, capsys):
    """Files on the slot canvas or an era's canvas are skipped wherever they sort; the marker keeps the slot canvas."""
    custom_config(project, cfg, tiny_sport)
    src = project / "src"
    art(src / "a" / "j.png", (58, 28))  # authored, era `wide` -> tiny_wide
    art(src / "b" / "j.png", (40, 30), (38, 28))  # already on the slot canvas
    art(src / "c" / "j.png", (38, 28))  # authored, era `std` -> tiny
    art(src / "d" / "j.png", (60, 30), (58, 28))  # already on the era canvas
    before = {p: p.read_bytes() for p in src.rglob("*.png")}
    main(monkeypatch, standardize, "pad", "src", "Test/T/Jerseys Front")
    dest = project / "Test/T/Jerseys Front"
    written = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*.png"))
    assert written == ["a/j.png", "c/j.png"]
    assert bbox(dest / "a" / "j.png")[0] == (60, 30)
    assert bbox(dest / "c" / "j.png")[0] == (40, 30)
    assert all(p.read_bytes() == b for p, b in before.items())
    out = capsys.readouterr().out
    assert "!! 2 files were SKIPPED — already 40 x 30 or 60 x 30." in out
    assert "canvas 40 x 30, anchor top-center" in out
    assert "era canvas tiny_wide 60 x 30" in out
    marker = json.loads((dest / ".generated").read_text())
    assert marker["canvas"] == "40x30"
    assert marker["era_canvases"] == {"tiny_wide": "60x30"}


def test_pad_refuses_input_all_on_slot_or_era_canvases(project, cfg, monkeypatch):
    """Source entirely on the slot canvas and an era's canvas is refused, and nothing is written."""
    custom_config(project, cfg, tiny_sport)
    art(project / "src" / "a" / "j.png", (40, 30), (38, 28))
    art(project / "src" / "b" / "j.png", (60, 30), (58, 28))
    with pytest.raises(SystemExit, match="All 2 files are ALREADY 40 x 30 or 60 x 30"):
        main(monkeypatch, standardize, "pad", "src", "Test/T/Jerseys Front")
    assert not (project / "Test").exists()


def test_pad_canvas_hint_fits_centred_content_with_a_margin(project, cfg, monkeypatch, capsys):
    """The canvas hint is content plus 1px each side on a centred axis, never the canvas that just failed."""
    cv = canvas_size(cfg, "soccer_shorts")
    e = era(cfg, "soccer-shorts-front", "all")["size"]
    w, h = cv[0] + 1, e[1]  # one px wider than the canvas, still within tolerance of the era
    assert w - e[0] <= cfg["tolerance"]
    art(project / "src" / "w" / "s.png", (w, h))
    with pytest.raises(SystemExit, match="Nothing written"):  # every file falls off the canvas: nothing written
        main(monkeypatch, standardize, "pad", "src", "Soccer/T/Shorts Front")
    out = capsys.readouterr().out
    assert f"{w}x{h} -> {w}x{h} at ({(cv[0] - w) // 2},0)  w/s.png" in out
    assert f"A canvas of at least {w + 2} x {h} would fit them (soccer_shorts)." in out


@pytest.mark.parametrize(
    "anchor, extent, offset, need",
    [
        ("start", 10, 3, 13),
        ("start", 10, -1, None),
        ("end", 10, -3, 13),
        ("end", 10, 1, None),
        ("centre", 10, 0, 12),
        ("centre", 11, 0, 13),
        ("centre", 10, 3, 17),
        ("centre", 10, -2, 16),
    ],
)
def test_fit_extent(anchor, extent, offset, need):
    """fit_extent is the smallest canvas side holding the content at its anchor, with 1px each side when centred."""
    assert standardize.fit_extent(anchor, extent, offset) == need


def test_pad_canvas_hint_per_canvas_and_for_offsets_that_never_fit(project, cfg, monkeypatch, capsys):
    """Skipped files get a hint per canvas, and one pushed off its anchored edge is named as fitting no canvas."""

    def mutate(c):
        """tiny_sport plus a too-wide era on tiny_wide, a too-tall one, and one whose dx pushes it off the left."""
        tiny_sport(c)
        c["profiles"]["test-jersey-front"] += [
            {"era": "huge", "size": [70, 10], "canvas": "tiny_wide"},
            {"era": "off", "size": [30, 3], "anchor": "top-left", "dx": -1},
            {"era": "deep", "size": [12, 40]},
        ]

    custom_config(project, cfg, mutate)
    art(project / "src" / "huge" / "j.png", (70, 10))
    art(project / "src" / "off" / "j.png", (30, 3))
    art(project / "src" / "deep" / "j.png", (12, 40))
    with pytest.raises(SystemExit, match="Nothing written"):  # every file falls off the canvas: nothing written
        main(monkeypatch, standardize, "pad", "src", "Test/T/Jerseys Front")
    out = capsys.readouterr().out
    assert "!! 3 files fall outside the canvas:" in out
    assert "A canvas of at least 40 x 40 would fit them (tiny)." in out
    assert "A canvas of at least 72 x 30 would fit them (tiny_wide)." in out
    assert "No canvas fits off/j.png: its era's dx/dy pushes it past the anchored edge." in out


def test_pad_blank_file_does_not_slip_standardized_output_past_the_refusal(project, cfg, monkeypatch):
    """Standardized output plus one fully transparent file is still refused, and no marker is left behind."""
    cv = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "src" / "x" / "h.png", cv, b)
    art(project / "src" / "y" / "h.png", cv, b)
    blank(project / "src" / "z" / "blank.png", cv)
    with pytest.raises(
        SystemExit, match=re.escape(f"All 2 files are ALREADY {cv[0]} x {cv[1]} (1 fully transparent file ignored)")
    ):
        main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert not (project / HELMET_FRONT).exists()


def test_pad_refuses_a_source_with_no_opaque_content(project, monkeypatch):
    """A source of only fully transparent files is refused, and nothing (not even a marker) is written."""
    blank(project / "src" / "a" / "blank.png", (9, 9))
    blank(project / "src" / "b" / "blank.png", (9, 9))
    with pytest.raises(SystemExit, match="No file has opaque content: all 2 PNGs are fully transparent"):
        main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert not (project / HELMET_FRONT).exists()


def test_pad_writes_no_marker_when_nothing_was_written(project, monkeypatch, capsys):
    """When no file both matches an era and fits, pad reports why, exits 1 and creates no destination or marker."""
    art(project / "src" / "odd" / "h.png", (40, 40))
    with pytest.raises(SystemExit, match="Nothing written"):
        main(monkeypatch, standardize, "pad", "src", HELMET_FRONT)
    assert "!! 1 files matched NO era and were NOT written:" in capsys.readouterr().out
    assert not (project / HELMET_FRONT).exists()


def test_pad_fill_canvas_source_cropped_to_content_is_padded_not_refused(project, cfg, monkeypatch):
    """On a `fills: fill` canvas, authored source cropped to its content equals the canvas and is still padded."""
    cv = canvas_size(cfg, "football_jersey_sleeve")
    assert cfg["canvases"]["football_jersey_sleeve"]["fills"] == "fill"
    src = art(project / "src" / "1990 White" / "1990 White.png", cv)
    main(monkeypatch, standardize, "pad", "src", "Football/T/Jerseys Left")
    out = project / "Football/T/Jerseys Left/1990 White/1990 White.png"
    assert bbox(out)[0] == cv
    assert np.array_equal(pixels(out), pixels(src))
    assert (project / "Football/T/Jerseys Left/.generated").is_file()


def test_pad_takes_the_closest_era_where_windows_overlap(project, cfg, monkeypatch):
    """A width within tolerance of helmet back E and E2 but nearer E2 is filed as E2, not as E, the first listed."""
    (e, h), (e2, _) = era(cfg, "football-helmet-back", "E")["size"], era(cfg, "football-helmet-back", "E2")["size"]
    w = e2 - 3
    assert w - e <= cfg["tolerance"] and e2 - w < w - e
    art(project / "src" / "2010 White" / "h.png", (w, h))
    out = main(monkeypatch, standardize, "pad", "src", "Football/T/Helmets Back")
    rows = [line.split() for line in out.splitlines()]
    assert ["E2", str(w), "x", str(h)] in [r[:4] for r in rows]


@pytest.mark.parametrize("argv", [("survey", "src"), ("pad", "src", HELMET_FRONT)], ids=["survey", "pad"])
def test_survey_and_pad_need_tolerance_in_the_config(project, monkeypatch, argv):
    """With no `tolerance` in the config, survey and pad exit saying so rather than guessing one."""
    small_configs(project, lambda c: c.pop("tolerance"))
    b = era(standardize.load_config(project), "football-helmet-front", "B")["size"]
    art(project / "src" / "x" / "h.png", b)
    with pytest.raises(SystemExit, match="No `tolerance`"):
        main(monkeypatch, standardize, *argv)
