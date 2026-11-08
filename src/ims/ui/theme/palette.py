"""12-step tonal palettes generated in OKLCH (ARCHITECTURE.md §7.2).

Each step has one job, in every palette and theme:

====  ==========================  ====  ==========================
step  use                          step  use
====  ==========================  ====  ==========================
1     app / window background      7     border
2     subtle background (surface)  8     strong border (controls)
3     element background           9     solid fill (buttons)
4     element hover                10    solid hover
5     element pressed / selected   11    low-contrast text
6     divider                      12    high-contrast text
====  ==========================  ====  ==========================

Steps 8, 11 and 12 are pushed until they meet WCAG contrast against the surfaces they
sit on, so accessibility is guaranteed by construction (and checked again in tests).
"""

from __future__ import annotations

from dataclasses import dataclass

from ims.ui.theme.color import (
    Oklch,
    contrast_ratio,
    ensure_contrast,
    hex_to_oklch,
    oklch_to_hex,
)

# Lightness of each step (steps 9-10 come from the base colour).
_LIGHT_L = (0.993, 0.982, 0.957, 0.933, 0.909, 0.880, 0.835, 0.765, None, None, 0.470, 0.250)
_DARK_L = (0.165, 0.193, 0.238, 0.272, 0.305, 0.350, 0.415, 0.505, None, None, 0.805, 0.945)
# Share of the base chroma used by each step: quiet backgrounds, colourful solids.
_CHROMA = (0.035, 0.07, 0.15, 0.22, 0.30, 0.40, 0.52, 0.68, 1.0, 1.0, 0.85, 0.45)

AA_TEXT = 4.5
AAA_TEXT = 7.0
AA_NON_TEXT = 3.0


@dataclass(frozen=True, slots=True)
class Palette:
    steps: tuple[str, ...]  # 12 hex colours; index 0 is step 1

    def __getitem__(self, step: int) -> str:
        if not 1 <= step <= 12:
            raise IndexError("palette steps are 1-12")
        return self.steps[step - 1]


def _solid(base: Oklch, dark: bool) -> Oklch:
    if not dark:
        return base
    # Solids read slightly brighter on dark backgrounds.
    return base.with_(l=min(0.80, max(0.52, base.l + 0.04)))


def generate(base_hex: str, *, dark: bool, chroma: float | None = None) -> Palette:
    """Palette whose solid (step 9) is ``base_hex``; ``chroma`` overrides colourfulness."""
    base = hex_to_oklch(base_hex)
    if chroma is not None:
        base = base.with_(c=chroma)
    lightness = _DARK_L if dark else _LIGHT_L
    solid = _solid(base, dark)
    colors: list[Oklch] = []
    for index, (target, share) in enumerate(zip(lightness, _CHROMA, strict=True)):
        step = index + 1
        if step == 9:
            colors.append(solid)
        elif step == 10:
            colors.append(solid.with_(l=solid.l + (0.04 if dark else -0.04)))
        else:
            if target is None:
                raise ValueError(f"lightness table has no value for step {step}")
            colors.append(Oklch(target, base.c * share, base.h))

    hexes = [oklch_to_hex(c) for c in colors]
    surfaces = (hexes[0], hexes[1])
    # Strong border (8) must be visible on both backgrounds; text steps must be readable.
    for step, minimum in ((8, AA_NON_TEXT), (11, AA_TEXT), (12, AAA_TEXT)):
        adjusted = colors[step - 1]
        for surface in surfaces:
            adjusted = ensure_contrast(adjusted, surface, minimum, darken=not dark)
        colors[step - 1] = adjusted
        hexes[step - 1] = oklch_to_hex(adjusted)
    return Palette(tuple(hexes))


def best_text_on(fill_hex: str) -> tuple[str, float]:
    """White or near-black text, whichever is more readable on ``fill_hex``."""
    options = ("#ffffff", "#111113")
    ratios = [(contrast_ratio(text, fill_hex), text) for text in options]
    ratio, text = max(ratios)
    return text, ratio
