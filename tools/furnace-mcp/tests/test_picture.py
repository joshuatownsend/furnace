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


def test_silent_keeps_a_lone_short_hit():
    x = np.zeros((44100, 1), np.float32)
    t = np.arange(882) / 44100  # a 20 ms hit, inside one 2048-sample block
    x[20000:20882, 0] = 0.3 * np.sin(2 * np.pi * 180 * t) * np.exp(-t * 150)
    assert not picture._silent(x)
    assert not picture._silent(x[19900:21000])  # shorter than a block


def test_spectrogram_survives_antiphase_stereo():
    t = np.arange(44100) / 44100
    s = 0.5 * np.sin(2 * np.pi * 440 * t)
    out = []
    for x in (np.stack([s, s], axis=1), np.stack([s, -s], axis=1)):
        img = np.zeros((80, 200, 3), np.uint8)
        picture._draw_spectrogram(img, 0, 0, 200, 80, x, 44100)
        out.append(int(img.sum()))
    assert out[1] == out[0]  # opposite polarity looks the same, not blank


def test_loop_seam_follows_the_loop_mode():
    x = np.arange(100, dtype=np.float32).reshape(-1, 1)
    fwd, cut, title, _ = picture._loop_seam(x, (20, 80, 0), k=3)
    assert fwd[:, 0].tolist() == [77, 78, 79, 20, 21, 22] and cut == 3 and title == "loop seam"
    back, cut, _, _ = picture._loop_seam(x, (20, 80, 1), k=3)
    assert back[:, 0].tolist() == [22, 21, 20, 79, 78, 77]
    pp, cut, title, _ = picture._loop_seam(x, (20, 80, 2), k=3)
    assert pp[:, 0].tolist() == [77, 78, 79, 79, 78, 77] and title == "loop turnaround"


@needs_ffmpeg
def test_note_picture_with_a_short_hold_and_no_release(tmp_path):
    import wave
    rate = 44100
    t = np.arange(int(0.2 * rate)) / rate
    x = (0.3 * np.sin(2 * np.pi * 262 * t) * (t > 0.1)).astype(np.float32)
    with wave.open(str(tmp_path / "n.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    # note on at 0.1 s, off at the very end: one row held, no release rendered
    out = picture.draw_note(tmp_path / "n.wav", 0.1, 0.2, 262.0, {}, tmp_path / "n.png")
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_clipped_runs_count_flat_tops_only():
    from furnace_mcp import analysis
    level = analysis.full_scale(8)
    x = np.zeros(100)
    x[10] = level  # a lone peak at full scale: not clipping
    x[50:54] = -1.0  # a flat top
    assert analysis.clipped_runs(x, level) == 4
    alt = np.tile([level, -1.0], 50)  # straight from rail to rail: no flat top
    assert analysis.clipped_runs(alt, level) == 0
    assert analysis.clipped_runs(np.full(10, -127 / 128), level) == 0  # the rail is -128
    _, _, clipped = picture._columns(np.full((10, 1), -127 / 128), 1, (level, -1.0))
    assert not clipped[0]
    assert level == 127 / 128 and analysis.full_scale(16) == 32767 / 32768
