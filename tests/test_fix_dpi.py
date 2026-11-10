"""Tests for scripts/migration/fix_dpi.py: `check` reports DPI tags read-only, `set` retags without touching pixels."""

import runpy
import sys

import fix_dpi
import numpy as np
import pytest
from conftest import REPO, art
from PIL import Image, ImageCms, ImageOps, PngImagePlugin

SCRIPT = str(REPO / "scripts" / "migration" / "fix_dpi.py")


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
    assert "300 DPI" in out
    assert "2 files   e.g. a.png" in out
    assert "72 DPI" in out
    assert "e.g. c.png" in out
    assert "no DPI tag" in out
    assert "e.g. d.png" in out
    assert "Mixed DPI" in out
    assert {p.name: p.read_bytes() for p in (tmp_path / "T").iterdir()} == before


def test_check_all_untagged_notes_the_72_dpi_default(tmp_path, capsys):
    """check on files that are all untagged says they default to 72 DPI, without the mixed warning."""
    untagged(tmp_path / "a.png")
    fix_dpi.cmd_check(tmp_path)
    out = capsys.readouterr().out
    assert "no DPI tag" in out
    assert "default to 72 DPI" in out
    assert "Mixed" not in out


def test_check_uniform_tag_prints_no_warning(tmp_path, capsys):
    """check on files all at one DPI reports just the count."""
    art(tmp_path / "a.png", (4, 4))
    fix_dpi.cmd_check(tmp_path)
    out = capsys.readouterr().out
    assert "1 files" in out
    assert "Mixed" not in out
    assert "default to 72" not in out


@pytest.mark.parametrize("cmd", [fix_dpi.cmd_check, lambda p: fix_dpi.cmd_set(p, 300, apply=True)])
def test_no_pngs_exits(tmp_path, cmd):
    """Both commands exit naming the root when there are no PNGs under it."""
    with pytest.raises(SystemExit, match="No PNGs under"):
        cmd(tmp_path)


def test_set_retags_only_files_off_target_and_keeps_pixels(tmp_path, monkeypatch, capsys):
    """set --apply rewrites files not at the target to that DPI, leaves correct ones byte-identical, and changes no pixel."""
    a = art(tmp_path / "x" / "a.png", (30, 20), (10, 8), top=3, seed=1, dpi=(72, 72))
    b = untagged(tmp_path / "x" / "b.png")
    c = art(tmp_path / "x" / "c.png", (7, 7), dpi=(300, 300))
    px = {p: pixels(p) for p in (a, b, c)}
    c_bytes = c.read_bytes()
    run_script(monkeypatch, "set", str(tmp_path / "x"), "300", "--apply")
    out = capsys.readouterr().out
    assert "Set 300 DPI on 2 files (1 already correct)." in out
    assert "verified unchanged" in out
    assert c.read_bytes() == c_bytes
    for p in (a, b, c):
        assert fix_dpi.read_dpi(p) == 300
        with Image.open(p) as im:
            assert im.size == px[p].shape[1::-1]
        assert np.array_equal(pixels(p), px[p])
    assert sorted(q.name for q in (tmp_path / "x").iterdir()) == ["a.png", "b.png", "c.png"]


def test_set_without_apply_is_a_dry_run(tmp_path, monkeypatch, capsys):
    """set without --apply lists what it would retag and writes nothing."""
    a = art(tmp_path / "x" / "a.png", (6, 6), dpi=(72, 72))
    b = untagged(tmp_path / "x" / "b.png")
    c = art(tmp_path / "x" / "c.png", (6, 6), dpi=(300, 300))
    before = {p: p.read_bytes() for p in (a, b, c)}
    run_script(monkeypatch, "set", str(tmp_path / "x"), "300")
    out = capsys.readouterr().out
    assert "would set 300 DPI on 2 files (1 already correct)" in out
    assert "72 DPI -> 300" in out
    assert "no DPI tag -> 300" in out
    assert "--apply" in out
    assert {p: p.read_bytes() for p in (a, b, c)} == before


