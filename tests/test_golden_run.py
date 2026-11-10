"""Tests for scripts/golden/golden_run.py: automatic checks, filtering, report, sheets and --strict."""

import json
import sys
import types
from pathlib import Path

import golden_run as gr
import pytest
import yaml
from conftest import REPO, art, canvas_size, era
from PIL import Image

MSU = "Mississippi State"

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def manifest(project, entries):
    """Write golden/manifest.yaml."""
    (project / "golden/manifest.yaml").write_text(yaml.safe_dump(entries, sort_keys=False))


def entry(id_, sport="football", view="icons-horizontal", **kw):
    """One manifest example."""
    e = {"id": id_, "approved": True, "sport": sport, "view": view, "team": MSU, "uniform1": {"jersey": "2020 Maroon"}}
    e.update(kw)
    return e


def placed(file, element="2020 Maroon", slot="jersey", vp="icon", u=1, **kw):
    """One compose placement record with status 'placed'."""
    p = {
        "label": f"{slot}/{vp}" + (f" #{u}" if u != 1 else ""),
        "slot": slot,
        "viewpoint": vp,
        "uniform": u,
        "element": element,
        "file": str(file),
        "status": "placed",
        "number_requested": None,
        "number_found": None,
        "tokens_requested": [],
        "tokens_found": [],
        "clipped": {},
    }
    p.update(kw)
    return p


def opaque_png(path, size=(20, 20)):
    """A small fully opaque composition."""
    return art(path, size)


def empty_png(path, size=(20, 20)):
    """A composition with no opaque pixels."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (0, 0, 0, 0)).save(path)
    return path


class FakeCompose:
    """Stands in for compose.py: per example id, writes a crafted JSON result and PNG, or neither."""

    def __init__(self, behaviours):
        """`behaviours` maps example id -> (result dict | str | None, png writer | None, stderr)."""
        self.behaviours = behaviours
        self.calls = []

    def __call__(self, cmd, **kw):
        """Record the command and write what the behaviour says."""
        self.calls.append(cmd)
        out = Path(cmd[cmd.index("--out") + 1])
        js = Path(cmd[cmd.index("--json") + 1])
        result, png, err = self.behaviours.get(out.stem, ({"missing": [], "placements": []}, opaque_png, ""))
        js.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(result, dict):
            js.write_text(json.dumps(result))
        elif isinstance(result, str):
            js.write_text(result)
        if png:
            png(out)
        return types.SimpleNamespace(returncode=1 if err else 0, stdout="", stderr=err)


def run_main(monkeypatch, *argv):
    """Call golden_run.main() with the given arguments."""
    monkeypatch.setattr(sys, "argv", ["golden_run.py", *argv])
    gr.main()


def report(project):
    """golden/run/REPORT.md."""
    return (project / "golden/run/REPORT.md").read_text()


# --------------------------------------------------------------------------
# check()
# --------------------------------------------------------------------------


def test_check_failed_short_circuits(tmp_path):
    """A result with missing placements reports FAILED for each and nothing else."""
    res = {"missing": [{"label": "jersey/front", "reason": "no file"}, {"label": "pants/left", "reason": "gone"}]}
    issues, notes = gr.check({"sport": "football"}, res, tmp_path / "none.png", {}, [])
    assert issues == ["FAILED jersey/front: no file", "FAILED pants/left: gone"]
    assert notes == []


def test_check_empty_output(tmp_path):
    """A composition with no opaque pixels is EMPTY; skipped placements are ignored."""
    png = empty_png(tmp_path / "x.png")
    res = {"placements": [{"status": "skipped", "label": "jersey/left"}]}
    assert gr.check({"sport": "football"}, res, png, {}, []) == (["EMPTY output"], [])


def test_check_clipping_threshold(tmp_path):
    """Clipping over 2px is a CLIPPED defect; 1-2px is a rounding note."""
    png = opaque_png(tmp_path / "x.png")
    f = tmp_path / "f.png"
    res = {"placements": [placed(f, clipped={"L": 1, "B": 2})]}
    assert gr.check({"sport": "football"}, res, png, {}, []) == ([], ["clip (rounding) jersey/icon L1,B2px"])
    res = {"placements": [placed(f, clipped={"R": 3})]}
    assert gr.check({"sport": "football"}, res, png, {}, []) == (["CLIPPED jersey/icon R3px"], [])


def test_check_wrong_era(tmp_path, cfg):
    """The placed file's era is measured from content size and compared with the planned one."""
    W = canvas_size(cfg, "mbk_shorts")
    a = art(tmp_path / "a" / "2000 White.png", W, era(cfg, "mens_basketball-shorts-left", "a")["size"])
    b = art(tmp_path / "b" / "2000 White.png", W, era(cfg, "mens_basketball-shorts-left", "b")["size"])
    odd = art(tmp_path / "c" / "2000 White.png", W, (10, 10))
    blank = empty_png(tmp_path / "d" / "2000 White.png")
    ex = {"sport": "mens_basketball", "expect_eras": {"1/shorts/left": "a", "1/shorts/right": None}}
    P = lambda f: {"placements": [placed(f, "2000 White", "shorts", "left")]}  # noqa: E731
    assert gr.check(ex, P(a), None, cfg, []) == ([], [])
    assert gr.check(ex, P(b), None, cfg, []) == (["WRONG ERA shorts/left: planned a, placed b"], [])
    assert gr.check(ex, P(odd), None, cfg, [])[0] == ["WRONG ERA shorts/left: planned a, placed unrecognised size"]
    assert gr.check(ex, P(blank), None, cfg, [])[0] == ["WRONG ERA shorts/left: planned a, placed unrecognised size"]
    # the nearest of two eras inside tolerance wins (helmet back E 667 vs E2 674)
    e = era(cfg, "football-helmet-back", "E")["size"]
    near = art(tmp_path / "e" / "2000 White.png", (700, 800), (e[0] + 3, e[1]))
    hb = {"sport": "football", "expect_eras": {"1/helmet/back": "E"}}
    assert gr.check(hb, {"placements": [placed(near, "2000 White", "helmet", "back")]}, None, cfg, []) == ([], [])
    # a viewpoint whose expected era is empty is not checked
    r = {"placements": [placed(odd, "2000 White", "shorts", "right")]}
    assert gr.check(ex, r, None, cfg, []) == ([], [])


