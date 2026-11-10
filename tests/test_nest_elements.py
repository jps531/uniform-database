"""Tests for scripts/migration/nest_elements.py: element folder = filename minus non-design tokens; dry run, then copy."""

import os
import runpy
import sys

import nest_elements as ne
import pytest
import yaml
from conftest import REPO, art


@pytest.fixture(scope="module")
def football():
    """The real football vocabulary, sorted for nesting."""
    return ne.load_vocab(REPO, "football")


@pytest.fixture(scope="module")
def baseball():
    """The real baseball vocabulary, sorted for nesting."""
    return ne.load_vocab(REPO, "baseball")


def nest(stem, vocab):
    """element_for() on one stem with a loaded vocabulary."""
    strip, design, form, seq, known = vocab
    return ne.element_for(stem, strip, design, form, seq, known)


def custom_configs(project, files):
    """Replace the project's configs link with a directory linking the real files plus `files` (name -> dict)."""
    d = project / "configs"
    d.unlink()
    d.mkdir()
    for f in (REPO / "configs").iterdir():
        if f.name not in files:
            os.symlink(f, d / f.name)
    for name, data in files.items():
        (d / name).write_text(yaml.safe_dump(data))


def run(monkeypatch, *argv):
    """Call nest_elements.main() with the given arguments."""
    monkeypatch.setattr(sys, "argv", ["nest_elements.py", *argv])
    ne.main()


def stage(project, rel, seed=0):
    """Draw a small staged PNG at project/rel."""
    return art(project / rel, (6, 5), seed=seed)


# --- vocabulary --------------------------------------------------------------


def test_vocab_sorts_tokens_by_scope_and_kind(football):
    """Patches and variations are strippable, designs and finishes kept, shells are forms, letters are sequences."""
    strip, design, form, seq, known = football
    assert {"Grad", "NCAA", "Liberty Bowl", "Empty Shoulders", "Banner"} <= set(strip)
    assert {"Egg Bowl", "Flying M", "M over S", "DWS100", "Matte"} <= set(design)
    assert set(form) == {"Leather", "Plastic", "Double Bar", "Classic", "Speed", "Speedflex"}
    assert {"A", "B", "C", "D", "N"} <= seq
    assert {"Egg", "Bowl", "Flying", "M", "Maroon", "White", "Dark Gray"} <= known
    for xs in (strip, design, form):
        assert [len(t) for t in xs] == sorted((len(t) for t in xs), reverse=True)


def test_sport_token_overrides_shared_and_colorways_inherit(project):
    """A token redefined in a sport's file wins over shared, and a sport without colorways inherits shared's."""
    custom_configs(
        project,
        {"modifiers_mine.yaml": {"extends": "shared", "tokens": {"grad": {"label": "Grad", "scope": "design"}}}},
    )
    tokens, colorways = ne.read_vocab(project, "mine")
    assert tokens["grad"]["scope"] == "design"
    assert "ncaa" in tokens
    assert "pink" in colorways
    strip, design, *_ = ne.load_vocab(project, "mine")
    assert "Grad" in design
    assert "Grad" not in strip
    assert nest("2020 White Grad", ne.load_vocab(project, "mine"))[0] == "2020 White Grad"


def test_token_of_unexpected_kind_is_kept_and_unlabelled_one_ignored(project):
    """A token with no recognised scope or kind is KEPT in the name; an entry with no token or label is skipped."""
    custom_configs(
        project,
        {
            "modifiers_mine.yaml": {
                "tokens": {"odd": {"label": "Sparkle", "kind": "glitter"}, "nolabel": {"scope": "patch"}},
                "colorways": ["white"],
            }
        },
    )
    vocab = ne.load_vocab(project, "mine")
    assert "Sparkle" in vocab[1]
    assert None not in vocab[0]
    assert nest("2020 White Sparkle 12", vocab) == ("2020 White Sparkle", ["#12"])


def test_circular_extends_exits(project):
    """Vocabularies that extend each other in a loop exit rather than recursing forever."""
    custom_configs(project, {"modifiers_a.yaml": {"extends": "b"}, "modifiers_b.yaml": {"extends": "a"}})
    with pytest.raises(SystemExit, match="Circular `extends` reaching modifiers_a.yaml"):
        ne.read_vocab(project, "a")


