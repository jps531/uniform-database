"""Tests for scripts/migration/nest_elements.py: element folder = filename minus non-design tokens; dry run, then copy."""

import os

import common
import nest_elements as ne
import pytest
from helpers import REPO, art, main, override_configs


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
    strip, design, form, _seq, known = vocab
    return ne.element_for(stem, strip, design, form, known)


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
    override_configs(
        project,
        {"modifiers_mine.yaml": {"extends": "shared", "tokens": {"grad": {"label": "Grad", "scope": "design"}}}},
    )
    v = common.load_vocabulary(project, "mine")
    tokens, colorways = v.tokens, v.colorways
    assert tokens["grad"]["scope"] == "design"
    assert "ncaa" in tokens
    assert "pink" in colorways
    strip, design, *_ = ne.load_vocab(project, "mine")
    assert "Grad" in design
    assert "Grad" not in strip
    assert nest("2020 White Grad", ne.load_vocab(project, "mine"))[0] == "2020 White Grad"


def test_token_of_unexpected_kind_is_kept_and_unlabelled_one_ignored(project):
    """A token with no recognised scope or kind is KEPT in the name; an entry with no token or label is skipped."""
    override_configs(
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
    override_configs(project, {"modifiers_a.yaml": {"extends": "b"}, "modifiers_b.yaml": {"extends": "a"}})
    with pytest.raises(SystemExit, match="Circular `extends` reaching modifiers_a.yaml"):
        common.load_vocabulary(project, "a")


def test_missing_vocabulary_exits(project):
    """A sport with no modifiers file exits: nesting can't tell designs from variations without one."""
    with pytest.raises(SystemExit, match="No vocabulary at configs/modifiers_curling.yaml"):
        ne.load_vocab(project, "curling")


def test_empty_vocabulary_file_is_allowed(project):
    """An empty modifiers file loads as no tokens and no colorways."""
    override_configs(project, {"modifiers_blank.yaml": ""})
    assert common.load_vocabulary(project, "blank") == common.Vocabulary({}, [])


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
    assert (got, stripped) == (element, notes)


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
        # purple is a SHARED colorway: baseball's own list adds to shared's, so it is not read as a surname
        ("2020 White Purple", "2020 White Purple", []),
    ],
)
def test_baseball_element_names(baseball, stem, element, notes):
    """Baseball: the number is stripped wherever it sits, surnames parse out, colorway and design words never do."""
    got, stripped = nest(stem, baseball)
    assert (got, stripped) == (element, notes)


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
    main(monkeypatch, ne, "--sport", "football")
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
    main(monkeypatch, ne, "--sport", "football", "--apply")
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
    main(monkeypatch, ne, "--sport", "football", "--apply")
    assert "source: temp  ->  dest: Football" in capsys.readouterr().out
    assert (project / "Football/Jones/Helmets Left/2019 Black/2019 Black Cats.png").is_file()


