"""Design tokens: every colour, size, radius, shadow and duration the UI uses.

Screens never hard-code a visual value; they read these through the ``Theme`` QML
singleton. Pure Python, so contrast and proportions are unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from ims.ui.theme.color import (
    Oklch,
    contrast_ratio,
    ensure_contrast,
    hex_to_oklch,
    oklch_to_hex,
)
from ims.ui.theme.palette import AA_NON_TEXT, AA_TEXT, Palette, best_text_on, generate


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


DEFAULT_ACCENT = "#2f6fed"

ACCENT_PRESETS: MappingProxyType[str, str] = MappingProxyType(
    {
        "Blue": "#2f6fed",
        "Indigo": "#5b5bd6",
        "Purple": "#8e4ec6",
        "Pink": "#d6409f",
        "Red": "#dc3e42",
        "Orange": "#e5670c",
        "Amber": "#c98a00",
        "Green": "#2b9a66",
        "Teal": "#12a594",
        "Graphite": "#6f6e77",
    }
)

# Semantic status hues (OKLCH degrees) and chroma, shared by every theme.
STATUS_HUES: MappingProxyType[str, tuple[float, float]] = MappingProxyType(
    {
        "success": (150.0, 0.15),  # serviceable
        "warning": (75.0, 0.16),  # limited / due soon
        "danger": (27.0, 0.19),  # grounded / overdue
        "info": (250.0, 0.15),  # information
        "neutral": (260.0, 0.01),  # retired / inactive
    }
)

TYPOGRAPHY: MappingProxyType[str, Any] = MappingProxyType(
    {
        # Windows 11's interface font; fallbacks keep older machines looking right.
        "families": ("Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Inter"),
        "displayFamilies": ("Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI", "Inter"),
        # Modular scale, ratio 1.2 from a 14 px body.
        "caption": 12,
        "body": 14,
        "headline": 17,
        "title3": 20,
        "title2": 24,
        "title1": 29,
        "regular": 400,
        "medium": 500,
        "semibold": 600,
        "bold": 700,
        "lineHeight": 1.4,
    }
)

SPACING: MappingProxyType[str, int] = MappingProxyType(
    {"xxs": 4, "xs": 8, "sm": 12, "md": 16, "lg": 24, "xl": 32, "xxl": 48}
)
RADIUS: MappingProxyType[str, int] = MappingProxyType({"sm": 6, "md": 10, "lg": 14, "pill": 999})

MOTION: MappingProxyType[str, Any] = MappingProxyType(
    {
        "micro": 120,  # hover, press, toggles
        "standard": 220,  # popovers, list changes, theme cross-fade
        "page": 350,  # page transitions, sheets
        # Fast start, gentle settle (cubic-bezier 0.2, 0.0, 0.0, 1.0).
        "easing": (0.2, 0.0, 0.0, 1.0, 1.0, 1.0),
        "pressScale": 0.97,
        "hoverLift": 1,
        "springStiffness": 6.0,
        "springDamping": 0.42,
    }
)


@dataclass(frozen=True, slots=True)
class Theme:
    dark: bool
    high_contrast: bool
    accent: str
    colors: dict[str, str]
    shadows: dict[str, dict[str, float]]
    palettes: dict[str, Palette] = field(repr=False)

    def as_qml(self) -> dict[str, Any]:
        return {
            "dark": self.dark,
            "highContrast": self.high_contrast,
            "accent": self.accent,
            "colors": dict(self.colors),
            "shadows": {k: dict(v) for k, v in self.shadows.items()},
        }


def _readable_fill(fill: str) -> tuple[str, str]:
    """Returns ``fill`` (nudged in lightness if needed) and its text colour, at least 4.5:1."""
    text, ratio = best_text_on(fill)
    if ratio >= AA_TEXT:
        return fill, text
    adjusted = ensure_contrast(hex_to_oklch(fill), text, AA_TEXT, darken=text == "#ffffff")
    return oklch_to_hex(adjusted), text


def _hover_of(fill: str, text: str) -> str:
    """Hover shade that moves *away* from the text colour, so contrast only improves."""
    color = hex_to_oklch(fill)
    shift = -0.045 if text == "#ffffff" else 0.045
    return oklch_to_hex(color.with_(l=min(0.98, max(0.05, color.l + shift))))


def accent_adjustment(accent: str, *, dark: bool) -> float:
    """How far the accent's lightness was nudged for readability (0 = used exactly)."""
    used = hex_to_oklch(build_theme(dark=dark, accent=accent).colors["accent"]).l
    requested = hex_to_oklch(generate(accent, dark=dark)[9]).l
    return abs(used - requested)


