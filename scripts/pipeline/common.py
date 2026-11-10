"""
Helpers every script in scripts/ shares: finding the project, reading config,
naming sports, matching eras, measuring artwork and walking a tree.

Not a script: nothing here runs on its own. Each helper used to exist in
several scripts, written slightly differently each time — three markers for
the project root, closest-era matching in some scripts and first-match in
others, blank files measured as None in one and as the whole image in
another, AppleDouble `._*.png` files read as artwork by one walker and
skipped by the rest. A new script imports these rather than writing its own.

Scripts in scripts/pipeline/ import it directly; those in migration/ and
golden/ add scripts/pipeline/ to sys.path first, as they already do for
standardize.py and compose.py.
"""

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Missing dependencies: run `uv sync`")

# The DPI tag every PNG the pipeline writes carries. Photoshop places by
# physical size, so an untagged file (read as 72) lands at 4.17x.
DPI = 300
# The provenance marker in a generated directory (docs/reference.md, "Provenance").
MARKER = ".generated"
# Physical form variants that select a canvas: helmet shell, jersey cut, hat
# style. Different domain words, identical handling: file-level, never part
# of the element name.
FORM_KINDS = ("shell", "cut", "style")
# The file whose presence marks the project root.
ROOT_MARKER = Path("configs") / "canvas_definitions.yaml"


# ---------------------------------------------------------------- the project


def find_root(start: Path) -> Path:
    """The nearest directory at or above `start` holding configs/canvas_definitions.yaml; exits if none."""
    for d in [start, *start.parents]:
        if (d / ROOT_MARKER).is_file():
            return d
    sys.exit(
        f"No {ROOT_MARKER.as_posix()} in {start} or any directory above it. Run from inside the project, or pass --root."
    )


def add_root_arg(parser: argparse.ArgumentParser) -> None:
    """Give a script's parser the `--root` option every script takes."""
    parser.add_argument(
        "--root",
        help=f"project root (default: the nearest directory at or above the current one holding {ROOT_MARKER.as_posix()})",
    )


def root_from(args: argparse.Namespace) -> Path:
    """The project root: `--root` if given, else found above the current directory."""
    return Path(args.root).expanduser().resolve() if args.root else find_root(Path.cwd().resolve())


def resolve(path_arg: str, root: Path) -> Path:
    """A path argument as an absolute path; relative ones are taken from the project root, not the cwd."""
    p = Path(path_arg).expanduser()
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def load_yaml(path: Path):
    """A YAML file, parsed, with the file closed afterwards. An empty file is None."""
    with Path(path).open() as fh:
        return yaml.safe_load(fh)


def load_config(root: Path) -> dict:
    """Parsed configs/canvas_definitions.yaml."""
    return load_yaml(root / ROOT_MARKER)


def tolerance(cfg: dict) -> int:
    """The px tolerance for matching content to an era, from the config; exits if the config has none.

    There is no default. Scripts once fell back to 3, 5 or a hard-coded 5 when
    the key was missing, so the same file could match an era in one script
    and not another.
    """
    if "tolerance" not in cfg:
        sys.exit(f"No `tolerance` in {ROOT_MARKER.as_posix()}: eras can't be matched without it.")
    return cfg["tolerance"]


def slot_dirs(cfg: dict) -> dict:
    """Slot key -> its directory word, from `directory_slots`: {'helmet': 'Helmets', 'jersey': 'Jerseys', …}."""
    return {slot: word for word, slot in cfg["directory_slots"].items()}


# ---------------------------------------------------------------- sports


def sport_slug(name: str) -> str:
    """Directory name -> sport slug: lowercase, apostrophes (straight or curly) dropped, spaces to underscores."""
    return name.lower().replace("\u2019", "").replace("'", "").replace(" ", "_")


def sport_dir(root: Path, slug: str) -> Path | None:
    """The directory directly under `root` whose name slugs to `slug`, or None if there is none.

    Matched on the slug, never by title-casing it: `.title()` turns
    mens_basketball into "Mens Basketball" and never finds "Men's
    Basketball". Works for any parent — the project root, temp/, or
    Venues/, where basketball is the ungendered "Basketball".
    """
    if not root.is_dir():
        return None
    return next((d for d in sorted(root.iterdir()) if d.is_dir() and sport_slug(d.name) == slug), None)


# ---------------------------------------------------------------- vocabulary


@dataclass(frozen=True)
class Vocabulary:
    """A sport's vocabulary with its `extends` chain merged: tokens by key, and colorways in order."""

    tokens: dict
    colorways: list


def load_vocabulary(root: Path, name: str) -> Vocabulary:
    """configs/modifiers_{name}.yaml merged over every file it `extends`.

    A token defined in the extending file wins over the same key in its
    base. Colorways are MERGED, base first: a sport listing its own colorways
    adds to shared's rather than replacing them. Exits naming the file when
    one in the chain is missing, or when the chain loops.
    """
    chain, seen = [], set()
    while name:
        if name in seen:
            sys.exit(f"Circular `extends` reaching modifiers_{name}.yaml")
        seen.add(name)
        p = root / "configs" / f"modifiers_{name}.yaml"
        if not p.is_file():
            sys.exit(
                f"No vocabulary at configs/modifiers_{name}.yaml"
                + (f" (extended by modifiers_{chain[-1][0]}.yaml)" if chain else "")
            )
        cfg = load_yaml(p) or {}
        chain.append((name, cfg))
        name = cfg.get("extends")
    tokens, colorways = {}, []
    for _, cfg in reversed(chain):
        tokens.update(cfg.get("tokens") or {})
        for c in cfg.get("colorways") or []:
            if c not in colorways:
                colorways.append(c)
    return Vocabulary(tokens, colorways)