def test_check_number(tmp_path):
    """NUMBER fires on another number placed, or on an unnumbered file placed while the requested number exists."""
    d = tmp_path / "2020 Maroon"
    plain = opaque_png(d / "2020 Maroon.png")
    ex = {"sport": "football"}
    res = {"placements": [placed(plain, number_requested="7")]}
    assert gr.check(ex, res, None, {}, []) == ([], [])
    opaque_png(d / "2020 Maroon 17.png")
    opaque_png(d / "2020 Maroon 07.png")
    assert gr.check(ex, res, None, {}, []) == ([], [])  # '07' and '17' are not '7'
    opaque_png(d / "2020 Maroon 7 Grad.png")
    assert gr.check(ex, res, None, {}, []) == (
        ["NUMBER jersey/icon: asked for 7, a file exists, placed unnumbered"],
        [],
    )
    res = {"placements": [placed(d / "2020 Maroon 17.png", number_requested="7", number_found="17")]}
    assert gr.check(ex, res, None, {}, [])[0] == [
        "NUMBER jersey/icon: asked for 7, placed 17: another number is never used"
    ]
    (d / "2020 Maroon 7 Grad.png").unlink()  # even with no file numbered 7 at all
    assert gr.check(ex, res, None, {}, [])[0] == [
        "NUMBER jersey/icon: asked for 7, placed 17: another number is never used"
    ]
    opaque_png(d / "2020 Maroon 7 Grad.png")
    res = {"placements": [placed(d / "2020 Maroon 7 Grad.png", number_requested="7", number_found="7")]}
    assert gr.check(ex, res, None, {}, []) == ([], [])


