"""Tests for scripts/migration/offsize.py: near-misses, exact matches, and every kind of skipped or unmatched file."""

import csv

import common
import offsize
import pytest
from helpers import art, blank, canvas_size, era, main

VIEW = "Football/T/Helmets Front"


def test_content_size(tmp_path):
    """content_size is the alpha bbox size, or None for a blank image."""
    assert common.content_size(art(tmp_path / "a.png", (30, 20), (7, 5), top=3)) == (7, 5)
    assert common.content_size(blank(tmp_path / "b.png", (9, 9))) is None


def test_exact_matches(project, cfg, monkeypatch):
    """Files exactly at their era's size are reported as exact, counting only files actually checked."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / VIEW / "x/h.png", b)
    art(project / VIEW / "y/h.png", (b[0] + 6, b[1] + 4), b, top=2)
    blank(project / VIEW / "z/blank.png", (9, 9))
    out = main(monkeypatch, offsize, "Football")
    assert "checked 2 files under Football" in out
    assert "All 2 checked files are an exact match for their profile." in out
    assert "!!" not in out
    assert "skipped" not in out


def test_near_misses_and_unmatched_with_csv(project, cfg, monkeypatch, tmp_path):
    """Files inside tolerance but off-size are grouped with their offset; ones beyond tolerance are UNMATCHED; --csv lists both."""
    tol = cfg["tolerance"]
    b = era(cfg, "football-helmet-front", "B")["size"]
    near = (b[0] + 2, b[1] - tol)
    far = (b[0] + tol + 1, b[1])
    art(project / VIEW / "p/h.png", near)
    art(project / VIEW / "q/h.png", near, seed=1)
    art(project / VIEW / "r/h.png", far)
    art(project / VIEW / "s/h.png", b)
    out_csv = tmp_path / "off.csv"
    out = main(monkeypatch, offsize, VIEW, "--csv", str(out_csv))
    assert "checked 4 files under Football/T/Helmets Front" in out
    assert "2 files are within tolerance but NOT exact:" in out
    assert (
        f"  football-helmet-front era B: {near[0]}x{near[1]} should be {b[0]}x{b[1]}  (+2, {-tol:+d})  — 2 files" in out
    )
    assert f"       {VIEW}/p/h.png" in out
    assert f"       {VIEW}/q/h.png" in out
    assert f"1 files match NO profile entry even within tolerance {tol}:" in out
    assert f"  {far[0]}x{far[1]}  [football-helmet-front]  {VIEW}/r/h.png" in out
    assert f"Wrote {out_csv}" in out
    rows = list(csv.reader(out_csv.open()))
    assert rows[0] == ["path", "width", "height", "want_w", "want_h", "dw", "dh", "profile", "era"]
    assert rows[1][:7] == [f"{VIEW}/p/h.png", str(near[0]), str(near[1]), str(b[0]), str(b[1]), "2", str(-tol)]
    assert rows[-1] == [
        f"{VIEW}/r/h.png",
        str(far[0]),
        str(far[1]),
        "",
        "",
        "",
        "",
        "football-helmet-front",
        "UNMATCHED",
    ]
    assert len(rows) == 4


def test_only_unmatched_without_csv(project, monkeypatch):
    """With nothing near, only the unmatched section prints, and no CSV is written."""
    art(project / VIEW / "r/h.png", (40, 40))
    out = main(monkeypatch, offsize, "Football")
    assert "NOT exact" not in out
    assert "1 files match NO profile entry" in out
    assert "Wrote" not in out


def test_skips_generated_standardized_unparsed_and_unprofiled(project, cfg, monkeypatch):
    """Generated trees, files on their padded canvas, non-tree paths and missing profiles are skipped and counted."""
    cv = canvas_size(cfg, "football_helmet_face")
    b = era(cfg, "football-helmet-front", "B")["size"]
    gen = project / "Football/T/Helmets Left"
    art(gen / "x/h.png", (50, 50))
    art(gen / "y/h.png", (50, 50))
    (gen / ".generated").write_text("{}")
    art(project / VIEW / "std/h.png", cv, b)
    art(project / VIEW / ".hidden/h.png", (50, 50))
    art(project / "Football/T/Loose/h.png", (5, 5))
    art(project / "Football/T/Helmets Side/x/h.png", (5, 5))
    art(project / "Football/T/Helmets Side/y/h.png", (5, 5))
    out = main(monkeypatch, offsize, "Football")
    assert "checked 0 files under Football" in out
    assert "skipped 2 files in 1 generated directories" in out
    assert "skipped 1 files already on their standardized canvas" in out
    assert "!! skipped 1 files whose path is not {Sport}/{Team}/{Slot} {Viewpoint}:" in out
    assert "     Football/T/Loose  (1 files)" in out
    assert "!! skipped 2 files whose profile is not in canvas_definitions.yaml:" in out
    assert "     football-helmet-side  (2 files)" in out
    assert out.rstrip().endswith("No files were checked against a profile.")
    assert "exact" not in out


def test_fill_canvas_files_are_checked(project, cfg, monkeypatch):
    """On a `fills: fill` canvas the canvas IS the content, so files equal to it are checked, not skipped."""
    cv = canvas_size(cfg, "football_jersey_sleeve")
    art(project / "Football/T/Jerseys Left/x/s.png", cv)
    out = main(monkeypatch, offsize, "Football")
    assert "checked 1 files" in out
    assert "All 1 checked files are an exact match" in out


def test_off_canvas_padded_file_is_checked(project, cfg, monkeypatch):
    """A padded-canvas slot only skips files sitting exactly on that canvas."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    cv = canvas_size(cfg, "football_helmet_face")
    art(project / VIEW / "x/h.png", (cv[0] + 1, cv[1]), b)
    assert "All 1 checked files are an exact match" in main(monkeypatch, offsize, "Football")