def token_name(entry: dict):
    """A token's string as it appears in filenames: its `token`, else its `label`; None if it has neither."""
    return entry.get("token") or entry.get("label")


def longest_first(strings) -> list:
    """Distinct strings, longest first and alphabetical within a length, so matching prefers the longest and never depends on set order."""
    return sorted(set(strings), key=lambda s: (-len(s), s))


def known_colorways(root: Path) -> set:
    """Colorway strings AS THEY APPEAR IN FILENAMES, lowercased, from configs/slots_global.yaml; empty if it is missing.

    Both the KEY and the token/label are accepted, because filenames use
    either: "Dark Gray" matches the key dark_gray, while "Powder" matches
    the key where the label is "Powder Blue". Keys alone missed every
    multi-word colorway; labels alone missed the shortened ones.
    """
    p = root / "configs" / "slots_global.yaml"
    if not p.is_file():
        return set()
    out = set()
    for key, v in ((load_yaml(p) or {}).get("colorways") or {}).items():
        out.add(str(key).replace("_", " ").lower())
        if isinstance(v, dict):
            out |= {alt.lower() for alt in (v.get("token"), v.get("label")) if alt}
    return out


# ---------------------------------------------------------------- eras


def era_size(entry: dict, post_scale: bool = False) -> tuple:
    """An era's content size: as authored, or with `post_scale` as its scale correction leaves it."""
    w, h = entry["size"]
    if not post_scale:
        return w, h
    s = entry.get("scale", 1)
    return round(w * s), round(h * s)


def match_era(profile, size, tol: int, post_scale: bool = False):
    """The profile entry CLOSEST to `size` (smallest |dw| + |dh|) within `tol` on each axis, or None.

    Ties go to the first listed. With `post_scale`, each era's size after its
    scale correction is compared instead, for standardized files whose
    correction is baked in. Closest, not first: helmet back eras E (667) and
    E2 (674) are 7px apart, so at tolerance 5 their windows overlap for
    content 669-672 wide, and first-match gave all of it to E.
    """
    best = None
    for entry in profile or []:
        w, h = era_size(entry, post_scale)
        dw, dh = abs(w - size[0]), abs(h - size[1])
        if dw <= tol and dh <= tol and (best is None or dw + dh < best[0]):
            best = (dw + dh, entry)
    return best[1] if best else None


def scaled_eras(profile) -> list:
    """The eras of a profile that carry a scale correction (scale other than 1)."""
    return [e for e in profile or [] if e.get("scale", 1) != 1]


def standard_canvases(cfg: dict, canvas, profile) -> set:
    """Every (width, height) a standardized file of this slot can sit on: the slot canvas plus each era `canvas:` override.

    A file already sitting on one of these has been through `pad`, which
    refuses to pad it again. `fills: fill` canvases are left out: there the
    canvas IS the content, so authored source cropped to its content
    already sits on it and canvas size can't tell source from output.
    """
    out = set()
    if canvas and canvas.get("width") and canvas.get("fills") != "fill":
        out.add((canvas["width"], canvas["height"]))
    for e in profile or []:
        oc = cfg["canvases"].get(e.get("canvas") or "") or {}
        if oc.get("width") and oc.get("fills") != "fill":
            out.add((oc["width"], oc["height"]))
    return out


# ---------------------------------------------------------------- artwork


@contextmanager
def open_rgba(path: Path) -> Iterator[Image.Image]:
    """Open a PNG as RGBA with its EXIF orientation applied, closing the file and every copy afterwards.

    Finder's "rotate" writes an EXIF tag instead of turning the pixels, so
    every measurement goes through exif_transpose.
    """
    with Image.open(path) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGBA")
        try:
            yield im
        finally:
            im.close()


def alpha_box(im: Image.Image):
    """The bounding box of an open RGBA image's opaque pixels, or None if it is fully transparent."""
    return im.getchannel("A").getbbox()


def content_box(path: Path) -> tuple:
    """(image size, opaque bounding box) of a PNG, orientation applied; the box is None for a fully transparent file."""
    with open_rgba(path) as im:
        return im.size, alpha_box(im)


def content_size(path: Path):
    """(width, height) of a PNG's opaque content, orientation applied, or None for a fully transparent file."""
    _, box = content_box(path)
    return None if box is None else (box[2] - box[0], box[3] - box[1])


def pngs(root: Path, recursive: bool = True) -> list:
    """Every PNG under `root`, sorted, skipping any with a hidden part (a dot-file or dot-folder) below `root`.

    Judged relative to `root` only, so a checkout under a dot-folder
    (.claude/worktrees/…) isn't hidden wholesale. Skips AppleDouble `._*.png`
    files and iCloud placeholders too. With `recursive` False, only the PNGs
    directly in `root`.
    """
    if not root.is_dir():
        return []
    found = root.rglob("*.png") if recursive else root.glob("*.png")
    return sorted(p for p in found if not any(part.startswith(".") for part in p.relative_to(root).parts))
