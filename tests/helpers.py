"""Plain helpers shared by the tests: synthetic artwork, config lookups, throwaway projects and scaled-down configs.

Fixtures live in conftest.py; everything here is an ordinary function or
constant, imported by name (`from helpers import art, era`). No test file
imports from another test file.
"""

import os
import shutil
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

REPO = Path(__file__).resolve().parent.parent

# The synthetic team most fixtures draw, and the six football helmet eras.
TEAM = "Testers"
ERAS = ("A", "B", "C", "D", "E", "F")
# How far small_configs() shrinks helmet and venue canvases.
HELMET_DIV = 8
VENUE_DIV = {"football": 16, "baseball": 16, "basketball": 32}


# --- artwork -----------------------------------------------------------------


def art(path: Path, canvas, content=None, top=0, left=None, seed=0, dpi=(300, 300)) -> Path:
    """Draw a PNG of size `canvas` whose opaque content is a noise rectangle of size `content`.

    The content sits `top` px from the top and is centred horizontally unless
    `left` is given. With no `content` the whole canvas is opaque; with
    `content=(0, 0)` the file is fully transparent (a blank, as `blank()`
    draws). Noise makes every pixel meaningful, so a crop or offset that's
    off by one shows up in a pixel comparison. The content must fit the
    canvas: nothing is silently clipped. Returns the path.
    """
    W, H = canvas
    w, h = content or canvas
    x = (W - w) // 2 if left is None else left
    assert 0 <= x and x + w <= W and 0 <= top and top + h <= H, f"content {w}x{h} at ({x}, {top}) is off {W}x{H}"
    rng = np.random.default_rng(seed)
    a = np.zeros((H, W, 4), np.uint8)
    a[top : top + h, x : x + w, :3] = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    a[top : top + h, x : x + w, 3] = 255
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path, dpi=dpi)
    return path


def blank(path: Path, size=(20, 20)) -> Path:
    """Draw a fully transparent PNG of `size`; returns the path."""
    return art(path, size, (0, 0))


def bbox(path: Path) -> tuple:
    """(size, alpha bbox) of a PNG; the bbox is None for a fully transparent file."""
    with Image.open(path) as im:
        return im.size, im.convert("RGBA").getchannel("A").getbbox()


def pixels(path: Path) -> np.ndarray:
    """A PNG's RGBA pixels as an (H, W, 4) array."""
    with Image.open(path) as im:
        return np.array(im.convert("RGBA"))


def region(path: Path, box) -> np.ndarray:
    """The RGBA pixels of `box` (x0, y0, x1, y1) in a PNG, for comparing one region with another."""
    x0, y0, x1, y1 = box
    return pixels(path)[y0:y1, x0:x1]


# --- config lookups ----------------------------------------------------------


def era(cfg: dict, key: str, name: str) -> dict:
    """One era entry from profile `key` (e.g. 'football-helmet-left'), by its era name; KeyError naming both if absent."""
    for e in cfg["profiles"][key]:
        if e["era"] == name:
            return e
    raise KeyError(f"no era {name!r} in profile {key!r}")


def canvas_size(cfg: dict, name: str) -> tuple:
    """(width, height) of a named canvas."""
    c = cfg["canvases"][name]
    return c["width"], c["height"]


def scaled(e: dict) -> tuple:
    """The content size an era's scale produces from its listed size (the listed size when it has no scale)."""
    s = e.get("scale", 1)
    return round(e["size"][0] * s), round(e["size"][1] * s)


# --- projects and configs ----------------------------------------------------


def make_project(root: Path) -> Path:
    """A throwaway project at `root`: a COPY of the real configs/, a link to scripts/, an empty golden/.

    configs/ is copied, never linked, so a test that writes a config file
    changes only its own copy and never the repository's tracked config.
    """
    root.mkdir(parents=True)
    shutil.copytree(REPO / "configs", root / "configs")
    os.symlink(REPO / "scripts", root / "scripts")
    (root / "golden").mkdir()
    return root


def override_configs(project: Path, files: dict) -> None:
    """Rewrite files in project/configs: a dict or list is written as YAML, a str verbatim, and None deletes the file."""
    d = project / "configs"
    assert not d.is_symlink(), "configs/ must be the project's own copy"
    for name, data in files.items():
        path = d / name
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False))


def small_configs(root: Path, mutate=None) -> dict:
    """Scale root/configs' helmet and venue canvases and eras down, then apply `mutate(cfg)`; returns the cfg.

    Synthetic helmets and venues then stay a few hundred pixels instead of a
    few thousand.
    """
    cfg = yaml.safe_load((root / "configs" / "canvas_definitions.yaml").read_text())
    for vp in ("left", "right", "front", "back"):
        for e in cfg["profiles"][f"football-helmet-{vp}"]:
            e["size"] = [round(v / HELMET_DIV) for v in e["size"]]
    post = [scaled(e) for e in cfg["profiles"]["football-helmet-left"]]
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
    override_configs(root, {"canvas_definitions.yaml": cfg})
    return cfg


def write_manifest(root: Path, examples: list) -> None:
    """Write golden/manifest.yaml and push its mtime into the past, so results written later are newer."""
    p = root / "golden" / "manifest.yaml"
    p.write_text(yaml.safe_dump(examples, sort_keys=False))
    os.utime(p, (1_000_000, 1_000_000))


# --- helmets, venues, placements ---------------------------------------------


def mark(root: Path, cfg: dict, side: str, element: str, era_name: str, team=TEAM, name=None, seed=0) -> Path:
    """Draw a Marks helmet file whose content is exactly the pre-scale size of `era_name` on `side`."""
    w, h = era(cfg, f"football-helmet-{side.lower()}", era_name)["size"]
    f = root / "Marks" / "Football" / team / f"Helmets {side}" / element / f"{name or element}.png"
    return art(f, (w + 4, h + 4), (w, h), top=2, seed=seed)


def venue_dirs(sport: str) -> tuple:
    """(slot, directory word) of a sport's playing surface: courts for basketball, fields otherwise."""
    return ("court", "Courts") if sport == "basketball" else ("field", "Fields")


def venue(root: Path, cfg: dict, sport: str, element: str, seed=0, size=None, team=TEAM, tree="Venues") -> Path:
    """Draw one Full playing surface for `sport` under root/tree on its canvas (or `size`); returns the path."""
    slot, sdir = venue_dirs(sport)
    path = root / tree / sport.title() / team / f"{sdir} Full" / element / f"{element}.png"
    return art(path, size or canvas_size(cfg, f"{sport}_{slot}_full"), seed=seed)


def cropped_of(path: Path) -> Path:
    """The "… Cropped" sibling of a "… Full" venue file."""
    return path.parents[2] / path.parents[1].name.replace(" Full", " Cropped") / path.parent.name / path.name


def placed(file, slot="jersey", vp="icon", element="2020 Maroon", number=None, status="placed", u=1, **kw) -> dict:
    """One placement record as compose's --json writes it; a skipped placement has no file. `kw` overrides fields."""
    p = {
        "label": f"{slot}/{vp}" + (f" #{u}" if u != 1 else ""),
        "slot": slot,
        "viewpoint": vp,
        "uniform": u,
        "element": element,
        "file": str(file) if file else None,
        "status": status,
        "number_requested": number,
        "number_found": None,
        "tokens_requested": [],
        "tokens_found": [],
        "clipped": {},
    }
    p.update(kw)
    return p
