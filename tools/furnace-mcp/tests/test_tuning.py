"""Lumatone maps, Scala scales and EDOs to note plus E5xx (ideas/019). The .ltn
fixtures are presets from the Lumatone Editor (BSD-3-Clause, see LICENSE)."""

import math
from pathlib import Path

import pytest

from furnace_mcp import tuning as t
from furnace_mcp.notation import parse_note

PRESETS = Path(__file__).parent / "fixtures" / "lumatone"


def preset(name):
    return t.read_ltn(next(PRESETS.glob(f"*{name}*.ltn")))


def test_read_ltn_skips_disabled_keys():
    assert len(preset("53ET")) == 280
    assert len(preset("31ET")) == 278  # two corner keys are on channel 0
    assert {k.chan for k in preset("12ET")} == {1, 2, 3, 4, 5, 6}


def test_read_ltn_skips_controls(tmp_path):
    f = tmp_path / "x.ltn"
    f.write_text("[Board0]\nKey_0=60\nChan_0=1\nKey_1=61\nChan_1=1\nKTyp_1=2\nKey_2=62\nChan_2=17\n")
    assert t.read_ltn(f) == [t.Key(0, 0, 1, 60)]
    f.write_text("AfterTouchActive=1\n")
    with pytest.raises(t.TuningError):
        t.read_ltn(f)


@pytest.mark.parametrize("name,rule,steps", [
    ("12ET", [0], (2, 1)),  # the channel means nothing: plain MIDI notes
    ("19ET", None, (3, 1)),  # one channel
    ("24ET", None, (4, 1)),
    ("31ET", [31], (5, 2)),  # one period per channel
    ("53ET", [53], (9, 5)),
])
def test_presets_are_isomorphic_under_one_rule(name, rule, steps):
    keys = preset(name)
    assert t.guess_steps_per_channel(keys) == rule
    # a whole tone to the right, a semitone up: the Bosanquet layout
    assert t.layout(keys, rule[0] if rule else 0) == steps


def test_a_wrong_channel_rule_breaks_the_layout():
    assert t.layout(preset("31ET"), 0) is None
    assert t.layout(preset("53ET"), 31) is None


def test_separate_regions_must_share_one_offset():
    keys = preset("31ET")
    assert t.layout(keys, 31) == (5, 2)
    # two keys far from the rest (board 4's corner) moved up one step: every
    # neighbour step is unchanged, but the offset no longer fits them
    far = {(4, 54), (4, 55)}
    moved = [k._replace(note=k.note + 1) if (k.board, k.key) in far else k for k in keys]
    near = [k for k in moved if (k.board, k.key) not in {(4, 53), (4, 52), (4, 48), (4, 49)}]
    assert t.layout(near, 31) is None


def test_read_scl(tmp_path):
    f = tmp_path / "x.scl"
    f.write_text("! meantone\n!\nQuarter-comma meantone, 3 notes\n 3\n!\n193.157\n5/4 ! a third\n2\n")
    s = t.read_scl(f)
    assert s.name.startswith("Quarter-comma")
    assert s.cents[0] == 0 and s.cents[1] == pytest.approx(193.157)
    assert s.cents[2] == pytest.approx(1200 * math.log2(5 / 4))
    assert s.period == pytest.approx(1200)
    f.write_text("x\n3\n100.0\n200.0\n")
    with pytest.raises(t.TuningError):
        t.read_scl(f)


def test_nearest_note_and_detune():
    assert t.nearest(0) == (parse_note("C-4"), 0x80)
    assert t.nearest(1200) == (parse_note("C-5"), 0x80)
    assert t.nearest(-100) == (parse_note("B-3"), 0x80)
    note, e5 = t.nearest(1200 / 31)  # 38.7 cents
    assert note == parse_note("C-4") and e5 == 0x80 + 50
    note, e5 = t.nearest(3 * 1200 / 31)  # 116.1 cents: C# plus 16
    assert note == parse_note("C#4") and e5 == 0x80 + 21
    note, e5 = t.nearest(-1200 / 31)
    assert note == parse_note("C-4") and e5 == 0x80 - 50


def test_quarter_tones_round_down_and_sharpen():
    for k in range(-24, 25, 2):
        note, e5 = t.nearest((k + 1) * 50)  # every odd step of 24-EDO
        assert e5 == 0xC0, k


@pytest.mark.parametrize("n", [12, 19, 24, 31, 41, 53, 72])
def test_every_edo_step_is_within_half_a_unit(n):
    s = t.edo(n)
    for d in range(-3 * n, 3 * n):
        note, e5 = t.nearest(t.cents(s, d))
        assert 0x40 <= e5 <= 0xC0
        played = (note - t.MIDDLE_C) * 100 + (e5 - 0x80) / 1.28
        assert abs(played - t.cents(s, d)) <= 0.5 / 1.28 + 1e-9


def test_key_table_for_the_53_preset():
    keys = preset("53ET")
    table = t.key_table(keys, t.edo(53))
    assert len(table) == 265  # 15 keys repeat another key's channel and note
    assert table[1, 60] == (parse_note("C-4"), 0x80)
    # one channel up is one octave up, on every note
    for (chan, note), (n, e5) in table.items():
        if (chan + 1, note) in table:
            assert table[chan + 1, note] == (n + 12, e5)


def test_in_tune_keys_still_get_e580():
    table = t.key_table(preset("12ET"), t.edo(12))  # guesses: the channel means nothing
    assert {e5 for _, e5 in table.values()} == {0x80}
    assert table[1, 60] == (parse_note("C-4"), 0x80)
    assert table[6, 60] == table[1, 60]


def test_key_table_wants_a_rule_when_none_fits():
    keys = [t.Key(0, 0, 1, 60), t.Key(0, 1, 2, 60), t.Key(0, 2, 1, 61)]
    with pytest.raises(t.TuningError, match="steps_per_channel"):
        t.key_table(keys, t.edo(31))
    assert len(t.key_table(keys, t.edo(31), steps_per_channel=31)) == 3