def test_marks_paths_resolve_like_sport_trees(project, cfg, monkeypatch):
    """Marks/ trees are checked against the same sport-qualified profile."""
    f = era(cfg, "football-helmet-right", "D")["size"]
    art(project / "Marks/Football/T/Helmets Right/x/h.png", (f[0] - 1, f[1]))
    out = main(monkeypatch, offsize, "Marks")
    assert f"football-helmet-right era D: {f[0] - 1}x{f[1]} should be {f[0]}x{f[1]}  (-1, +0)" in out


def test_explicit_root_and_bad_target(project, monkeypatch, tmp_path):
    """--root works from outside the project; a missing target exits."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    (project / "Football").mkdir()
    assert "No files were checked" in main(monkeypatch, offsize, "Football", "--root", str(project))
    with pytest.raises(SystemExit, match="Not a directory"):
        main(monkeypatch, offsize, "Nope", "--root", str(project))


def test_files_on_an_era_canvas_are_skipped_as_standardized(project, cfg, monkeypatch):
    """A file on an era's own canvas (soccer long sleeve) is standardized output, skipped like one on the slot canvas."""
    ls = canvas_size(cfg, "soccer_jersey_ls")
    e = era(cfg, "soccer-jersey-front", "ls")["size"]
    art(project / "Soccer/T/Jerseys Front/k/j.png", ls, (e[0] - 2, e[1]))
    out = main(monkeypatch, offsize, "Soccer")
    assert "skipped 1 files already on their standardized canvas" in out
    assert "checked 0 files" in out


def test_standard_canvases_mirror_pad(cfg):
    """standard_canvases is the slot canvas plus every era canvas override, leaving out `fills: fill` ones."""
    slot = cfg["assignments"]["soccer"]["jersey"]["front"]
    got = common.standard_canvases(cfg, cfg["canvases"][slot], cfg["profiles"]["soccer-jersey-front"])
    assert got == {canvas_size(cfg, slot), canvas_size(cfg, "soccer_jersey_ls")}
    sleeve = cfg["canvases"]["football_jersey_sleeve"]
    fill_era = [{"era": "x", "size": [1, 1], "canvas": "football_jersey_sleeve"}]
    assert common.standard_canvases(cfg, sleeve, fill_era) == set()


def test_offsize_compares_with_the_closest_era(project, cfg, monkeypatch):
    """A width in both the helmet back E and E2 windows but nearer E2 is measured against E2, the closer one."""
    e2 = era(cfg, "football-helmet-back", "E2")["size"]
    art(project / "Football/T/Helmets Back/x/h.png", (e2[0] - 3, e2[1]))
    out = main(monkeypatch, offsize, "Football")
    assert f"football-helmet-back era E2: {e2[0] - 3}x{e2[1]} should be {e2[0]}x{e2[1]}  (-3, +0)" in out
