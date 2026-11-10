"""Tests for scripts/standardize.py: path parsing, era matching, survey, and pad's writes and refusals."""

import copy
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import standardize
import yaml
from conftest import art, canvas_size, era
from PIL import Image

HELMET_FRONT = "Football/T/Helmets Front"


def run(monkeypatch, *argv):
    """Call standardize.main() with the given command-line arguments."""
    monkeypatch.setattr(sys, "argv", ["standardize.py", *argv])
    standardize.main()


def bbox(path: Path):
    """(size, alpha bbox) of a PNG."""
    with Image.open(path) as im:
        return im.size, im.getchannel("A").getbbox()


def size_line(size, n, tag) -> str:
    """One line of survey's size table, formatted as survey prints it."""
    return f"  {size[0]:>5} x {size[1]:<5}  {n:>4} files{tag}"


def scaled(e: dict) -> tuple:
    """The content size an era's scale produces from its listed size."""
    s = e.get("scale", 1)
    return round(e["size"][0] * s), round(e["size"][1] * s)


def custom_config(project: Path, cfg: dict, mutate) -> dict:
    """Replace the project's configs link with a copy whose canvas_definitions.yaml is mutate(copy of cfg)."""
    real = Path(os.readlink(project / "configs"))
    (project / "configs").unlink()
    (project / "configs").mkdir()
    for f in real.iterdir():
        if f.name != "canvas_definitions.yaml":
            os.symlink(f, project / "configs" / f.name)
    new = copy.deepcopy(cfg)
    mutate(new)
    (project / "configs" / "canvas_definitions.yaml").write_text(yaml.safe_dump(new))
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
    assert standardize.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(SystemExit) as e:
        standardize.find_root(lone)
    assert "Could not find configs/canvas_definitions.yaml" in str(e.value)


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
    assert (canvas["width"], canvas["height"]) == canvas_size(cfg, "football_helmet_face")
    assert profile == cfg["profiles"]["football-helmet-front"]
    canvas, profile, names = standardize.lookup(cfg, "football", "helmet", "side")
    assert canvas is None and profile is None and names == (None, "football-helmet-side")


def test_pngs_skips_hidden_files_and_directories(tmp_path):
    """pngs yields visible PNGs only, sorted."""
    for rel in ("b/x.png", "a/y.png", ".hidden/z.png", "a/.w.png", "a/n.txt"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"")
    assert [p.relative_to(tmp_path).as_posix() for p in standardize.pngs(tmp_path)] == ["a/y.png", "b/x.png"]


def test_content_size_of_opaque_and_empty_images(tmp_path):
    """content_size returns the alpha bbox and its size, or (None, None) for a blank image."""
    with Image.open(art(tmp_path / "a.png", (20, 10), (6, 4), top=2)) as im:
        assert standardize.content_size(im.convert("RGBA")) == ((7, 2, 13, 6), (6, 4))
    assert standardize.content_size(Image.new("RGBA", (5, 5))) == (None, None)


def test_match_era_within_tolerance_only(cfg):
    """match_era accepts a size up to `tolerance` off on each axis and rejects one pixel beyond."""
    tol = cfg["tolerance"]
    profile = cfg["profiles"]["football-helmet-front"]
    w, h = era(cfg, "football-helmet-front", "B")["size"]
    assert standardize.match_era(profile, w + tol, h - tol, tol)["era"] == "B"
    assert standardize.match_era(profile, w + tol + 1, h, tol) is None
    assert standardize.match_era(profile, w, h - tol - 1, tol) is None


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
    art(src / "2003 White" / "blank.png", (40, 40), (0, 0))
    run(monkeypatch, "survey", HELMET_FRONT)
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


def test_survey_elements_and_profile_override(project, cfg, monkeypatch, capsys):
    """--profile overrides the path's profile and --elements lists the elements at each size."""
    b = era(cfg, "football-helmet-back", "BCD")["size"]
    src = project / "temp" / "helmets"
    art(src / "2010 White" / "h.png", b)
    art(src / "2011 Black" / "h.png", b)
    art(src / "2012 Black" / "blank.png", (9, 9), (0, 0))
    run(monkeypatch, "survey", "temp/helmets", "--profile", "football-helmet-back", "--elements")
    out = capsys.readouterr().out
    assert "profile=football-helmet-back (override)" in out
    assert "-> era BCD" in out
    assert f"{b[0]} x {b[1]}  (2 elements)" in out
    assert "      2010 White" in out and "      2011 Black" in out
    assert "2012 Black" not in out


def test_survey_rejects_unknown_profile(project, monkeypatch):
    """survey exits naming a --profile that isn't in the config."""
    art(project / "src" / "x.png", (5, 5))
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "survey", "src", "--profile", "nope")
    assert "No profile 'nope' in config." in str(e.value)