def test_check_extra_token(tmp_path):
    """EXTRA TOKEN fires when the placed file carries unrequested tokens and a plainer same-number file exists."""
    vocab = ["NCAA", "Grad"]
    d = tmp_path / "2020 Maroon"
    both = opaque_png(d / "2020 Maroon 7 Grad NCAA.png")
    ex = {"sport": "football"}
    res = {"placements": [placed(both, number_found="7", tokens_found=["Grad", "NCAA"])]}
    assert gr.check(ex, res, None, {}, vocab) == ([], [])  # nothing plainer yet
    opaque_png(d / "2020 Maroon 9.png")  # plainer but a different number
    opaque_png(d / "2020 Maroon 7 Grad.png")  # plainer, same number
    issues, _ = gr.check(ex, res, None, {}, vocab)
    assert issues == [
        "EXTRA TOKEN jersey/icon: placed 2020 Maroon 7 Grad NCAA.png but plainer 2020 Maroon 7 Grad.png exists"
    ]
    # a requested token is not "extra": with Grad asked for, only the NCAA-free file is plainer
    res = {"placements": [placed(both, number_found="7", tokens_found=["Grad", "NCAA"], tokens_requested=["Grad"])]}
    assert gr.check(ex, res, None, {}, vocab)[0] == [
        "EXTRA TOKEN jersey/icon: placed 2020 Maroon 7 Grad NCAA.png but plainer 2020 Maroon 7 Grad.png exists"
    ]
    # every token requested: nothing to check
    res = {"placements": [placed(both, number_found="7", tokens_found=["Grad"], tokens_requested=["Grad"])]}
    assert gr.check(ex, res, None, {}, vocab) == ([], [])


def test_check_number_ignores_patch_tokens_ending_in_digits(tmp_path):
    """With 21 asked for, CWS21 is a patch token, not number 21, so placing the unnumbered file is not a NUMBER defect."""
    vocab = gr.vocab_tokens(REPO, "baseball")
    d = tmp_path / "2021 White"
    plain = opaque_png(d / "2021 White.png")
    opaque_png(d / "2021 White CWS21.png")
    res = {"placements": [placed(plain, "2021 White", number_requested="21")]}
    assert gr.check({"sport": "baseball"}, res, None, {}, vocab) == ([], [])
    opaque_png(d / "2021 White 21 CWS21.png")
    assert gr.check({"sport": "baseball"}, res, None, {}, vocab)[0] == [
        "NUMBER jersey/icon: asked for 21, a file exists, placed unnumbered"
    ]


def test_plainer_exists_ignores_patch_tokens_ending_in_digits(tmp_path):
    """An unnumbered SEC75 file is plainer than an unnumbered Grad NCAA one: SEC75 is a token, not number 75."""
    vocab = gr.vocab_tokens(REPO, "football")
    d = tmp_path / "2020 Maroon"
    both = opaque_png(d / "2020 Maroon Grad NCAA.png")
    opaque_png(d / "2020 Maroon SEC75.png")
    assert gr.plainer_exists(placed(both, tokens_found=["Grad", "NCAA"]), vocab) == "2020 Maroon SEC75.png"


def test_plainer_exists_reads_stems_outside_element(tmp_path):
    """A file whose stem does not start with the element name is still parsed for tokens and number."""
    d = tmp_path / "2020 Maroon"
    p = opaque_png(d / "2020 Maroon Grad.png")
    opaque_png(d / "other.png")
    rec = placed(p, tokens_found=["Grad"])
    assert gr.plainer_exists(rec, ["Grad"]) == "other.png"


# --------------------------------------------------------------------------
# small functions
# --------------------------------------------------------------------------


def test_vocab_tokens_extends_cycles_and_sequences(tmp_path):
    """Vocabularies follow `extends`, a sport's own token wins, sequences are dropped, cycles and missing files exit."""
    c = tmp_path / "configs"
    c.mkdir()
    (c / "modifiers_a.yaml").write_text(
        yaml.safe_dump(
            {
                "extends": "b",
                "tokens": {
                    "x": {"token": "Long Sleeve", "scope": "variation"},
                    "s": {"token": "A", "kind": "sequence"},
                },
            }
        )
    )
    (c / "modifiers_b.yaml").write_text(
        yaml.safe_dump({"tokens": {"x": {"token": "Old"}, "g": {"label": "Grad"}, "n": {"note": "no name"}}})
    )
    (c / "modifiers_c.yaml").write_text(yaml.safe_dump({"extends": "missing"}))
    (c / "modifiers_d.yaml").write_text(yaml.safe_dump({"extends": "e"}))
    (c / "modifiers_e.yaml").write_text(yaml.safe_dump({"extends": "d"}))
    with pytest.raises(SystemExit, match="Circular `extends` reaching modifiers_d.yaml"):
        gr.vocab_tokens(tmp_path, "d")
    assert gr.vocab_tokens(tmp_path, "a") == ["Long Sleeve", "Grad"]
    with pytest.raises(SystemExit, match="No vocabulary at configs/modifiers_missing.yaml"):
        gr.vocab_tokens(tmp_path, "c")
    with pytest.raises(SystemExit, match="No vocabulary at configs/modifiers_nope.yaml"):
        gr.vocab_tokens(tmp_path, "nope")


