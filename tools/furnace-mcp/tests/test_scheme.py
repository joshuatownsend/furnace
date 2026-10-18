"""Color schemes: the contrast check and the Light preset (ideas/007)."""

from furnace_mcp import scheme


def test_light_preset_is_readable():
    assert scheme.contrast_report(scheme.light_scheme()) == []


def test_light_preset_sets_every_color():
    name, settings, colors = scheme.presets()[1]
    assert name == "Light" and settings == {"guiColorsBase": 1}
    assert list(colors) == list(scheme.defaults())


def test_preset_header_is_up_to_date():
    # regenerate with: python -m furnace_mcp.scheme presets
    assert scheme.PRESET_HEADER.read_text(encoding="utf-8") == scheme.preset_header()


def test_contrast_check_flags_unreadable_text():
    colors = scheme.defaults()
    colors["GUI_COLOR_TEXT"] = (0.05, 0.05, 0.05, 1.0)  # black text on the black window
    low = {(fg, bg) for fg, bg, _ in scheme.contrast_report(colors)}
    assert ("GUI_COLOR_TEXT", "GUI_COLOR_FRAME_BACKGROUND") in low


def test_dark_defaults_have_two_dim_effect_colors():
    # upstream's own defaults: the time and misc effect colors are below AA on black
    low = [(fg, round(r, 2)) for fg, _, r in scheme.contrast_report(scheme.defaults())]
    assert low == [("GUI_COLOR_PATTERN_EFFECT_TIME", 3.28), ("GUI_COLOR_PATTERN_EFFECT_MISC", 3.72)]


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
