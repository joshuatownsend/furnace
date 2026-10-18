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


def defaults(source=None):
    """{key: (r, g, b, a)} with floats 0..1, in the order guiConst.cpp lists them."""
    text = Path(source or _REPO / "src" / "gui" / "guiConst.cpp").read_text(encoding="utf-8")
    out = {}
    for key, nums in _COLOR_DEF.findall(text):
        out[key] = tuple(float(v.strip().rstrip("f")) for v in nums.split(","))
    if not out:
        raise ValueError(f"no color definitions found in {source or 'guiConst.cpp'}")
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