def test_missing_vocabulary_exits(project):
    """A sport with no modifiers file exits: nesting can't tell designs from variations without one."""
    with pytest.raises(SystemExit, match="No vocabulary at configs/modifiers_curling.yaml"):
        ne.load_vocab(project, "curling")


def test_empty_vocabulary_file_is_allowed(project):
    """An empty modifiers file loads as no tokens and no colorways."""
    (project / "configs").unlink()
    (project / "configs").mkdir()
    (project / "configs" / "modifiers_blank.yaml").write_text("")
    assert ne.read_vocab(project, "blank") == ({}, [])


# --- element_for -------------------------------------------------------------


@pytest.mark.parametrize(
    "stem, element, notes",
    [
        ("2025 Black", "2025 Black", []),
        ("2025 Black Speedflex", "2025 Black", ["Speedflex"]),
        ("2016 Maroon Speedflex A", "2016 Maroon", ["Speedflex A"]),
        ("2015 Maroon A Speed", "2015 Maroon A", ["Speed"]),
        ("1955 White Double Bar", "1955 White", ["Double Bar"]),
        ("2012 White Egg Bowl Liberty Bowl", "2012 White Egg Bowl", ["Liberty Bowl"]),
        ("2019 Navy Rebs A", "2019 Navy", ["Rebs A"]),
        ("2010 Black Eagles", "2010 Black", ["Eagles"]),
        ("2010 Black EagleHead", "2010 Black", ["EagleHead"]),
        ("2010 Black Eagle", "2010 Black Eagle", []),
        ("2018 White Grad NCAA", "2018 White", ["Grad", "NCAA"]),
        ("2014 White A", "2014 White A", []),
        ("2014 White B Speedflex", "2014 White B", ["Speedflex"]),
        ("2011 Maroon Matte A", "2011 Maroon Matte A", []),
        ("2019 White 34 A", "2019 White", ["#34 A"]),
        ("2019 White 03", "2019 White", ["#03"]),
        ("2019 White 7 Empty Shoulders", "2019 White", ["Empty Shoulders", "#7"]),
        ("1980 White Flying M", "1980 White Flying M", []),
        ("1980 White Flying M 12", "1980 White Flying M", ["#12"]),
        ("1980 White Flying M Grad", "1980 White Flying M", ["Grad"]),
        ("2020 Maroon M over S 7", "2020 Maroon M over S", ["#7"]),
        ("2014 Maroon DWS100 Speedflex", "2014 Maroon DWS100", ["Speedflex"]),
        ("2014 Maroon DWS100 5", "2014 Maroon DWS100", ["#5"]),
        ("2014 White XYZ", "2014 White XYZ", []),
        ("2014 White Sparkle Egg Bowl", "2014 White Sparkle Egg Bowl", []),
    ],
)
def test_football_element_names(football, stem, element, notes):
    """Football stems lose form, patch, variation and number tokens and keep design tokens and design letters."""
    got, stripped = nest(stem, football)
    # Equal-length tokens match in set order, so the order of `notes` is not fixed.
    assert (got, sorted(stripped)) == (element, sorted(notes))


@pytest.mark.parametrize(
    "stem, element, notes",
    [
        ("2015 White 85s 19 Grad", "2015 White 85s", ["Grad", "#19"]),
        ("2014 White 85s 18 Girodo", "2014 White 85s", ["#18", "player Girodo"]),
        ("2014 White 85s 18 Heck", "2014 White 85s", ["#18", "player Heck"]),
        ("1968 Maroon Classic", "1968 Maroon", ["Classic"]),
        ("2019 White Vest 4", "2019 White", ["Vest", "#4"]),
        ("2018 Gray Pinstripes 34 B", "2018 Gray Pinstripes", ["#34 B"]),
        ("2020 Natural Wool", "2020 Natural Wool", []),
        ("2020 White Teal Trim", "2020 White Teal Trim", []),
        ("2020 White Teal Belt", "2020 White", ["Teal Belt"]),
        ("2020 Maroon White", "2020 Maroon White", []),
        ("2014 Heck", "2014 Heck", []),
    ],
)
def test_baseball_element_names(baseball, stem, element, notes):
    """Baseball: the number is stripped wherever it sits, surnames parse out, colorway and design words never do."""
    got, stripped = nest(stem, baseball)
    # Equal-length tokens match in set order, so the order of `notes` is not fixed.
    assert (got, sorted(stripped)) == (element, sorted(notes))


