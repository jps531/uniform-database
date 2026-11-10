"""Tests for scripts/migration/migrate_marks.py: flat, nested and flat-noyear plans, their problems, dry run vs --apply."""

import os
import runpy
import sys
from pathlib import Path

import common
import migrate_marks as mm
import pytest
from helpers import REPO, art, era, override_configs, small_configs

T = Path("Marks/Temp")
D = Path("Marks/Football")


def touch(root: Path, rel, size=(4, 4)) -> Path:
    """Draw a small PNG at root/rel."""
    return art(root / rel, size)


def run_main(monkeypatch, root: Path, *flags):
    """Call migrate_marks.main() with --root and the given flags."""
    monkeypatch.setattr(sys, "argv", ["migrate_marks.py", "--root", str(root), *flags])
    mm.main()


def rels(moves, src: Path, dest: Path) -> list:
    """(source, destination) pairs as strings relative to their roots."""
    return [(str(s.relative_to(src)), str(d.relative_to(dest))) for s, d in moves]


# ---------------------------------------------------------------- flat


def test_plan_flat_parses_team_year_side_shell_and_number(project):
    """Flat names become {Year} {Colour} folders with the shell on every file and a trailing number kept."""
    for n in ("Ole Miss 1979 Navy 2", "Alabama 2015 Crimson 1", "Alabama 2015 Crimson Script 12 2"):
        touch(project, T / "Speedflex" / f"{n}.png")
    touch(project, T / "Double Bar" / "Alabama 1965 White 1.png")
    touch(project, T / "Speedflex" / ".Alabama 2015 Crimson 1.png")
    (project / T / "notes.txt").write_text("")
    moves, problems = mm.plan(project / T, project / D, mm.known_colorways(project), "Helmets")
    assert problems == []
    assert sorted(rels(moves, project / T, project / D)) == sorted(
        [
            ("Double Bar/Alabama 1965 White 1.png", "Alabama/Helmets Right/1965 White/1965 White Double Bar.png"),
            ("Speedflex/Alabama 2015 Crimson 1.png", "Alabama/Helmets Right/2015 Crimson/2015 Crimson Speedflex.png"),
            (
                "Speedflex/Alabama 2015 Crimson Script 12 2.png",
                "Alabama/Helmets Left/2015 Crimson Script/2015 Crimson Script Speedflex 12.png",
            ),
            ("Speedflex/Ole Miss 1979 Navy 2.png", "Ole Miss/Helmets Left/1979 Navy/1979 Navy Speedflex.png"),
        ]
    )


def test_plan_flat_reports_unknown_shells_unparsed_names_and_colorways(project):
    """Unknown shell folders, unparseable names and colorways missing from slots_global are reported."""
    touch(project, T / "Mystery" / "Alabama 2015 Crimson 1.png")
    touch(project, T / "Speed" / "garbage.png")
    touch(project, T / "Speed" / "Alabama 2015 Zebra 1.png")
    moves, problems = mm.plan(project / T, project / D, mm.known_colorways(project), "Helmets")
    assert ("unknown shell directory", "Mystery", "") in problems
    assert ("unparsed filename", "Speed/garbage.png", "") in problems
    assert ("unknown colorway", "zebra", "Speed/Alabama 2015 Zebra 1.png") in problems
    assert len(moves) == 1


def test_plan_flat_without_colorways_skips_the_colour_check(project):
    """With no colorway list, no colour is reported unknown."""
    touch(project, T / "Speed" / "Alabama 2015 Zebra 1.png")
    moves, problems = mm.plan(project / T, project / D, set(), "Helmets")
    assert problems == []
    assert len(moves) == 1


def test_known_colorways_accepts_keys_tokens_and_labels(project):
    """known_colorways() holds each key with underscores as spaces, plus its token and label, lowercased."""
    c = mm.known_colorways(project)
    assert {"maroon", "dark gray", "powder", "powder blue", "vegas gold", "brown"} <= c


def test_known_colorways_and_shells_with_missing_or_odd_config(project):
    """A missing slots_global gives no colorways and a missing vocabulary exits; a colorway with no mapping counts by key."""
    override_configs(project, {"slots_global.yaml": "colorways:\n  plain:\n  fancy: {label: Fancy Red}\n"})
    assert mm.known_colorways(project) == {"plain", "fancy", "fancy red"}
    override_configs(project, {"slots_global.yaml": None, "modifiers_football.yaml": None})
    assert mm.known_colorways(project) == set()
    with pytest.raises(SystemExit, match="No vocabulary at configs/modifiers_football.yaml"):
        mm.shell_by_era(project)


