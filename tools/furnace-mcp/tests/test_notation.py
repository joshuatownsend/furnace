import pytest

from furnace_mcp import notation


@pytest.mark.parametrize("n,name", [
    (108, "C-4"), (60, "C-0"), (117, "A-4"), (0, "c_5"), (1, "c+5"), (59, "b_1"),
    (179, "B-9"), (-1, "..."), (253, "OFF"), (254, "==="), (255, "REL"),
])
def test_note_names_round_trip(n, name):
    assert notation.note_name(n) == name
    assert notation.parse_note(name) == n


def test_row_round_trip():
    row = {"note": 108, "ins": 12, "vol": 127, "effects": [{"code": 0xEC, "value": 1}]}
    text = notation.format_row(row, 2)
    assert text == "C-4 0C 7F EC01 ...."
    assert notation.parse_row(text) == row


def test_empty_and_partial_rows():
    assert notation.format_row({}, 1) == "... .. .. ...."
    assert notation.parse_row("... .. .. ....") == {}
    assert notation.parse_row("") == {}
    assert notation.parse_row("OFF") == {"note": 253}
    # an effect cell with only a code keeps the empty value
    assert notation.parse_row("... .. .. 04..") == {"effects": [{"code": 4, "value": -1}]}


def test_raw_rows_are_shown_but_not_writable():
    assert notation.format_row({"rawFreq": 1234}, 0).startswith("RAW")
    with pytest.raises(notation.NotationError):
        notation.parse_row("RAW .. ..")


@pytest.mark.parametrize("bad", ["H-4", "E#4", "C-x", "C-4 0G", "C-4 .. .. EC1", "C-4 100"])
def test_bad_input_is_rejected(bad):
    with pytest.raises(notation.NotationError):
        notation.parse_row(bad)
