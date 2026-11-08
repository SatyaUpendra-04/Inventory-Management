# ADR-0004: Qt Quick (QML) UI with a token-based design system

- **Status:** Accepted (amended 2026-11-08 during Sprint 2, see "Amendments")
- **Date:** 2026-11-08

## Context
The product owner requires a top-notch, theme-adjustable UI with macOS-inspired animations and colour-theory-accurate proportions. Sprint 0 used a Qt Widgets window. Qt Widgets draws on the CPU, styles through style sheets with limited animation support, and makes smooth sheets, springs, blur and animated list changes difficult and slow.

## Decision
- Build every screen in **Qt Quick (QML)**, GPU-rendered, with Python view-models exposed as `QObject`s. Business logic stays in Python layers below.
- All visual values come from **design tokens**: OKLCH-generated tonal palettes, 60-30-10 colour proportions, semantic status colours, a modular type scale, a 4-point spacing grid, and motion durations and easing curves.
- Themes: Light, Dark, System, high-contrast, and a user-chosen accent colour generated and contrast-checked in OKLCH.
- Motion follows macOS-style principles (sheets, spring easing, gliding selection, animated lists) and honours the Windows reduced-motion setting.
- Contrast (WCAG 2.2 AA) is checked in CI for every theme and for random custom accents.

## Consequences
- Fluid, GPU-accelerated animation and theming are straightforward.
- Two UI languages (QML for layout, Python for logic); view-models must be designed carefully so QML never contains business rules.
- QML screens are tested through their view-models, a zero-QML-warnings check across every page and theme, keyboard tests, and screenshots.
- A design-system sprint is added before feature screens, extending the plan by about two weeks.

## Amendments (Sprint 2)
1. **Font: Segoe UI Variable instead of bundled Inter.** Only Inter Regular and Bold were available locally; a polished UI needs the in-between weights. Segoe UI Variable is Windows 11's own interface font, has every weight, and is hinted for Windows screens — the better choice for a Windows-first desktop app. Fallbacks: Segoe UI, then Inter. Bundling Inter can be revisited if the app ever ships beyond Windows.
2. **Icons: our own outline set** (45 SVGs, 1.75 px rounded strokes) instead of Lucide, so nothing is downloaded or licensed. Rendered by a Python image provider that tints them to theme colours at exact pixel size.
3. **Automatic accent nudging** instead of rejecting colours: if button text would fall below 4.5:1, the accent's lightness is nudged just enough (hue and chroma kept). Presets move by at most 1 % lightness. Only unparseable input is rejected.
4. **Screenshots instead of pixel-diff baselines in CI.** Off-screen rendering on CI uses Qt's software renderer, which cannot draw GPU effects (shadows, blur) and may differ in font rasterisation between machines, so exact baseline comparisons would be flaky. CI instead renders every key page in light, dark and high-contrast, checks none is blank or emits QML warnings, and uploads the images as the `ui-screenshots` artifact for human review. Shadows and blur were verified separately on the real Direct3D renderer.
5. **View-models are exposed as QML context properties** (`Theme`, `Shell`, `Toasts`) set per engine. This keeps each test's engine isolated; it can move to registered QML singletons later without changing any screen code.

## Alternatives considered
- **Qt Widgets with style sheets:** familiar and fine for forms, but cannot meet the motion and polish requirement without heavy custom painting.
- **Web UI in a desktop shell (Electron / Tauri):** excellent styling, but a second language stack (JavaScript) and a larger, slower install for a single-platform desktop app.
- **Third-party Fluent/Material widget kits:** quick to start, but would impose another product's look instead of our own design system.