def test_shell_by_era_reads_the_shell_tokens(project):
    """shell_by_era() maps each helmet era letter to its shell label."""
    assert mm.shell_by_era(project) == {
        "A": "Leather",
        "B": "Plastic",
        "C": "Double Bar",
        "D": "Classic",
        "E": "Speed",
        "F": "Speedflex",
    }


def test_main_flat_dry_run_then_apply_copies_and_keeps_sources(project, monkeypatch, capsys):
    """The dry run writes nothing and warns on unknown colorways; --apply copies and leaves the source intact."""
    src = touch(project, T / "Speedflex" / "Alabama 2015 Crimson 1.png")
    touch(project, T / "Speed" / "Alabama 2015 Zebra 1.png")
    run_main(monkeypatch, project)
    out = capsys.readouterr().out
    assert "2 files -> 1 teams, 2 element folders" in out
    assert "!! 1 colorways not in slots_global.yaml (1 files):" in out
    assert "e.g. Speed/Alabama 2015 Zebra 1.png" in out
    assert "DRY RUN — nothing written." in out
    assert "Resolve the flagged items first" not in out
    assert not (project / D).exists()

    run_main(monkeypatch, project, "--apply")
    assert "Copied 2 files. Source tree left intact." in capsys.readouterr().out
    out_file = project / D / "Alabama/Helmets Right/2015 Crimson/2015 Crimson Speedflex.png"
    assert out_file.read_bytes() == src.read_bytes()
    assert src.is_file()


def test_main_flat_blocks_on_problems_and_collisions(project, monkeypatch, capsys):
    """Unparsed names and two sources writing one destination are flagged in the dry run and refused on --apply."""
    touch(project, T / "Speedflex" / "Alabama 2015 Crimson 1.png")
    touch(project, T / "Speedflex" / "Alabama 2015 Crimson  1.png")
    touch(project, T / "Speedflex" / "garbage.png")
    touch(project, T / "Mystery" / "x.png")
    run_main(monkeypatch, project)
    out = capsys.readouterr().out
    assert "!! 1 unknown shell directory:" in out
    assert "!! 1 unparsed filename:" in out
    assert "!! 1 destination collisions" in out
    assert "Alabama/Helmets Right/2015 Crimson/2015 Crimson Speedflex.png (2 sources)" in out
    assert "Resolve the flagged items first" in out
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project, "--apply")
    assert "Refusing to apply" in str(e.value.code)
    assert not (project / D).exists()


def test_main_refuses_to_overwrite_a_different_existing_file(project, monkeypatch, capsys):
    """A destination file that already exists with other bytes is flagged, blocks --apply, and survives."""
    touch(project, T / "Speedflex" / "Alabama 2015 Crimson 1.png")
    there = art(project / D / "Alabama/Helmets Right/2015 Crimson/2015 Crimson Speedflex.png", (4, 4), seed=5)
    before = there.read_bytes()
    run_main(monkeypatch, project)
    out = capsys.readouterr().out
    assert "!! 1 files already exist at the destination with different contents:" in out
    assert "     Alabama/Helmets Right/2015 Crimson/2015 Crimson Speedflex.png" in out
    assert "Resolve the flagged items first" in out
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project, "--apply")
    assert "Refusing to apply" in str(e.value.code)
    assert there.read_bytes() == before


def test_main_skips_an_identical_existing_file(project, monkeypatch, capsys):
    """A destination file identical to its source is reported as in place and not copied again."""
    src = touch(project, T / "Speedflex" / "Alabama 2015 Crimson 1.png")
    touch(project, T / "Speedflex" / "Alabama 2015 Crimson 2.png")
    there = project / D / "Alabama/Helmets Right/2015 Crimson/2015 Crimson Speedflex.png"
    there.parent.mkdir(parents=True)
    there.write_bytes(src.read_bytes())
    os.utime(there, (0, 0))
    run_main(monkeypatch, project, "--apply")
    out = capsys.readouterr().out
    assert "1 files already at the destination, identical: nothing to copy for them." in out
    assert "Copied 1 files (1 already in place). Source tree left intact." in out
    assert there.stat().st_mtime == 0
    assert (project / D / "Alabama/Helmets Left/2015 Crimson/2015 Crimson Speedflex.png").is_file()