@pytest.mark.parametrize("stem", [" 12", " Speedflex"])
def test_nothing_left_is_reported(football, stem):
    """A stem that strips to nothing returns no element and says so."""
    assert nest(stem, football) == (None, ["nothing left"])


# --- main --------------------------------------------------------------------


def test_dry_run_plans_and_writes_nothing(project, monkeypatch, capsys):
    """Without --apply the plan is printed, nothing is written to the destination and the source is untouched."""
    (project / "Football").mkdir()
    stage(project, "temp/Football/EMCC/Helmets Right/2014 White A Speedflex.png")
    stage(project, "temp/Football/EMCC/Helmets Right/2014 White B Speedflex.png")
    stage(project, "temp/Football/EMCC/Jerseys Front/2014 White 34 A.png")
    run(monkeypatch, "--sport", "football")
    out = capsys.readouterr().out
    assert "source: temp/Football  ->  dest: Football" in out
    assert "3 files -> 3 element folders" in out
    assert "EMCC" in out
    assert "Helmets Right" in out
    assert "-> 2014 White A/   [Speedflex]" in out
    assert "-> 2014 White/   [#34 A]" in out
    assert "DRY RUN" in out
    assert not any((project / "Football").iterdir())
    assert len(list((project / "temp").rglob("*.png"))) == 3


def test_apply_copies_into_element_folders_and_keeps_source(project, monkeypatch, capsys):
    """--apply copies every file, unrenamed, into its element folder and leaves the staging tree intact."""
    (project / "Football").mkdir()
    names = {
        "Helmets Right/2016 Maroon Speedflex A.png": "2016 Maroon",
        "Helmets Right/2016 Maroon Speedflex B.png": "2016 Maroon",
        "Jerseys Front/2016 Maroon 03.png": "2016 Maroon",
        "Jerseys Front/2016 Maroon Egg Bowl 3 Grad.png": "2016 Maroon Egg Bowl",
    }
    srcs = {}
    for i, rel in enumerate(names):
        srcs[rel] = stage(project, f"temp/Football/Mississippi State/{rel}", seed=i)
    stage(project, "temp/Football/Mississippi State/Helmets Right/.2016 Maroon.png")
    run(monkeypatch, "--sport", "football", "--apply")
    out = capsys.readouterr().out
    assert "Copied 4 files. Source tree left intact." in out
    for rel, el in names.items():
        view, name = rel.split("/")
        dest = project / "Football" / "Mississippi State" / view / el / name
        assert dest.read_bytes() == srcs[rel].read_bytes()
        assert srcs[rel].exists()
    assert not list((project / "Football").rglob(".*.png"))


def test_staging_without_sport_level_falls_back_to_temp(project, monkeypatch, capsys):
    """With no temp/{Sport}/, staging is read from temp/{Team}/ directly."""
    (project / "Football").mkdir()
    stage(project, "temp/Jones/Helmets Left/2019 Black Cats.png")
    run(monkeypatch, "--sport", "football", "--apply")
    assert "source: temp  ->  dest: Football" in capsys.readouterr().out
    assert (project / "Football/Jones/Helmets Left/2019 Black/2019 Black Cats.png").is_file()


def test_explicit_src_dest_root_and_team_filter(project, tmp_path, monkeypatch, capsys):
    """--src/--dest/--root pick the trees and --team limits the plan to one team."""
    stage(project, "stage/Baseball/Mississippi State/Jerseys Front/2014 White 85s 18 Girodo.png")
    stage(project, "stage/Baseball/Southern Miss/Jerseys Front/2014 Gold 5.png")
    monkeypatch.chdir(tmp_path)
    run(
        monkeypatch,
        "--root",
        str(project),
        "--sport",
        "baseball",
        "--src",
        "stage/Baseball",
        "--dest",
        "out/Baseball",
        "--team",
        "Mississippi State",
        "--apply",
    )
    out = capsys.readouterr().out
    assert "1 files -> 1 element folders" in out
    assert "player Girodo" in out
    assert (
        project / "out/Baseball/Mississippi State/Jerseys Front/2014 White 85s/2014 White 85s 18 Girodo.png"
    ).is_file()
    assert not (project / "out/Baseball/Southern Miss").exists()


