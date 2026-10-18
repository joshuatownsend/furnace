"""Oscilloscope videos: one scope per channel, in time with the song (ideas/014).

Renders the mix and one WAV per channel with the furnace CLI, draws each
channel's waveform into a grid with numpy, and pipes the frames to ffmpeg with
the mix as the soundtrack. ffmpeg must be on PATH (or pass ffmpeg=).

Usage: python -m furnace_mcp.video SONG OUT.mp4 [--orders 0-3] [--size 1920x1080]
"""

import argparse
import math
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import scheme as fscheme
from . import song as fsong
from .analysis import read_wav

_FONT = fscheme._REPO / "res" / "fonts" / "IBMPlexSans-Regular.otf"  # Furnace's UI font
SILENT = 1e-3  # a channel that moves less than this is left out


def parse_size(text):
    """'1920x1080' -> (1920, 1080)."""
    try:
        width, height = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise ValueError(f"size must look like 1920x1080, not {text!r}") from None
    return width, height


def layout(n, width, height, aspect=2.0):
    """(columns, rows) for n scopes: panels nearest `aspect` wide, then fewest empty cells."""
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        shape = (width / cols) / (height / rows)
        score = (abs(math.log(shape / aspect)), cols * rows - n)
        if best is None or score < best[0]:
            best = (score, cols, rows)
    return best[1], best[2]


def grid_cells(n, cols, rows, width, height):
    """(x, y, w, h) for n panels, row by row; a short last row stretches to the full width."""
    ys = np.linspace(0, height, rows + 1).astype(int)
    cells = []
    for r in range(rows):
        k = min(cols, n - r * cols)
        xs = np.linspace(0, width, k + 1).astype(int)
        cells += [(int(xs[c]), int(ys[r]), int(xs[c + 1] - xs[c]), int(ys[r + 1] - ys[r])) for c in range(k)]
    return cells


def rising_edges(x, hysteresis):
    """Indices where x crosses zero upward after having dipped below -hysteresis,
    so noise riding on the zero line doesn't trigger."""
    up = np.flatnonzero((x[:-1] < 0) & (x[1:] >= 0)) + 1
    if len(up) < 2:
        return up
    # keep a crossing only if the signal went below -hysteresis since the last one
    lows = np.minimum.reduceat(x[:up[-1]], np.r_[0, up[:-1]])
    return up[lows < -hysteresis]


def window_start(edges, center, size, n):
    """Start of the display window around sample `center`: aligned so a rising edge
    sits in the middle (steady scopes), or plain centered when none is near."""
    start = center - size // 2
    if len(edges):
        i = np.searchsorted(edges, center)
        near = [edges[j] for j in (i - 1, i) if 0 <= j < len(edges)]
        k = min(near, key=lambda e: abs(e - center))
        if abs(k - center) <= size // 2:
            start = k - size // 2
    return int(min(max(start, 0), max(n - size, 0)))


def _rgb(c):
    return np.array([round(v * 255) for v in c[:3]], dtype=np.uint8)


def _wave_span(seg, w, h, scale, thick):
    """Per pixel column, the first and last row the waveform covers."""
    n = len(seg)
    if n >= 2 * w:
        edges = np.linspace(0, n, w + 1).astype(int)
        top = np.maximum.reduceat(seg, edges[:-1])
        bot = np.minimum.reduceat(seg, edges[:-1])
    else:
        top = bot = np.interp(np.linspace(0, n - 1, w), np.arange(n), seg)
    mid = (h - 1) / 2
    y_top, y_bot = mid - top * scale, mid - bot * scale
    # join each column to the previous one so steep edges stay connected
    lo = np.minimum(y_top, np.r_[y_top[0], y_bot[:-1]]) - thick
    hi = np.maximum(y_bot, np.r_[y_bot[0], y_top[:-1]]) + thick
    return (np.clip(np.ceil(lo), 0, h - 1).astype(np.intp),
            np.clip(np.floor(hi), 0, h - 1).astype(np.intp))


def _span_pixels(lo, hi):
    """(rows, cols) of every pixel in the column spans lo..hi, touching only those
    pixels (a full-panel mask costs three times as much per frame)."""
    hi = np.maximum(hi, lo)
    n = hi - lo + 1
    cols = np.repeat(np.arange(len(lo)), n)
    rows = np.repeat(lo - np.cumsum(n) + n, n) + np.arange(n.sum())
    return rows, cols


