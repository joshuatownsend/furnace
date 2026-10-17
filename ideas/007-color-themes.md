# 007 — Color themes and a Perfect Palette link

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat e9988cf35..HEAD -- src/gui/settings.cpp src/gui/settings/allSettings.cpp src/gui/settings/loadSettings.cpp src/gui/guiConst.cpp`.

- **Status**: SELECTED
- **Verdict**: Advance
- **Score**: 7/10 (my estimate; /ideate has not scored this)
- **Lenses**: both (code check plus community demand)
- **Effort (coarse)**: S–M
- **Planned at**: e9988cf35 on 2026-10-17

## The idea

Make color themes easy to find and easy to get right. Three parts, in this order:

1. **Presets.** Ship a few ready-made scheme files, including a light theme that is actually readable, and pick them from the Color tab.
2. **Contrast check.** Flag text and background pairs below the WCAG AA ratio of 4.5:1 in the current scheme.
3. **Perfect Palette.** Let a palette made in Josh's own app (perfectpalette.io) become a Furnace scheme file, and link to the app from the Color tab. Josh decides whether the in-app link is wanted.

## Who wants this and why now

- A r/FurnaceTracker thread, "theme color settings" (relayed by Josh), asked for settings to change the theme colors and said "I wouldn't mind doing more of a light mode." The one reply pointed to Ctrl+, and the Color tab. The feature exists but the asker did not know where it was.
- Perfect Palette checks WCAG AA (4.5:1) and AAA (7.0:1), simulates color blindness, and exports 26+ formats. A Furnace scheme would be one more format, and Furnace would be a new place to find the app.
- Arkos Tracker 3 advertises a themeable interface, so themes are a normal expectation.

## What the fork already has

- **A Color tab with import, export and reset buttons**: `src/gui/settings/allSettings.cpp` around lines 2453–2475. `importColors` and `exportColors` are in `src/gui/settings.cpp` around lines 286–320. A scheme file is plain key=value text written through `DivConfig`.
- **361 color entries**, keyed by their enum names (`#x` at `src/gui/guiConst.cpp:890`). Defaults are the dark theme.
- **Two modes.** `basicColors` defaults to on (`gui.h:2303`, `loadSettings.cpp:422`). In basic mode the tab shows only frame shading, a Dark/Light radio, and the two accent colors (`allSettings.cpp:2479–2489`). The full color list is behind the "Guru mode" checkbox (`allSettings.cpp:2471`).
- **A derivation already exists for the accents.** In basic mode, buttons, tabs, headers and frames come from the two accents (`settings.cpp:823–850`, `pushAccentColors` at `:525`).
- **No bundled presets.** `res/` has no theme or scheme files.

Correction to my earlier notes: I said the Dark/Light choice was hidden behind guru mode. It is not. Only the per-color list is.

## Why this might not be enough

The Dark/Light radio switches the Dear ImGui base style (`settings.cpp:700`), but text, window and frame colors still come from the 361-entry table, whose defaults are the dark ones (`settings.cpp:817` sets text from `uiColors[GUI_COLOR_TEXT]`, default white). Choosing "Light" alone may therefore not give a readable light UI. I could not run the GUI here, so this is unconfirmed. It is the first thing to check.

## Trade-offs and risks

- **Merge cost.** Preset files and a checker are new files, which is cheap. The dropdown touches `allSettings.cpp`, which is busy upstream. Keep it to one `SettingEntry`.
- **Role mapping.** 361 keys need grouping into roles (background, surface, text, muted text, accents, pattern colors, channel colors) before a palette can generate them. The grouping is the real work.
- **Two repos.** A Perfect Palette export format lives in Josh's other project. This repo only needs the scheme file format. Ask Josh before changing anything outside this repo.
- **Idea 014** will take scope colors from the theme, so keep scope and channel colors in the role map.

## Open questions

1. Does "Light" in basic mode give a usable theme today? Which pairs fail?
2. Presets as files copied at install, or built into the binary?
3. How many roles does a palette need to fill 361 keys without looking flat?
4. Which side converts: a new "Furnace scheme" export in Perfect Palette, or an importer in Furnace for an existing format such as W3C Design Tokens? (Recommendation: the Perfect Palette side, to keep the fork small.)
5. Does Josh want an in-app link to perfectpalette.io?

## Spike plan

1. **Run the GUI build** (`build-gui` exists), switch to Light, and screenshot the main windows. *You'll know when* you have a list of unreadable pairs, or proof there are none.
2. **Export the current scheme** and read the file. Sort the 361 keys into roles. *You'll know when* you have a role table with each key assigned once.
3. **Hand-edit a light scheme file** from that table and import it. *You'll know when* the UI is readable from a file alone, with no code change.
4. **Prototype the contrast checker** as a standalone script over a scheme file. *You'll know when* it flags a known-bad scheme (white text on a white window) and passes the default.
5. **Draft the Perfect Palette mapping**: palette roles to scheme keys, written as a short table for Josh to review. *You'll know when* Josh can say yes or no without reading code.

## Decision criteria

- **Build it**: step 3 gives a readable light UI from a file alone. Ship presets as files, add the dropdown, then the checker.
- **Reshape it**: Light already works and only discoverability is weak. Skip the C++ and ship the Perfect Palette export plus a short doc.
- **Drop it**: both are true, so a fork change adds nothing.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\007-color-themes.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: find out whether Furnace's built-in Light option gives a readable theme, work out how a palette becomes a scheme file, and prototype a contrast checker. Do not build beyond the spike; prototype work happens behind a flag or on a branch. Ask Josh before changing anything outside this repo.
```
