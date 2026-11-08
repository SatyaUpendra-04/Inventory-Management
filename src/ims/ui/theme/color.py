"""Colour maths: OKLCH <-> sRGB, gamut mapping and WCAG contrast.

OKLCH (Björn Ottosson, 2020) is a perceptually uniform colour space: equal steps in
lightness *look* equal, which is why every palette in the app is generated in it.
Pure Python, no Qt, so it can be tested exactly.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


@dataclass(frozen=True, slots=True)
class Oklch:
    l: float  # lightness 0..1  # noqa: E741 (standard name in colour science)
    c: float  # chroma 0..~0.37
    h: float  # hue in degrees 0..360

    def with_(self, *, l: float | None = None, c: float | None = None) -> Oklch:  # noqa: E741
        return Oklch(self.l if l is None else l, self.c if c is None else c, self.h)


# ------------------------------------------------------------------ sRGB transfer


def _to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else float(((channel + 0.055) / 1.055) ** 2.4)


def _to_gamma(channel: float) -> float:
    if channel <= 0.0031308:
        return 12.92 * channel
    return float(1.055 * channel ** (1 / 2.4) - 0.055)


# ------------------------------------------------------------------ conversions


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    match = _HEX.match(value.strip())
    if not match:
        raise ValueError(f"not a #RRGGBB colour: {value!r}")
    digits = match.group(1)
    return (int(digits[0:2], 16) / 255, int(digits[2:4], 16) / 255, int(digits[4:6], 16) / 255)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(min(1.0, max(0.0, ch)) * 255):02x}" for ch in rgb)


def rgb_to_oklch(rgb: tuple[float, float, float]) -> Oklch:
    r, g, b = (_to_linear(ch) for ch in rgb)
    l_ = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    chroma = math.hypot(a, bb)
    hue = math.degrees(math.atan2(bb, a)) % 360 if chroma > 1e-6 else 0.0
    return Oklch(lightness, chroma, hue)


def oklch_to_linear(color: Oklch) -> tuple[float, float, float]:
    a = color.c * math.cos(math.radians(color.h))
    b = color.c * math.sin(math.radians(color.h))
    l_ = color.l + 0.3963377774 * a + 0.2158037573 * b
    m_ = color.l - 0.1055613458 * a - 0.0638541728 * b
    s_ = color.l - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_**3, m_**3, s_**3
    return (
        4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
        -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
        -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc,
    )


def in_gamut(color: Oklch, tolerance: float = 1e-4) -> bool:
    return all(-tolerance <= ch <= 1 + tolerance for ch in oklch_to_linear(color))


def to_srgb(color: Oklch) -> tuple[float, float, float]:
    """Maps into the sRGB gamut by reducing chroma (keeps lightness and hue), then encodes."""
    if not in_gamut(color):
        low, high = 0.0, color.c
        for _ in range(24):  # binary search on chroma
            mid = (low + high) / 2
            if in_gamut(color.with_(c=mid)):
                low = mid
            else:
                high = mid
        color = color.with_(c=low)
    r, g, b = oklch_to_linear(color)
    return (
        _to_gamma(min(1.0, max(0.0, r))),
        _to_gamma(min(1.0, max(0.0, g))),
        _to_gamma(min(1.0, max(0.0, b))),
    )


def oklch_to_hex(color: Oklch) -> str:
    return rgb_to_hex(to_srgb(color))


def hex_to_oklch(value: str) -> Oklch:
    return rgb_to_oklch(hex_to_rgb(value))


# ------------------------------------------------------------------ contrast (WCAG 2.2)


def relative_luminance(hex_color: str) -> float:
    r, g, b = (_to_linear(ch) for ch in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    a, b = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def ensure_contrast(color: Oklch, background: str, minimum: float, *, darken: bool) -> Oklch:
    """Moves ``color``'s lightness (darker or lighter) until it meets ``minimum`` contrast.

    Hue and chroma are kept, so the colour stays recognisably itself.
    """
    candidate = color
    step = -0.005 if darken else 0.005
    for _ in range(220):
        if contrast_ratio(oklch_to_hex(candidate), background) >= minimum:
            return candidate
        next_l = candidate.l + step
        if not 0.0 <= next_l <= 1.0:
            break
        candidate = candidate.with_(l=next_l)
    return candidate


def with_alpha(hex_color: str, alpha: float) -> str:
    """``#AARRGGBB`` as Qt expects, for translucent fills."""
    return f"#{round(min(1.0, max(0.0, alpha)) * 255):02x}{hex_color.lstrip('#')}"