def test_main_exits_without_source_or_team(project, monkeypatch):
    """A missing source tree, or nested mode without --team, exits with a message."""
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project)
    assert "Source not found" in str(e.value.code)
    (project / T).mkdir(parents=True)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, project, "--mode", "nested")
    assert e.value.code == "--team is required in nested mode"


def test_main_finds_root_from_cwd(project, monkeypatch, capsys):
    """Without --root, main() finds the project from the working directory."""
    touch(project, T / "Speed" / "Alabama 2015 Crimson 1.png")
    monkeypatch.setattr(sys, "argv", ["migrate_marks.py"])
    mm.main()
    assert "1 files -> 1 teams" in capsys.readouterr().out


def test_find_root_exits_without_configs(tmp_path):
    """find_root() exits when no directory above holds the configs."""
    with pytest.raises(SystemExit) as e:
        common.find_root(tmp_path)
    assert "pass --root." in str(e.value.code)


# ---------------------------------------------------------------- nested


def helmet(root: Path, cfg: dict, side: str, element: str, name: str, era_name="F", src=Path("Incoming")) -> Path:
    """Draw a nested-source helmet mark whose content is the pre-scale size of `era_name`."""
    w, h = era(cfg, f"football-helmet-{side.lower()}", era_name)["size"]
    return art(root / src / f"Helmets {side}" / element / f"{name}.png", (w + 4, h + 4), (w, h), top=2)


def test_plan_nested_takes_shell_from_name_or_size(project):
    """The shell comes from the filename when present, otherwise from the era its content size matches."""
    cfg = small_configs(project)
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson", "E")
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson Speedflex 12")
    helmet(project, cfg, "Right", "1940 White", "1940 White", "A")
    touch(project, "Incoming/Helmets Right/1940 White/.hidden.png")
    moves, problems = mm.plan_nested(project / "Incoming", project / D, "Alabama", project)
    assert problems == []
    assert rels(moves, project / "Incoming", project / D) == [
        (
            "Helmets Left/2015 Crimson/2015 Crimson Speedflex 12.png",
            "Alabama/Helmets Left/2015 Crimson/2015 Crimson Speedflex 12.png",
        ),
        ("Helmets Left/2015 Crimson/2015 Crimson.png", "Alabama/Helmets Left/2015 Crimson/2015 Crimson Speed.png"),
        ("Helmets Right/1940 White/1940 White.png", "Alabama/Helmets Right/1940 White/1940 White Leather.png"),
    ]


def test_plan_nested_skips_non_source_directories(project, capsys):
    """Generated trees, non-mark viewpoints, suffixed folders and non-helmet folders are skipped and listed."""
    cfg = small_configs(project)
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson")
    (project / "Incoming/Helmets Right").mkdir()
    (project / "Incoming/Helmets Right/.generated").write_text("{}")
    (project / "Incoming/Helmets Front").mkdir()
    (project / "Incoming/Helmets Left STD").mkdir()
    (project / "Incoming/Jerseys Left").mkdir()
    (project / "Incoming/readme.txt").write_text("")
    moves, _ = mm.plan_nested(project / "Incoming", project / D, "Alabama", project)
    out = capsys.readouterr().out
    assert len(moves) == 1
    assert f"{'Helmets Right':<24} generated output" in out
    assert f"{'Helmets Front':<24} not a mark viewpoint" in out
    assert f"{'Helmets Left STD':<24} not a mark viewpoint" in out
    assert "Jerseys" not in out


def test_plan_nested_skips_a_destination_that_is_not_a_sport_tree(project, capsys):
    """A destination that does not parse as a sport tree, or has no profile, skips every viewpoint."""
    cfg = small_configs(project)
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson")
    moves, _ = mm.plan_nested(project / "Incoming", project / "Marks", "Alabama", project)
    assert moves == []
    assert f"dest {project / 'Marks'} is not a sport tree" in capsys.readouterr().out
    moves, _ = mm.plan_nested(project / "Incoming", project / "Elsewhere", "Alabama", project)
    assert moves == []
    assert "no profile elsewhere-helmet-left" in capsys.readouterr().out