def _status_palette(name: str, dark: bool) -> Palette:
    hue, chroma = STATUS_HUES[name]
    base = oklch_to_hex(Oklch(0.62 if name != "warning" else 0.78, chroma, hue))
    return generate(base, dark=dark)


def build_theme(*, dark: bool, accent: str = DEFAULT_ACCENT, high_contrast: bool = False) -> Theme:
    accent_palette = generate(accent, dark=dark)
    # Neutrals carry a whisper of the accent hue, so greys feel related to it.
    neutral = generate(accent, dark=dark, chroma=min(0.02, hex_to_oklch(accent).c))
    n, a = neutral, accent_palette

    if high_contrast:
        window = surface = "#000000" if dark else "#ffffff"
        raised = "#121212" if dark else "#ffffff"
        text = "#ffffff" if dark else "#000000"
        muted = text
        divider = border = control_border = n[11]
    else:
        window = n[1] if dark else n[2]
        surface = n[2] if dark else n[1]
        raised = n[3] if dark else n[1]
        text, muted = n[12], n[11]
        divider, border, control_border = n[6], n[7], n[8]

    solid = a[9]
    if high_contrast:
        solid = oklch_to_hex(ensure_contrast(hex_to_oklch(solid), window, AA_TEXT, darken=not dark))
    solid, on_accent = _readable_fill(solid)
    hover = _hover_of(solid, on_accent)
    # The focus ring must be visible on every surface it can appear over.
    backgrounds = (window, surface, raised)
    focus = solid if min(contrast_ratio(solid, bg) for bg in backgrounds) >= AA_NON_TEXT else a[11]

    colors: dict[str, str] = {
        "window": window,
        "surface": surface,
        "surfaceRaised": raised,
        "sidebar": n[2] if not dark else n[1],
        "element": n[3],
        "elementHover": n[4],
        "elementActive": n[5],
        "divider": divider,
        "border": border,
        "controlBorder": control_border,
        "text": text,
        "textMuted": muted,
        "textDisabled": n[8] if not high_contrast else n[11],
        "accent": solid,
        "accentHover": hover,
        "accentSubtle": a[4],
        "accentSubtleHover": a[5],
        "accentBorder": a[7],
        "accentText": a[11],
        "onAccent": on_accent,
        "focusRing": focus,
        "overlay": "#8c000000" if dark else "#59000000",
        "shadow": "#000000",
    }
    palettes: dict[str, Palette] = {"neutral": neutral, "accent": accent_palette}
    for name in STATUS_HUES:
        p = _status_palette(name, dark)
        palettes[name] = p
        on_solid, _ = best_text_on(p[9])
        colors.update(
            {
                f"{name}Bg": p[3],
                f"{name}Border": p[7],
                f"{name}Text": p[11],
                f"{name}Solid": p[9],
                f"{name}OnSolid": on_solid,
            }
        )

    shadow_strength = 2.4 if dark else 1.0
    shadows = {
        level: {"blur": blur, "offset": offset, "opacity": min(0.6, opacity * shadow_strength)}
        for level, blur, offset, opacity in (
            ("low", 0.35, 2.0, 0.10),
            ("medium", 0.6, 6.0, 0.14),
            ("high", 1.0, 16.0, 0.20),
        )
    }
    return Theme(
        dark=dark,
        high_contrast=high_contrast,
        accent=accent,
        colors=colors,
        shadows=shadows,
        palettes=palettes,
    )


def accent_problems(accent: str) -> list[str]:
    """Why an accent colour would be hard to read, or an empty list if it is fine."""
    try:
        hex_to_oklch(accent)
    except ValueError:
        return ["Enter a colour as #RRGGBB."]
    problems: list[str] = []
    for dark in (False, True):
        theme = build_theme(dark=dark, accent=accent)
        _, ratio = best_text_on(theme.colors["accent"])
        if ratio < AA_TEXT:
            mode = "dark" if dark else "light"
            problems.append(
                f"Button text on this colour would be hard to read in {mode} mode "
                f"(contrast {ratio:.1f}:1, needs {AA_TEXT}:1)."
            )
    return problems
