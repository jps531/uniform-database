"""Tests for scripts/migration/classify.py: canvas provenance (RAW / OLD-STD / NEW-STD) and scale state (SCALED / UNSCALED)."""

import sys

import classify
import pytest
from conftest import art, canvas_size, era

VIEW = "Football/T/Helmets Front"


def run(monkeypatch, capsys, *argv) -> str:
    """Call classify.main() with the given arguments and return what it printed."""
    monkeypatch.setattr(sys, "argv", ["classify.py", *argv])
    classify.main()
    return capsys.readouterr().out


def row(n, where, content, how, flag="") -> str:
    """One count line, formatted as classify prints it."""
    return f"   {n:>4}  {where:<9} content {content:<12} {how}{flag}"


def scaled(e: dict) -> tuple:
    """The content size an era's scale produces from its listed size."""
    return round(e["size"][0] * e["scale"]), round(e["size"][1] * e["scale"])


def test_near_uses_tolerance():
    """near() accepts sizes up to TOL apart on each axis, and no further."""
    assert classify.near((100, 100), (100 + classify.TOL, 100 - classify.TOL))
    assert not classify.near((100, 100), (100 + classify.TOL + 1, 100))
    assert classify.slug("Men's Basketball") == "mens_basketball"


def test_classifies_canvas_and_scale_state(project, cfg, monkeypatch, capsys):
    """Each file is labelled by the canvas it sits on and whether its era's scale is already applied."""
    cv = canvas_size(cfg, "football_helmet_face")
    old = classify.WAS["football_helmet_face"]
    a = era(cfg, "football-helmet-front", "A")
    b = tuple(era(cfg, "football-helmet-front", "B")["size"])
    post = scaled(a)
    d = project / VIEW
    art(d / "new" / "h.png", cv, b)
    art(d / "new" / "h2.png", cv, b)
    art(d / "old" / "h.png", old, post)
    art(d / "raw" / "h.png", tuple(a["size"]))
    art(d / "odd" / "h.png", (100, 100), (50, 50))
    art(d / "blank" / "h.png", (20, 20), (0, 0))
    art(d / "x" / ".hidden.png", cv, b)
    out = run(monkeypatch, capsys, "Football")
    assert f"\nFootball  T / Helmets Front\n{row(2, 'NEW-STD', f'{b[0]}x{b[1]}', 'era B, no correction')}\n" in out
    assert row(1, "OLD-STD", f"{post[0]}x{post[1]}", "SCALED (era A)", "  <-- CANNOT RE-PAD") in out
    assert row(1, "RAW", f"{a['size'][0]}x{a['size'][1]}", f"UNSCALED (era A, needs x{a['scale']})") in out
    assert row(1, "? 100x100", "50x50", "NO ERA MATCH") in out
    assert row(1, "? 20x20", "0x0", "NO ERA MATCH") in out
    assert len([ln for ln in out.splitlines() if ln.startswith("   ")]) == 5


def test_era_canvas_counts_as_new(project, cfg, monkeypatch, capsys):
    """A file on an era's own canvas (soccer long sleeve) is NEW-STD, one on that canvas's old size OLD-STD."""
    ls = canvas_size(cfg, "soccer_jersey_ls")
    art(project / "Soccer/MSU/Jerseys Front/k/j.png", ls, (10, 10))
    art(project / "Soccer/MSU/Jerseys Front/o/j.png", classify.WAS["soccer_jersey_ls"], (11, 11))
    art(project / "Soccer/MSU/Jerseys Front/r/j.png", (12, 12))
    out = run(monkeypatch, capsys, "Soccer")
    assert row(1, "NEW-STD", "10x10", "NO ERA MATCH") in out
    assert row(1, "OLD-STD", "11x11", "NO ERA MATCH") in out
    assert row(1, "RAW", "12x12", "NO ERA MATCH") in out


def test_skips_paths_it_cannot_place(project, monkeypatch, capsys):
    """Files with no slot directory, no known sport, or no assigned canvas are ignored."""
    art(project / "Football/T/Loose/x.png", (5, 5))
    art(project / "Curling/T/Jerseys Front/x.png", (5, 5))
    art(project / "Football/T/Helmets Side/x.png", (5, 5))
    assert run(monkeypatch, capsys).strip() == ""


def test_sport_flag_supplies_missing_sport(project, cfg, monkeypatch, capsys):
    """--sport classifies temp/{Team}/{View} trees that carry no sport segment, and without it they're skipped."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / "temp/T/Helmets Front/x/h.png", b)
    assert run(monkeypatch, capsys, "temp").strip() == ""
    out = run(monkeypatch, capsys, "temp", "--sport", "Football")
    assert "\ntemp  T / Helmets Front\n" in out
    assert row(1, "RAW", f"{b[0]}x{b[1]}", "era B, no correction") in out


def test_finds_root_from_a_subdirectory(project, cfg, monkeypatch, capsys):
    """Run from below the project root, classify still finds the config and resolves targets from the root."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / VIEW / "x/h.png", b)
    sub = project / "deep" / "er"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    out = run(monkeypatch, capsys, "Football")
    assert row(1, "RAW", f"{b[0]}x{b[1]}", "era B, no correction") in out


@pytest.mark.parametrize("args", [(), (".",)])
def test_default_target_is_whole_project(project, cfg, monkeypatch, capsys, args):
    """With no path, or '.', the whole project is classified."""
    b = era(cfg, "football-helmet-front", "B")["size"]
    art(project / VIEW / "x/h.png", b)
    assert "\n.  T / Helmets Front\n" in run(monkeypatch, capsys, *args)
