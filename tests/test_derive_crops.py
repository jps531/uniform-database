"""Tests for scripts/pipeline/derive_crops.py: rules from config, crop geometry, dry run vs --apply, markers and refusals."""

import json
import runpy
import sys

import derive_crops as dc
import numpy as np
import pytest
from conftest import REPO, art, canvas_size
from PIL import Image
from test_golden_fixture import TEAM, small_configs


def full(root, cfg, sport="football", element="2020 Grass", seed=0, size=None, team=TEAM, tree="Venues"):
    """Draw one Full playing surface for `sport` on its canvas (or `size`); returns the path."""
    slot = "court" if sport == "basketball" else "field"
    sdir = "Courts" if slot == "court" else "Fields"
    path = root / tree / sport.title() / team / f"{sdir} Full" / element / f"{element}.png"
    return art(path, size or canvas_size(cfg, f"{sport}_{slot}_full"), seed=seed)


def cropped_of(path):
    """The Cropped sibling of a Full file."""
    return path.parents[2] / path.parents[1].name.replace(" Full", " Cropped") / path.parent.name / path.name


def run_main(monkeypatch, root, *flags):
    """Call derive_crops.main() with --root and the given flags."""
    monkeypatch.setattr(sys, "argv", ["derive_crops.py", "--root", str(root), *flags])
    dc.main()


def test_jobs_for_reads_every_derived_canvas_from_the_real_config(cfg):
    """jobs_for() yields one OK rule per derived canvas, with the source viewpoint and crop from config."""
    rules = list(dc.jobs_for(cfg, None))
    assert {r[1] for r in rules} == {"football", "baseball", "basketball"}
    for status, sport, slot, src_vp, dst_vp, csrc, cdst, crop in rules:
        assert (status, src_vp, dst_vp) == ("OK", "full", "cropped")
        assert csrc == cfg["canvases"][f"{sport}_{slot}_full"]
        assert crop == tuple(cdst["derived_from"]["crop_at"])
    assert [r[1] for r in dc.jobs_for(cfg, "baseball")] == ["baseball"]


def test_jobs_for_reports_a_source_no_viewpoint_uses():
    """A derived canvas whose source canvas no viewpoint of the slot uses yields an ERROR rule."""
    cfg = {
        "canvases": {"a": {}, "b": {"derived_from": {"canvas": "zzz", "crop_at": [0, 0]}}},
        "assignments": {"s": {"field": {"full": "a", "cropped": "b", "other": "missing"}}},
    }
    assert list(dc.jobs_for(cfg, None)) == [("ERROR", "s", "field", "cropped", "no viewpoint of s/field uses zzz")]


def test_dry_run_reports_geometry_and_writes_nothing(project, monkeypatch, capsys):
    """Without --apply, main() prints each rule's crop and file count and writes nothing."""
    cfg = small_configs(project)
    f = full(project, cfg)
    run_main(monkeypatch, project, "--sport", "football")
    out = capsys.readouterr().out
    c = cfg["canvases"]["football_field_cropped"]
    s = cfg["canvases"]["football_field_full"]
    cx, cy = c["derived_from"]["crop_at"]
    assert "football/field: Fields Full -> Fields Cropped" in out
    assert f"crop {c['width']}x{c['height']} from ({cx}, {cy}) of {s['width']}x{s['height']}" in out
    assert f"margins {cx}/{s['width'] - cx - c['width']} horizontal" in out
    assert "DRY RUN — 1 files would be written." in out
    assert not cropped_of(f).parent.exists()


def test_apply_crops_every_sport_at_its_geometry_and_writes_markers(project, monkeypatch, capsys):
    """--apply writes each crop at the configured box, at 300 DPI, with a .generated marker per derived tree."""
    cfg = small_configs(project)
    sources = [full(project, cfg, s, seed=i) for i, s in enumerate(("football", "baseball", "basketball"))]
    art(sources[0].parent / ".hidden.png", (3, 3))
    run_main(monkeypatch, project, "--apply")
    assert "Wrote 3 files." in capsys.readouterr().out
    for sport, src in zip(("football", "baseball", "basketball"), sources):
        slot = "court" if sport == "basketball" else "field"
        c = cfg["canvases"][f"{sport}_{slot}_cropped"]
        cx, cy = c["derived_from"]["crop_at"]
        out = cropped_of(src)
        with Image.open(src) as a, Image.open(out) as b:
            want = np.asarray(a.convert("RGBA"))[cy : cy + c["height"], cx : cx + c["width"]]
            assert b.size == (c["width"], c["height"])
            assert np.array_equal(np.asarray(b.convert("RGBA")), want)
            assert round(b.info["dpi"][0]) == 300
        marker = json.loads((out.parents[1] / ".generated").read_text())
        assert marker["generated_by"] == "scripts/pipeline/derive_crops.py"
        assert marker["files_written"] == 1
    assert not (cropped_of(sources[0]).parent / ".hidden.png").exists()


