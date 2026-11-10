"""Cross-config checks: every sport the configs name has the vocabulary its scripts load."""

import compose
import nest_elements
import pytest
import yaml
from conftest import REPO


def sports() -> list[str]:
    """Every sport with a view template or a canvas assignment."""
    templates = yaml.safe_load((REPO / "configs" / "view_templates.yaml").read_text())["templates"]
    assignments = yaml.safe_load((REPO / "configs" / "canvas_definitions.yaml").read_text())["assignments"]
    return sorted({t["sport"] for t in templates} | set(assignments))


@pytest.mark.parametrize("sport", sports())
def test_every_sport_resolves_a_vocabulary(sport):
    """compose.load_vocab finds a non-empty vocabulary, shared tokens included, for every configured sport."""
    tokens, _, _ = compose.load_vocab(REPO, sport)
    assert tokens, f"no configs/modifiers_{sport}.yaml, or nothing it extends has tokens"
    assert "NCAA" in tokens, "shared tokens should arrive through `extends`"


@pytest.mark.parametrize("sport", sports())
def test_every_sport_nests(sport):
    """nest_elements.load_vocab finds patch tokens and colorways for every configured sport rather than exiting."""
    strip, _, _, _, known = nest_elements.load_vocab(REPO, sport)
    assert strip and known


@pytest.mark.parametrize(
    ("sport", "base"),
    [("softball", "baseball"), ("mens_basketball", "basketball"), ("womens_basketball", "basketball")],
)
def test_alias_vocabularies_match_their_base(sport, base):
    """Softball reads baseball's vocabulary and both basketball programs read basketball's, token for token."""
    assert compose.load_vocab(REPO, sport) == compose.load_vocab(REPO, base)
    assert nest_elements.load_vocab(REPO, sport) == nest_elements.load_vocab(REPO, base)
