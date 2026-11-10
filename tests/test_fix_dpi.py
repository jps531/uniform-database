"""Tests for scripts/fix_dpi.py: `check` reports DPI tags read-only, `set` retags without touching pixels."""

import runpy
import sys

import fix_dpi
import numpy as np
import pytest
from conftest import REPO, art
from PIL import Image

SCRIPT = str(REPO / "scripts" / "fix_dpi.py")


def run_script(monkeypatch, *argv):
    """Run fix_dpi.py as `__main__` with the given arguments."""
    monkeypatch.setattr(sys, "argv", ["fix_dpi.py", *argv])
    runpy.run_path(SCRIPT, run_name="__main__")


def untagged(path, size=(12, 9)):
    """Write a PNG with no pHYs chunk at all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (10, 20, 30, 255)).save(path)
    return path


def pixels(path):
    """The file's pixels as an array."""
    with Image.open(path) as im:
        return np.array(im)


def test_pngs_sorted_and_skips_hidden_files_and_directories(tmp_path):
    """pngs() yields PNGs in sorted order and ignores hidden files and anything under a hidden directory."""
    for rel in ("b/2.png", "a/1.png", ".hidden/3.png", "a/.4.png"):
        art(tmp_path / rel, (4, 4))
    (tmp_path / "a" / "notes.txt").write_text("x")
    assert [p.relative_to(tmp_path).as_posix() for p in fix_dpi.pngs(tmp_path)] == ["a/1.png", "b/2.png"]


def test_read_dpi_rounds_and_reports_untagged_as_none(tmp_path):
    """read_dpi() rounds the horizontal tag and returns None for an untagged file."""
    assert fix_dpi.read_dpi(art(tmp_path / "a.png", (4, 4), dpi=(72, 72))) == 72
    assert fix_dpi.read_dpi(untagged(tmp_path / "b.png")) is None


def test_check_reports_mixed_dpi_with_counts_and_examples(tmp_path, monkeypatch, capsys):
    """check counts files per DPI tag, gives an example of each and warns that the set is mixed."""
    art(tmp_path / "T" / "a.png", (5, 5), dpi=(300, 300))
    art(tmp_path / "T" / "b.png", (5, 5), dpi=(300, 300))
    art(tmp_path / "T" / "c.png", (5, 5), dpi=(72, 72))
    untagged(tmp_path / "T" / "d.png")
    before = {p.name: p.read_bytes() for p in (tmp_path / "T").iterdir()}
    run_script(monkeypatch, "check", str(tmp_path / "T"))
    out = capsys.readouterr().out
    assert "4 PNGs under T" in out
    assert "300 DPI" in out and "2 files   e.g. a.png" in out
    assert "72 DPI" in out and "e.g. c.png" in out
    assert "no DPI tag" in out and "e.g. d.png" in out
    assert "Mixed DPI" in out
    assert {p.name: p.read_bytes() for p in (tmp_path / "T").iterdir()} == before


def test_check_all_untagged_notes_the_72_dpi_default(tmp_path, capsys):
    """check on files that are all untagged says they default to 72 DPI, without the mixed warning."""
    untagged(tmp_path / "a.png")
    fix_dpi.cmd_check(tmp_path)
    out = capsys.readouterr().out
    assert "no DPI tag" in out and "default to 72 DPI" in out and "Mixed" not in out


def test_check_uniform_tag_prints_no_warning(tmp_path, capsys):
    """check on files all at one DPI reports just the count."""
    art(tmp_path / "a.png", (4, 4))
    fix_dpi.cmd_check(tmp_path)
    out = capsys.readouterr().out
    assert "1 files" in out and "Mixed" not in out and "default to 72" not in out


@pytest.mark.parametrize("cmd", [fix_dpi.cmd_check, lambda p: fix_dpi.cmd_set(p, 300)])
def test_no_pngs_exits(tmp_path, cmd):
    """Both commands exit naming the root when there are no PNGs under it."""
    with pytest.raises(SystemExit, match="No PNGs under"):
        cmd(tmp_path)


def test_set_retags_only_files_off_target_and_keeps_pixels(tmp_path, monkeypatch, capsys):
    """set rewrites files not at the target to that DPI, leaves correct ones byte-identical, and changes no pixel."""
    a = art(tmp_path / "x" / "a.png", (30, 20), (10, 8), top=3, seed=1, dpi=(72, 72))
    b = untagged(tmp_path / "x" / "b.png")
    c = art(tmp_path / "x" / "c.png", (7, 7), dpi=(300, 300))
    px = {p: pixels(p) for p in (a, b, c)}
    c_bytes = c.read_bytes()
    run_script(monkeypatch, "set", str(tmp_path / "x"), "300")
    out = capsys.readouterr().out
    assert "Set 300 DPI on 2 files (1 already correct)." in out
    assert "verified unchanged" in out
    assert c.read_bytes() == c_bytes
    for p in (a, b, c):
        assert fix_dpi.read_dpi(p) == 300
        with Image.open(p) as im:
            assert im.size == px[p].shape[1::-1]
        assert np.array_equal(pixels(p), px[p])


def test_set_aborts_if_a_save_changes_pixel_dimensions(tmp_path, monkeypatch):
    """set aborts naming the file if the re-saved image's dimensions differ from the original."""
    p = art(tmp_path / "a.png", (10, 10), dpi=(72, 72))
    real_save = Image.Image.save

    def shrinking_save(self, fp, *args, **kwargs):
        """Save a cropped copy, simulating a save that did more than retag."""
        return real_save(self.crop((0, 0, 5, 5)), fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", shrinking_save)
    with pytest.raises(SystemExit, match=r"ABORT: .*a\.png changed size \(10, 10\) -> \(5, 5\)"):
        fix_dpi.cmd_set(tmp_path, 300)
    monkeypatch.undo()
    assert p.exists()


@pytest.mark.parametrize("argv", [[], ["check"], ["set", "x"], ["frob", "x"]])
def test_bad_arguments_print_usage_and_exit_1(monkeypatch, capsys, argv):
    """Anything other than `check PATH` or `set PATH DPI` prints the usage text and exits 1."""
    with pytest.raises(SystemExit) as e:
        run_script(monkeypatch, *argv)
    assert e.value.code == 1
    assert "Normalize PNG DPI metadata" in capsys.readouterr().out


def test_missing_pillow_exits_with_a_hint(monkeypatch):
    """Without Pillow installed the script exits telling the user to run `uv sync`."""
    monkeypatch.setitem(sys.modules, "PIL", None)
    with pytest.raises(SystemExit, match="uv sync"):
        runpy.run_path(SCRIPT, run_name="fix_dpi_noimport")
