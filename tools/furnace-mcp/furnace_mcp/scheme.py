"""Furnace color schemes: the defaults in guiConst.cpp and the files that
Settings > Color > Export writes.

A scheme file is a DivConfig: key=value lines, each color an ImU32 stored as a
signed int (0xAABBGGRR). Furnace fills a key the file leaves out with its
default, and so does read() here.
"""

import re
from pathlib import Path

from .song import furnace_config_dir

_REPO = Path(__file__).resolve().parents[3]
_COLOR_DEF = re.compile(r'D\((GUI_COLOR_\w+),_N\("[^"]*"\),ImVec4\(([^)]*)\)\)')


def defaults():
    """{key: (r, g, b, a)} with floats 0..1, in the order guiConst.cpp lists them.
    (The tests pin this parse against gui.h, so a format change fails loudly.)"""
    text = (_REPO / "src" / "gui" / "guiConst.cpp").read_text(encoding="utf-8")
    out = {}
    for key, nums in _COLOR_DEF.findall(text):
        out[key] = tuple(float(v.strip().rstrip("f")) for v in nums.split(","))
    if not out:
        raise ValueError("no color definitions found in guiConst.cpp")
    return out


def unpack(v):
    """ImU32 (as Furnace stores it, possibly negative) -> (r, g, b, a) floats."""
    v = int(v) & 0xFFFFFFFF
    return tuple(((v >> s) & 255) / 255 for s in (0, 8, 16, 24))


def pack(rgba):
    """(r, g, b, a) floats -> the signed int Furnace writes (ImGui rounding)."""
    r, g, b, a = (min(255, max(0, int(c * 255 + 0.5))) for c in rgba)
    v = r | g << 8 | b << 16 | a << 24
    return v - (1 << 32) if v >= 1 << 31 else v


def read(path):
    """The scheme in a file (an exported scheme or furnace.cfg), over the defaults:
    returns (colors, settings) where settings holds the non-color keys."""
    colors = defaults()
    settings = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        if key in colors:
            colors[key] = unpack(value)
        else:
            settings[key] = value
    return colors, settings


def over(top, bottom):
    """top composited over an opaque bottom color: (r, g, b)."""
    a = top[3]
    return tuple(t * a + b * (1 - a) for t, b in zip(top[:3], bottom[:3]))


def current():
    """The colors the Furnace GUI uses now (its furnace.cfg), else the defaults."""
    cfg = furnace_config_dir() / "furnace.cfg"
    return read(cfg)[0] if cfg.is_file() else defaults()


# --- contrast (WCAG 2) ----------------------------------------------------

AA = 4.5  # WCAG AA for normal text

_WINDOW = ("GUI_COLOR_FRAME_BACKGROUND", "GUI_COLOR_BACKGROUND")
_PATTERN = ("GUI_COLOR_PATTERN_BG",) + _WINDOW

# (text color, background layers from the top down). The C++ check in
# settings.cpp (FurnaceGUI::lowContrastColors) checks the same pairs, with the
# widget backgrounds taken from the applied ImGui style so basic mode counts.
CONTRAST_PAIRS = [
    ("GUI_COLOR_TEXT", _WINDOW),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_FRAME_BACKGROUND_POPUP",) + _WINDOW),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_MENU_BAR",) + _WINDOW),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_BUTTON",) + _WINDOW),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_WIDGET_BACKGROUND",) + _WINDOW),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_IMGUI_HEADER",) + _WINDOW),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_TAB_ACTIVE",) + _WINDOW),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_TITLE_BACKGROUND_ACTIVE", "GUI_COLOR_BACKGROUND")),
    ("GUI_COLOR_TEXT", ("GUI_COLOR_TABLE_HEADER",) + _WINDOW),
    ("GUI_COLOR_ORDER_ROW_INDEX", _WINDOW),
    ("GUI_COLOR_PATTERN_ROW_INDEX", _PATTERN),
    ("GUI_COLOR_PATTERN_ACTIVE", _PATTERN),
    ("GUI_COLOR_PATTERN_ACTIVE", ("GUI_COLOR_PATTERN_CURSOR",) + _PATTERN),
    ("GUI_COLOR_PATTERN_INS", _PATTERN),
    ("GUI_COLOR_PATTERN_VOLUME_MAX", _PATTERN),
    ("GUI_COLOR_PATTERN_VOLUME_HALF", _PATTERN),
] + [(f"GUI_COLOR_PATTERN_EFFECT_{k}", _PATTERN) for k in
     ("INVALID", "PITCH", "VOLUME", "PANNING", "SONG", "TIME", "SPEED",
      "SYS_PRIMARY", "SYS_SECONDARY", "MISC")]