def test_survey_without_profile_groups_and_truncates_elements(project, monkeypatch, capsys):
    """With no profile, survey lists elements per size, eliding the middle of long lists, and asks for a profile."""
    src = project / "Football/T/Helmets Side"
    for i in range(10):
        art(src / f"20{i:02d} White" / "h.png", (12, 8))
    run(monkeypatch, "survey", "Football/T/Helmets Side")
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
    run(monkeypatch, "survey", HELMET_FRONT)
    out = capsys.readouterr().out
    assert f"every file is already {cv[0]} x {cv[1]}" in out


def test_survey_no_note_for_fill_canvas(project, cfg, monkeypatch, capsys):
    """A `fills: fill` canvas never triggers the standardized-output note, even when files equal it."""
    cv = canvas_size(cfg, "football_jersey_sleeve")
    art(project / "Football/T/Jerseys Left" / "2000 White" / "s.png", cv)
    run(monkeypatch, "survey", "Football/T/Jerseys Left")
    out = capsys.readouterr().out
    assert "-> era all" in out
    assert "NOTE" not in out


def test_survey_mixed_canvas_sizes_no_note(project, cfg, monkeypatch, capsys):
    """The standardized-output note needs EVERY file on the canvas."""
    cv = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / HELMET_FRONT / "a" / "h.png", cv, b)
    art(project / HELMET_FRONT / "b" / "h.png", b)
    run(monkeypatch, "survey", HELMET_FRONT)
    assert "NOTE" not in capsys.readouterr().out


def test_survey_refuses_missing_or_empty_dirs(project, monkeypatch):
    """survey exits on a path that isn't a directory, and on one with no PNGs."""
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "survey", "nothing")
    assert "Not a directory" in str(e.value)
    (project / "empty").mkdir()
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "survey", "empty")
    assert "No PNGs under" in str(e.value) and "brctl download" in str(e.value)


# ---------------------------------------------------------------- pad: writes


def test_pad_bakes_scale_and_places_top_centre(project, cfg, monkeypatch, capsys):
    """pad crops to content, applies a scaled era's factor and places it top-centre on the slot canvas."""
    a = era(cfg, "football-helmet-front", "A")
    cv = canvas_size(cfg, "football_helmet_face")
    art(project / "src" / "1960 White" / "helmet.png", (a["size"][0] + 20, a["size"][1] + 9), a["size"], top=4)
    run(monkeypatch, "pad", "src", HELMET_FRONT)
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
    run(monkeypatch, "pad", "src", HELMET_FRONT, "--dpi", "144")
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
    run(monkeypatch, "pad", "src", HELMET_FRONT)
    marker = json.loads((project / HELMET_FRONT / ".generated").read_text())
    assert marker["generated_by"] == "scripts/standardize.py"
    assert marker["source"] == str((project / "src").resolve())
    assert marker["canvas"] == f"{cv[0]}x{cv[1]}"
    assert marker["files_written"] == 1
    assert "profile=football-helmet-front" in marker["profile"]
    assert marker["anchor"] == "top-center" and marker["dpi"] == 300


def test_pad_rewrites_a_marked_destination(project, cfg, monkeypatch):
    """A destination that carries a marker is treated as generated and overwritten."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    dest = project / HELMET_FRONT
    art(dest / "x" / "h.png", (3, 3))
    (dest / ".generated").write_text("{}")
    art(project / "src" / "x" / "h.png", b)
    run(monkeypatch, "pad", "src", HELMET_FRONT)
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
    run(monkeypatch, "pad", "src", HELMET_FRONT, "--anchor", anchor)
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
    art(project / "src" / "blank" / "s.png", (9, 9), (0, 0))
    run(monkeypatch, "pad", "src", dest)
    out = capsys.readouterr().out
    written = sorted(p.relative_to(project / dest).as_posix() for p in (project / dest).rglob("*.png"))
    assert written == ["good/s.png"]
    assert "Wrote 1 of 5 files" in out
    assert f"!! 1 files were SKIPPED — already {cv[0]} x {cv[1]}." in out
    assert "!! 1 files matched NO era and were NOT written:" in out
    assert "40x40  odd/s.png" in out
    assert "!! 1 files fall outside the canvas:" in out
    assert "would fit them." in out
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
    run(monkeypatch, "pad", "src", "Test/T/Jerseys Front")
    dest = project / "Test/T/Jerseys Front"
    assert bbox(dest / "std" / "j.png") == ((40, 30), (1, 0, 39, 28))
    assert bbox(dest / "wide" / "j.png") == ((60, 30), (1, 0, 59, 28))
    assert bbox(dest / "shift" / "j.png") == ((40, 30), (3, 2, 13, 12))
    assert not (dest / "nocanvas").exists() and not (dest / "blank").exists()
    out = capsys.readouterr().out
    assert "!! 2 files matched NO era" in out
    assert "20x20  nocanvas/j.png" in out


def test_pad_canvas_and_profile_overrides(project, cfg, monkeypatch, capsys):
    """--canvas and --profile let pad run on a path the config doesn't recognise."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "src" / "x" / "h.png", b)
    run(monkeypatch, "pad", "src", "out/anything", "--canvas", "700X900", "--profile", "football-helmet-front")
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
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "pad", "src", HELMET_FRONT)
    assert "REFUSING to write" in str(e.value) and "holds 1 PNGs" in str(e.value)
    assert authored.read_bytes() == before
    assert not (dest / "y").exists() and not (dest / ".generated").exists()


