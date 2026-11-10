"""Tests for scripts/golden/golden_ci.py: a consistent synthetic fixture passes, and each kind of drift fails by name.

The fixture is built once per module, end to end, the way it is on the Mac:
helmet marks for every era on both sides padded with standardize.py, venues
cropped with derive_crops.py, golden_run.py, then golden_fixture.py --apply.
Each test copies just what CI has (configs, scripts, manifest, fixture).

A full golden_ci.main() renders every composition through golden_run.py and
compose.py, so only three tests run it end to end (a pass, a composition
failure, an empty fixture). The helmet and venue drift cases call
check_helmets() / check_venues() on the throwaway project main() would
build. The module's tests are marked to share one xdist worker
(`--dist loadgroup`) so the module-scoped build happens once; with
pytest-xdist 3.8 on pytest 9.2 the mark has no effect yet (see
pyproject.toml), and each worker builds its own.
"""

import re
import shutil
import tempfile
from pathlib import Path

import common
import derive_crops
import golden_ci
import golden_fixture
import golden_run
import pytest
import standardize
from helpers import (
    ERAS,
    REPO,
    TEAM,
    art,
    canvas_size,
    era,
    main,
    make_project,
    mark,
    small_configs,
    write_manifest,
)
from PIL import Image

pytestmark = pytest.mark.xdist_group("golden_ci")

ELEMENTS = dict(zip(ERAS, ("1950 White", "1960 White", "1970 White", "1980 White", "1990 White", "2020 Maroon")))
VENUES = (
    ("Football", "Fields", "football_field"),
    ("Baseball", "Fields", "baseball_field"),
    ("Basketball", "Courts", "basketball_court"),
)


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    """A project built end to end once: artwork, padded helmets, crops, a golden run and an applied fixture."""
    root = make_project(tmp_path_factory.mktemp("ci") / "project")
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
            src, dest = f"Marks/Football/{TEAM}/Helmets {side}", f"Football/{TEAM}/Helmets {side}"
            main(mp, standardize, "--root", str(root), "pad", src, dest)
        main(mp, derive_crops, "--root", str(root), "--apply")
        main(mp, golden_run, "--strict")
        main(mp, golden_fixture, "--root", str(root), "--apply")
    return root


@pytest.fixture
def ci(base, tmp_path, monkeypatch) -> Path:
    """A fresh copy of what CI sees: configs, scripts, the manifest and the fixture; temp files kept under tmp_path."""
    root = tmp_path / "repo"
    (root / "golden").mkdir(parents=True)
    shutil.copytree(base / "configs", root / "configs")
    (root / "scripts").symlink_to(REPO / "scripts")
    shutil.copy2(base / "golden/manifest.yaml", root / "golden/manifest.yaml")
    shutil.copytree(base / "golden/fixture", root / "golden/fixture")
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return root


@pytest.fixture
def tmp(ci, tmp_path) -> Path:
    """The throwaway project main() builds from the CI copy (golden_ci.build_project), for calling one check."""
    t = tmp_path / "golden-x" / "project"
    golden_ci.build_project(ci, ci / "golden/fixture", t)
    return t


@pytest.fixture
def ci_cfg(ci) -> dict:
    """The CI copy's (scaled-down) canvas config, as main() loads it."""
    return common.load_config(ci)


def fixture_path(root: Path, *parts) -> Path:
    """A path inside root/golden/fixture."""
    return root.joinpath("golden", "fixture", *parts)


def nudge_first_pixel(f: Path) -> None:
    """Change the red channel of the first opaque pixel of a PNG by one."""
    with Image.open(f) as im:
        im = im.convert("RGBA")
    box = im.getchannel("A").getbbox()
    assert box is not None
    x, y = box[:2]
    px = im.getpixel((x, y))
    assert isinstance(px, tuple)
    r, g, b, a = px
    im.putpixel((x, y), ((r + 1) % 256, g, b, a))
    im.save(f)


# --- main(), end to end --------------------------------------------------------


def test_consistent_fixture_passes(ci, monkeypatch, tmp_path):
    """A clean fixture passes all three checks, writes the job summary, copies results to golden/run-ci/ and cleans up.

    A stale golden/run-ci/ is replaced, and a local full run in golden/run/ is never touched.
    """
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    local = ci / "golden/run/football/full/ex.json"
    local.parent.mkdir(parents=True)
    local.write_text('{"local": true}')
    stale = ci / "golden/run-ci/stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old")
    out = main(monkeypatch, golden_ci, "--root", str(ci))
    assert "Every composition, helmet and venue is ok." in out
    assert "## Golden suite" in summary.read_text()
    assert (ci / "golden/run-ci/REPORT.md").is_file()
    assert not stale.exists()
    assert sorted(p.relative_to(ci / "golden/run").as_posix() for p in (ci / "golden/run").rglob("*")) == [
        "football",
        "football/full",
        "football/full/ex.json",
    ]
    assert local.read_text() == '{"local": true}'
    assert list((tmp_path / "temp").iterdir()) == []


