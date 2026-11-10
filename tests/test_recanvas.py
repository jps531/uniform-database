"""Tests for scripts/migration/recanvas.py: moving standardized files to a new canvas without ever rescaling."""

import json

import common
import numpy as np
import pytest
import recanvas
from helpers import art, canvas_size, era, main
from PIL import Image

DEST = "Football/T/Helmets Front"


def test_find_root(project, tmp_path):
    """find_root walks up from a subdirectory and exits when none is found."""
    sub = project / "x" / "y"
    sub.mkdir(parents=True)
    assert common.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(SystemExit) as e:
        common.find_root(lone)
    assert "No configs/canvas_definitions.yaml in" in str(e.value)


def test_dry_run_reports_and_writes_nothing(project, cfg, monkeypatch, capsys):
    """Without --apply, recanvas prints the plan and writes nothing."""
    W, H = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "old" / "x" / "h.png", (W + 40, H + 40), b)
    main(monkeypatch, recanvas, "old", DEST)
    out = capsys.readouterr().out
    assert f"canvas football_helmet_face = {W} x {H}, anchor top-center" in out
    assert "1 files, 1 distinct content sizes:" in out
    assert f"-> placed at ({(W - b[0]) // 2}, 0)" in out
    assert "DRY RUN — nothing written." in out
    assert not (project / DEST).exists()


def test_apply_moves_content_without_rescaling(project, cfg, monkeypatch, capsys):
    """--apply crops to content and places it top-centre, pixel-for-pixel, even for a scaled era's output."""
    W, H = canvas_size(cfg, "football_helmet_face")
    a = era(cfg, "football-helmet-front", "A")
    post = (round(a["size"][0] * a["scale"]), round(a["size"][1] * a["scale"]))
    src = art(project / "old" / "1960 White" / "h.png", (W + 30, H + 20), post, top=7, seed=2)
    art(project / "old" / "1960 White" / ".hidden.png", (5, 5))
    before = src.read_bytes()
    main(monkeypatch, recanvas, "old", DEST, "--apply")
    out_file = project / DEST / "1960 White" / "h.png"
    x = (W - post[0]) // 2
    with Image.open(src) as s, Image.open(out_file) as o:
        sx = ((W + 30) - post[0]) // 2
        s_px = np.asarray(s.convert("RGBA"))[7 : 7 + post[1], sx : sx + post[0]]
        o_px = np.asarray(o.convert("RGBA"))
        assert o.size == (W, H)
        assert o.info["dpi"] == pytest.approx((300, 300), abs=0.01)
    assert np.array_equal(o_px[: post[1], x : x + post[0]], s_px)
    assert o_px[:, :, 3].sum() == s_px[:, :, 3].sum()
    assert not (project / DEST / "1960 White" / ".hidden.png").exists()
    assert src.read_bytes() == before
    assert "Wrote 1 files. Source left intact." in capsys.readouterr().out


def test_apply_keeps_blank_file_blank(project, cfg, monkeypatch):
    """A fully transparent file is written as a blank canvas."""
    W, H = canvas_size(cfg, "football_helmet_face")
    art(project / "old" / "x" / "blank.png", (20, 20), (0, 0))
    main(monkeypatch, recanvas, "old", DEST, "--apply")
    with Image.open(project / DEST / "x" / "blank.png") as o:
        assert o.size == (W, H)
        assert o.getchannel("A").getbbox() is None


def test_too_big_is_listed_and_blocks_apply(project, cfg, monkeypatch, capsys):
    """Content larger than the canvas is listed in a dry run and refuses --apply, writing nothing."""
    W, H = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "old" / "big" / "h.png", (W + 1, 10))
    art(project / "old" / "tall" / "h.png", (10, H + 1))
    art(project / "old" / "ok" / "h.png", b)
    main(monkeypatch, recanvas, "old", DEST)
    out = capsys.readouterr().out
    assert "!! 2 files are LARGER than the canvas:" in out
    assert f"{W + 1}x10  big/h.png" in out
    assert f"10x{H + 1}  tall/h.png" in out
    with pytest.raises(SystemExit) as e:
        main(monkeypatch, recanvas, "old", DEST, "--apply")
    assert "Refusing to apply while files exceed the canvas." in str(e.value)
    assert not (project / DEST).exists()


