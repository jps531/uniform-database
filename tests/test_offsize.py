"""Tests for scripts/offsize.py: near-misses, exact matches, and every kind of skipped or unmatched file."""

import csv
import sys

import offsize
import pytest
from conftest import art, canvas_size, era

VIEW = "Football/T/Helmets Front"


def run(monkeypatch, capsys, *argv) -> str:
    """Call offsize.main() with the given arguments and return what it printed."""
    monkeypatch.setattr(sys, "argv", ["offsize.py", *argv])
    offsize.main()
    return capsys.readouterr().out


def test_content_size(tmp_path):
    """content_size is the alpha bbox size, or None for a blank image."""
    assert offsize.content_size(art(tmp_path / "a.png", (30, 20), (7, 5), top=3)) == (7, 5)
    assert offsize.content_size(art(tmp_path / "b.png", (9, 9), (0, 0))) is None


def test_exact_matches(project, cfg, monkeypatch, capsys):
    """Files exactly at their era's size are reported as exact, counting only files actually checked."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / VIEW / "x/h.png", b)
    art(project / VIEW / "y/h.png", (b[0] + 6, b[1] + 4), b, top=2)
    art(project / VIEW / "z/blank.png", (9, 9), (0, 0))
    out = run(monkeypatch, capsys, "Football")
    assert "checked 2 files under Football" in out
    assert "All 2 checked files are an exact match for their profile." in out
    assert "!!" not in out and "skipped" not in out


def test_near_misses_and_unmatched_with_csv(project, cfg, monkeypatch, capsys, tmp_path):
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
    out = run(monkeypatch, capsys, VIEW, "--csv", str(out_csv))
    assert "checked 4 files under Football/T/Helmets Front" in out
    assert "2 files are within tolerance but NOT exact:" in out
    assert (
        f"  football-helmet-front era B: {near[0]}x{near[1]} should be {b[0]}x{b[1]}  (+2, {-tol:+d})  — 2 files" in out
    )
    assert f"       {VIEW}/p/h.png" in out and f"       {VIEW}/q/h.png" in out
    assert f"1 files match NO profile entry even within tolerance {tol}:" in out
    assert f"  {far[0]}x{far[1]}  [football-helmet-front]  {VIEW}/r/h.png" in out
    assert f"Wrote {out_csv}" in out
    rows = list(csv.reader(out_csv.open()))
    assert rows[0] == ["path", "width", "height", "want_w", "want_h", "dw", "dh", "profile", "era"]
    assert [f"{VIEW}/p/h.png", str(near[0]), str(near[1]), str(b[0]), str(b[1]), "2", str(-tol)] == rows[1][:7]
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


def test_only_unmatched_without_csv(project, monkeypatch, capsys):
    """With nothing near, only the unmatched section prints, and no CSV is written."""
    art(project / VIEW / "r/h.png", (40, 40))
    out = run(monkeypatch, capsys, "Football")
    assert "NOT exact" not in out
    assert "1 files match NO profile entry" in out
    assert "Wrote" not in out


def test_skips_generated_standardized_unparsed_and_unprofiled(project, cfg, monkeypatch, capsys):
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
    out = run(monkeypatch, capsys, "Football")
    assert "checked 0 files under Football" in out
    assert "skipped 2 files in 1 generated directories" in out
    assert "skipped 1 files already on their standardized canvas" in out
    assert "!! skipped 1 files whose path is not {Sport}/{Team}/{Slot} {Viewpoint}:" in out
    assert "     Football/T/Loose  (1 files)" in out
    assert "!! skipped 2 files whose profile is not in canvas_definitions.yaml:" in out
    assert "     football-helmet-side  (2 files)" in out
    assert out.rstrip().endswith("No files were checked against a profile.")
    assert "exact" not in out


def test_fill_canvas_files_are_checked(project, cfg, monkeypatch, capsys):
    """On a `fills: fill` canvas the canvas IS the content, so files equal to it are checked, not skipped."""
    cv = canvas_size(cfg, "football_jersey_sleeve")
    art(project / "Football/T/Jerseys Left/x/s.png", cv)
    out = run(monkeypatch, capsys, "Football")
    assert "checked 1 files" in out and "All 1 checked files are an exact match" in out


def test_off_canvas_padded_file_is_checked(project, cfg, monkeypatch, capsys):
    """A padded-canvas slot only skips files sitting exactly on that canvas."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    cv = canvas_size(cfg, "football_helmet_face")
    art(project / VIEW / "x/h.png", (cv[0] + 1, cv[1]), b)
    assert "All 1 checked files are an exact match" in run(monkeypatch, capsys, "Football")


def test_marks_paths_resolve_like_sport_trees(project, cfg, monkeypatch, capsys):
    """Marks/ trees are checked against the same sport-qualified profile."""
    f = era(cfg, "football-helmet-right", "D")["size"]
    art(project / "Marks/Football/T/Helmets Right/x/h.png", (f[0] - 1, f[1]))
    out = run(monkeypatch, capsys, "Marks")
    assert f"football-helmet-right era D: {f[0] - 1}x{f[1]} should be {f[0]}x{f[1]}  (-1, +0)" in out


def test_explicit_root_and_bad_target(project, monkeypatch, capsys, tmp_path):
    """--root works from outside the project; a missing target exits."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    (project / "Football").mkdir()
    assert "No files were checked" in run(monkeypatch, capsys, "Football", "--root", str(project))
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, capsys, "Nope", "--root", str(project))
    assert "Not a directory" in str(e.value)