def test_pad_force_writes_marker_into_unmarked_destination(project, cfg, monkeypatch):
    """--force overrides the provenance guard and labels the destination generated."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    dest = project / HELMET_FRONT
    art(dest / "old" / "h.png", b)
    art(project / "src" / "x" / "h.png", b)
    run(monkeypatch, "pad", "src", HELMET_FRONT, "--force")
    assert (dest / ".generated").is_file()
    assert (dest / "x" / "h.png").is_file()


def test_pad_allows_unmarked_destination_without_pngs(project, cfg, monkeypatch):
    """An existing destination with no PNGs in it is not authored artwork, so pad writes."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    (project / HELMET_FRONT).mkdir(parents=True)
    art(project / "src" / "x" / "h.png", b)
    run(monkeypatch, "pad", "src", HELMET_FRONT)
    assert (project / HELMET_FRONT / ".generated").is_file()


def test_pad_refuses_post_correction_input(project, cfg, monkeypatch):
    """Content matching what a scaled era PRODUCES is refused, and none of the batch is written."""
    a = era(cfg, "football-helmet-front", "A")
    b = era(cfg, "football-helmet-front", "B")["size"]
    tol = cfg["tolerance"]
    w, h = scaled(a)
    art(project / "src" / "1960 White" / "h.png", (w + tol, h - tol))
    art(project / "src" / "2000 White" / "h.png", b)
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "pad", "src", HELMET_FRONT)
    msg = str(e.value)
    assert "REFUSING: 1 of 2 files are ALREADY POST-CORRECTION (era A)" in msg
    assert f"{w + tol}x{h - tol}  era A  1960 White/h.png" in msg
    assert "Nothing written" in msg
    assert not (project / HELMET_FRONT).exists()


def test_pad_refuses_input_already_on_canvas(project, cfg, monkeypatch):
    """Source whose every file already sits on the target canvas is refused and nothing is written."""
    cv = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "src" / "x" / "h.png", cv, b)
    art(project / "src" / "y" / "h.png", cv, b)
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "pad", "src", HELMET_FRONT)
    assert f"All 2 files are ALREADY {cv[0]} x {cv[1]}" in str(e.value)
    assert not (project / HELMET_FRONT).exists()


def test_pad_refuses_bad_arguments(project, monkeypatch, tmp_path):
    """pad exits on a missing source, dest == src, an empty source, and unknown canvas or profile."""
    cases = [
        (("pad", "missing", HELMET_FRONT), "Not a directory"),
        (("pad", "src", "src"), "Destination must differ from source."),
        (("pad", "empty", HELMET_FRONT), "No PNGs under"),
        (("pad", "src", "out/x"), "No canvas size for this path ((path not recognized"),
        (("pad", "src", "Football/T/Helmets Side"), "No canvas size for this path (football/helmet/side"),
        (("pad", "src", "out/x", "--canvas", "10x10"), "No profile for this path"),
        (("pad", "src", HELMET_FRONT, "--profile", "nope"), "No profile 'nope' in config."),
    ]
    art(project / "src" / "x.png", (5, 5))
    (project / "empty").mkdir()
    for argv, msg in cases:
        with pytest.raises(SystemExit) as e:
            run(monkeypatch, *argv)
        assert msg in str(e.value), argv
    assert not (project / HELMET_FRONT).exists() and not (project / "out").exists()


def test_main_accepts_explicit_root(project, cfg, monkeypatch, tmp_path, capsys):
    """--root lets the script run from outside the project."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / HELMET_FRONT / "x" / "h.png", b)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    run(monkeypatch, "--root", str(project), "survey", HELMET_FRONT)
    assert "-> era B" in capsys.readouterr().out


def test_survey_of_unrecognised_path_lists_elements(project, monkeypatch, capsys):
    """A path outside any sport tree, with no --profile, is surveyed with no era matching."""
    art(project / "temp" / "loose" / "2000 White" / "h.png", (14, 9))
    run(monkeypatch, "survey", "temp/loose")
    out = capsys.readouterr().out
    assert "sport=" not in out
    assert size_line((14, 9), 1, "") in out
    assert "14 x 9  (1 elements)" in out and "No profile yet." in out
