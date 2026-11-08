"""Colour maths: OKLCH conversion, gamut mapping and WCAG contrast."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ims.ui.theme.color import (
    Oklch,
    contrast_ratio,
    ensure_contrast,
    hex_to_oklch,
    hex_to_rgb,
    in_gamut,
    oklch_to_hex,
    relative_luminance,
    rgb_to_hex,
    with_alpha,
)


def test_reference_values() -> None:
    white, black = hex_to_oklch("#ffffff"), hex_to_oklch("#000000")
    assert white.l == pytest.approx(1.0, abs=1e-4) and white.c == pytest.approx(0, abs=1e-4)
    assert black.l == pytest.approx(0.0, abs=1e-4)
    # sRGB red in OKLCH is L 0.628, C 0.258, h 29.2 (Ottosson's reference)
    red = hex_to_oklch("#ff0000")
    assert (red.l, red.c, red.h) == pytest.approx((0.628, 0.258, 29.23), abs=1e-2)


hex_colors = st.integers(0, 0xFFFFFF).map(lambda v: f"#{v:06x}")


@given(hex_colors)
def test_round_trip_is_exact_to_the_8_bit_value(color: str) -> None:
    assert oklch_to_hex(hex_to_oklch(color)) == color


def test_out_of_gamut_colours_keep_lightness_and_hue() -> None:
    vivid = Oklch(0.7, 0.4, 145.0)  # far beyond sRGB green
    assert not in_gamut(vivid)
    mapped = hex_to_oklch(oklch_to_hex(vivid))
    assert mapped.l == pytest.approx(0.7, abs=0.01)
    assert mapped.h == pytest.approx(145.0, abs=2.0)
    assert mapped.c < 0.4


def test_wcag_contrast_reference_values() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0)
    assert contrast_ratio("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    assert relative_luminance("#ffffff") == pytest.approx(1.0)


def test_ensure_contrast_moves_lightness_only() -> None:
    pale = hex_to_oklch("#9db8ff")
    fixed = ensure_contrast(pale, "#ffffff", 4.5, darken=True)
    assert contrast_ratio(oklch_to_hex(fixed), "#ffffff") >= 4.5
    assert (fixed.c, fixed.h) == (pale.c, pale.h)
    assert ensure_contrast(fixed, "#ffffff", 4.5, darken=True) == fixed  # already fine


def test_hex_parsing_and_alpha() -> None:
    assert hex_to_rgb("2f6fed") == pytest.approx((47 / 255, 111 / 255, 237 / 255))
    assert rgb_to_hex((1.2, -0.1, 0.5)) == "#ff0080"
    assert with_alpha("#2f6fed", 0.5) == "#802f6fed"
    with pytest.raises(ValueError, match="#RRGGBB"):
        hex_to_rgb("blue")
