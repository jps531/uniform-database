"""Tests for scripts/golden/golden_fixture.py: what the fixture copies, every refusal, dry run vs --apply.

Also holds `small_configs()`, shared with test_golden_ci.py and test_derive_crops.py:
a copy of the real configs with the helmet and venue canvases scaled down, so
synthetic artwork stays a few hundred pixels instead of a few thousand.
"""

import json
import os
import runpy
import shutil
import sys
from pathlib import Path

import common
import golden_fixture as gf
import pytest
import yaml
from conftest import REPO, art, canvas_size, era

TEAM = "Testers"
HELMET_DIV = 8
VENUE_DIV = {"football": 16, "baseball": 16, "basketball": 32}
ERAS = ("A", "B", "C", "D", "E", "F")


def small_configs(root: Path, mutate=None) -> dict:
    """Replace root/configs with a copy whose helmet and venue canvases and eras are scaled down; returns the cfg."""
    link = root / "configs"
    if link.is_symlink():
        link.unlink()
        shutil.copytree(REPO / "configs", link)
    path = link / "canvas_definitions.yaml"
    cfg = yaml.safe_load(path.read_text())
    for vp in ("left", "right", "front", "back"):
        for e in cfg["profiles"][f"football-helmet-{vp}"]:
            e["size"] = [round(v / HELMET_DIV) for v in e["size"]]
    post = [
        (round(e["size"][0] * e.get("scale", 1)), round(e["size"][1] * e.get("scale", 1)))
        for e in cfg["profiles"]["football-helmet-left"]
    ]
    cfg["canvases"]["football_helmet_profile"].update(
        width=max(w for w, _ in post) + 2, height=max(h for _, h in post) + 2
    )
    face = cfg["canvases"]["football_helmet_face"]
    face.update(width=round(face["width"] / HELMET_DIV), height=round(face["height"] / HELMET_DIV))
    for sport, k in VENUE_DIV.items():
        slot = "court" if sport == "basketball" else "field"
        for kind in ("full", "cropped"):
            c = cfg["canvases"][f"{sport}_{slot}_{kind}"]
            c.update(width=c["width"] // k, height=c["height"] // k)
            if "derived_from" in c:
                c["derived_from"]["crop_at"] = [v // k for v in c["derived_from"]["crop_at"]]
    if mutate:
        mutate(cfg)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return cfg


def mark(root: Path, cfg: dict, side: str, element: str, era_name: str, team=TEAM, name=None, seed=0) -> Path:
    """Draw a Marks helmet file whose content is exactly the pre-scale size of `era_name` on `side`."""
    w, h = era(cfg, f"football-helmet-{side.lower()}", era_name)["size"]
    f = root / "Marks" / "Football" / team / f"Helmets {side}" / element / f"{name or element}.png"
    return art(f, (w + 4, h + 4), (w, h), top=2, seed=seed)


def generated(root: Path, side: str, element: str, team=TEAM, name=None) -> Path:
    """Draw a stand-in generated helmet file in Football/<team>/Helmets <side>/<element>/."""
    f = root / "Football" / team / f"Helmets {side}" / element / f"{name or element}.png"
    return art(f, (8, 8), (4, 4))


def venue(root: Path, cfg: dict, sport: str, element: str, cropped=True, seed=0) -> tuple:
    """Draw a Full venue file (and, if asked, a stand-in cropped copy); returns the two relative paths."""
    slot = "court" if sport == "basketball" else "field"
    sdir = "Courts" if slot == "court" else "Fields"
    base = root / "Venues" / sport.title() / TEAM
    full = art(base / f"{sdir} Full" / element / f"{element}.png", canvas_size(cfg, f"{sport}_{slot}_full"), seed=seed)
    crop = base / f"{sdir} Cropped" / element / f"{element}.png"
    if cropped:
        art(crop, canvas_size(cfg, f"{sport}_{slot}_cropped"), seed=seed)
    return full.relative_to(root), crop.relative_to(root)


def write_manifest(root: Path, examples: list) -> None:
    """Write golden/manifest.yaml and push its mtime into the past, so results written later are newer."""
    p = root / "golden" / "manifest.yaml"
    p.write_text(yaml.safe_dump(examples, sort_keys=False))
    os.utime(p, (1_000_000, 1_000_000))


def write_result(root: Path, ex: dict, placements: list) -> Path:
    """Write a compose --json result for manifest example `ex` holding `placements`."""
    js = root / "golden" / "run" / ex["sport"] / ex["view"] / f"{ex['id']}.json"
    js.parent.mkdir(parents=True, exist_ok=True)
    js.write_text(json.dumps({"placements": placements, "missing": []}))
    return js


def placed(file: Path | None, slot: str, vp: str, element: str, number=None, status="placed") -> dict:
    """One placement record as compose writes it; a skipped placement has no file, as in compose's JSON."""
    return {
        "file": str(file) if file else None,
        "slot": slot,
        "viewpoint": vp,
        "element": element,
        "number_requested": number,
        "status": status,
    }


def scene(root: Path, cfg: dict) -> dict:
    """Build a consistent synthetic tree and run results; returns the relative paths the fixture should hold."""
    want = set()
    jf = root / "Football" / TEAM / "Jerseys Front" / "2020 White"
    for n in ("2020 White", "2020 White 12", "2020 White Grad", "2020 White 34"):
        art(jf / f"{n}.png", (8, 8))
    want |= {(jf / f"{n}.png").relative_to(root) for n in ("2020 White", "2020 White 12", "2020 White Grad")}
    jb = root / "Football" / TEAM / "Jerseys Back" / "2020 White"
    want.add(art(jb / "2020 White 5.png", (8, 8)).relative_to(root))
    art(jb / "2020 White 7.png", (8, 8))  # another number: never a candidate for 5

    # The placed helmet: right side carries all six eras, left only F.
    for i, e in enumerate(ERAS):
        want.add(mark(root, cfg, "Right", "2020 Maroon", e, name=f"2020 Maroon {e}", seed=i).relative_to(root))
        want.add(generated(root, "Right", "2020 Maroon", name=f"2020 Maroon {e}").relative_to(root))
    want.add(mark(root, cfg, "Left", "2020 Maroon", "F").relative_to(root))
    want.add(generated(root, "Left", "2020 Maroon").relative_to(root))
    hf = root / "Football" / TEAM / "Helmets Front" / "2020 Maroon" / "2020 Maroon.png"
    want.add(art(hf, (8, 8)).relative_to(root))

    # Left-side top-up across teams: Aardvark has no marks; Alpha gives A and an
    # empty file; its B has no generated copy; Beta finishes B-E; Gamma is never reached.
    generated(root, "Left", "x", team="Aardvark")
    want.add(mark(root, cfg, "Left", "1950 White", "A", team="Alpha").relative_to(root))
    want.add(
        art(root / "Marks/Football/Alpha/Helmets Left/1950 White/1950 White Empty.png", (8, 8), (0, 0)).relative_to(
            root
        )
    )
    want.add(generated(root, "Left", "1950 White", team="Alpha").relative_to(root))
    mark(root, cfg, "Left", "1960 White", "B", team="Alpha")
    for el, e in (("1960 Navy", "B"), ("1970 Navy", "C"), ("1980 Navy", "D"), ("1990 Navy", "E")):
        want.add(mark(root, cfg, "Left", el, e, team="Beta").relative_to(root))
        want.add(generated(root, "Left", el, team="Beta").relative_to(root))
    mark(root, cfg, "Left", "1999 Gold", "A", team="Gamma")
    generated(root, "Left", "1999 Gold", team="Gamma")

    # Venues: three football fields (first and last kept), baseball without a
    # Cropped tree, and an empty basketball Full folder with a Cropped sibling.
    a = venue(root, cfg, "football", "2020 Grass")
    venue(root, cfg, "football", "2021 Grass", seed=1)
    c = venue(root, cfg, "football", "2022 Grass", seed=2)
    want |= {*a, *c}
    venue(root, cfg, "baseball", "2020 Dirt", cropped=False)
    (root / "Venues/Basketball" / TEAM / "Courts Full").mkdir(parents=True)
    (root / "Venues/Basketball" / TEAM / "Courts Cropped").mkdir(parents=True)

    ex1 = {"id": "f--jersey--01", "sport": "football", "view": "jersey-full", "team": TEAM}
    ex2 = {"id": "f--helmets--01", "sport": "football", "view": "helmets-4", "team": TEAM}
    ex3 = {"id": "f--off--01", "sport": "football", "view": "helmets-4", "team": TEAM, "approved": False}
    write_manifest(root, [ex1, ex2, ex3])
    write_result(
        root,
        ex1,
        [
            placed(jf / "2020 White 12.png", "jersey", "front", "2020 White", "12"),
            placed(jb / "2020 White 5.png", "jersey", "back", "2020 White", "5"),
            placed(None, "jersey", "left", "2020 White", status="skipped"),
        ],
    )
    hr = root / "Football" / TEAM / "Helmets Right" / "2020 Maroon" / "2020 Maroon F.png"
    hl = root / "Football" / TEAM / "Helmets Left" / "2020 Maroon" / "2020 Maroon.png"
    write_result(
        root,
        ex2,
        [
            placed(hf, "helmet", "front", "2020 Maroon"),
            placed(hr, "helmet", "right", "2020 Maroon"),
            placed(hl, "helmet", "left", "2020 Maroon"),
        ],
    )
    return {"want": want, "ex": [ex1, ex2, ex3]}


@pytest.fixture
def small(project) -> dict:
    """The test project switched to the scaled-down configs."""
    return small_configs(project)


def run_main(monkeypatch, root: Path, *flags):
    """Call golden_fixture.main() with --root and the given flags."""
    monkeypatch.setattr(sys, "argv", ["golden_fixture.py", "--root", str(root), *flags])
    gf.main()


def test_plan_copies_candidates_whole_helmets_era_top_up_and_venue_ends(project, small):
    """plan() gathers numbered+unnumbered candidates, whole helmet folders with marks, era top-ups and venue ends."""
    s = scene(project, small)
    need, errors = gf.plan(project)
    assert errors == []
    assert need == s["want"]


def test_composition_files_never_keeps_another_number(project, small):
    """With a number requested, files carrying any other number are left out, as compose never picks them."""
    folder = project / "Football" / TEAM / "Jerseys Back" / "2020 White"
    files = [art(folder / f"2020 White {n}.png", (4, 4)) for n in ("5", "7")]
    vocab = {0: gf.load_vocab(project, "football")[0]}
    p = placed(files[1], "jersey", "back", "2020 White", "7")
    assert gf.composition_files(p, vocab) == [files[1]]
    plain = art(folder / "2020 White.png", (4, 4))
    p = placed(plain, "jersey", "back", "2020 White", "12")
    assert gf.composition_files(p, vocab) == [plain]
    # a stale result naming another number still keeps the file it placed, and nothing else numbered
    p = placed(files[0], "jersey", "back", "2020 White", "12")
    assert gf.composition_files(p, vocab) == [files[0], plain]


def test_composition_files_without_a_number_keeps_unnumbered_else_the_whole_folder(project, small):
    """With no number requested, the unnumbered files are kept if any exist, else every file, as compose ranks them."""
    folder = project / "Football" / TEAM / "Jerseys Back" / "2020 White"
    files = [art(folder / f"2020 White {n}.png", (4, 4)) for n in ("5", "7")]
    vocab = {0: gf.load_vocab(project, "football")[0]}
    p = placed(files[0], "jersey", "back", "2020 White")
    assert gf.composition_files(p, vocab) == files
    plain = art(folder / "2020 White.png", (4, 4))
    assert gf.composition_files(placed(plain, "jersey", "back", "2020 White"), vocab) == [plain]


def test_helmet_eras_matches_marks_and_ignores_empty_files(project, small):
    """helmet_eras() names the profile era of each file by content size and skips fully transparent files."""
    mark(project, small, "Left", "1950 White", "A")
    mark(project, small, "Left", "1950 White", "D", name="1950 White D")
    folder = project / "Marks/Football" / TEAM / "Helmets Left/1950 White"
    art(folder / "blank.png", (8, 8), (0, 0))
    art(folder / ".hidden.png", (8, 8))
    assert gf.helmet_eras(folder, small["profiles"]["football-helmet-left"], 5) == {"A", "D"}


def test_plan_refuses_missing_and_stale_results(project, small):
    """An approved example with no result, or a result older than the manifest, is an error."""
    s = scene(project, small)
    ex1, ex2, _ = s["ex"]
    (project / "golden/run/football/jersey-full" / f"{ex1['id']}.json").unlink()
    js = project / "golden/run/football/helmets-4" / f"{ex2['id']}.json"
    os.utime(js, (10, 10))
    _, errors = gf.plan(project)
    assert f"no result for {ex1['id']}: run scripts/golden/golden_run.py first" in errors
    assert f"{ex2['id']}: result is older than manifest.yaml, re-run scripts/golden/golden_run.py" in errors


def test_plan_refuses_placements_outside_the_project(project, small, tmp_path):
    """A placed file outside the project root is an error."""
    s = scene(project, small)
    outside = tmp_path / "elsewhere.png"
    write_result(project, s["ex"][0], [placed(outside, "jersey", "front", "2020 White")])
    _, errors = gf.plan(project)
    assert f"{s['ex'][0]['id']}: {outside} is outside the project" in errors


def test_plan_refuses_generated_helmet_without_marks_source(project, small):
    """A placed generated helmet with no Marks folder is an error."""
    scene(project, small)
    shutil.rmtree(project / "Marks/Football" / TEAM / "Helmets Left/2020 Maroon")
    _, errors = gf.plan(project)
    gen = Path("Football") / TEAM / "Helmets Left/2020 Maroon"
    assert f"{gen} has no source in Marks ({Path('Marks') / gen})" in errors


def test_plan_refuses_an_era_no_team_has(project, small):
    """An era with no mark on any tracked team is reported per side."""
    scene(project, small)
    shutil.rmtree(project / "Marks/Football/Beta/Helmets Left/1990 Navy")
    _, errors = gf.plan(project)
    assert errors == ["no tracked team has a left helmet mark of era E"]


def test_plan_refuses_venue_without_cropped_copy(project, small):
    """A first or last Full venue file with no cropped copy is an error."""
    scene(project, small)
    crop = Path("Venues/Football") / TEAM / "Fields Cropped/2022 Grass/2022 Grass.png"
    (project / crop).unlink()
    _, errors = gf.plan(project)
    full = Path("Venues/Football") / TEAM / "Fields Full/2022 Grass/2022 Grass.png"
    assert errors == [f"{full} has no cropped copy at {crop}"]


def test_plan_refuses_icloud_placeholders(project, small):
    """A needed file that iCloud has evicted to a .name.icloud placeholder is an error."""
    scene(project, small)
    rel = Path("Football") / TEAM / "Jerseys Front/2020 White/2020 White 12.png"
    (project / rel.parent / f".{rel.name}.icloud").write_text("")
    assert gf.evicted(project / rel)
    _, errors = gf.plan(project)
    assert errors == [f"{rel} is in iCloud only: run brctl download on it first"]


def test_plan_without_venues_or_examples(project, small):
    """An empty manifest and no Venues tree still plan, reporting only uncovered helmet eras."""
    (project / "golden/manifest.yaml").write_text("")
    generated(project, "Left", "x")
    need, errors = gf.plan(project)
    assert need == set()
    assert errors == [f"no tracked team has a {s} helmet mark of era {e}" for s in ("left", "right") for e in ERAS]


def test_main_dry_run_writes_nothing(project, small, monkeypatch, capsys):
    """Without --apply, main() reports the files to add and writes nothing."""
    s = scene(project, small)
    run_main(monkeypatch, project)
    out = capsys.readouterr().out
    assert f"fixture: {len(s['want'])} files" in out
    assert f"add {len(s['want'])}, update 0, remove 0" in out
    assert f"… {len(s['want']) - 10} more" in out
    assert "DRY RUN" in out
    assert not (project / "golden/fixture").exists()


def test_main_apply_adds_updates_removes_and_prunes(project, small, monkeypatch, capsys):
    """--apply copies the plan, then updates changed files, removes stale ones and prunes empty folders."""
    s = scene(project, small)
    dest = project / "golden/fixture"
    run_main(monkeypatch, project, "--apply")
    have = {f.relative_to(dest) for f in dest.rglob("*") if f.is_file()}
    assert have == s["want"]
    assert not list(dest.rglob(".generated"))

    stale = dest / "Old/Deep/stale.png"
    stale.parent.mkdir(parents=True)
    stale.write_text("x")
    changed = Path("Football") / TEAM / "Jerseys Front/2020 White/2020 White.png"
    art(project / changed, (8, 8), seed=9)
    capsys.readouterr()
    run_main(monkeypatch, project, "--apply")
    out = capsys.readouterr().out
    assert "add 0, update 1, remove 1" in out
    assert f"~ {changed}" in out
    assert "- Old/Deep/stale.png" in out
    assert "Wrote 1 files, removed 1." in out
    assert not (dest / "Old").exists()
    assert (dest / changed).read_bytes() == (project / changed).read_bytes()


def test_main_warns_over_size_limit(project, small, monkeypatch, capsys):
    """A fixture over WARN_MB is flagged as growing history."""
    scene(project, small)
    monkeypatch.setattr(gf, "WARN_MB", 0)
    run_main(monkeypatch, project)
    assert "!! over 0 MB" in capsys.readouterr().out


def test_main_exits_on_problems(project, small, monkeypatch, capsys):
    """main() lists the problems and exits without writing."""
    s = scene(project, small)
    (project / "golden/run/football/jersey-full" / f"{s['ex'][0]['id']}.json").unlink()
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project, "--apply")
    assert e.value.code == "Fix these before syncing the fixture."
    assert "!! 1 problems:" in capsys.readouterr().out
    assert not (project / "golden/fixture").exists()


def test_main_refuses_fixture_outside_golden(project, small, monkeypatch, tmp_path):
    """A golden/fixture that resolves outside golden/ is refused before anything is written."""
    scene(project, small)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, project / "golden/fixture")
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project, "--apply")
    assert "is outside golden/" in str(e.value.code)
    assert list(outside.iterdir()) == []


def test_main_finds_root_from_cwd(project, small, monkeypatch, capsys):
    """Without --root, main() finds the project from the working directory."""
    scene(project, small)
    sub = project / "Football"
    monkeypatch.chdir(sub)
    monkeypatch.setattr(sys, "argv", ["golden_fixture.py"])
    gf.main()
    assert "DRY RUN" in capsys.readouterr().out


def test_find_root_exits_without_configs(tmp_path):
    """find_root() exits when no directory above holds the configs."""
    with pytest.raises(SystemExit) as e:
        common.find_root(tmp_path)
    assert "No configs/canvas_definitions.yaml" in str(e.value.code)


def test_runs_as_a_script(monkeypatch):
    """Run as a script, the module reaches main(); --help exits cleanly."""
    monkeypatch.setattr(sys, "argv", ["golden_fixture.py", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(REPO / "scripts" / "golden" / "golden_fixture.py"), run_name="__main__")
    assert e.value.code == 0
