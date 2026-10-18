# 007 — Color themes and a Perfect Palette link

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat e9988cf35..HEAD -- src/gui/settings.cpp src/gui/settings/allSettings.cpp src/gui/settings/loadSettings.cpp src/gui/guiConst.cpp`.

- **Status**: BUILT (presets, contrast check and Light hint, 2026-10-17; see Spike results)
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

## Spike results (2026-10-17)

**Question 1: Light alone is not a light theme.** Confirmed from the code (`settings.cpp`, `applyUISettings`): the Dark/Light radio picks the Dear ImGui base style and how basic mode derives buttons, tabs and headers from the two accents. Window, popup and text colors still come from the 361-key table, whose defaults are dark (window black at 85%, text white). So "Light" gives light buttons on dark windows. That is why the Reddit asker found nothing.

**Build it** (decision criteria): a scheme file alone makes the UI light, so the fork now ships:

- **Presets in Settings > Color**: Dark (default) and Light buttons, with a confirmation, since a preset replaces every color. They are built into the binary (`src/gui/colorPresets.h`), not installed as files (question 2). A preset keeps the user's guru-mode and frame-shading choices.
- **The Dark/Light radio offers the matching preset** when the choice doesn't match the window color (with the same confirmation). That is the discoverability fix for the Reddit question: choosing Light now leads to a light UI.
- **A contrast check** in the Color tab: 31 text colors, each against every background it is drawn on, reported at its worst. That means UI text on windows, popups, the menu bar and the title bar, and on buttons, inputs, headers and tabs in their normal, hovered and pressed states; order numbers on the playing order and the song loop; and pattern text (notes, highlighted notes, instrument with its warning and error colors, volume, every effect) on plain, highlighted, play-head and edited rows, under the selection and the cursor, hovered or not, and their combinations. The dimmed placeholder colors are left out on purpose. Each is held to WCAG AA (4.5:1); a failing color shows a sample of the text on its worst background and the ratio. It reads the applied style, so basic mode's derived colors count. Upstream's own dark defaults fail on pressed buttons, inputs and headers (white on bright blue, 3.0 to 3.6:1) and for eleven pattern colors under the light blue hovered cursor (down to 1.04:1).
- **Pressed widgets in Light basic mode** now derive at half saturation and 85% value instead of upstream's half value, so dark text stays readable while a button is held or an input is being typed into.
- **`python -m furnace_mcp.scheme check FILE`** runs the same check over an exported scheme file (question 4's prototype), deriving basic mode's colors from the accents as Furnace does; `... presets` regenerates the header.

**Question 3: how many roles.** The Light preset is generated, not hand-edited (`light_scheme` in `tools/furnace-mcp/furnace_mcp/scheme.py`). Of the 361 keys, 61 are surfaces (backgrounds, buttons, cursors, selections), 11 keep their color (piano keys, backdrops, shadows), 4 are set by hand (text, disabled text, the two accents), and 285 are ink: hue-coded colors for pattern effects, instrument types, macros, files, channels, memory and scopes. Surfaces and ink keep their hue and get their lightness inverted in OKLab. Ink that was readable on the dark window is then darkened, along its own hue, until it passes AA on the light window and on every light pattern background. Ink that was meant to be subtle (grid lines, the note-off dot) stays subtle. The Light preset passes every check, in basic and guru mode.

**Questions 4 and 5: Perfect Palette.** The same split is the mapping a palette needs. A Perfect Palette export only has to supply about eight roles:

| Palette role | Scheme keys (each `GUI_COLOR_` + ...) |
|---|---|
| Background | `BACKGROUND`, `FRAME_BACKGROUND*`, `MENU_BAR`, `TITLE_*`, `TABLE_HEADER`, scope, sample, piano and memory backgrounds |
| Surface (controls) | `BUTTON*`, `WIDGET_BACKGROUND*`, `TAB*`, `IMGUI_HEADER*`, `PATTERN_SELECTION*` |
| Text | `TEXT`, `CHANNEL_FG`, `PATTERN_ACTIVE*`, `CLOCK_TEXT` |
| Muted text | `TEXT_DISABLED`, `PATTERN_INACTIVE*`, `PATTERN_ROW_INDEX*`, `ORDER_ROW_INDEX` |
| Accent 1 and 2 | `ACCENT_PRIMARY`, `ACCENT_SECONDARY` (basic mode derives buttons, tabs and headers from these), `CHECK_MARK`, `SLIDER_GRAB*`, `NAV_HIGHLIGHT`, `TEXT_LINK`, `PATTERN_CURSOR*` |
| Warning, error | `WARNING`, `ERROR`, `DESTRUCTIVE`, `PATTERN_STATUS_WARNING`, `PATTERN_STATUS_ERROR` |
| Hue-coded ink (about 250 keys) | Keep Furnace's hues; set the lightness for the palette's background, as `light_scheme` does |

My recommendation stands: the converter belongs in Perfect Palette as a "Furnace scheme" export (key=value lines, colors as signed 0xAABBGGRR ints, as `scheme.pack` writes them). I changed nothing outside this repo and added no in-app link to perfectpalette.io. Both are Josh's call.

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
