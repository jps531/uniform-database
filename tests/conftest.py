"""Shared fixtures: a throwaway project on a copy of the real configs, the real configs themselves, and small configs.

Tests never touch the repository's own tree or the iCloud artwork. Each one
that needs files gets `project`: a temporary directory holding a COPY of the
real configs/ and a link to scripts/, where it draws whatever artwork it
needs with `helpers.art()`. Sizes come from the real configs (`cfg`), so a
test exercises the same canvases, profiles and eras the pipeline does.

Plain helpers (artwork, lookups, config overrides) are in helpers.py; this
file holds fixtures only.
"""

from pathlib import Path

import pytest
import yaml
from helpers import REPO, make_project, small_configs


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
    """A throwaway project root (see helpers.make_project), with the cwd set to it."""
    root = make_project(tmp_path / "project")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def small(project) -> dict:
    """The test project switched to scaled-down helmet and venue configs (helpers.small_configs); returns the cfg."""
    return small_configs(project)