def test_vocab_tokens_real_shared():
    """The real football vocabulary includes shared tokens, longest first."""
    v = gr.vocab_tokens(REPO, "football")
    assert "NCAA" in v
    assert "Grad" in v
    assert v == sorted(v, key=len, reverse=True)


def test_font_falls_back_to_default(monkeypatch):
    """Without any TrueType font installed, the label font is Pillow's default."""
    from PIL import ImageFont

    real = ImageFont.truetype

    def nope(f, *a, **k):
        """Pretend no font file exists on disk; Pillow's embedded font still loads."""
        if isinstance(f, str):
            raise OSError
        return real(f, *a, **k)

    monkeypatch.setattr(gr.ImageFont, "truetype", nope)
    assert isinstance(gr.font(10, True), type(ImageFont.load_default()))


def test_find_root_and_missing_manifest(tmp_path, project, monkeypatch):
    """No configs above the cwd exits; a project without a manifest exits telling you to plan first."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch)
    assert "No configs/canvas_definitions.yaml" in str(e.value)
    monkeypatch.chdir(project)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch)
    assert "run scripts/golden/golden_plan.py first" in str(e.value)


# --------------------------------------------------------------------------
# main() with a real compose
# --------------------------------------------------------------------------


def draw_icons(project, cfg):
    """Draw MSU football helmet, jersey and pants icons on the icon canvas."""
    W = canvas_size(cfg, "football_icon")
    base = project / "Football" / MSU
    for slot in ("Helmets", "Jerseys", "Pants"):
        art(base / f"{slot} Icon" / "2020 Maroon" / "2020 Maroon.png", W)


def test_end_to_end_strict_ok(project, cfg, monkeypatch, capsys):
    """A real composition passes every check, and --strict reports every example ok."""
    draw_icons(project, cfg)
    els = {"helmet": "2020 Maroon", "jersey": "2020 Maroon", "pants": "2020 Maroon"}
    eras = {f"1/{s}/icon": "all" for s in els}
    manifest(project, [entry("football--icons-horizontal--01", uniform1=els, number=None, expect_eras=eras)])
    run_main(monkeypatch, "--strict")
    out = capsys.readouterr().out
    assert "1 examples to render" in out
    assert "ok     football--icons-horizontal--01" in out
    assert "STRICT: every example is ok" in out
    d = project / "golden/run/football/icons-horizontal"
    with Image.open(d / "football--icons-horizontal--01.png") as im:
        assert im.size == (2430, 750)
    assert json.loads((d / "football--icons-horizontal--01.json").read_text())["missing"] == []
    assert (project / "golden/run/sheets/football--icons-horizontal.png").is_file()
    assert "**1 examples, 0 with defects.**" in report(project)
    assert "| football | `icons-horizontal` | 1 |  | [sheet](sheets/football--icons-horizontal.png) |" in report(
        project
    )
    html = (project / "golden/run/index.html").read_text()
    assert "1 rendered" in html
    assert "<h2>football / icons-horizontal</h2>" in html


def test_end_to_end_failed_placement(project, cfg, monkeypatch, capsys):
    """A real composition with an element that has no artwork is FAILED and fails --strict."""
    draw_icons(project, cfg)
    els = {"helmet": "2020 Maroon", "jersey": "1999 Nothing", "pants": "2020 Maroon"}
    manifest(project, [entry("football--icons-horizontal--01", uniform1=els)])
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, "--strict")
    assert str(e.value) == "STRICT: 1 with defects, 0 with notes (of 1 rendered this run)"
    out = capsys.readouterr().out
    assert "DEFECT football--icons-horizontal--01" in out
    assert "- FAILED jersey/icon: no file under Jerseys Icon/1999 Nothing" in out
    r = report(project)
    assert "## Defects" in r
    assert "### `football--icons-horizontal--01` — Mississippi State" in r


# --------------------------------------------------------------------------
# main() with a crafted compose
# --------------------------------------------------------------------------


def suite(project, monkeypatch, tmp_path):
    """A manifest of examples with every outcome, and a fake compose producing each."""
    f = opaque_png(tmp_path / "art" / "2020 Maroon" / "2020 Maroon.png")
    ok = {"missing": [], "placements": [placed(f)]}
    behaviours = {
        "fb--a--01": (ok, opaque_png, ""),
        "fb--a--02": ({"missing": [], "placements": [placed(f, clipped={"T": 2})]}, opaque_png, ""),
        "fb--a--03": ({"missing": [], "placements": [placed(f, clipped={"T": 5})]}, opaque_png, ""),
        "fb--b--01": ({"missing": [{"label": "jersey/icon", "reason": "no file"}], "placements": []}, None, ""),
        "fb--b--02": (ok, empty_png, ""),
        "fb--b--03": (None, None, "Traceback\nValueError: boom\n"),
        "fb--b--04": (None, None, ""),
        "fb--b--05": ("{not json", None, ""),
        "sc--c--01": (ok, opaque_png, ""),
    }
    entries = [
        entry("fb--a--01", view="a", number="7"),
        entry("fb--a--02", view="a"),
        entry("fb--a--03", view="a"),
        entry("fb--b--01", view="b"),
        entry("fb--b--02", view="b"),
        entry("fb--b--03", view="b"),
        entry("fb--b--04", view="b"),
        entry("fb--b--05", view="b"),
        entry("fb--b--06", view="b", approved=False),
        entry(
            "sc--c--01",
            sport="soccer",
            view="c",
            uniform2={"jersey": "2024 Blue Keeper", "shorts": "2024 Blue"},
            number="10",
            number2="1",
            expect_eras={"1/jersey/front": "ss", "2/jersey/front": "ss", "2/shorts/front": "all"},
            helmet_left=True,
            **{"with": ["Grad"]},
        ),
    ]
    manifest(project, entries)
    fake = FakeCompose(behaviours)
    monkeypatch.setattr(gr.subprocess, "run", fake)
    return fake


def test_every_outcome_reported(project, monkeypatch, tmp_path, capsys):
    """Each outcome is printed, reported in REPORT.md, sheeted, and --strict counts defects and notes.

    A compose that wrote no result is a FAILED defect of this run, so it is in the report too.
    """
    fake = suite(project, monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, "--strict")
    assert str(e.value) == "STRICT: 6 with defects, 1 with notes (of 9 rendered this run)"
    out = capsys.readouterr().out
    assert "9 examples to render (1 not approved, skipped)" in out
    assert "[  1/9] ok     fb--a--01" in out
    assert "[  2/9] note   fb--a--02" in out
    assert "[  3/9] DEFECT fb--a--03" in out
    assert "- CLIPPED jersey/icon T5px" in out
    assert "- FAILED jersey/icon: no file" in out
    assert "- EMPTY output" in out
    assert "- FAILED compose: ValueError: boom" in out
    assert "- FAILED compose: no output" in out
    for x in ("fb--b--03", "fb--b--04", "fb--b--05"):
        assert f"DEFECT {x}" in out
    assert "fb--b--06" not in out
    assert "9 rendered this run; report covers 9, 6 with defects" in out

    # the command carries every manifest field compose needs
    sc = next(c for c in fake.calls if "sc--c--01.png" in c[c.index("--out") + 1])
    for flag in (["--number", "10"], ["--number2", "1"], ["--with", "Grad"], ["--jersey2", "2024 Blue Keeper"]):
        i = sc.index(flag[0])
        assert sc[i : i + 2] == flag
    assert "--helmet-left" in sc
    assert sc[sc.index("--team") + 1] == MSU

    r = report(project)
    assert "**9 examples, 6 with defects.**" in r
    assert "### `fb--a--03` — Mississippi State\n- CLIPPED jersey/icon T5px" in r
    assert "### `fb--b--01`" in r
    assert "### `fb--b--02`" in r
    assert "- EMPTY output" in r
    assert "## Notes (not defects)\n\n- `fb--a--02`: clip (rounding) jersey/icon T2px" in r
    assert "### `fb--b--03` — Mississippi State\n- FAILED compose: ValueError: boom" in r
    assert "### `fb--b--05`" in r
    assert "fb--b--06" not in r
    assert "| football | `a` | 3 | 1 | [sheet](sheets/football--a.png) |" in r
    assert "| football | `b` | 5 | 5 | [sheet](sheets/football--b.png) |" in r
    assert "| soccer | `c` | 1 |  | [sheet](sheets/soccer--c.png) |" in r
    sheets = sorted(p.name for p in (project / "golden/run/sheets").iterdir())
    assert sheets == ["football--a.png", "football--b.png", "soccer--c.png"]
    html = (project / "golden/run/index.html").read_text()
    assert "<b class=bad>6 with defects</b>" in html
    assert "<h2 class=bad>football / a — 1 defect</h2>" in html
    assert "<h2 class=bad>football / b — 5 defects</h2>" in html


def test_strict_counts_a_note_alone(project, monkeypatch, tmp_path, capsys):
    """Under --strict a 1-2px clipping note fails the run even with no defects."""
    suite(project, monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, "--strict", "--only", "fb--a--02")
    assert str(e.value) == "STRICT: 0 with defects, 1 with notes (of 1 rendered this run)"
    assert "1 examples to render" in capsys.readouterr().out


def test_only_refreshes_one_and_reports_all(project, monkeypatch, tmp_path, capsys):
    """--only composes just the named example while the report still covers every result on disk."""
    fake = suite(project, monkeypatch, tmp_path)
    run_main(monkeypatch)
    capsys.readouterr()
    fake.calls.clear()
    fake.behaviours["fb--a--03"] = fake.behaviours["fb--a--01"]
    # --strict judges only what this run rendered; older results on disk (2
    # defects, 1 note) are reported but not judged
    run_main(monkeypatch, "--only", "fb--a--03", "--strict")
    out = capsys.readouterr().out
    assert "STRICT: every example is ok (1 rendered this run)" in out
    assert len(fake.calls) == 1
    assert "fb--a--03.png" in fake.calls[0][fake.calls[0].index("--out") + 1]
    assert "1 rendered this run; report covers 6, 2 with defects" in out
    r = report(project)
    assert "### `fb--a--03`" not in r
    assert "| football | `a` | 3 |  |" in r
    assert "### `fb--b--02`" in r


def test_only_strict_ok(project, monkeypatch, tmp_path, capsys):
    """--strict exits normally when every approved result on disk is clean."""
    fake = suite(project, monkeypatch, tmp_path)
    run_main(monkeypatch, "--sport", "soccer", "--strict")
    out = capsys.readouterr().out
    assert len(fake.calls) == 1
    assert "STRICT: every example is ok" in out
    assert "| soccer | `c` | 1 |" in report(project)


def test_strict_with_sport_ignores_earlier_results_on_disk(project, monkeypatch, tmp_path, capsys):
    """--strict --sport passes on a clean sport even when another sport's earlier results on disk have defects."""
    suite(project, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        run_main(monkeypatch, "--sport", "football", "--strict")
    capsys.readouterr()
    run_main(monkeypatch, "--sport", "soccer", "--strict")
    out = capsys.readouterr().out
    assert "report covers 6, 3 with defects" in out
    assert "STRICT: every example is ok (1 rendered this run)" in out


def test_strict_judges_this_runs_defect_not_an_older_clean_result(project, monkeypatch, tmp_path, capsys):
    """A defect rendered in this run fails --strict even if earlier results of other examples are clean."""
    fake = suite(project, monkeypatch, tmp_path)
    run_main(monkeypatch, "--only", "fb--a--01")
    fake.behaviours["sc--c--01"] = fake.behaviours["fb--a--03"]
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, "--sport", "soccer", "--strict")
    assert str(e.value) == "STRICT: 1 with defects, 0 with notes (of 1 rendered this run)"


