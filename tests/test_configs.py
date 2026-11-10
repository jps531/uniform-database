"""Cross-config checks: every sport the configs name has the vocabulary its scripts load."""

import common
import compose
import nest_elements
import pytest
import yaml
from helpers import REPO


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
    assert strip
    assert known


@pytest.mark.parametrize(
    ("sport", "base"),
    [("softball", "baseball"), ("mens_basketball", "basketball"), ("womens_basketball", "basketball")],
)
def test_alias_vocabularies_match_their_base(sport, base):
    """Softball reads baseball's vocabulary and both basketball programs read basketball's, token for token."""
    assert compose.load_vocab(REPO, sport) == compose.load_vocab(REPO, base)
    assert nest_elements.load_vocab(REPO, sport) == nest_elements.load_vocab(REPO, base)


# --- cross-file invariants ---------------------------------------------------

CONFIGS = REPO / "configs"
FOLDER_SCOPES, FILE_SCOPES = {"design"}, {"patch", "variation"}
FOLDER_KINDS, FILE_KINDS = {"finish"}, set(compose.FORM_KINDS)


def load(name: str) -> dict:
    """One config file under configs/, parsed."""
    return yaml.safe_load((CONFIGS / name).read_text()) or {}


def vocabularies() -> list[str]:
    """Every vocabulary name: modifiers_{name}.yaml in configs/."""
    return sorted(p.stem.removeprefix("modifiers_") for p in CONFIGS.glob("modifiers_*.yaml"))


@pytest.mark.parametrize("name", vocabularies())
def test_no_token_at_both_folder_and_file_scope(name):
    """No token string is both folder-level (design, finish) and file-level (patch, variation, form) in a resolved vocabulary."""
    tokens = common.load_vocabulary(REPO, name).tokens
    folder, file = {}, {}
    for key, v in tokens.items():
        s = v.get("token") or v.get("label")
        if v.get("scope") in FOLDER_SCOPES or v.get("kind") in FOLDER_KINDS:
            folder.setdefault(s, []).append(key)
        elif v.get("scope") in FILE_SCOPES or v.get("kind") in FILE_KINDS:
            file.setdefault(s, []).append(key)
    both = {s: (folder[s], file[s]) for s in folder.keys() & file.keys()}
    assert not both, f"tokens at both levels (folder keys, file keys): {both}"


def test_every_colorway_is_global():
    """Every colorway any modifiers file lists is in slots_global.yaml, by key, token or label."""
    known = set()
    for key, v in load("slots_global.yaml")["colorways"].items():
        known |= {s.lower() for s in (key.replace("_", " "), v.get("token"), v.get("label")) if s}
    missing = {
        f"{name}: {c}"
        for name in vocabularies()
        for c in load(f"modifiers_{name}.yaml").get("colorways") or []
        if c.lower() not in known
    }
    assert not missing, f"add these to configs/slots_global.yaml: {sorted(missing)}"


def test_every_named_canvas_exists_with_a_size():
    """Every canvas an assignment or an era `canvas:` names is defined with a positive integer width and height."""
    cfg = load("canvas_definitions.yaml")
    named = {cv for slots in cfg["assignments"].values() for vps in slots.values() for cv in vps.values()}
    named |= {e["canvas"] for eras in cfg["profiles"].values() for e in eras if "canvas" in e}
    for name in sorted(named):
        canvas = cfg["canvases"].get(name)
        assert canvas, f"canvas {name} is used but not defined"
        for side in ("width", "height"):
            assert isinstance(canvas.get(side), int) and canvas[side] > 0, f"{name} needs a positive {side}"


def test_tolerance_is_below_the_closest_era_gap():
    """`tolerance` is smaller than the smallest gap between two distinct era sizes in any one profile."""
    cfg = load("canvas_definitions.yaml")
    gaps = [
        (max(abs(a["size"][0] - b["size"][0]), abs(a["size"][1] - b["size"][1])), key, a["era"], b["era"])
        for key, eras in cfg["profiles"].items()
        for i, a in enumerate(eras)
        for b in eras[i + 1 :]
        if a["size"] != b["size"]
    ]
    gap, key, a, b = min(gaps)
    assert cfg["tolerance"] < gap, f"tolerance {cfg['tolerance']} reaches {key} {a} vs {b}, {gap}px apart"
