"""Smoke test for the shared fixtures in conftest.py."""

from helpers import art, canvas_size


def test_art_draws_content_at_the_requested_size(project, cfg):
    """art() puts an opaque rectangle of exactly the requested size on the canvas."""
    from PIL import Image

    p = art(project / "x.png", canvas_size(cfg, "football_helmet_face"), (600, 700), top=3)
    with Image.open(p) as im:
        assert im.size == canvas_size(cfg, "football_helmet_face")
        box = im.getchannel("A").getbbox()
        assert box is not None
        x0, y0, x1, y1 = box
    assert (x1 - x0, y1 - y0, y0) == (600, 700, 3)
