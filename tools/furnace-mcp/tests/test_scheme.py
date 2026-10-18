"""Color schemes: the contrast check and the Light preset (ideas/007)."""

import re

from furnace_mcp import scheme


def test_light_preset_is_readable():
    # basic mode (buttons, tabs, headers from the accents) and guru mode alike
    light = scheme.light_scheme()
    assert scheme.contrast_report(light, settings={"guiColorsBase": "1"}) == []
    assert scheme.contrast_report(light, settings={"guiColorsBase": "1", "basicColors": "0"}) == []


def test_basic_mode_checks_the_colors_drawn_from_the_accents():
    light = scheme.light_scheme()
    light["GUI_COLOR_ACCENT_PRIMARY"] = (0.0, 0.0, 0.0, 1.0)  # black buttons under dark text
    low = {(fg, bg) for fg, bg, _ in scheme.contrast_report(light, settings={"guiColorsBase": "1"})}
    assert ("GUI_COLOR_TEXT", "GUI_COLOR_BUTTON") in low
    assert scheme.contrast_report(light, settings={"guiColorsBase": "1", "basicColors": "0"}) == []


def test_light_preset_sets_every_color():
    name, settings, colors = scheme.presets()[1]
    assert name == "Light" and settings == {"guiColorsBase": 1}
    assert list(colors) == list(scheme.defaults())


def test_preset_header_is_up_to_date():
    # regenerate with: python -m furnace_mcp.scheme presets
    assert scheme.PRESET_HEADER.read_text(encoding="utf-8") == scheme.preset_header()


def test_gui_checks_the_same_pairs():
    # settings.cpp's drawContrastCheck and CONTRAST_PAIRS must check the same
    src = (scheme._REPO / "src" / "gui" / "settings.cpp").read_text(encoding="utf-8")
    body = src[src.index("void FurnaceGUI::drawContrastCheck"):]

    def table(name):
        start = body.index(name)
        return body[start + len(name):body.index("};", start)]

    # the widget and order rows: text color, then the name of each background
    widgets = []
    for line in table("pairs={").splitlines():
        names = re.findall(r"GUI_COLOR_\w+", re.sub(r"uiColors\[\w+\]", "", line))  # names, not lookups
        if names:
            widgets.append((names[0], names[1:]))
    assert widgets == [(fg, [bg[0] for bg in bgs]) for fg, bgs in scheme.CONTRAST_PAIRS[:10]]
    assert re.findall(r"GUI_COLOR_\w+", table("patternRowOverlays[]={")) == scheme._ROW_OVERLAYS
    stacks = re.findall(r"\{(GUI_COLOR_\w+),(GUI_COLOR_\w+|-1)\}", table("patternCellStacks[][2]={"))
    assert [tuple(k for k in s if k != "-1") for s in stacks] == scheme._CELL_STACKS
    assert re.findall(r"GUI_COLOR_\w+", table("rowText[]={")) == scheme._ROW_TEXT
    assert re.findall(r"GUI_COLOR_\w+", table("patternText[]={")) == scheme._PATTERN_TEXT
    assert scheme.CONTRAST_PAIRS[10:] == ([(k, scheme._GUTTER_BGS) for k in scheme._ROW_TEXT]
                                          + [(k, scheme._CELL_BGS) for k in scheme._PATTERN_TEXT])



def test_contrast_check_flags_unreadable_text():
    colors = scheme.defaults()
    colors["GUI_COLOR_TEXT"] = (0.05, 0.05, 0.05, 1.0)  # black text on the black window
    low = {(fg, bg) for fg, bg, _ in scheme.contrast_report(colors)}
    assert ("GUI_COLOR_TEXT", "GUI_COLOR_FRAME_BACKGROUND") in low


def test_dark_defaults_fail_on_pressed_widgets_and_the_hovered_cursor():
    # upstream's own defaults: white text on pressed buttons, inputs and headers,
    # and twelve pattern colors, worst on the light blue hovered cursor
    low = [(fg[10:], bg[10:], round(r, 2)) for fg, bg, r in scheme.contrast_report(scheme.defaults())]
    assert low[:3] == [("TEXT", "BUTTON_ACTIVE", 3.58), ("TEXT", "WIDGET_BACKGROUND_ACTIVE", 3.0),
                       ("TEXT", "IMGUI_HEADER_ACTIVE", 3.0)]
    assert [(fg[8:], bg) for fg, bg, _ in low[3:]] == [(k, "PATTERN_CURSOR_HOVER") for k in (
        "INS", "INS_ERROR", "VOLUME_MAX", "VOLUME_HALF", "VOLUME_MIN", "EFFECT_INVALID", "EFFECT_VOLUME",
        "EFFECT_SONG", "EFFECT_TIME", "EFFECT_SPEED", "EFFECT_SYS_SECONDARY", "EFFECT_MISC")]



def test_contrast_ratio_matches_wcag():
    assert round(scheme.contrast_ratio((0, 0, 0), (1, 1, 1)), 2) == 21.0
    assert round(scheme.contrast_ratio((0.5, 0.5, 0.5), (1, 1, 1)), 2) == 3.98


def test_oklab_round_trip():
    for c in [(0.2, 0.4, 0.6), (1.0, 1.0, 0.0), (0.0, 0.0, 0.0), (0.9, 0.1, 0.5)]:
        assert all(abs(a - b) < 1e-4 for a, b in zip(scheme.from_oklab(*scheme.to_oklab(c)), c))


def test_light_keeps_hue_and_inverts_lightness():
    dark, light = scheme.defaults(), scheme.light_scheme()
    # the window turns light, ink turns dark, piano keys stay as they are
    assert scheme.luminance(scheme.flatten(light, ("GUI_COLOR_FRAME_BACKGROUND", "GUI_COLOR_BACKGROUND"))) > 0.8
    assert scheme.luminance(light["GUI_COLOR_PATTERN_VOLUME_MAX"]) < 0.2
    assert light["GUI_COLOR_PIANO_KEY_BOTTOM"] == dark["GUI_COLOR_PIANO_KEY_BOTTOM"]
    g = light["GUI_COLOR_PATTERN_VOLUME_MAX"]
    assert g[1] > g[0] and g[1] > g[2]  # still green