def test_explicit_src_dest_root_and_team_filter(project, tmp_path, monkeypatch, capsys):
    """--src/--dest/--root pick the trees and --team limits the plan to one team."""
    stage(project, "stage/Baseball/Mississippi State/Jerseys Front/2014 White 85s 18 Girodo.png")
    stage(project, "stage/Baseball/Southern Miss/Jerseys Front/2014 Gold 5.png")
    monkeypatch.chdir(tmp_path)
    main(
        monkeypatch,
        ne,
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
        main(monkeypatch, ne, "--apply")
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
        main(monkeypatch, ne, "--apply")
    assert "!! 1 destination collisions" in capsys.readouterr().out
    assert not dest.exists()


def test_existing_different_destination_blocks_apply(project, monkeypatch, capsys):
    """A file already at the destination with different bytes is listed and --apply refuses, leaving it untouched."""
    stage(project, "temp/Football/EMCC/Jerseys Front/2014 White 12.png", seed=1)
    other = stage(project, "temp/Football/EMCC/Jerseys Front/2014 White 13.png", seed=2)
    there = stage(project, "Football/EMCC/Jerseys Front/2014 White/2014 White 12.png", seed=3)
    before = there.read_bytes()
    main(monkeypatch, ne)
    out = capsys.readouterr().out
    assert "!! 1 files already exist at the destination with different contents:" in out
    assert "   EMCC/Jerseys Front/2014 White/2014 White 12.png" in out
    with pytest.raises(SystemExit, match="Refusing to apply"):
        main(monkeypatch, ne, "--apply")
    assert there.read_bytes() == before
    assert not (project / "Football/EMCC/Jerseys Front/2014 White" / other.name).exists()


def test_identical_destination_is_a_reported_no_op(project, monkeypatch, capsys):
    """A file already at the destination byte for byte is reported as in place and not copied again."""
    src = stage(project, "temp/Football/EMCC/Jerseys Front/2014 White 12.png", seed=1)
    stage(project, "temp/Football/EMCC/Jerseys Front/2014 White 13.png", seed=2)
    there = project / "Football/EMCC/Jerseys Front/2014 White/2014 White 12.png"
    there.parent.mkdir(parents=True)
    there.write_bytes(src.read_bytes())
    os.utime(there, (0, 0))
    main(monkeypatch, ne, "--apply")
    out = capsys.readouterr().out
    assert "1 files already at the destination, identical: nothing to copy for them." in out
    assert "Copied 1 files (1 already in place). Source tree left intact." in out
    assert there.stat().st_mtime == 0
    assert (there.parent / "2014 White 13.png").read_bytes() == (src.parent / "2014 White 13.png").read_bytes()


def test_default_destination_matches_the_sport_slug(project, monkeypatch, capsys):
    """mens_basketball resolves to Men's Basketball, for staging and destination."""
    (project / "Men's Basketball").mkdir()
    src = stage(project, "temp/Men's Basketball/Mississippi State/Jerseys Front/2019 White 23.png")
    main(monkeypatch, ne, "--sport", "mens_basketball", "--apply")
    assert "source: temp/Men's Basketball  ->  dest: Men's Basketball" in capsys.readouterr().out
    dest = project / "Men's Basketball/Mississippi State/Jerseys Front/2019 White/2019 White 23.png"
    assert dest.read_bytes() == src.read_bytes()
    assert not (project / "Mens Basketball").exists()


def test_no_sport_directory_requires_dest(project, monkeypatch):
    """With no directory matching the sport slug, main() exits asking for --dest rather than inventing a name."""
    stage(project, "temp/EMCC/Helmets Right/2014 White A.png")
    with pytest.raises(SystemExit, match="No directory for sport 'football'.*--dest"):
        main(monkeypatch, ne, "--sport", "football", "--apply")
    assert not (project / "Football").exists()


def test_missing_source_exits(project, monkeypatch):
    """A source tree that doesn't exist exits naming it."""
    with pytest.raises(SystemExit, match="Source not found"):
        main(monkeypatch, ne, "--src", "nowhere")


def test_source_without_pngs_exits(project, monkeypatch):
    """A source tree with no PNGs exits rather than printing an empty plan."""
    (project / "Football").mkdir()
    (project / "temp/Football/EMCC/Helmets Right").mkdir(parents=True)
    (project / "temp/Football/notes.txt").write_text("not a team")
    with pytest.raises(SystemExit, match="No PNGs under"):
        main(monkeypatch, ne)


def test_find_root_walks_up_and_fails_cleanly(project, tmp_path):
    """find_root() finds the project from a subdirectory, and exits when there is none above."""
    sub = project / "temp" / "deep"
    sub.mkdir(parents=True)
    assert common.find_root(sub) == project
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(SystemExit, match="No configs/canvas_definitions.yaml in"):
        common.find_root(lone)


def test_default_sport_is_football(project, monkeypatch):
    """With no --sport, main() nests football from temp/Football into Football/."""
    (project / "Football").mkdir()
    stage(project, "temp/Football/EMCC/Helmets Right/2014 White A.png")
    out = main(monkeypatch, ne)
    assert "source: temp/Football  ->  dest: Football" in out
    assert "DRY RUN" in out


def test_equal_length_tokens_are_ordered_alphabetically(football):
    """Within one length, tokens are in alphabetical order, so the plan prints the same way every run."""
    for tokens in football[:3]:
        assert tokens == sorted(tokens, key=lambda t: (-len(t), t))