def test_sport_filter_and_report_from_disk(project, monkeypatch, tmp_path, capsys):
    """--sport composes one sport; results for other sports already on disk stay in the report."""
    fake = suite(project, monkeypatch, tmp_path)
    run_main(monkeypatch, "--sport", "football")
    capsys.readouterr()
    assert all("soccer" not in c for c in fake.calls)
    fake.calls.clear()
    run_main(monkeypatch, "--sport", "soccer")
    out = capsys.readouterr().out
    assert len(fake.calls) == 1
    assert "report covers 6, 3 with defects" in out
    r = report(project)
    assert "| football | `b` | 2 | 2 |" in r
    assert "| soccer | `c` | 1 |  |" in r


def test_stale_png_removed_before_compose(project, monkeypatch, tmp_path, capsys):
    """A PNG left from an earlier run is deleted before compose runs, so a failed compose shows NOT RENDERED."""
    suite(project, monkeypatch, tmp_path)
    old = opaque_png(project / "golden/run/football/b/fb--b--01.png")
    run_main(monkeypatch, "--only", "fb--b--01")
    assert not old.exists()
    assert "### `fb--b--01`" in report(project)


def test_stale_json_not_read_as_ok(project, monkeypatch, tmp_path, capsys):
    """A compose that writes no JSON is FAILED with its last error line, never the previous run's result."""
    fake = suite(project, monkeypatch, tmp_path)
    run_main(monkeypatch, "--only", "fb--a--01", "--strict")
    js = project / "golden/run/football/a/fb--a--01.json"
    assert js.is_file()
    capsys.readouterr()
    fake.behaviours["fb--a--01"] = (None, None, "Unknown token(s): Bogus\nNot in configs/modifiers_football.yaml\n")
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, "--only", "fb--a--01", "--strict")
    assert str(e.value).startswith("STRICT: 1 with defects")
    out = capsys.readouterr().out
    assert "DEFECT fb--a--01" in out
    assert "- FAILED compose: Not in configs/modifiers_football.yaml" in out
    assert not js.exists()
    assert not js.with_suffix(".png").exists()
    r = report(project)
    assert "### `fb--a--01` — Mississippi State\n- FAILED compose: Not in configs/modifiers_football.yaml" in r