def test_plan_nested_reports_each_problem(project):
    """Misnamed files, unknown trailing tokens, unmatched sizes and eras without a shell token are reported."""

    def extra_era(cfg):
        """Add a left-helmet era with no shell token in the vocabulary."""
        cfg["profiles"]["football-helmet-left"].append({"era": "G", "size": [40, 40]})

    cfg = small_configs(project, extra_era)
    helmet(project, cfg, "Left", "2015 Crimson", "Other Name")
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson Bogus")
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson G", "G")
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson 7", "G")
    art(project / "Incoming/Helmets Left/2015 Crimson/2015 Crimson 9.png", (20, 20), (13, 11))
    moves, problems = mm.plan_nested(project / "Incoming", project / D, "Alabama", project)
    assert moves == []
    assert sorted(problems) == sorted(
        [
            ("filename does not match folder", "Helmets Left/2015 Crimson/Other Name.png", ""),
            ("unrecognised trailing token", "2015 Crimson/2015 Crimson Bogus.png", "Bogus"),
            ("unrecognised trailing token", "2015 Crimson/2015 Crimson G.png", "G"),
            ("era has no shell token", "2015 Crimson/2015 Crimson 7.png", "G"),
            ("size matches no era", "2015 Crimson/2015 Crimson 9.png", "13x11"),
        ]
    )


def test_plan_nested_reports_an_empty_mark(project):
    """A fully transparent mark with no shell token is a problem, not a crash."""
    small_configs(project)
    art(project / "Incoming/Helmets Left/2015 Crimson/2015 Crimson.png", (20, 20), (0, 0))
    moves, problems = mm.plan_nested(project / "Incoming", project / D, "Alabama", project)
    assert moves == []
    assert problems == [("no opaque content", "2015 Crimson/2015 Crimson.png", "")]


def test_main_nested_blocks_on_an_empty_mark(project, monkeypatch, capsys):
    """An empty mark is printed among nested problems and blocks --apply."""
    small_configs(project)
    art(project / "Incoming/Helmets Left/2015 Crimson/2015 Crimson.png", (20, 20), (0, 0))
    with pytest.raises(SystemExit):
        run_main(monkeypatch, project, "--mode", "nested", "--team", "X", "--src", "Incoming", "--apply")
    out = capsys.readouterr().out
    assert "!! 1 no opaque content:" in out
    assert "2015 Crimson/2015 Crimson.png" in out
    assert not (project / D).exists()


def test_content_size_of_an_empty_file_is_none(tmp_path):
    """content_size() is None for a fully transparent image and the bbox size otherwise."""
    assert mm.content_size(art(tmp_path / "e.png", (6, 6), (0, 0))) is None
    assert mm.content_size(art(tmp_path / "f.png", (6, 6), (3, 2))) == (3, 2)


def test_main_nested_reports_problems_and_collisions_then_refuses(project, monkeypatch, capsys):
    """Nested problems and a size-derived name colliding with an explicit one block --apply."""
    cfg = small_configs(project)
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson")
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson Speedflex")
    helmet(project, cfg, "Left", "2015 Crimson", "2015 Crimson Bogus")
    art(project / "Incoming/Helmets Left/2015 Crimson/2015 Crimson 9.png", (20, 20), (13, 11))
    flags = ("--mode", "nested", "--team", "Alabama", "--src", "Incoming")
    run_main(monkeypatch, project, *flags)
    out = capsys.readouterr().out
    assert "!! 1 unrecognised trailing token:" in out
    assert "!! 1 size matches no era:" in out
    assert "!! 1 destination collisions" in out
    with pytest.raises(SystemExit):
        run_main(monkeypatch, project, *flags, "--apply")
    assert not (project / D).exists()


def test_main_nested_apply_copies(project, monkeypatch, capsys):
    """A clean nested plan is copied into Marks/Football/<Team>, leaving the source in place."""
    cfg = small_configs(project)
    src = helmet(project, cfg, "Right", "1980 Maroon", "1980 Maroon", "D")
    run_main(monkeypatch, project, "--mode", "nested", "--team", "Alabama", "--src", "Incoming", "--apply")
    assert "Copied 1 files." in capsys.readouterr().out
    assert (project / D / "Alabama/Helmets Right/1980 Maroon/1980 Maroon Classic.png").read_bytes() == src.read_bytes()
    assert src.is_file()


# ---------------------------------------------------------------- flat-noyear


def test_plan_flat_noyear_splits_team_at_the_first_colorway(project):
    """Hat names split at the earliest colorway; multi-word colorways and teams survive; hidden files are skipped."""
    for n in ("Auburn Navy A", "Ole Miss Navy Red Bill", "Kansas Powder", "Rice Dark Gray"):
        touch(project, T / f"{n}.png")
    touch(project, T / "sub" / ".Auburn Navy A.png")
    moves, problems = mm.plan_flat_noyear(project / T, project / "Marks/Baseball", "Hats", "Front", project)
    assert problems == []
    assert sorted(rels(moves, project / T, project / "Marks/Baseball")) == [
        ("Auburn Navy A.png", "Auburn/Hats Front/Navy A/Navy A.png"),
        ("Kansas Powder.png", "Kansas/Hats Front/Powder/Powder.png"),
        ("Ole Miss Navy Red Bill.png", "Ole Miss/Hats Front/Navy Red Bill/Navy Red Bill.png"),
        ("Rice Dark Gray.png", "Rice/Hats Front/Dark Gray/Dark Gray.png"),
    ]


