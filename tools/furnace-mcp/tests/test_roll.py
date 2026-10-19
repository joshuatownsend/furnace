"""Piano roll note extraction (ideas/013), without the furnace binary."""

import json

import pytest

from furnace_mcp import roll
from furnace_mcp.notation import MACRO_RELEASE, NOTE_OFF, NOTE_RELEASE

C4, E4, G4 = 108, 112, 115


def make_song(patterns, orders, plen=8):
    """patterns: per channel, a list of row lists ({row: dict}); orders: per channel."""
    pats = []
    for chpats in patterns:
        pats.append([{"rows": [rows.get(r, {}) for r in range(plen)]} for rows in chpats])
    return {
        "songInfo": {"name": "Test"},
        "chips": [{"name": "Test Chip (TC1)", "channels": len(patterns)}],
        "instruments": [{"name": "Lead"}, {"name": "Bass"}],
        "subsongs": [{"orders": orders, "orderLength": len(orders[0]), "patternLength": plen,
                      "highlights": [4, 8], "patterns": pats,
                      "channelData": [{"effectColumns": 1} for _ in patterns]}],
    }


def test_bar_ends_at_next_note_off_and_release_but_not_macro_release():
    rows = {0: {"note": C4, "ins": 0}, 2: {"note": E4}, 3: {"note": MACRO_RELEASE},
            5: {"note": NOTE_OFF}, 6: {"note": G4}, 7: {"note": NOTE_RELEASE}}
    d = roll.notes(make_song([[rows]], [[0]]))
    assert [(n["name"], n["x"], n["len"]) for n in d["notes"]] == [("C-4", 0, 2), ("E-4", 2, 3), ("G-4", 6, 1)]
    assert [(m["x"], m["n"], m["what"]) for m in d["marks"]] == [(3, E4, "macro release")]


def test_bars_carry_across_orders_and_hold_to_the_end():
    d = roll.notes(make_song([[{6: {"note": C4}}, {}]], [[0, 1]]))
    assert d["notes"][0]["len"] == 10  # rows 6..7 of order 0, all 8 of order 1
    assert [o["start"] for o in d["orders"]] == [0, 8]


def test_a_break_in_any_channel_ends_the_order():
    brk = {3: {"effects": [{"code": 0x0D, "value": 0}]}}
    d = roll.notes(make_song([[{0: {"note": C4}}], [brk]], [[0, 0], [0, 0]]), channels=[0])
    assert [(o["start"], o["rows"]) for o in d["orders"]] == [(0, 4), (4, 4)]
    assert [(n["x"], n["len"]) for n in d["notes"]] == [(0, 4), (4, 4)]


def test_missing_patterns_and_rows_are_empty():
    song = make_song([[{0: {"note": C4}}]], [[5]])  # pattern 5 does not exist
    assert roll.notes(song)["notes"] == []


def test_instrument_carries_to_notes_without_one():
    d = roll.notes(make_song([[{0: {"note": C4, "ins": 1}, 4: {"note": E4}}]], [[0]]))
    assert [(n["ins"], n["insName"]) for n in d["notes"]] == [(1, "Bass"), (1, "Bass")]


def test_pitch_effects_mark_the_held_note():
    rows = {0: {"note": C4, "effects": [{"code": 0x00, "value": 0x47}]},
            2: {"effects": [{"code": 0x04, "value": 0x24}]},
            3: {"effects": [{"code": 0x0F, "value": 3}]},  # speed: not a pitch effect
            4: {"effects": [{"code": 0xE5, "value": 0x80}]}}  # detune to center: no change
    d = roll.notes(make_song([[rows]], [[0]]))
    assert [(m["x"], m["n"], m["what"]) for m in d["marks"]] == [(0, C4, "arpeggio 47"), (2, C4, "vibrato 24")]


def test_order_range_and_channel_selection():
    song = make_song([[{0: {"note": C4}}, {0: {"note": E4}}], [{0: {"note": G4}}, {}]],
                     [[0, 1], [0, 1]])
    d = roll.notes(song, order_start=1, channels="1")
    assert d["notes"] == [] and d["channels"][0]["ch"] == 1 and d["orders"][0]["order"] == 1
    with pytest.raises(IndexError):
        roll.notes(song, order_start=2)


def test_custom_channel_name_and_color_win():
    song = make_song([[{}], [{}]], [[0], [0]])
    song["subsongs"][0]["channelData"][1].update(name="Kick", color={"r": 255, "g": 0, "b": 16})
    d = roll.notes(song)
    assert [(c["label"], c["color"]) for c in d["channels"]] == [("TC1 #1", roll.PALETTE[0]), ("Kick", "#ff0010")]


def test_page_embeds_the_data_safely():
    song = make_song([[{0: {"note": C4}}]], [[0]])
    song["songInfo"]["name"] = "</script><b>"
    page = roll.html(roll.notes(song))
    assert "</script><b>" not in page
    blob = page.split("const D=", 1)[1].split(";\nconst NS", 1)[0]
    assert json.loads(blob)["title"] == "</script><b>"