def test_end_to_end_unknown_token_after_ok_run(project, cfg, monkeypatch, capsys):
    """With a real compose: an ok example given `with: [Bogus]` fails --strict instead of reusing its old result."""
    draw_icons(project, cfg)
    els = {"helmet": "2020 Maroon", "jersey": "2020 Maroon", "pants": "2020 Maroon"}
    ex = entry("football--icons-horizontal--01", uniform1=els)
    manifest(project, [ex])
    run_main(monkeypatch, "--strict")
    capsys.readouterr()
    manifest(project, [{**ex, "with": ["Bogus"]}])
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, "--strict")
    assert str(e.value).startswith("STRICT: 1 with defects")
    out = capsys.readouterr().out
    assert "DEFECT football--icons-horizontal--01" in out
    assert "- FAILED compose: " in out
    assert not (project / "golden/run/football/icons-horizontal/football--icons-horizontal--01.png").exists()


@pytest.mark.parametrize(
    "entries, argv",
    [
        ([], []),
        ([entry("fb--a--01", view="a", approved=False)], []),
        ([entry("fb--a--01", view="a")], ["--sport", "soccer"]),
    ],
    ids=["empty manifest", "none approved", "sport with no entries"],
)
def test_nothing_selected_reports_zero(project, monkeypatch, capsys, entries, argv):
    """With no example selected, golden/run/ is created and the report says 0 examples; --strict then fails."""
    manifest(project, entries)
    run_main(monkeypatch, *argv)
    assert "**0 examples, 0 with defects.**" in report(project)
    assert "0 rendered" in (project / "golden/run/index.html").read_text()
    assert "0 rendered this run; report covers 0" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, *argv, "--strict")
    assert str(e.value) == "STRICT: no approved example matched the selection, so nothing was checked"