def test_canvas_override_and_marks_prefix(project, cfg, monkeypatch, capsys):
    """--canvas names the canvas directly; Marks/ paths resolve like sport trees."""
    W, H = canvas_size(cfg, "football_helmet_profile")
    art(project / "old" / "x" / "h.png", (30, 20))
    main(monkeypatch, recanvas, "old", "out/anything", "--canvas", "football_helmet_profile", "--apply")
    with Image.open(project / "out/anything/x/h.png") as o:
        assert o.size == (W, H)
        assert o.getchannel("A").getbbox() == ((W - 30) // 2, 0, (W - 30) // 2 + 30, 20)
    capsys.readouterr()
    main(monkeypatch, recanvas, "old", "Marks/Football/T/Helmets Left")
    assert f"canvas football_helmet_profile = {W} x {H}" in capsys.readouterr().out


def test_explicit_root(project, monkeypatch, tmp_path, capsys):
    """--root lets recanvas run from outside the project."""
    art(project / "old" / "x.png", (5, 5))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    main(monkeypatch, recanvas, "old", DEST, "--root", str(project))
    assert "DRY RUN" in capsys.readouterr().out


@pytest.mark.parametrize(
    "src, dest, msg",
    [
        ("missing", DEST, "Source not found"),
        ("old", "Football/T", "Cannot read sport/slot/viewpoint from Football/T"),
        ("old", "Football/T/Helmets Side", "No canvas assigned for Football/T/Helmets Side"),
        ("old", "Curling/T/Jerseys Front", "No canvas assigned for Curling/T/Jerseys Front"),
    ],
)
def test_refusals(project, monkeypatch, src, dest, msg):
    """recanvas exits on a missing source, an unparseable destination, and one with no canvas."""
    art(project / "old" / "x.png", (5, 5))
    with pytest.raises(SystemExit) as e:
        main(monkeypatch, recanvas, src, dest)
    assert msg in str(e.value)


@pytest.mark.parametrize("dest", ["old", "old/", "./old", "x/../old"])
def test_refuses_destination_equal_to_source(project, monkeypatch, dest):
    """A destination that resolves to the source is refused before anything is read or written."""
    src = art(project / "old" / "x" / "h.png", (5, 5))
    before = src.read_bytes()
    with pytest.raises(SystemExit) as e:
        main(monkeypatch, recanvas, "old", dest, "--canvas", "football_helmet_face", "--apply")
    assert "Destination must differ from source." in str(e.value)
    assert src.read_bytes() == before


def test_std_sibling_resolves_its_canvas(project, cfg, monkeypatch, capsys):
    """A "… STD" sibling (the recommended destination) resolves the same canvas as the folder it shadows."""
    W, H = canvas_size(cfg, "football_jersey")
    art(project / "old" / "x" / "j.png", (10, 10))
    main(monkeypatch, recanvas, "old", "Football/T/Jerseys Front STD")
    assert f"canvas football_jersey = {W} x {H}, anchor top-center" in capsys.readouterr().out


def test_destination_outside_the_project_is_unreadable(project, monkeypatch, tmp_path):
    """A destination outside the project root cannot name a canvas, and exits cleanly."""
    art(project / "old" / "x.png", (5, 5))
    with pytest.raises(SystemExit) as e:
        main(monkeypatch, recanvas, "old", str(tmp_path / "elsewhere" / "Football/T/Jerseys Front"))
    assert "Cannot read sport/slot/viewpoint from" in str(e.value)


def test_refuses_an_authored_destination(project, cfg, monkeypatch):
    """A destination holding PNGs without a .generated marker is authored artwork: refused, dry run or not."""
    art(project / "old" / "x" / "h.png", (10, 10))
    authored = art(project / DEST / "x" / "h.png", (7, 7), seed=4)
    before = authored.read_bytes()
    for flags in ((), ("--apply",)):
        with pytest.raises(SystemExit) as e:
            main(monkeypatch, recanvas, "old", DEST, *flags)
        assert "REFUSING to write to" in str(e.value)
        assert "holds 1 PNGs but has no .generated marker" in str(e.value)
    assert authored.read_bytes() == before


def test_writes_a_marker_and_may_rewrite_its_own_output(project, cfg, monkeypatch, capsys):
    """--apply writes a .generated marker naming source and canvas, so a second run into it is allowed."""
    W, H = canvas_size(cfg, "football_helmet_face")
    art(project / "old" / "x" / "h.png", (10, 10))
    (project / DEST).mkdir(parents=True)
    (project / DEST / "notes.txt").write_text("")
    main(monkeypatch, recanvas, "old", DEST, "--apply")
    main(monkeypatch, recanvas, "old", DEST, "--apply")
    assert capsys.readouterr().out.count("Wrote 1 files.") == 2
    marker = json.loads((project / DEST / ".generated").read_text())
    assert marker["generated_by"] == "scripts/migration/recanvas.py"
    assert marker["source"] == str(project / "old")
    assert marker["canvas"] == f"{W}x{H}"
    assert marker["canvas_name"] == "football_helmet_face"
    assert marker["files_written"] == 1


def test_nothing_to_write_leaves_no_marker(project, monkeypatch, capsys):
    """A source with no PNGs writes nothing, so no destination or marker is created."""
    (project / "old").mkdir()
    main(monkeypatch, recanvas, "old", DEST, "--apply")
    assert "Wrote 0 files." in capsys.readouterr().out
    assert not (project / DEST).exists()