def test_unresolvable_composition_fails_and_keep_leaves_the_project(ci, monkeypatch, capsys, tmp_path):
    """A placement the fixture can no longer resolve fails the composition check; --keep prints and keeps the project."""
    shutil.rmtree(fixture_path(ci, "Football", TEAM, "Helmets Front"))
    with pytest.raises(SystemExit) as e:
        main(monkeypatch, golden_ci, "--root", str(ci), "--keep")
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "- compositions: golden_run.py --strict failed (see REPORT.md)" in out
    assert "## Defects" in (ci / "golden/run-ci/REPORT.md").read_text()
    kept = re.search(r"^kept (.+)$", out, re.M)
    assert kept, out
    kept = Path(kept.group(1))
    assert kept.is_relative_to(tmp_path / "temp")
    assert (kept / "golden/run/REPORT.md").is_file()


def test_empty_fixture_fails(ci, monkeypatch, capsys):
    """An empty fixture fails at once with instructions to build it."""
    shutil.rmtree(fixture_path(ci))
    with pytest.raises(SystemExit) as e:
        main(monkeypatch, golden_ci, "--root", str(ci))
    assert e.value.code == 1
    assert "golden/fixture/ is empty: run scripts/golden/golden_fixture.py --apply" in capsys.readouterr().out


def test_main_finds_root_from_cwd(project, monkeypatch, capsys):
    """Without --root, main() uses the project found from the working directory."""
    with pytest.raises(SystemExit) as e:
        main(monkeypatch, golden_ci)
    assert e.value.code == 1
    assert "golden/fixture/ is empty" in capsys.readouterr().out


# --- one check at a time ---------------------------------------------------------


def test_composition_check_without_a_run_fails(ci, tmp):
    """When golden_run.py writes no run at all (no manifest), the composition check fails and nothing is copied back."""
    (tmp / "golden/manifest.yaml").unlink()
    assert golden_ci.check_compositions(ci, tmp) == ["compositions: golden_run.py --strict failed (see REPORT.md)"]
    assert not (tmp / "golden/run").exists()
    assert not (ci / "golden/run-ci").exists()


def test_changed_pixel_in_generated_helmet_fails(tmp, ci_cfg):
    """One pixel changed in a fixture's generated helmet fails the helmet check for that file, and only that."""
    rel = Path(ELEMENTS["A"]) / f"{ELEMENTS['A']}.png"
    nudge_first_pixel(tmp / "Football" / TEAM / "Helmets Left" / rel)
    assert golden_ci.check_helmets(tmp, ci_cfg) == [f"helmets {TEAM} Left: pixels differ: {rel}"]


def test_missing_helmet_era_fails(tmp, ci_cfg):
    """A fixture with no mark of one era fails the coverage check for that era and side only."""
    el = ELEMENTS["C"]
    for tree in ("Football", "Marks/Football"):
        shutil.rmtree(tmp / tree / TEAM / "Helmets Right" / el)
    assert golden_ci.check_helmets(tmp, ci_cfg) == ["helmets: no right mark of era C in the fixture"]


def test_fixture_without_helmet_marks_fails(tmp, ci_cfg):
    """A fixture with no Marks helmet folders fails the helmet check."""
    shutil.rmtree(tmp / "Marks")
    assert golden_ci.check_helmets(tmp, ci_cfg) == ["helmets: the fixture has no Marks/Football/*/Helmets Left|Right"]


def test_pad_refusal_fails(tmp, ci_cfg):
    """A Marks helmet folder that standardize.py refuses to pad is reported as a failure."""
    (tmp / "Marks" / "Football" / "Other" / "Helmets Left").mkdir(parents=True)
    assert "helmets: pad refused Other / Helmets Left" in golden_ci.check_helmets(tmp, ci_cfg)


def test_different_crop_fails(tmp, ci_cfg):
    """A cropped venue that no longer matches its re-derived crop fails the venue check for that file."""
    rel = Path("2021 B/2021 B.png")
    f = tmp / "Venues" / "Baseball" / TEAM / "Fields Cropped" / rel
    with Image.open(f) as im:
        size = im.size
    art(f, size, seed=99)
    assert golden_ci.check_venues(tmp, ci_cfg) == [f"venues Baseball/{TEAM}/Fields Cropped: pixels differ: {rel}"]


def test_derived_sport_without_venue_fails(tmp, ci_cfg):
    """A sport whose canvases have derived_from but no venue in the fixture fails the venue check for that sport only."""
    shutil.rmtree(tmp / "Venues" / "Basketball")
    assert golden_ci.check_venues(tmp, ci_cfg) == ["venues: the fixture has no cropped venue for basketball"]


def test_derive_crops_refusal_fails(tmp, ci_cfg):
    """A Full venue that derive_crops.py refuses (off its canvas) is reported as a failure."""
    art(tmp / "Venues" / "Football" / TEAM / "Fields Full" / "2030 X" / "2030 X.png", (5, 5))
    assert golden_ci.check_venues(tmp, ci_cfg) == ["venues: derive_crops.py refused"]


# --- helpers ----------------------------------------------------------------------


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


def test_find_root_exits_without_configs(tmp_path):
    """find_root() exits when no directory above holds the configs."""
    with pytest.raises(SystemExit, match=r"No configs/canvas_definitions\.yaml"):
        common.find_root(tmp_path)


def test_png_set_ignores_dot_folders_only_inside_the_folder(tmp_path):
    """A dot-folder ABOVE the scanned folder (a checkout under .claude/, say) hides nothing; one inside it does."""
    root = tmp_path / ".hidden-parent" / "fixture"
    art(root / "a" / "x.png", (4, 4))
    art(root / ".cache" / "y.png", (4, 4))
    art(root / "a" / ".z.png", (4, 4))
    assert golden_ci.png_set(root) == {Path("a/x.png")}