def test_contact_sheet_labels_and_outline(tmp_path):
    """Defect rows are outlined in red and an unrendered row says NOT RENDERED; more than four rows wrap."""
    good = opaque_png(tmp_path / "g.png", (800, 400))
    out = tmp_path / "sheets" / "s.png"
    rows = [(good, ["#01 ok"], False), (tmp_path / "missing.png", ["DEFECT #02"], True)] + [(good, ["x"], False)] * 3
    gr.contact_sheet(rows, out, "title")
    with Image.open(out) as im:
        assert im.size == (4 * (520 + 40) + 40, 2 * (520 + 32 * 6 + 40) + 130)
        # the defect's outline, just outside its thumbnail
        assert im.getpixel((40 + 560 - 2, 110 + 100)) == (200, 30, 30)
        assert im.getpixel((40 - 4, 110 + 100)) == (210, 210, 210)


def test_runs_as_a_script(project, monkeypatch, capsys):
    """Executed as __main__, the script runs the manifest of the project it is run in."""
    import runpy

    manifest(project, [])
    monkeypatch.setattr(sys, "argv", ["golden_run.py"])
    runpy.run_path(str(REPO / "scripts/golden/golden_run.py"), run_name="__main__")
    assert "0 rendered this run; report covers 0, 0 with defects" in capsys.readouterr().out


def test_root_flag_from_outside_the_project(project, tmp_path, monkeypatch):
    """--root names the project when run from elsewhere: its missing manifest is what's reported."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    with pytest.raises(SystemExit, match="No golden/manifest.yaml"):
        run_main(monkeypatch, "--root", str(project))
