"""The render picture (ideas/022): order lines at the right times, clipped columns,
and the PNG itself. Furnace and ffmpeg tests skip when those aren't available."""

import shutil
from pathlib import Path

import numpy as np
import pytest

from furnace_mcp import picture, song as fsong
from furnace_mcp.analysis import read_wav

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "demos" / "genesis" / "All Good Times.fur"

try:
    fsong.furnace_exe()
    HAVE_FURNACE = True
except fsong.FurnaceError:
    HAVE_FURNACE = False
needs_furnace = pytest.mark.skipif(not HAVE_FURNACE, reason="furnace binary not built")
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def test_columns_mark_clipping():
    x = np.zeros((1000, 2), np.float32)
    x[100:110, 0] = 1.0  # one output at full scale
    x[600:610, 1] = -0.5
    top, bot, clipped = picture._columns(x, 10)
    assert clipped.tolist() == [False, True] + [False] * 8
    assert bot[6] == pytest.approx(-0.5) and top[6] == 0


def test_silent_ignores_offsets_but_not_quiet_sound():
    x = np.full((44100, 2), 0.035, np.float32)
    x[:3000] = 0  # an idle chip stepping to its offset as the song starts
    assert picture._silent(x)
    t = np.arange(44100) / 44100
    tone = 0.005 * np.sin(2 * np.pi * 220 * t)  # about -46 dBFS
    assert not picture._silent(np.stack([tone, tone], axis=1))


def _one_note_per_order():
    """Three orders of the demo where only channel 0 plays: one note at row 0 of
    each order. Order 1 sets both speeds to 2 (09xx and 0Fxx), so its rows are
    shorter than order 0's; order 2 keeps that speed."""
    song = fsong.excerpt(fsong.load(DEMO), 0, 0, 2)
    sub = fsong.subsong(song, 0)
    nchans = len(sub["orders"])
    for o in range(3):
        fsong.set_order(song, 0, o, {ch: 0x7F for ch in range(nchans)} | {0: 0x70 + o})
        fsong.write_rows(song, 0, 0, 0x70 + o, 0, "A-4 0C 7F" + (" 0902 0F02" if o == 1 else "") + "\n...\n...\nOFF")
    fsong.write_rows(song, 0, 1, 0x7F, 0, "\n".join(["..."] * sub.get("patternLength", 64)))
    return song


def _onsets(x, rate, threshold=0.02, gap_s=0.05):
    """Times where the signal rises above threshold after gap_s of quiet."""
    loud = np.abs(x).max(axis=1) > threshold
    out, quiet_since = [], -1e9
    for i in np.flatnonzero(loud):
        if i - quiet_since > gap_s * rate:
            out.append(i / rate)
        quiet_since = i
    return out


@needs_furnace
def test_order_starts_follow_a_speed_change(tmp_path):
    song = _one_note_per_order()
    starts, total = picture.order_starts(song)
    (_, wav), = fsong.render(song, tmp_path / "x.wav")
    x, rate = read_wav(wav)
    assert total == pytest.approx(len(x) / rate, abs=0.05)
    # the demo's speeds are 4 and 3, so order 1 at speed 2 takes 2/3.5 as long
    assert starts[2] - starts[1] == pytest.approx((starts[1] - starts[0]) * 2 / 3.5, rel=0.02)
    onsets = _onsets(x, rate)
    assert len(onsets) == 3, onsets
    # furnace's walk counts the speed effect two ticks late (33 ms at 60 Hz)
    for start, onset in zip(starts, onsets):
        assert onset == pytest.approx(start, abs=0.04)


@needs_furnace
@needs_ffmpeg
def test_draw_writes_a_png(tmp_path):
    song = _one_note_per_order()
    starts, _ = picture.order_starts(song)
    (_, mix), = fsong.render(song, tmp_path / "mix.wav")
    files = fsong.render(song, tmp_path / "ch.wav", per_channel=True, channels=[0, 9])
    r = picture.draw(mix, [(f"ch{i}", f) for i, f in files], starts, tmp_path / "pic.png",
                     first_order=4)
    assert r["drawn"] == ["ch0"] and r["silent"] == ["ch9"]
    data = r["path"].read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") == 1200