def test_refuses_to_apply_while_a_source_is_off_canvas(project, monkeypatch, capsys):
    """A Full file not on its canvas is listed as a problem; the dry run continues and --apply refuses."""
    cfg = small_configs(project)
    good = full(project, cfg)
    bad = full(project, cfg, element="2021 Bad", size=(7, 9))
    run_main(monkeypatch, project, "--sport", "football")
    out = capsys.readouterr().out
    W, H = canvas_size(cfg, "football_field_full")
    assert f"{bad.relative_to(project)}  (7x9, expected {W}x{H})" in out
    assert "DRY RUN — 1 files would be written." in out
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project, "--sport", "football", "--apply")
    assert e.value.code == "Refusing to apply while problems remain."
    assert not cropped_of(good).exists()


def test_refuses_a_crop_box_outside_the_source(project, monkeypatch, capsys):
    """A crop_at that pushes the box past the source canvas is a problem and blocks --apply."""

    def push(cfg):
        """Move football's crop past the right edge."""
        cfg["canvases"]["football_field_cropped"]["derived_from"]["crop_at"][0] = 10_000

    cfg = small_configs(project, push)
    full(project, cfg)
    with pytest.raises(SystemExit):
        run_main(monkeypatch, project, "--sport", "football", "--apply")
    assert "football/field/cropped  (crop box falls outside the source canvas)" in capsys.readouterr().out


def test_reports_a_slot_missing_from_directory_slots(project, monkeypatch, capsys):
    """A derived slot with no directory name is a problem."""
    cfg = small_configs(project, lambda c: c["directory_slots"].pop("Fields"))
    full(project, cfg)
    run_main(monkeypatch, project, "--sport", "baseball")
    assert "baseball/field  (slot missing from directory_slots)" in capsys.readouterr().out


def test_prints_error_rules_and_exits_when_no_rules_remain(project, monkeypatch, capsys):
    """ERROR rules are printed, and with no OK rule left main() exits naming the sport filter."""

    def broken(cfg):
        """Point football's crop at a canvas none of its viewpoints use."""
        cfg["canvases"]["football_field_cropped"]["derived_from"]["canvas"] = "nowhere"

    small_configs(project, broken)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project, "--sport", "football")
    assert e.value.code == "No canvases carry a `derived_from` block for sport 'football'."
    assert "!! football/field/cropped: no viewpoint of football/field uses nowhere" in capsys.readouterr().out


def test_exits_when_no_canvas_is_derived(project, monkeypatch):
    """With no derived_from anywhere, main() exits without a sport suffix."""

    def strip(cfg):
        """Remove every derived_from block."""
        for c in cfg["canvases"].values():
            c.pop("derived_from", None)

    small_configs(project, strip)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project)
    assert e.value.code == "No canvases carry a `derived_from` block."


def test_sport_tree_fallback_and_teams_without_source(project, monkeypatch, capsys):
    """Without Venues/<Sport>, the uniform tree is searched; teams without the source viewpoint are skipped."""
    cfg = small_configs(project)
    f = full(project, cfg, tree=".", team="Alpha")
    (project / "Football/Beta/Jerseys Front").mkdir(parents=True)
    (project / "Football/stray.txt").write_text("")
    run_main(monkeypatch, project, "--sport", "football", "--apply")
    assert cropped_of(f).is_file()
    assert not (project / "Football/Beta/Fields Cropped").exists()


def test_empty_source_writes_no_marker(project, monkeypatch, capsys):
    """A Full folder holding no files produces no derived folder or marker; a missing sport tree finds nothing."""
    small_configs(project)
    src = project / "Venues/Football" / TEAM / "Fields Full"
    src.mkdir(parents=True)
    run_main(monkeypatch, project, "--apply")
    assert "Wrote 0 files." in capsys.readouterr().out
    assert not (src.parent / "Fields Cropped").exists()


def test_main_finds_root_from_cwd(project, monkeypatch, capsys):
    """Without --root, main() finds the project from the working directory."""
    monkeypatch.setattr(sys, "argv", ["derive_crops.py"])
    dc.main()
    assert "DRY RUN — 0 files" in capsys.readouterr().out


def test_find_root_exits_without_configs(tmp_path):
    """find_root() exits when no directory above holds the configs."""
    with pytest.raises(SystemExit) as e:
        dc.find_root(tmp_path)
    assert "No configs/canvas_definitions.yaml" in str(e.value.code)


def test_runs_as_a_script(monkeypatch):
    """Run as a script, the module reaches main(); --help exits cleanly."""
    monkeypatch.setattr(sys, "argv", ["derive_crops.py", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(REPO / "scripts" / "pipeline" / "derive_crops.py"), run_name="__main__")
    assert e.value.code == 0