def luminance(rgb):
    """WCAG relative luminance of an sRGB color (floats 0..1)."""
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb[:3]]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def flatten(colors, layers):
    """The opaque color you see through a stack of colors (top first)."""
    out = colors[layers[-1]][:3]
    for key in reversed(layers[:-1]):
        out = over(colors[key], out)
    return out


def contrast_report(colors, threshold=AA):
    """[(text key, background key, ratio)] for the pairs below threshold."""
    low = []
    for fg, layers in CONTRAST_PAIRS:
        bg = flatten(colors, layers)
        ratio = contrast_ratio(over(colors[fg], bg), bg)
        if ratio < threshold:
            low.append((fg, layers[0], ratio))
    return low


# --- the Light preset ------------------------------------------------------
# Furnace's colors are drawn for a dark window. A light theme can't just flip
# lightness: a key that is a surface (buttons, cursors, scope backgrounds) must
# stay light under dark text, while ink (text, note and effect colors, waves)
# must go dark. Both keep their hue. Some keys keep their color outright.

_SURFACE = re.compile(
    r"GUI_COLOR_(BACKGROUND|FRAME_BACKGROUND\w*|HEADER|TITLE_\w+|MENU_BAR|SCROLL_BACKGROUND|"
    r"DOCKING_EMPTY|TABLE_HEADER|BUTTON\w*|TAB|TAB_HOVER|TAB_ACTIVE|TAB_UNFOCUSED\w*|"
    r"IMGUI_HEADER\w*|RESIZE_GRIP\w*|WIDGET_BACKGROUND\w*|CHECKBOX_BACKGROUND_ACTIVE|TEXT_SELECTION|"
    r"TOGGLE_\w+|EDITING\w*|OSC_BG\d|FM_ALG_BG|SAMPLE_BG|SAMPLE_LOOP|SAMPLE_TIME_BG|"
    r"PATTERN_CURSOR|PATTERN_CURSOR_HOVER|PATTERN_CURSOR_ACTIVE|PATTERN_SELECTION\w*|"
    r"PAT_MANAGER_NULL|PIANO_BACKGROUND|CLOCK_BEAT_LOW|PATCHBAY_PORTSET|PATCHBAY_CONNECTION_BG|"
    r"MEMORY_BG|MEMORY_FREE|MEMORY_PADDING|CHANNEL_BG|SCROLL\w*)$")
_KEEP = re.compile(
    r"GUI_COLOR_(MODAL_BACKDROP|BORDER_SHADOW|FM_BORDER_SHADOW_\w+|NAV_WIN_BACKDROP|PIANO_KEY_\w+)$")
LIGHT_OVERRIDES = {
    "GUI_COLOR_TEXT": (0.08, 0.08, 0.1, 1.0),
    "GUI_COLOR_TEXT_DISABLED": (0.42, 0.42, 0.45, 1.0),
    "GUI_COLOR_ACCENT_PRIMARY": (0.45, 0.66, 0.98, 1.0),
    "GUI_COLOR_ACCENT_SECONDARY": (0.55, 0.72, 0.98, 1.0),
}