def tagged(path, orientation=6):
    """Write a 300-DPI-less PNG carrying an EXIF Orientation tag, an ICC profile and text chunks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(np.arange(4 * 6 * 4, dtype=np.uint8).reshape(4, 6, 4) | 1)
    exif = Image.Exif()
    exif[0x0112] = orientation
    info = PngImagePlugin.PngInfo()
    info.add_text("Software", "Finder")
    info.add_itxt("Comment", "rotated", lang="en", tkey="Comment")
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    im.save(path, dpi=(72, 72), exif=exif, icc_profile=icc, pnginfo=info)
    return path, icc


def test_set_keeps_exif_orientation_icc_and_text(tmp_path):
    """set --apply keeps the EXIF Orientation tag, the ICC profile and the text chunks, so the file still displays the same way."""
    p, icc = tagged(tmp_path / "r.png")
    px = pixels(p)
    fix_dpi.cmd_set(tmp_path, 300, apply=True)
    with Image.open(p) as im:
        assert im.getexif().get(0x0112) == 6
        assert im.info.get("icc_profile") == icc
        assert im.text["Software"] == "Finder"
        assert im.text["Comment"] == "rotated"
        assert round(im.info["dpi"][0]) == 300
        with ImageOps.exif_transpose(im) as t:
            assert t.size == (4, 6)
    assert np.array_equal(pixels(p), px)


def test_set_keeps_the_file_mode(tmp_path):
    """set --apply replaces the file atomically but keeps its permission bits."""
    p = art(tmp_path / "a.png", (5, 5), dpi=(72, 72))
    p.chmod(0o640)
    fix_dpi.cmd_set(tmp_path, 300, apply=True)
    assert p.stat().st_mode & 0o777 == 0o640


def test_set_aborts_if_a_save_changes_pixel_dimensions(tmp_path, monkeypatch):
    """set aborts naming the file if the re-saved image's dimensions differ, leaving the original untouched and no temp file."""
    p = art(tmp_path / "a.png", (10, 10), dpi=(72, 72))
    before = p.read_bytes()
    real_save = Image.Image.save

    def shrinking_save(self, fp, *args, **kwargs):
        """Save a cropped copy, simulating a save that did more than retag."""
        return real_save(self.crop((0, 0, 5, 5)), fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", shrinking_save)
    with pytest.raises(SystemExit, match=r"ABORT: .*a\.png changed size \(10, 10\) -> \(5, 5\)"):
        fix_dpi.cmd_set(tmp_path, 300, apply=True)
    monkeypatch.undo()
    assert p.read_bytes() == before
    assert [q.name for q in tmp_path.iterdir()] == ["a.png"]


def test_set_aborts_if_a_save_changes_pixels(tmp_path, monkeypatch):
    """set aborts if the re-saved pixels differ at the same size, leaving the original untouched."""
    p = art(tmp_path / "a.png", (10, 10), dpi=(72, 72))
    before = p.read_bytes()
    real_save = Image.Image.save

    def blanking_save(self, fp, *args, **kwargs):
        """Save a transparent image of the same size, simulating a lossy save."""
        return real_save(Image.new("RGBA", self.size), fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", blanking_save)
    with pytest.raises(SystemExit, match=r"ABORT: .*a\.png pixels changed"):
        fix_dpi.cmd_set(tmp_path, 300, apply=True)
    monkeypatch.undo()
    assert p.read_bytes() == before
    assert [q.name for q in tmp_path.iterdir()] == ["a.png"]


def test_set_aborts_if_a_save_drops_the_orientation(tmp_path, monkeypatch):
    """set aborts if the re-saved file's EXIF orientation differs, leaving the original untouched."""
    p, _ = tagged(tmp_path / "r.png")
    before = p.read_bytes()
    real_save = Image.Image.save

    def exif_dropping_save(self, fp, *args, **kwargs):
        """Save without the EXIF block, as Pillow does when it isn't passed explicitly."""
        kwargs.pop("exif", None)
        return real_save(self, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", exif_dropping_save)
    with pytest.raises(SystemExit, match=r"ABORT: .*r\.png orientation changed 6 -> None"):
        fix_dpi.cmd_set(tmp_path, 300, apply=True)
    monkeypatch.undo()
    assert p.read_bytes() == before


def test_set_aborts_if_a_save_drops_the_dpi_tag(tmp_path, monkeypatch):
    """set aborts if the re-saved file doesn't carry the target DPI, leaving the original untouched."""
    p = art(tmp_path / "a.png", (6, 6), dpi=(72, 72))
    before = p.read_bytes()
    real_save = Image.Image.save

    def dpi_dropping_save(self, fp, *args, **kwargs):
        """Save without any DPI tag."""
        kwargs.pop("dpi", None)
        return real_save(self, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", dpi_dropping_save)
    with pytest.raises(SystemExit, match=r"ABORT: .*a\.png re-saved without the 300 DPI tag"):
        fix_dpi.cmd_set(tmp_path, 300, apply=True)
    monkeypatch.undo()
    assert p.read_bytes() == before


def test_set_removes_the_temp_file_if_the_save_raises(tmp_path, monkeypatch):
    """A save that raises leaves the original untouched and no temp file behind."""
    p = art(tmp_path / "a.png", (6, 6), dpi=(72, 72))
    before = p.read_bytes()

    def failing_save(self, fp, *args, **kwargs):
        """Fail as a full disk would."""
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", failing_save)
    with pytest.raises(OSError, match="disk full"):
        fix_dpi.cmd_set(tmp_path, 300, apply=True)
    monkeypatch.undo()
    assert p.read_bytes() == before
    assert [q.name for q in tmp_path.iterdir()] == ["a.png"]


@pytest.mark.parametrize(
    "argv",
    [[], ["check"], ["set", "x"], ["frob", "x"], ["set", "x", "abc"], ["set", "x", "0"], ["check", "x", "--apply"]],
)
def test_bad_arguments_print_usage_and_exit_2(monkeypatch, capsys, argv):
    """Anything other than `check PATH` or `set PATH DPI [--apply]` prints a usage error, not a traceback, and exits 2."""
    with pytest.raises(SystemExit) as e:
        run_script(monkeypatch, *argv)
    assert e.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_missing_pillow_exits_with_a_hint(monkeypatch):
    """Without Pillow installed the script exits telling the user to run `uv sync`."""
    monkeypatch.setitem(sys.modules, "PIL", None)
    with pytest.raises(SystemExit, match="uv sync"):
        runpy.run_path(SCRIPT, run_name="fix_dpi_noimport")
