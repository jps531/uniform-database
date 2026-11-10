"""Tests for scripts/golden/golden_ci.py: a consistent synthetic fixture passes, and each kind of drift fails by name.

The fixture is built once per module, end to end, the way it is on the Mac:
helmet marks for every era on both sides padded with standardize.py, venues
cropped with derive_crops.py, golden_run.py, then golden_fixture.py --apply.
Each test copies just what CI has (configs, scripts, manifest, fixture).
"""

import os
import runpy
import shutil
import sys
import tempfile
from pathlib import Path

import derive_crops
import golden_ci
import golden_fixture
import golden_run
import pytest
import standardize
from conftest import REPO, art, canvas_size, era
from PIL import Image
from test_golden_fixture import ERAS, TEAM, mark, small_configs, write_manifest

ELEMENTS = dict(zip(ERAS, ("1950 White", "1960 White", "1970 White", "1980 White", "1990 White", "2020 Maroon")))
VENUES = (
    ("Football", "Fields", "football_field"),
    ("Baseball", "Fields", "baseball_field"),
    ("Basketball", "Courts", "basketball_court"),
)


def call(mp, module, *argv):
    """Run `module.main()` in-process with argv, treating a zero or absent exit as success."""
    mp.setattr(sys, "argv", [module.__name__, *argv])
    try:
        module.main()
    except SystemExit as e:
        assert e.code in (0, None), e.code


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    """A project built end to end once: artwork, padded helmets, crops, a golden run and an applied fixture."""
    root = tmp_path_factory.mktemp("ci") / "project"
    root.mkdir()
    for name in ("configs", "scripts"):
        os.symlink(REPO / name, root / name)
    (root / "golden").mkdir()
    cfg = small_configs(root)
    for side in ("Left", "Right"):
        for i, (e, el) in enumerate(ELEMENTS.items()):
            mark(root, cfg, side, el, e, seed=i)
    for vp in ("front", "back"):
        w, h = era(cfg, f"football-helmet-{vp}", "F")["size"]
        art(
            root / "Football" / TEAM / f"Helmets {vp.title()}/2020 Maroon/2020 Maroon.png",
            canvas_size(cfg, "football_helmet_face"),
            (w, h),
        )
    for i, (sport, sdir, canvas) in enumerate(VENUES):
        for j, el in enumerate(("2020 A", "2021 B")):
            art(
                root / "Venues" / sport / TEAM / f"{sdir} Full/{el}/{el}.png",
                canvas_size(cfg, f"{canvas}_full"),
                seed=10 * i + j,
            )
    write_manifest(
        root,
        [
            {
                "id": "football--helmets-4--01",
                "sport": "football",
                "view": "helmets-4",
                "team": TEAM,
                "uniform1": {"helmet": "2020 Maroon"},
            }
        ],
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(root)
        for side in ("Left", "Right"):
            call(
                mp,
                standardize,
                "--root",
                str(root),
                "pad",
                f"Marks/Football/{TEAM}/Helmets {side}",
                f"Football/{TEAM}/Helmets {side}",
            )
        call(mp, derive_crops, "--root", str(root), "--apply")
        call(mp, golden_run, "--strict")
        call(mp, golden_fixture, "--root", str(root), "--apply")
    return root


@pytest.fixture
def ci(base, tmp_path, monkeypatch) -> Path:
    """A fresh copy of what CI sees: configs, scripts, the manifest and the fixture; temp files kept under tmp_path."""
    root = tmp_path / "repo"
    (root / "golden").mkdir(parents=True)
    shutil.copytree(base / "configs", root / "configs")
    os.symlink(REPO / "scripts", root / "scripts")
    shutil.copy2(base / "golden/manifest.yaml", root / "golden/manifest.yaml")
    shutil.copytree(base / "golden/fixture", root / "golden/fixture")
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return root


def run_ci(monkeypatch, capsys, root: Path, *flags) -> tuple:
    """Run golden_ci.main() on `root`; returns (exit code, stdout)."""
    monkeypatch.setattr(sys, "argv", ["golden_ci.py", "--root", str(root), *flags])
    with pytest.raises(SystemExit) as e:
        golden_ci.main()
    return e.value.code, capsys.readouterr().out


def fixture_path(root: Path, *parts) -> Path:
    """A path inside root/golden/fixture."""
    return root.joinpath("golden", "fixture", *parts)


def test_consistent_fixture_passes(ci, monkeypatch, capsys, tmp_path):
    """A fixture built from a clean run passes all three checks, writes the job summary and cleans up."""
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 0, out
    assert "Every composition, helmet and venue is ok." in out
    assert "## Golden suite" in summary.read_text()
    assert (ci / "golden/run/REPORT.md").is_file()
    assert list((tmp_path / "temp").iterdir()) == []


def test_keep_leaves_the_temporary_project(ci, monkeypatch, capsys, tmp_path):
    """--keep prints the temporary project's path and leaves it in place."""
    code, out = run_ci(monkeypatch, capsys, ci, "--keep")
    assert code == 0
    kept = Path(out.split("kept ", 1)[1].split()[0])
    assert kept.is_relative_to(tmp_path / "temp")
    assert (kept / "golden/run/REPORT.md").is_file()


def test_changed_pixel_in_generated_helmet_fails(ci, monkeypatch, capsys):
    """One pixel changed in a fixture's generated helmet fails the helmet check for that file."""
    rel = Path(ELEMENTS["A"]) / f"{ELEMENTS['A']}.png"
    f = fixture_path(ci, "Football", TEAM, "Helmets Left", rel)
    with Image.open(f) as im:
        im = im.convert("RGBA")
        x, y = im.getchannel("A").getbbox()[:2]
        r, g, b, a = im.getpixel((x, y))
        im.putpixel((x, y), ((r + 1) % 256, g, b, a))
        im.save(f)
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert f"- helmets {TEAM} Left: pixels differ: {rel}" in out


def test_different_crop_fails(ci, monkeypatch, capsys):
    """A cropped venue that no longer matches its re-derived crop fails the venue check."""
    rel = Path("2021 B/2021 B.png")
    f = fixture_path(ci, "Venues", "Baseball", TEAM, "Fields Cropped", rel)
    with Image.open(f) as im:
        size = im.size
    art(f, size, seed=99)
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert f"- venues Baseball/{TEAM}/Fields Cropped: pixels differ: {rel}" in out


def test_missing_helmet_era_fails(ci, monkeypatch, capsys):
    """A fixture with no mark of one era fails the coverage check for that era and side."""
    el = ELEMENTS["C"]
    for tree in ("Football", "Marks/Football"):
        shutil.rmtree(fixture_path(ci, tree, TEAM, "Helmets Right", el))
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "- helmets: no right mark of era C in the fixture" in out
    assert "no left mark" not in out


def test_unresolvable_composition_fails(ci, monkeypatch, capsys):
    """A placement the fixture can no longer resolve fails the composition check."""
    shutil.rmtree(fixture_path(ci, "Football", TEAM, "Helmets Front"))
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "- compositions: golden_run.py --strict failed (see REPORT.md)" in out
    assert "## Defects" in (ci / "golden/run/REPORT.md").read_text()


def test_composition_check_without_a_run_fails(ci, monkeypatch, capsys):
    """When golden_run.py writes no run at all (no manifest), the composition check fails and nothing is copied back."""
    (ci / "golden/manifest.yaml").unlink()
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "- compositions: golden_run.py --strict failed (see REPORT.md)" in out
    assert not (ci / "golden/run").exists()


def test_empty_fixture_fails(ci, monkeypatch, capsys):
    """An empty fixture fails at once with instructions to build it."""
    shutil.rmtree(fixture_path(ci))
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "golden/fixture/ is empty: run scripts/golden/golden_fixture.py --apply" in out


def test_fixture_without_helmet_marks_fails(ci, monkeypatch, capsys):
    """A fixture with no Marks helmet folders fails the helmet check."""
    shutil.rmtree(fixture_path(ci, "Marks"))
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "- helmets: the fixture has no Marks/Football/*/Helmets Left|Right" in out


def test_derived_sport_without_venue_fails(ci, monkeypatch, capsys):
    """A sport whose canvases have derived_from but no venue in the fixture fails the venue check."""
    shutil.rmtree(fixture_path(ci, "Venues", "Basketball"))
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "- venues: the fixture has no cropped venue for basketball" in out
    assert "for football" not in out and "for baseball" not in out


def test_pad_refusal_fails(ci, monkeypatch, capsys):
    """A Marks helmet folder that standardize.py refuses to pad is reported as a failure."""
    fixture_path(ci, "Marks", "Football", "Other", "Helmets Left").mkdir(parents=True)
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "- helmets: pad refused Other / Helmets Left" in out


def test_derive_crops_refusal_fails(ci, monkeypatch, capsys):
    """A Full venue that derive_crops.py refuses (off its canvas) is reported as a failure."""
    art(fixture_path(ci, "Venues", "Football", TEAM, "Fields Full", "2030 X", "2030 X.png"), (5, 5))
    code, out = run_ci(monkeypatch, capsys, ci)
    assert code == 1
    assert "- venues: derive_crops.py refused" in out


def test_compare_reports_missing_extra_and_different(tmp_path):
    """compare() lists files not regenerated, regenerated extras and pixel differences, ignoring hidden paths."""
    got, want = tmp_path / "got", tmp_path / "want"
    art(got / "same.png", (4, 4))
    art(want / "same.png", (4, 4))
    art(got / "diff.png", (4, 4), seed=1)
    art(want / "diff.png", (4, 4), seed=2)
    art(got / "extra.png", (4, 4))
    art(want / "a/missing.png", (4, 4))
    art(want / ".hidden/x.png", (4, 4))
    assert golden_ci.compare("L", got, want) == [
        "L: not regenerated: a/missing.png",
        "L: regenerated but not in the fixture: extra.png",
        "L: pixels differ: diff.png",
    ]
    assert golden_ci.png_set(tmp_path / "nope") == set()


def test_same_pixels_compares_size_and_rgba(tmp_path):
    """same_pixels() is false for different sizes and true for equal pixels in different encodings."""
    a = art(tmp_path / "a.png", (4, 4))
    b = tmp_path / "b.png"
    with Image.open(a) as im:
        im.save(b, compress_level=0)
    assert golden_ci.same_pixels(a, b)
    assert not golden_ci.same_pixels(a, art(tmp_path / "c.png", (4, 5)))


def test_main_finds_root_from_cwd(project, monkeypatch, capsys):
    """Without --root, main() uses the project found from the working directory."""
    monkeypatch.setattr(sys, "argv", ["golden_ci.py"])
    with pytest.raises(SystemExit) as e:
        golden_ci.main()
    assert e.value.code == 1
    assert "golden/fixture/ is empty" in capsys.readouterr().out


def test_find_root_exits_without_configs(tmp_path):
    """find_root() exits when no directory above holds the configs."""
    with pytest.raises(SystemExit) as e:
        golden_ci.find_root(tmp_path)
    assert "No configs/canvas_definitions.yaml" in str(e.value.code)


def test_runs_as_a_script(monkeypatch):
    """Run as a script, the module reaches main(); --help exits cleanly."""
    monkeypatch.setattr(sys, "argv", ["golden_ci.py", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(REPO / "scripts" / "golden" / "golden_ci.py"), run_name="__main__")
    assert e.value.code == 0


def test_png_set_ignores_dot_folders_only_inside_the_folder(tmp_path):
    """A dot-folder ABOVE the scanned folder (a checkout under .claude/, say) hides nothing; one inside it does."""
    root = tmp_path / ".hidden-parent" / "fixture"
    art(root / "a" / "x.png", (4, 4))
    art(root / ".cache" / "y.png", (4, 4))
    art(root / "a" / ".z.png", (4, 4))
    assert golden_ci.png_set(root) == {Path("a/x.png")}
