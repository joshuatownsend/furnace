"""Scope drawing and color scheme parsing, without the furnace binary or ffmpeg."""

import re

import numpy as np
import pytest

from furnace_mcp import scheme, video


def test_layout_prefers_wide_panels_without_gaps():
    assert video.layout(1, 1920, 1080) == (1, 1)
    assert video.layout(4, 1920, 1080) == (2, 2)
    assert video.layout(16, 1920, 1080) == (4, 4)


def test_short_last_row_fills_the_width():
    cells = video.grid_cells(5, 2, 3, 1920, 1080)
    assert cells[-1] == (0, 720, 1920, 360)
    assert sum(w * h for _, _, w, h in cells) == 1920 * 1080


def test_rising_edges_ignore_noise_on_the_zero_line():
    rate, hz = 44100, 441
    t = np.arange(rate // 10)
    x = np.sin(2 * np.pi * hz * t / rate) + 0.02 * np.sin(2 * np.pi * 9000 * t / rate)
    edges = video.rising_edges(x, 0.1)
    # one per period (the ripple moves a crossing by a sample at most), none extra
    assert np.all(np.abs(np.diff(edges) - rate // hz) <= 1)


def test_window_centers_on_the_nearest_edge():
    edges = np.array([100, 200, 300])
    assert video.window_start(edges, 190, 50, 1000) == 175  # edge 200 in the middle
    assert video.window_start(edges, 600, 50, 1000) == 575  # no edge near: plain center
    assert video.window_start(edges, 5, 50, 1000) == 0      # clamped to the start


def test_span_pixels_cover_exactly_the_spans():
    rng = np.random.default_rng(1)
    lo = rng.integers(0, 50, 40)
    hi = lo + rng.integers(0, 20, 40)
    rows, cols = video._span_pixels(lo, hi)
    got = np.zeros((80, 40), bool)
    got[rows, cols] = True
    want = (np.arange(80)[:, None] >= lo) & (np.arange(80)[:, None] <= hi)
    assert (got == want).all()


def test_wave_span_stays_inside_the_panel():
    seg = np.concatenate([np.full(100, -1.0), np.full(100, 1.0)])
    lo, hi = video._wave_span(seg, 50, 40, 30.0, 1.5)
    assert lo.min() >= 0 and hi.max() <= 39
    assert hi[25] - lo[25] > 30  # the step joins top to bottom


def test_extended_operators_export_once():
    ext = video.fsong.EXT_OPERATOR
    types = [0, 0, ext, ext, ext, ext, 0, 1]
    assert video._export_units({"subsongs": [{}]}, 0, types) == [0, 1, 2, 6, 7]
    # a hidden channel is left out; any shown operator keeps its extended channel
    hidden = {"subsongs": [{"channelData": [{"show": {"chanOsc": False}}, {}, {"show": {"chanOsc": False}}]}]}
    assert video._export_units(hidden, 0, types) == [1, 2, 6, 7]


def test_bad_options_fail_before_rendering():
    with pytest.raises(ValueError, match="color_mode"):
        video.make_video({}, "x.mp4", color_mode="rainbow")
    with pytest.raises(ValueError, match="fps"):
        video.make_video({}, "x.mp4", fps=0)


def test_scheme_defaults_match_furnace():
    d = scheme.defaults()
    gui_h = (scheme._REPO / "src" / "gui" / "gui.h").read_text(encoding="utf-8")
    enum = gui_h[gui_h.index("enum FurnaceGUIColors"):gui_h.index("GUI_COLOR_MAX")]
    assert list(d) == re.findall(r"\b(GUI_COLOR_\w+)\s*[,=]", enum)  # every color, in order
    assert d["GUI_COLOR_TEXT"] == (1.0, 1.0, 1.0, 1.0)
    assert d["GUI_COLOR_FRAME_BACKGROUND"] == (0.0, 0.0, 0.0, 0.85)


def test_scheme_pack_matches_imgui():
    # ImGui packs 0xAABBGGRR; Furnace stores it as a signed int
    assert scheme.pack((1.0, 1.0, 1.0, 1.0)) == -1
    assert scheme.pack((1.0, 0.0, 0.0, 1.0)) == -16776961
    for c in [(0.2, 0.4, 0.6, 0.8), (0.0, 1.0, 0.5, 0.0)]:
        assert all(abs(a - b) < 1 / 255 for a, b in zip(scheme.unpack(scheme.pack(c)), c))


def test_scheme_file_overrides_only_its_keys(tmp_path):
    f = tmp_path / "light.cfgc"
    f.write_text("!DIV_CONFIG_START!\nconfigVersion=232\nguiColorsBase=1\n"
                 f"GUI_COLOR_TEXT={scheme.pack((0, 0, 0, 1))}\n", encoding="utf-8")
    colors, settings = scheme.read(f)
    assert colors["GUI_COLOR_TEXT"] == (0, 0, 0, 1)
    assert colors["GUI_COLOR_BACKGROUND"] == scheme.defaults()["GUI_COLOR_BACKGROUND"]
    assert settings == {"configVersion": "232", "guiColorsBase": "1"}



def test_ffmpeg_path_is_absolute(tmp_path, monkeypatch):
    # ffmpeg runs from a temporary directory, so a relative path must be resolved first
    fake = tmp_path / "bin" / "ffmpeg.exe"
    fake.parent.mkdir()
    fake.write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    assert video.find_ffmpeg("bin/ffmpeg.exe") == str(fake.resolve())
    with pytest.raises(FileNotFoundError):
        video.find_ffmpeg("bin/nothing.exe")
