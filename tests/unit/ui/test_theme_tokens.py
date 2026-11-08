"""Every theme must meet WCAG 2.2 AA, and palettes must step evenly."""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ims.ui.theme.color import contrast_ratio, hex_to_oklch
from ims.ui.theme.palette import generate
from ims.ui.theme.tokens import (
    ACCENT_PRESETS,
    STATUS_HUES,
    accent_adjustment,
    accent_problems,
    build_theme,
)

AA_TEXT, AA_UI = 4.5, 3.0
THEMES = [
    pytest.param(dark, hc, accent, id=f"{name}-{'dark' if dark else 'light'}{'-hc' if hc else ''}")
    for (name, accent), dark, hc in itertools.product(
        ACCENT_PRESETS.items(), (False, True), (False, True)
    )
]


def contrast_failures(colors: dict[str, str]) -> list[str]:
    """Every foreground/background pair the UI actually uses, with its WCAG minimum."""
    pairs: list[tuple[str, str, float]] = []
    for bg in ("window", "surface", "surfaceRaised", "element"):
        pairs += [("text", bg, AA_TEXT), ("textMuted", bg, AA_TEXT)]
    pairs += [
        ("accentText", "surface", AA_TEXT),
        ("accentText", "window", AA_TEXT),
        ("accentText", "accentSubtle", AA_TEXT),  # selected sidebar item
        ("onAccent", "accent", AA_TEXT),
        ("onAccent", "accentHover", AA_TEXT),
        ("controlBorder", "surface", AA_UI),
        ("controlBorder", "window", AA_UI),
        ("focusRing", "window", AA_UI),
        ("focusRing", "surface", AA_UI),
    ]
    for status in STATUS_HUES:
        pairs += [
            (f"{status}Text", f"{status}Bg", AA_TEXT),
            (f"{status}Text", "surface", AA_TEXT),
            (f"{status}OnSolid", f"{status}Solid", AA_TEXT),
        ]
    return [
        f"{fg} on {bg}: {contrast_ratio(colors[fg], colors[bg]):.2f} < {minimum}"
        for fg, bg, minimum in pairs
        if contrast_ratio(colors[fg], colors[bg]) < minimum
    ]


@pytest.mark.parametrize(("dark", "high_contrast", "accent"), THEMES)
def test_every_preset_theme_meets_wcag_aa(dark: bool, high_contrast: bool, accent: str) -> None:
    colors = build_theme(dark=dark, accent=accent, high_contrast=high_contrast).colors
    assert contrast_failures(colors) == []


@given(st.integers(0, 0xFFFFFF).map(lambda v: f"#{v:06x}"), st.booleans())
def test_any_accepted_custom_accent_meets_wcag_aa(accent: str, dark: bool) -> None:
    """Whatever colour someone types, if it is accepted the theme stays readable."""
    if accent_problems(accent):
        return
    assert contrast_failures(build_theme(dark=dark, accent=accent).colors) == []


def test_high_contrast_is_stronger_than_normal() -> None:
    normal = build_theme(dark=False).colors
    high = build_theme(dark=False, high_contrast=True).colors
    assert contrast_ratio(high["text"], high["window"]) == pytest.approx(21.0)
    assert contrast_ratio(high["controlBorder"], high["surface"]) > contrast_ratio(
        normal["controlBorder"], normal["surface"]
    )


@pytest.mark.parametrize("dark", [False, True])
def test_palettes_step_evenly_in_lightness(dark: bool) -> None:
    """Steps 1-7 move steadily away from the background, as OKLCH promises.

    Step 8 (control borders) is deliberately pushed further, to reach 3:1 contrast.
    """
    palette = generate("#2f6fed", dark=dark)
    lightness = [hex_to_oklch(palette[step]).l for step in range(1, 8)]
    steps = [b - a for a, b in itertools.pairwise(lightness)]
    assert all((s > 0) if dark else (s < 0) for s in steps)
    assert max(abs(s) for s in steps) / min(abs(s) for s in steps) < 4.5
    assert contrast_ratio(palette[8], palette[1]) >= AA_UI
    with pytest.raises(IndexError):
        palette[13]


def test_accent_validation_and_nudging() -> None:
    assert accent_problems("blue") == ["Enter a colour as #RRGGBB."]
    assert all(accent_problems(c) == [] for c in ACCENT_PRESETS.values())
    assert accent_adjustment("#2f6fed", dark=False) == pytest.approx(0, abs=1e-9)
    assert max(accent_adjustment(c, dark=d) for c in ACCENT_PRESETS.values()
               for d in (False, True)) < 0.02  # presets barely move  # fmt: skip


def test_theme_serialises_for_qml() -> None:
    data = build_theme(dark=True).as_qml()
    assert data["dark"] is True and data["colors"]["window"].startswith("#")
    assert set(data["shadows"]) == {"low", "medium", "high"}
