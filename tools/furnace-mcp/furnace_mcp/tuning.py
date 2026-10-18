"""Microtonal tunings for the Lumatone (ideas/019).

Reads a Lumatone key map (.ltn), a Scala scale (.scl) or an EDO size, and maps
each key (MIDI channel plus note) to the nearest Furnace note plus an E5xx
detune. E5xx works in 1/128 semitone (0.78 cents) under linear pitch, the
default; it stays set until the next E5xx, so every key gets one, E580 (no
detune) included.

Which pitch a key plays isn't in the .ltn: the receiving synth decides. The
rule here is "steps per channel": each MIDI channel up adds that many scale
steps. One period per channel, the default, fits the Lumatone Editor's 31 and
53-EDO presets.
"""

import math
import re
from fractions import Fraction
from pathlib import Path
from typing import NamedTuple

MIDDLE_C = 108  # Furnace's C-4 (notation.py)
BOARDS, KEYS = 5, 56


class TuningError(ValueError):
    pass


class Key(NamedTuple):
    board: int
    key: int
    chan: int  # 1-16
    note: int  # 0-127


class Scale(NamedTuple):
    cents: list  # degree 0 (always 0.0) to the last step below the period
    period: float
    name: str

    @property
    def size(self):
        return len(self.cents)


def read_ltn(path):
    """The note keys of a .ltn file. Keys with a channel outside 1-16 are
    disabled; keys with a KTyp line are faders or other controls."""
    boards, board = {}, None
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        m = re.fullmatch(r"\[Board(\d)\]", line)
        if m:
            board = boards.setdefault(int(m[1]), {})
            continue
        m = re.fullmatch(r"(Key|Chan|KTyp)_(\d+)=(-?\d+)", line)
        if m and board is not None:
            board.setdefault(int(m[2]), {})[m[1]] = int(m[3])
    keys = []
    for b in sorted(boards):
        for k, f in sorted(boards[b].items()):
            if f.get("KTyp", 1) != 1 or not 1 <= f.get("Chan", 0) <= 16 or "Key" not in f:
                continue
            if not 0 <= f["Key"] <= 127:
                raise TuningError(f"board {b} key {k}: note {f['Key']} is not a MIDI note")
            keys.append(Key(b, k, f["Chan"], f["Key"]))
    if not keys:
        raise TuningError(f"{path}: no note keys found (is it a Lumatone .ltn file?)")
    return keys


def _scl_value(tok):
    if "." in tok:
        return float(tok)
    try:
        r = Fraction(tok)
    except (ValueError, ZeroDivisionError):
        raise TuningError(f"bad Scala pitch {tok!r}") from None
    if r <= 0:
        raise TuningError(f"bad Scala ratio {tok!r}")
    return 1200 * math.log2(r)


def read_scl(path):
    """A Scala .scl file: description, note count, then one pitch per line in
    cents (has a '.') or as a ratio. The last pitch is the period."""
    lines = [l.strip() for l in Path(path).read_text(errors="replace").splitlines()]
    lines = [l for l in lines if not l.startswith("!")]
    if len(lines) < 2:
        raise TuningError(f"{path}: too short for a Scala file")
    name = lines[0]
    try:
        count = int(lines[1].split()[0])
    except (ValueError, IndexError):
        raise TuningError(f"{path}: line 2 should be the note count, not {lines[1]!r}") from None
    values = [_scl_value(l.split()[0]) for l in lines[2:] if l][:count]
    if count < 1 or len(values) < count:
        raise TuningError(f"{path}: says {count} notes, has {len(values)}")
    period = values[-1]
    if period <= 0:
        raise TuningError(f"{path}: the period {period:.2f} cents isn't positive")
    return Scale([0.0] + values[:-1], period, name)


def edo(n):
    if not 1 <= n <= 1200:
        raise TuningError(f"an EDO needs 1 to 1200 steps, not {n}")
    return Scale([k * 1200 / n for k in range(n)], 1200.0, f"{n}-EDO")


def degree(chan, note, steps_per_channel, ref_chan=1, ref_note=60):
    return note - ref_note + (chan - ref_chan) * steps_per_channel


def cents(scale, deg):
    """Cents above degree 0."""
    return (deg // scale.size) * scale.period + scale.cents[deg % scale.size]


def nearest(c, ref=MIDDLE_C):
    """Nearest Furnace note to c cents above ref, and the E5xx value that makes
    up the rest. A quarter tone exactly between two notes goes to the lower
    one, sharpened (E5C0), so spellings stay the same."""
    base = math.ceil(c / 100 - 0.5 - 1e-9)
    e5 = 0x80 + math.floor((c - base * 100) * 1.28 + 0.5)
    note = ref + base
    if not 0 <= note <= 179:
        raise TuningError(f"{c:.1f} cents from C-4 is outside Furnace's notes")
    return note, e5


def key_table(keys, scale, steps_per_channel=None, ref_chan=1, ref_note=60, ref=MIDDLE_C):
    """{(chan, note): (furnace note, E5xx value)} for every key. ref_chan and
    ref_note name the key that plays degree 0, at Furnace note ref."""
    if steps_per_channel is None:
        steps_per_channel = scale.size
    out = {}
    for k in keys:
        d = degree(k.chan, k.note, steps_per_channel, ref_chan, ref_note)
        out[k.chan, k.note] = nearest(cents(scale, d), ref)
    return out


# Key positions, from the Lumatone Editor's BoardGeometry.cpp (56-key boards,
# BSD-3-Clause, Lumatone Inc.). x runs along the shallow diagonal, y along the
# right-upward one.
_ROWS = [(0, 1), (2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12), (13, 14, 15, 16, 17, 18),
         (19, 20, 21, 22, 23, 24), (25, 26, 27, 28, 29, 30), (31, 32, 33, 34, 35, 36),
         (37, 38, 39, 40, 41, 42), (43, 44, 45, 46, 47, 48), (49, 50, 51, 52, 53), (54, 55)]
_ROW_OFFSETS = [-4, -3, -3, -2, -2, -1, -1, 0, 0, 2, 5]


def coordinates(board, key):
    for r, row in enumerate(_ROWS):
        if key in row:
            return 7 * board + row.index(key) + _ROW_OFFSETS[r], -2 * board - r
    raise TuningError(f"no key {key} on a 56-key board")


def layout(keys, steps_per_channel):
    """(right step, upward step) in scale steps if the map is isomorphic under
    this channel rule, or None: every key must sit at a * x + b * y + c."""
    at = {coordinates(k.board, k.key): degree(k.chan, k.note, steps_per_channel) for k in keys}
    right = {at[x + 1, y] - d for (x, y), d in at.items() if (x + 1, y) in at}
    up = {at[x, y + 1] - d for (x, y), d in at.items() if (x, y + 1) in at}
    if len(right) != 1 or len(up) != 1:
        return None
    return right.pop(), up.pop()


def guess_steps_per_channel(keys, most=128):
    """The channel rules (0 to most) that make the map isomorphic. A map on
    one channel fits every rule, so it returns None; no fit returns []."""
    if len({k.chan for k in keys}) == 1:
        return None
    return [s for s in range(most + 1) if layout(keys, s)]
