# ADR-0004: Qt Quick (QML) UI with a token-based design system

- **Status:** Accepted
- **Date:** 2026-11-08

## Context
The product owner requires a top-notch, theme-adjustable UI with macOS-inspired animations and colour-theory-accurate proportions. Sprint 0 used a Qt Widgets window. Qt Widgets draws on the CPU, styles through style sheets with limited animation support, and makes smooth sheets, springs, blur and animated list changes difficult and slow.

## Decision
- Build every screen in **Qt Quick (QML)**, GPU-rendered, with Python view-models exposed as `QObject`s. Business logic stays in Python layers below.
- All visual values come from **design tokens**: OKLCH-generated tonal palettes, 60-30-10 colour proportions, semantic status colours, a modular type scale, a 4-point spacing grid, and motion durations and easing curves.
- Themes: Light, Dark, System, high-contrast, and a user-chosen accent colour generated and contrast-checked in OKLCH.
- Motion follows macOS-style principles (sheets, spring easing, gliding selection, animated lists) and honours the Windows reduced-motion setting.
- Contrast (WCAG 2.2 AA) and visual regression screenshot tests run in CI.

## Consequences
- Fluid, GPU-accelerated animation and theming are straightforward.
- Two UI languages (QML for layout, Python for logic); view-models must be designed carefully so QML never contains business rules.
- QML screens are tested through their view-models plus screenshot tests, rather than widget-level clicks only.
- A design-system sprint is added before feature screens, extending the plan by about two weeks.

## Alternatives considered
- **Qt Widgets with style sheets:** familiar and fine for forms, but cannot meet the motion and polish requirement without heavy custom painting.
- **Web UI in a desktop shell (Electron / Tauri):** excellent styling, but a second language stack (JavaScript) and a larger, slower install for a single-platform desktop app.
- **Third-party Fluent/Material widget kits:** quick to start, but would impose another product's look instead of our own design system.