def test_unassignable_file_is_reported_and_blocks_apply(project, monkeypatch, capsys):
    """A file that strips to nothing is listed as unassigned, and --apply then refuses to copy anything."""
    (project / "Football").mkdir()
    stage(project, "temp/Football/EMCC/Jerseys Front/ 12.png")
    stage(project, "temp/Football/EMCC/Jerseys Front/2014 White 12.png")
    with pytest.raises(SystemExit, match="Refusing to apply"):
        run(monkeypatch, "--apply")
    out = capsys.readouterr().out
    assert "!! 1 files could not be assigned" in out
    assert "EMCC/Jerseys Front/ 12.png  (nothing left)" in out
    assert not any((project / "Football").iterdir())


def test_collision_is_reported_and_blocks_apply(project, monkeypatch, capsys):
    """Two sources planned onto one destination are listed as a collision and --apply refuses."""
    (project / "Football").mkdir()
    a = stage(project, "temp/Football/EMCC/Jerseys Front/2014 White 12.png")
    dest = project / "Football/EMCC/Jerseys Front/2014 White/2014 White 12.png"
    monkeypatch.setattr(ne, "build_plan", lambda *a_, **k: ([(a, dest, []), (a, dest, [])], []))
    with pytest.raises(SystemExit, match="Refusing to apply"):
        run(monkeypatch, "--apply")
    assert "!! 1 destination collisions" in capsys.readouterr().out
    assert not dest.exists()


def test_default_destination_matches_the_sport_slug(project, monkeypatch, capsys):
    """mens_basketball (basketball's vocabulary patched in) resolves to Men's Basketball, for staging and destination."""
    vocab = ne.load_vocab(REPO, "basketball")
    monkeypatch.setattr(ne, "load_vocab", lambda root, sport: vocab)
    (project / "Men's Basketball").mkdir()
    src = stage(project, "temp/Men's Basketball/Mississippi State/Jerseys Front/2019 White 23.png")
    run(monkeypatch, "--sport", "mens_basketball", "--apply")
    assert "source: temp/Men's Basketball  ->  dest: Men's Basketball" in capsys.readouterr().out
    dest = project / "Men's Basketball/Mississippi State/Jerseys Front/2019 White/2019 White 23.png"
    assert dest.read_bytes() == src.read_bytes()
    assert not (project / "Mens Basketball").exists()


def test_no_sport_directory_requires_dest(project, monkeypatch):
    """With no directory matching the sport slug, main() exits asking for --dest rather than inventing a name."""
    stage(project, "temp/EMCC/Helmets Right/2014 White A.png")
    with pytest.raises(SystemExit, match="No directory for sport 'football'.*--dest"):
        run(monkeypatch, "--sport", "football", "--apply")
    assert not (project / "Football").exists()


def test_missing_source_exits(project, monkeypatch):
    """A source tree that doesn't exist exits naming it."""
    with pytest.raises(SystemExit, match="Source not found"):
        run(monkeypatch, "--src", "nowhere")


def test_source_without_pngs_exits(project, monkeypatch):
    """A source tree with no PNGs exits rather than printing an empty plan."""
    (project / "Football").mkdir()
    (project / "temp/Football/EMCC/Helmets Right").mkdir(parents=True)
    (project / "temp/Football/notes.txt").write_text("not a team")
    with pytest.raises(SystemExit, match="No PNGs under"):
        run(monkeypatch)


def test_find_root_walks_up_and_fails_cleanly(project, tmp_path):
    """find_root() finds configs/ and scripts/ from a subdirectory, and exits when there are none above."""
    sub = project / "temp" / "deep"
    sub.mkdir(parents=True)
    assert ne.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(SystemExit, match="Could not find the project root"):
        ne.find_root(lone)


def test_runs_as_a_script(project, monkeypatch, capsys):
    """Run as `__main__`, the script plans the default (football) sport."""
    (project / "Football").mkdir()
    stage(project, "temp/Football/EMCC/Helmets Right/2014 White A.png")
    monkeypatch.setattr(sys, "argv", ["nest_elements.py"])
    runpy.run_path(str(REPO / "scripts" / "migration" / "nest_elements.py"), run_name="__main__")
    assert "DRY RUN" in capsys.readouterr().out


def test_missing_pyyaml_exits_with_a_hint(monkeypatch):
    """Without PyYAML installed the script exits telling the user to run `uv sync`."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(SystemExit, match="uv sync"):
        runpy.run_path(str(REPO / "scripts" / "migration" / "nest_elements.py"), run_name="nest_noimport")
