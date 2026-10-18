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
    # settings.cpp's drawContrastCheck and CONTRAST_PAIRS must check the same pairs
    src = (scheme._REPO / "src" / "gui" / "settings.cpp").read_text(encoding="utf-8")
    body = src[src.index("void FurnaceGUI::drawContrastCheck"):]

    def table(name):
        start = body.index(name)
        return re.findall(r"GUI_COLOR_\w+", body[start + len(name):body.index("};", start)])

    widgets = re.findall(r"\{(GUI_COLOR_\w+),\{\{(GUI_COLOR_\w+),", body[:body.index("};", body.index("pairs={"))])
    assert widgets == [(fg, bgs[0][0]) for fg, bgs in scheme.CONTRAST_PAIRS[:10]]
    assert table("patternRowOverlays[]={") == scheme._ROW_OVERLAYS
    assert table("patternCellOverlays[]={") == scheme._CELL_OVERLAYS
    assert table("rowText[]={") == scheme._ROW_TEXT
    assert table("patternText[]={") == scheme._PATTERN_TEXT
    assert scheme.CONTRAST_PAIRS[10:] == ([(k, scheme._ROW_BGS) for k in scheme._ROW_TEXT]
                                          + [(k, scheme._CELL_BGS) for k in scheme._PATTERN_TEXT])


def test_contrast_check_flags_unreadable_text():
    colors = scheme.defaults()
    colors["GUI_COLOR_TEXT"] = (0.05, 0.05, 0.05, 1.0)  # black text on the black window
    low = {(fg, bg) for fg, bg, _ in scheme.contrast_report(colors)}
    assert ("GUI_COLOR_TEXT", "GUI_COLOR_FRAME_BACKGROUND") in low


def test_dark_defaults_fail_under_the_hovered_cursor():
    # upstream's own defaults: eleven pattern colors are below AA, worst of all on
    # the light blue hovered cursor
    low = [(fg[18:], bg[18:], round(r, 2)) for fg, bg, r in scheme.contrast_report(scheme.defaults())]
    assert low == [
        ("INS", "CURSOR_HOVER", 2.69), ("INS_ERROR", "CURSOR_HOVER", 1.55), ("VOLUME_MAX", "CURSOR_HOVER", 4.37),
        ("VOLUME_HALF", "CURSOR_HOVER", 2.42), ("EFFECT_INVALID", "CURSOR_HOVER", 1.5),
        ("EFFECT_VOLUME", "CURSOR_HOVER", 4.37), ("EFFECT_SONG", "CURSOR_HOVER", 1.5),
        ("EFFECT_TIME", "CURSOR_HOVER", 1.04), ("EFFECT_SPEED", "CURSOR_HOVER", 1.91),
        ("EFFECT_SYS_SECONDARY", "CURSOR_HOVER", 4.46), ("EFFECT_MISC", "CURSOR_HOVER", 1.09)]



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