class Scope:
    def __init__(self, label, samples, color):
        self.label = label
        self.rgb = _rgb(color)
        samples -= samples.mean()  # in place: one full-length copy per channel is plenty
        self.peak = float(np.abs(samples).max())
        self.x = samples
        self.edges = rising_edges(samples, 0.1 * self.peak)


def _shown_channels(song, sub_index):
    """Channels not hidden from Furnace's Channel Oscilloscope."""
    data = fsong.subsong(song, sub_index).get("channelData") or []
    return [ch for ch in range(len(fsong.channel_labels(song)))
            if ch >= len(data) or (data[ch].get("show") or {}).get("chanOsc", True)]


def _render(song, channels, workdir):
    """(mix WAV, [(channel, WAV)]), rendered by several furnace processes at once:
    a per-channel render plays the whole song once per channel, so it is the slow part."""
    workers = max(1, min(len(channels), (os.cpu_count() or 2) // 2))
    groups = [channels[k::workers] for k in range(workers)]
    with ThreadPoolExecutor(workers + 1) as pool:
        mix = pool.submit(fsong.render, song, workdir / "mix.wav")
        parts = pool.map(lambda k: fsong.render(song, workdir / f"g{k}.wav", per_channel=True,
                                                channels=groups[k]), range(workers))
        # an extended channel's operators come back as one file under the first
        # operator, from each group that asked for one of them: keep one
        files = sorted(dict(f for part in parts for f in part).items())
        return mix.result()[0][1], files


def _channel_scopes(song, files, colors, color_mode, sub_index):
    labels = fsong.channel_labels(song)
    data = (fsong.subsong(song, sub_index).get("channelData") or [])
    chip_of = [ci for ci, chip in enumerate(song.get("chips") or []) for _ in range(chip.get("channels", 0))]
    palette = [colors[f"GUI_COLOR_MULTI_INS_{k}"] for k in range(1, 8)]
    scopes = []
    for ch, path in files:
        cd = data[ch] if ch < len(data) else {}
        x, rate = read_wav(path)
        mono = x.mean(axis=1)
        if np.ptp(mono) < SILENT:
            continue  # silent, or a constant offset (nothing to draw)
        if color_mode == "channel":
            c = cd.get("color")
            color = ((c["r"] / 255, c["g"] / 255, c["b"] / 255, 1.0) if c
                     else palette[chip_of[ch] % len(palette)] if ch < len(chip_of) else palette[0])
        else:
            color = colors["GUI_COLOR_OSC_WAVE"]
        label = cd.get("name") or (labels[ch] if ch < len(labels) else f"ch{ch}")
        scopes.append(Scope(label, mono, color))
    return scopes, rate


def make_video(song, out, *, sub_index=0, order_start=0, order_end=None,
               width=1920, height=1080, fps=60, window_ms=40.0, colors=None,
               color_mode="mono", labels=True, ffmpeg="ffmpeg", crf=18, preset="medium"):
    """Write an mp4 (H.264 + AAC, yuv420p: what YouTube expects) with one scope per
    audible channel. colors: a scheme dict from scheme.read/defaults (default: the
    colors Furnace uses now, see scheme.current). color_mode: "mono" (OSC_WAVE for
    every channel) or "channel" (each channel's custom color, else one color per chip).
    Returns a dict describing what was made."""
    if color_mode not in ("mono", "channel"):
        raise ValueError(f"color_mode must be mono or channel, not {color_mode!r}")
    if not (64 <= width <= 7680 and 64 <= height <= 4320) or width % 2 or height % 2:
        raise ValueError(f"size {width}x{height}: width and height must be even, 64 to 7680x4320")
    if not 1 <= fps <= 240:
        raise ValueError(f"fps must be 1 to 240, not {fps}")
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")
    exe = shutil.which(ffmpeg) or (ffmpeg if Path(ffmpeg).is_file() else None)
    if not exe:
        raise FileNotFoundError(f"ffmpeg not found ({ffmpeg}); install it or pass its path")
    colors = colors or fscheme.current()
    out = Path(out).resolve()
    sub = fsong.subsong(song, sub_index)
    end = sub.get("orderLength", 1) - 1 if order_end is None else order_end
    ex = fsong.excerpt(song, sub_index, order_start, end)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shown = _shown_channels(song, sub_index)
        if not shown:
            raise ValueError("every channel is hidden from the Channel Oscilloscope")
        mix, files = _render(ex, shown, td)
        scopes, rate = _channel_scopes(song, files, colors, color_mode, sub_index)
        if not scopes:
            raise ValueError("every channel is silent in that range; nothing to draw")
        nsamp = min(len(s.x) for s in scopes)
        nframes = math.ceil(nsamp / rate * fps)
        size = max(2, int(rate * window_ms / 1000))

        cols, rows = layout(len(scopes), width, height)
        cells = grid_cells(len(scopes), cols, rows, width, height)

        bg = fscheme.over(colors["GUI_COLOR_FRAME_BACKGROUND"], colors["GUI_COLOR_BACKGROUND"])
        base = np.empty((height, width, 3), dtype=np.uint8)
        base[:] = _rgb(bg)
        guide = _rgb(fscheme.over(colors["GUI_COLOR_OSC_GUIDE"], bg))
        border = _rgb(fscheme.over(colors["GUI_COLOR_BORDER"], bg))
        for x0, y0, w, h in cells:
            base[y0 + h // 2, x0:x0 + w] = guide
            base[y0:y0 + h, x0] = border
            base[y0, x0:x0 + w] = border
        thick = max(1.0, height / 720)

        vf = []
        if labels and _FONT.is_file():
            shutil.copyfile(_FONT, td / "font.otf")
            text = fscheme.over((*colors["GUI_COLOR_TEXT"][:3], 0.75), bg)
            hexcol = "".join(f"{round(v * 255):02x}" for v in text)
            for i, (s, (x0, y0, w, h)) in enumerate(zip(scopes, cells)):
                (td / f"label{i}.txt").write_text(s.label, encoding="utf-8")
                vf.append(f"drawtext=fontfile=font.otf:textfile=label{i}.txt:expansion=none:"
                          f"fontcolor=0x{hexcol}:fontsize={max(12, h // 12)}:x={x0 + h // 24}:y={y0 + h // 24}")
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
               "-i", str(mix)]
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, cwd=td)
        # draw the next frame while a writer thread hands the last one to ffmpeg
        free, full = queue.Queue(), queue.Queue()
        for _ in range(3):
            free.put(np.empty_like(base))
        broken = threading.Event()

        def write():
            while (frame := full.get()) is not None:
                if not broken.is_set():
                    try:
                        proc.stdin.write(memoryview(frame))
                    except (BrokenPipeError, OSError):
                        broken.set()  # ffmpeg quit; its stderr says why
                free.put(frame)

        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        for f in range(nframes):
            if broken.is_set():
                break
            frame = free.get()
            frame[:] = base
            center = int(f / fps * rate)
            for s, (x0, y0, w, h) in zip(scopes, cells):
                h_in = h - 2
                start = window_start(s.edges, center, size, nsamp)
                py, px = _span_pixels(*_wave_span(s.x[start:start + size], w - 1, h_in,
                                                  0.45 * h_in / s.peak, thick))
                frame[y0 + 1 + py, x0 + 1 + px] = s.rgb
            full.put(frame)
        full.put(None)
        writer.join()
        try:
            proc.stdin.close()
        except OSError:
            pass
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise fsong.FurnaceError(f"ffmpeg failed: {err.strip()[-2000:]}")

    return {"path": out, "bytes": out.stat().st_size, "seconds": nsamp / rate, "frames": nframes,
            "grid": (cols, rows), "channels": [s.label for s in scopes],
            "labels": bool(vf)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Make an oscilloscope video of a Furnace song.")
    ap.add_argument("song", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--orders", help="order range, e.g. 0-3 (hex like the order list; default all)")
    ap.add_argument("--subsong", type=int, default=0)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--window-ms", type=float, default=40.0, help="time shown in each scope")
    ap.add_argument("--scheme", type=Path,
                    help="color scheme file (Settings > Color > Export; default: Furnace's current colors)")
    ap.add_argument("--color", choices=("mono", "channel"), default="mono")
    ap.add_argument("--no-labels", action="store_true")
    a = ap.parse_args(argv)
    start, end = 0, None
    if a.orders:
        lo, _, hi = a.orders.partition("-")
        start, end = int(lo, 16), int(hi or lo, 16)
    width, height = parse_size(a.size)
    colors = fscheme.read(a.scheme)[0] if a.scheme else None
    r = make_video(fsong.load(a.song), a.out, sub_index=a.subsong, order_start=start, order_end=end,
                   width=width, height=height, fps=a.fps, window_ms=a.window_ms, colors=colors,
                   color_mode=a.color, labels=not a.no_labels)
    print(f"wrote {r['path']} ({r['bytes']} bytes, {r['seconds']:.1f} s, {r['frames']} frames, "
          f"{r['grid'][0]}x{r['grid'][1]} grid: {', '.join(r['channels'])})")


if __name__ == "__main__":
    main()