def test_plan_flat_noyear_reports_reversed_and_unknown_names(project):
    """A name starting with its colorway, or with no colorway at all, is reported rather than guessed."""
    touch(project, T / "Black Campbell.png")
    touch(project, T / "Zebra Thing.png")
    moves, problems = mm.plan_flat_noyear(project / T, project / "Marks/Baseball", "Hats", "Front", project)
    assert moves == []
    assert sorted(problems) == [
        ("no known colorway", "Zebra Thing.png", ""),
        ("nothing before the colorway — team and colour may be reversed", "Black Campbell.png", ""),
    ]


def test_plan_flat_noyear_without_colorways(project):
    """With no colorway list, flat-noyear plans nothing and says why."""
    override_configs(project, {"slots_global.yaml": None})
    assert mm.plan_flat_noyear(project / T, project, "Hats", "Front", project) == (
        [],
        [("no colorways", "configs/slots_global.yaml", "")],
    )


def test_main_flat_noyear_apply_copies(project, monkeypatch, capsys):
    """flat-noyear --apply copies hats into {Team}/{slot} {viewpoint}/{element}/ and keeps the source."""
    src = touch(project, T / "Auburn Navy A.png")
    flags = ("--mode", "flat-noyear", "--dest", "Marks/Baseball", "--slot-dir", "Hats", "--viewpoint", "Front")
    run_main(monkeypatch, project, *flags, "--apply")
    assert "Copied 1 files." in capsys.readouterr().out
    assert (project / "Marks/Baseball/Auburn/Hats Front/Navy A/Navy A.png").read_bytes() == src.read_bytes()
    assert src.is_file()


def test_main_flat_noyear_refuses_collisions(project, monkeypatch, capsys):
    """Two hats that would land on one destination block --apply."""
    touch(project, T / "a" / "Auburn Navy A.png")
    touch(project, T / "b" / "Auburn Navy A.png")
    with pytest.raises(SystemExit):
        run_main(monkeypatch, project, "--mode", "flat-noyear", "--dest", "Marks/Baseball", "--apply")
    assert "!! 1 destination collisions" in capsys.readouterr().out
    assert not (project / "Marks/Baseball").exists()


def test_main_flat_noyear_prints_problems_and_refuses(project, monkeypatch, capsys):
    """Reversed and colourless hat names are printed, flagged in the dry run, and block --apply."""
    good = touch(project, T / "Auburn Navy A.png")
    touch(project, T / "Black Campbell.png")
    touch(project, T / "Zebra Thing.png")
    flags = ("--mode", "flat-noyear", "--dest", "Marks/Baseball")
    run_main(monkeypatch, project, *flags)
    out = capsys.readouterr().out
    assert "!! 1 no known colorway:\n     Zebra Thing.png" in out
    assert "!! 1 nothing before the colorway — team and colour may be reversed:\n     Black Campbell.png" in out
    assert "Resolve the flagged items first" in out
    with pytest.raises(SystemExit):
        run_main(monkeypatch, project, *flags, "--apply")
    assert not (project / "Marks/Baseball").exists()
    assert good.is_file()


def test_main_flat_noyear_without_colorways_refuses(project, monkeypatch, capsys):
    """With no colorway list, main() says so and refuses --apply."""
    override_configs(project, {"slots_global.yaml": None})
    touch(project, T / "Auburn Navy A.png")
    with pytest.raises(SystemExit):
        run_main(monkeypatch, project, "--mode", "flat-noyear", "--dest", "Marks/Baseball", "--apply")
    assert "!! 1 no colorways:\n     configs/slots_global.yaml" in capsys.readouterr().out


def test_runs_as_a_script(monkeypatch):
    """Run as a script, the module reaches main(); --help exits cleanly."""
    monkeypatch.setattr(sys, "argv", ["migrate_marks.py", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(REPO / "scripts" / "migration" / "migrate_marks.py"), run_name="__main__")
    assert e.value.code == 0
