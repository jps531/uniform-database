"""Shared fixtures: a throwaway project on the real configs, and synthetic artwork.

Tests never touch the repository's own tree or the iCloud artwork. Each one
that needs files gets `project`: a temporary directory holding links to the
real configs/ and scripts/, where it draws whatever artwork it needs with
`art()`. Sizes come from the real configs (`cfg`), so a test exercises the
same canvases, profiles and eras the pipeline does.
"""

import os
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

REPO = Path(__file__).resolve().parent.parent


def art(path: Path, canvas, content=None, top=0, left=None, seed=0, dpi=(300, 300)) -> Path:
    """Draw a PNG of size `canvas` whose opaque content is a noise rectangle of size `content`.

    The content sits `top` px from the top and is centred horizontally unless
    `left` is given. With no `content` the whole canvas is opaque. Noise makes
    every pixel meaningful, so a crop or offset that's off by one shows up in
    a pixel comparison. Returns the path.
    """
    W, H = canvas
    w, h = content or canvas
    x = (W - w) // 2 if left is None else left
    rng = np.random.default_rng(seed)
    a = np.zeros((H, W, 4), np.uint8)
    a[top : top + h, x : x + w, :3] = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    a[top : top + h, x : x + w, 3] = 255
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path, dpi=dpi)
    return path


@pytest.fixture(scope="session")
def cfg() -> dict:
    """The real configs/canvas_definitions.yaml."""
    return yaml.safe_load((REPO / "configs" / "canvas_definitions.yaml").read_text())


@pytest.fixture(scope="session")
def templates() -> list:
    """The real view templates from configs/view_templates.yaml."""
    return yaml.safe_load((REPO / "configs" / "view_templates.yaml").read_text())["templates"]


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    """A throwaway project root: links to the real configs/ and scripts/, an empty golden/, cwd set to it."""
    root = tmp_path / "project"
    root.mkdir()
    for name in ("configs", "scripts"):
        os.symlink(REPO / name, root / name)
    (root / "golden").mkdir()
    monkeypatch.chdir(root)
    return root


def era(cfg: dict, key: str, name: str) -> dict:
    """One era entry from profile `key` (e.g. 'football-helmet-left'), by its era name."""
    return next(e for e in cfg["profiles"][key] if e["era"] == name)


def canvas_size(cfg: dict, name: str) -> tuple:
    """(width, height) of a named canvas."""
    c = cfg["canvases"][name]
    return c["width"], c["height"]
