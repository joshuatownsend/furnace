"""Compact tracker text for Furnace pattern rows.

A row is written the way Furnace shows it:

    C-4 0C 7F EC01 ....

note, instrument (hex), volume (hex), then one 4-character effect cell per
effect column (2 hex digits code, 2 hex digits value). Empty cells are dots.

Note numbering follows Furnace, not MIDI: 0..179 covers C-5..B-9, so 60 is
C-0 and middle C (C-4) is 108. Negative octaves are lowercase, as in
Furnace: "c_5" is C at octave -5 and "c+5" is C# at octave -5.
"""

import re

NOTE_OFF = 253
NOTE_RELEASE = 254
MACRO_RELEASE = 255

_UPPER = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]
_LOWER = ["c_", "c+", "d_", "d+", "e_", "f_", "f+", "g_", "g+", "a_", "a+", "b_"]
_SPECIAL = {NOTE_OFF: "OFF", NOTE_RELEASE: "===", MACRO_RELEASE: "REL"}
_SPECIAL_IN = {v: k for k, v in _SPECIAL.items()}

LEGEND = (
    "Row format: NOTE II VV EEXX... (hex). NOTE is C-4/C#4 (C-4 = middle C), "
    "lowercase c_1/c+1 for negative octaves, OFF = note off, === = note release, "
    "REL = macro release, ... = empty. II = instrument, VV = volume, "
    "EEXX = effect code EE with value XX. Dots mean empty."
)


class NotationError(ValueError):
    pass


def note_name(n):
    if n is None or n == -1:
        return "..."
    if n in _SPECIAL:
        return _SPECIAL[n]
    if not 0 <= n <= 179:
        return "???"
    octave = n // 12 - 5
    if octave < 0:
        return f"{_LOWER[n % 12]}{-octave}"
    return f"{_UPPER[n % 12]}{octave}"


_NOTE_RE = re.compile(r"^([A-Ga-g])([-#_+])(\d)$")


def parse_note(tok):
    if tok in ("...", "---"):
        return -1
    up = tok.upper()
    if up in _SPECIAL_IN:
        return _SPECIAL_IN[up]
    m = _NOTE_RE.match(tok)
    if not m:
        raise NotationError(f"bad note {tok!r} (expected e.g. C-4, F#3, c_1, OFF, ===, REL, ...)")
    letter, acc, octv = m.groups()
    negative = letter.islower()
    sharp = acc in "#+"
    name = letter.upper() + ("#" if sharp else "-")
    if name not in _UPPER:
        raise NotationError(f"bad note {tok!r}: {letter.upper()} has no sharp")
    octave = -int(octv) if negative else int(octv)
    n = (octave + 5) * 12 + _UPPER.index(name)
    if not 0 <= n <= 179:
        raise NotationError(f"note {tok!r} out of range (c_5 to B-9)")
    return n


def _hex2(v):
    return ".." if v is None or v < 0 else f"{v:02X}"


def _parse_hex2(tok, what):
    if tok == "..":
        return -1
    try:
        v = int(tok, 16)
    except ValueError:
        raise NotationError(f"bad {what} {tok!r} (expected 2 hex digits or ..)")
    if not 0 <= v <= 255:
        raise NotationError(f"{what} {tok!r} out of range")
    return v


def format_row(row, effect_cols):
    """Format one JSON row ({} or a dict with note/ins/vol/effects)."""
    row = row or {}
    if "rawFreq" in row:
        note = "RAW"
    else:
        note = note_name(row.get("note", -1))
    cells = [note, _hex2(row.get("ins", -1)), _hex2(row.get("vol", -1))]
    fx = row.get("effects", [])
    for k in range(effect_cols):
        e = fx[k] if k < len(fx) else {}
        code, val = e.get("code", -1), e.get("value", -1)
        cells.append(_hex2(code) + _hex2(val) if (code >= 0 or val >= 0) else "....")
    return " ".join(cells)


def parse_row(text):
    """Parse one row of tracker text into a JSON row dict (empty dict if blank)."""
    toks = text.split()
    if not toks:
        return {}
    if toks[0].upper() == "RAW":
        raise NotationError("raw frequency rows cannot be written")
    row = {}
    note = parse_note(toks[0])
    if note != -1:
        row["note"] = note
    if len(toks) > 1:
        ins = _parse_hex2(toks[1], "instrument")
        if ins != -1:
            row["ins"] = ins
    if len(toks) > 2:
        vol = _parse_hex2(toks[2], "volume")
        if vol != -1:
            row["vol"] = vol
    effects = []
    for tok in toks[3:]:
        if len(tok) != 4:
            raise NotationError(f"bad effect {tok!r} (expected 4 characters like EC01 or ....)")
        code = _parse_hex2(tok[:2], "effect code")
        val = _parse_hex2(tok[2:], "effect value")
        effects.append({"code": code, "value": val})
    if len(effects) > 8:
        raise NotationError("at most 8 effect columns")
    while effects and effects[-1] == {"code": -1, "value": -1}:
        effects.pop()
    if effects:
        row["effects"] = effects
    return row
