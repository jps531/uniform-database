"""Tests for scripts/migration/recanvas.py: moving standardized files to a new canvas without ever rescaling."""

import sys

import numpy as np
import pytest
import recanvas
from conftest import art, canvas_size, era
from PIL import Image

DEST = "Football/T/Helmets Front"


def run(monkeypatch, *argv):
    """Call recanvas.main() with the given command-line arguments."""
    monkeypatch.setattr(sys, "argv", ["recanvas.py", *argv])
    recanvas.main()


def test_slug_and_find_root(project, tmp_path):
    """slug matches the config keys; find_root walks up from a subdirectory and exits when none is found."""
    assert recanvas.slug("Women’s Basketball") == "womens_basketball"
    assert recanvas.slug("Men's Basketball") == "mens_basketball"
    sub = project / "x" / "y"
    sub.mkdir(parents=True)
    assert recanvas.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(SystemExit) as e:
        recanvas.find_root(lone)
    assert "No configs/canvas_definitions.yaml above" in str(e.value)


def test_dry_run_reports_and_writes_nothing(project, cfg, monkeypatch, capsys):
    """Without --apply, recanvas prints the plan and writes nothing."""
    W, H = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "old" / "x" / "h.png", (W + 40, H + 40), b)
    run(monkeypatch, "old", DEST)
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
    run(monkeypatch, "old", DEST, "--apply")
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
    run(monkeypatch, "old", DEST, "--apply")
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
    run(monkeypatch, "old", DEST)
    out = capsys.readouterr().out
    assert "!! 2 files are LARGER than the canvas:" in out
    assert f"{W + 1}x10  big/h.png" in out
    assert f"10x{H + 1}  tall/h.png" in out
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "old", DEST, "--apply")
    assert "Refusing to apply while files exceed the canvas." in str(e.value)
    assert not (project / DEST).exists()


def test_canvas_override_and_marks_prefix(project, cfg, monkeypatch, capsys):
    """--canvas names the canvas directly; Marks/ paths resolve like sport trees."""
    W, H = canvas_size(cfg, "football_helmet_profile")
    art(project / "old" / "x" / "h.png", (30, 20))
    run(monkeypatch, "old", "out/anything", "--canvas", "football_helmet_profile", "--apply")
    with Image.open(project / "out/anything/x/h.png") as o:
        assert o.size == (W, H)
        assert o.getchannel("A").getbbox() == ((W - 30) // 2, 0, (W - 30) // 2 + 30, 20)
    capsys.readouterr()
    run(monkeypatch, "old", "Marks/Football/T/Helmets Left")
    assert f"canvas football_helmet_profile = {W} x {H}" in capsys.readouterr().out


def test_explicit_root(project, monkeypatch, tmp_path, capsys):
    """--root lets recanvas run from outside the project."""
    art(project / "old" / "x.png", (5, 5))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    run(monkeypatch, "old", DEST, "--root", str(project))
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
        run(monkeypatch, src, dest)
    assert msg in str(e.value)