def _srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin_to_srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def to_oklab(rgb):
    r, g, b = (_srgb_to_lin(c) for c in rgb[:3])
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _oklab_to_lin(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def from_oklab(L, a, b):
    """sRGB for an OKLab color, losing chroma (not lightness or hue) until it fits."""
    lo, hi = 0.0, 1.0
    if all(-1e-6 <= c <= 1 + 1e-6 for c in _oklab_to_lin(L, a, b)):
        lo = 1.0
    else:
        for _ in range(24):
            mid = (lo + hi) / 2
            if all(-1e-6 <= c <= 1 + 1e-6 for c in _oklab_to_lin(L, a * mid, b * mid)):
                lo = mid
            else:
                hi = mid
    return tuple(min(1.0, max(0.0, _lin_to_srgb(min(1.0, max(0.0, c)))))
                 for c in _oklab_to_lin(L, a * lo, b * lo))


def _relight(rgba, surface):
    L, a, b = to_oklab(rgba)
    # surfaces: dark -> near white, mid -> light tint; ink: light -> dark,
    # dark -> light (a subtle line stays subtle)
    L2 = 0.985 - 0.3 * L if surface else 1.046 - 0.643 * L
    return min(1.0, max(0.0, L2)), a, b


def _darken_to(lab, bg, target):
    """The lightest version of an OKLab color (same hue) with contrast >= target on bg."""
    L, a, b = lab
    if contrast_ratio(from_oklab(L, a, b), bg) >= target:
        return L
    lo, hi = 0.0, L
    for _ in range(30):
        mid = (lo + hi) / 2
        if contrast_ratio(from_oklab(mid, a, b), bg) >= target:
            lo = mid
        else:
            hi = mid
    return lo


def light_scheme(dark=None):
    """The Light preset, derived from the dark defaults (see the note above)."""
    dark = dark or defaults()
    out = {}
    for key, rgba in dark.items():
        if key in LIGHT_OVERRIDES:
            out[key] = LIGHT_OVERRIDES[key]
        elif _KEEP.match(key):
            out[key] = rgba
        elif _SURFACE.match(key):
            out[key] = (*from_oklab(*_relight(rgba, True)), rgba[3])
    dark_bg = flatten(dark, _WINDOW)
    light_bg = flatten(out, _WINDOW)
    for key, rgba in dark.items():
        if key in out:
            continue
        lab = _relight(rgba, False)
        # ink you could read on the dark window stays readable on the light one
        if rgba[3] == 1.0 and contrast_ratio(rgba, dark_bg) >= 3.0:
            lab = (_darken_to(lab, light_bg, AA + 0.1), *lab[1:])
        out[key] = (*from_oklab(*lab), rgba[3])
    return {k: out[k] for k in dark}  # in guiConst.cpp order


# --- the presets Furnace ships (src/gui/colorPresets.h) ---------------------

PRESET_HEADER = _REPO / "src" / "gui" / "colorPresets.h"
_LICENSE = (_REPO / "src" / "gui" / "scaling.h").read_text(encoding="utf-8").split("*/")[0] + "*/\n"


def presets():
    """[(name, settings, colors)]: Dark is the defaults, so it sets only the base
    style; every other preset sets every color, so nothing of the scheme it
    replaces is left over."""
    return [("Dark (default)", {"guiColorsBase": 0}, {}),
            ("Light", {"guiColorsBase": 1}, light_scheme())]


def preset_header():
    """The C++ source of colorPresets.h."""
    out = [_LICENSE,
           "// generated by tools/furnace-mcp: python -m furnace_mcp.scheme presets",
           "// (change scheme.py and regenerate; don't edit this file)", "",
           "#ifndef _COLOR_PRESETS_H", "#define _COLOR_PRESETS_H", "",
           "struct FurnaceGUIColorPreset {", "  const char* name;", "  const char* config;", "};", "",
           "static const FurnaceGUIColorPreset guiColorPresets[]={"]
    for name, settings, colors in presets():
        lines = [f"{k}={v}" for k, v in settings.items()]
        lines += [f"{k}={pack(c)}" for k, c in colors.items()]
        out.append(f"  {{_N(\"{name}\"),")
        out += [f'    "{line}\\n"' for line in lines[:-1]]
        out.append(f'    "{lines[-1]}\\n"}},')
    out += ["};", "", "#endif", ""]
    return "\n".join(out)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Furnace color scheme tools.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="list text colors below WCAG AA contrast in a scheme file")
    c.add_argument("file", type=Path, nargs="?", help="exported scheme or furnace.cfg (default: built-in dark)")
    p = sub.add_parser("presets", help="regenerate src/gui/colorPresets.h")
    p.add_argument("--check", action="store_true", help="fail if the header is out of date instead")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        colors = read(a.file)[0] if a.file else defaults()
        low = contrast_report(colors)
        for fg, bg, ratio in low:
            print(f"{fg} on {bg}: {ratio:.2f}:1")
        print(f"{len(low)} of {len(CONTRAST_PAIRS)} pairs below {AA}:1")
        return 1 if low else 0
    text = preset_header()
    if a.check:
        if PRESET_HEADER.read_text(encoding="utf-8") != text:
            print(f"{PRESET_HEADER} is out of date: run python -m furnace_mcp.scheme presets")
            return 1
        return 0
    PRESET_HEADER.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {PRESET_HEADER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
