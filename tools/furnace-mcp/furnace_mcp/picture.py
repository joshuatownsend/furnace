"""A picture of a render for Claude to look at (ideas/022): one waveform per channel
under the mix, a spectrogram strip under the mix, a line at each order boundary
labelled in hex like the order list, and a time axis. Waveforms share one scale
(full scale fills the row), so a quiet channel looks quiet; clipped columns are red.

The image is drawn with numpy and labelled by ffmpeg's drawtext in Furnace's font,
like the scope video (video.py)."""

import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import song as fsong
from .analysis import read_wav
from .video import _FONT, find_ffmpeg

SILENT = 1e-3  # a channel whose samples spread less than this is left out
CLIP = 0.999  # |x| at or above this counts as clipped (int16 full scale is 0.99997)

_BG = (22, 24, 29)
_PANEL = (30, 33, 40)
_GUIDE = (52, 56, 66)
_WAVE = (110, 190, 255)
_MIX = (235, 235, 235)
_CLIPPED = (255, 60, 60)
_ORDER = (120, 125, 135)
_ORDER_DIM = (70, 74, 84)
_TEXT = "d8dce4"
_DIM_TEXT = "8a909c"

_DURATION = re.compile(r"^- duration: (\d+)\.(\d+)s$", re.M)


def duration(song):
    """Seconds the song plays for, from furnace -info (the engine's own timing walk)."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "song.json"
        src.write_text(json.dumps(song), encoding="utf-8")
        m = _DURATION.search(fsong.info(src))
    if not m:
        raise fsong.FurnaceError("furnace -info printed no duration")
    return int(m.group(1)) + int(m.group(2)) / 1e6


def order_starts(song):
    """Start time in seconds of each order of a one-sub-song song (an excerpt), and
    the total. Each start is the length of the orders before it, timed by furnace,
    so speed, tempo and groove changes on the way are counted. The walk counts a
    speed effect a couple of ticks late, so a start can trail the audio by about
    that much per speed change (33 ms at 60 Hz: about a pixel in a song-long image)."""
    n = fsong.subsong(song, 0).get("orderLength", 1)
    prefixes = [fsong.excerpt(song, 0, 0, k - 1) for k in range(1, n)] + [song]
    with ThreadPoolExecutor(8) as pool:
        times = list(pool.map(duration, prefixes))
    return [0.0] + times[:-1], times[-1]


def _silent(x, moving=1e-4, min_samples=64):
    """True when x only sits at constant levels: idle chips can hold an offset, or
    step to one when the song starts, which peak-to-peak would count as sound.
    A step settles within a few samples (about 16 move by more than 1e-4 in a
    render); a drum hit of 1.5 ms or more moves many more."""
    if len(x) < 2:
        return True
    return int((np.abs(np.diff(x, axis=0)).max(axis=1) > moving).sum()) < min_samples


def _ticks(total, width):
    """Time-axis tick step in seconds: the smallest nice step at least 70 px apart."""
    for step in (0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300):
        if total <= 0 or step / total * width >= 70:
            return step
    return 600


def _clock(t, step):
    if step < 1:
        return f"{t:.2f}".rstrip("0").rstrip(".") + "s"
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def _columns(x, w, clip=CLIP):
    """(top, bottom, clipped) per pixel column of samples x (frames x outputs).
    clip: the level counted as full scale (8-bit audio tops out at 127/128)."""
    hi, lo = x.max(axis=1), x.min(axis=1)
    edges = np.linspace(0, len(hi), w + 1).astype(int)
    edges = np.minimum(edges, len(hi) - 1)
    top = np.maximum.reduceat(hi, edges[:-1])
    bot = np.minimum.reduceat(lo, edges[:-1])
    return top, bot, np.maximum(top, -bot) >= clip


def _draw_wave(img, x0, y0, w, h, x, color, clip=CLIP):
    img[y0:y0 + h, x0:x0 + w] = _PANEL
    mid = y0 + (h - 1) / 2
    img[int(round(mid)), x0:x0 + w] = _GUIDE
    if not len(x):
        return 0.0
    top, bot, clipped = _columns(x, w, clip)
    half = (h - 2) / 2
    y_top = np.clip(np.round(mid - top * half), y0, y0 + h - 1).astype(int)
    y_bot = np.clip(np.round(mid - bot * half), y0, y0 + h - 1).astype(int)
    for c in range(w):
        img[y_top[c]:y_bot[c] + 1, x0 + c] = color
    # a clipped column must show at a glance: one red pixel in a dense waveform
    # doesn't, so each one gets a 3 px band the height of the row
    for c in np.flatnonzero(clipped):
        img[y0:y0 + h, x0 + max(c - 1, 0):x0 + min(c + 2, w)] = _CLIPPED
    return float(np.abs(x).max())


_HEAT = np.array([(0, 0, 4), (40, 11, 84), (101, 21, 110), (159, 42, 99),
                  (212, 72, 66), (245, 125, 21), (250, 193, 39), (252, 255, 164)], float)


def _draw_spectrogram(img, x0, y0, w, h, x, rate, fmin=40.0):
    """Log-frequency spectrogram of the mix, columns aligned with the waveforms.
    Returns [(y, label)] for the frequency ticks."""
    fmax = min(16000.0, rate / 2)
    size = 4096 if rate > 32000 else 2048
    win = np.hanning(size)
    centers = (np.arange(w) + 0.5) * len(x) / w
    # power averaged over the outputs, not the spectrum of their average: some
    # chips put opposite polarity on left and right, which a mono sum cancels
    power = 0.0
    for c in range(x.shape[1]):
        pad = np.concatenate([np.zeros(size // 2), x[:, c], np.zeros(size // 2)])
        frames = np.stack([pad[int(k):int(k) + size] for k in centers])
        power = power + (np.abs(np.fft.rfft(frames * win, axis=1)) / (win.sum() / 2)) ** 2
    db = 10 * np.log10(power / x.shape[1] + 1e-18)
    freqs = np.fft.rfftfreq(size, 1 / rate)
    # each pixel row takes the loudest bin in its slice of log frequency
    rows = np.geomspace(fmax, fmin, h + 1)
    out = np.empty((h, w))
    for r in range(h):
        sel = (freqs <= rows[r]) & (freqs > rows[r + 1])
        if sel.any():
            out[r] = db[:, sel].max(axis=1)
        else:
            k = np.searchsorted(freqs, (rows[r] * rows[r + 1]) ** 0.5)
            out[r] = db[:, min(k, len(freqs) - 1)]
    level = np.clip((out + 90) / 90, 0, 1) * (len(_HEAT) - 1)
    k = np.minimum(level.astype(int), len(_HEAT) - 2)
    t = (level - k)[..., None]
    img[y0:y0 + h, x0:x0 + w] = (_HEAT[k] * (1 - t) + _HEAT[k + 1] * t).astype(np.uint8)
    ticks = []
    for f, name in ((100, "100"), (1000, "1k"), (10000, "10k")):
        if fmin < f < fmax:
            ticks.append((y0 + int(h * np.log(fmax / f) / np.log(fmax / fmin)), name))
    return ticks


def draw(mix_wav, channels, starts, out_png, *, first_order=0, width=1200,
         ffmpeg="ffmpeg"):
    """Draw the picture of one render and write it to out_png.

    channels: [(label, wav)] in channel order. starts: start second of each order
    (from order_starts), first_order the number of the first one. Silent channels
    are left out. Returns {"path", "drawn": [labels], "silent": [labels]}."""
    exe = find_ffmpeg(ffmpeg)
    x, rate = read_wav(mix_wav)
    waves, silent = [], []
    for label, path in channels:
        cx, _ = read_wav(path)
        (silent if _silent(cx) else waves).append((label, cx))
    # the time axis is the WAV's: furnace's timing walk can run a few ticks longer
    total = max(len(x), 1) / rate

    left, right, head, axis = 120, 10, 22, 20
    pw = width - left - right
    mix_h, spec_h = 90, 80
    row_h = int(np.clip(640 // max(1, len(waves)), 26, 60)) if waves else 0
    height = head + mix_h + 4 + spec_h + 6 + len(waves) * (row_h + 2) + axis
    height += height % 2
    img = np.empty((height, width, 3), np.uint8)
    img[:] = _BG

    texts = []  # (x, y, text, size, color)
    y = head
    peak = _draw_wave(img, left, y, pw, mix_h, x, _MIX)
    texts.append((6, y + 4, "mix", 14, _TEXT))
    texts.append((6, y + 22, f"peak {20 * np.log10(max(peak, 1e-9)):.1f} dB", 12, _DIM_TEXT))
    y += mix_h + 4
    for ty, name in _draw_spectrogram(img, left, y, pw, spec_h, x, rate):
        img[ty, left - 6:left] = _ORDER
        texts.append((left - 34, ty - 7, name, 11, _DIM_TEXT))
    texts.append((6, y + 4, "spectrum", 12, _DIM_TEXT))
    y += spec_h + 6
    for label, cx in waves:
        peak = _draw_wave(img, left, y, pw, row_h, cx[:len(x)], _WAVE)
        texts.append((6, y + 2, label, 12, _TEXT))
        if row_h >= 40:
            texts.append((6, y + 18, f"peak {20 * np.log10(max(peak, 1e-9)):.1f} dB", 11, _DIM_TEXT))
        y += row_h + 2
    bottom = y

    # order lines: label every one that has room, dimmer lines for the rest
    last_label = -1e9
    for k, t in enumerate(starts):
        px = left + int(round(t / total * pw))
        if px >= left + pw:
            continue
        roomy = px - last_label >= 22
        img[head - 4:bottom, px] = _ORDER if roomy else _ORDER_DIM
        if roomy:
            texts.append((px + 2, 4, f"{first_order + k:02X}", 12, _TEXT))
            last_label = px
    step = _ticks(total, pw)
    t = 0.0
    while t <= total + 1e-9:
        px = left + int(round(t / total * pw))
        img[bottom:bottom + 5, min(px, width - 1)] = _ORDER
        texts.append((max(left, min(px - 12, width - 40)), bottom + 5, _clock(t, step), 11, _DIM_TEXT))
        t += step
    texts.append((6, 4, "order", 12, _DIM_TEXT))

    out_png = _write(exe, img, texts, out_png)
    return {"path": out_png, "drawn": [label for label, _ in waves],
            "silent": [label for label, _ in silent]}


def _write(exe, img, texts, out_png):
    """Label img with texts [(x, y, text, size, color)] in Furnace's font and write
    it as a PNG through ffmpeg. Returns the path."""
    out_png = Path(out_png)
    height, width = img.shape[:2]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        vf = []
        if _FONT.is_file():
            (td / "font.otf").write_bytes(_FONT.read_bytes())
            for i, (tx, ty, text, size, color) in enumerate(texts):
                (td / f"t{i}.txt").write_text(text, encoding="utf-8")
                vf.append(f"drawtext=fontfile=font.otf:textfile=t{i}.txt:expansion=none:"
                          f"fontcolor=0x{color}:fontsize={size}:x={tx}:y={ty}")
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-i", "-"]
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += ["-frames:v", "1", str(out_png.resolve())]
        p = subprocess.run(cmd, input=np.ascontiguousarray(img).tobytes(), capture_output=True, cwd=td)
        if p.returncode != 0:
            raise fsong.FurnaceError("ffmpeg failed: " + p.stderr.decode("utf-8", "replace").strip()[-2000:])
    return out_png


def _stretch(seg, w):
    """A few cycles resampled to w * 4 points, so a close-up draws as a line."""
    return np.stack([np.interp(np.linspace(0, len(seg) - 1, w * 4), np.arange(len(seg)), seg[:, c])
                     for c in range(seg.shape[1])], axis=1)


def _mark(img, texts, x, y0, y1, label, color=_ORDER):
    img[y0:y1, x] = color
    if label:
        texts.append((x + 3, y0 + 2, label, 11, _DIM_TEXT))


def _draw_bars(img, texts, x0, y0, w, h, groups, floor=-40.0):
    """Harmonic bars: groups [(name, [dB vs the strongest, ...])], side by side,
    0 dB at the top and floor at the bottom."""
    img[y0:y0 + h, x0:x0 + w] = _PANEL
    gw = w // max(1, len(groups))
    for g, (name, levels) in enumerate(groups):
        gx = x0 + g * gw
        texts.append((gx + 6, y0 + 4, name, 12, _TEXT))
        if not levels:
            texts.append((gx + 6, y0 + 22, "too quiet to measure", 11, _DIM_TEXT))
            continue
        top, base = y0 + 36, y0 + h - 18
        bw = (gw - 24) // len(levels)
        for k, db in enumerate(levels):
            y = int(base - (max(db, floor) - floor) / -floor * (base - top))
            bx = gx + 12 + k * bw
            img[y:base, bx + 2:bx + bw - 2] = _WAVE
            texts.append((bx + bw // 2 - 4, base + 2, str(k + 1), 11, _DIM_TEXT))
            texts.append((bx + 2, y - 14, f"{db:g}", 10, _DIM_TEXT))


def draw_note(wav, on, off, f0, report, out_png, *, width=1200, ffmpeg="ffmpeg"):
    """Picture of one previewed note: the whole note with note on and off marked,
    close-ups of about four cycles 20 ms into the attack, 150 ms in, and just
    before the release, then the first 8 harmonics of the attack and the held
    part (report: analyze_note's result)."""
    exe = find_ffmpeg(ffmpeg)
    x, rate = read_wav(wav)
    left, pw = 120, width - 130
    span = max(int(4 / f0 * rate), 16)
    # inside the hold however short it is: 20 ms in, then 150 ms in (or halfway),
    # then 100 ms before note off (or a quarter of the hold)
    hold = max(off - on, 0.0)
    held = min(0.15, hold / 2)
    shots = [("attack +20 ms", on + min(0.02, hold / 4)),
             (f"held +{held * 1000:.0f} ms", on + held),
             ("before release", off - min(0.1, hold / 4))]
    whole_h, shot_h, bars_h, gap = 130, 110, 150, 8
    height = gap + whole_h + 18 + len(shots) * (shot_h + gap) + bars_h + gap
    img = np.empty((height + height % 2, width, 3), np.uint8)
    img[:] = _BG
    texts = []
    y = gap
    total = max(len(x), 1) / rate
    _draw_wave(img, left, y, pw, whole_h, x, _MIX)
    texts.append((6, y + 4, "whole note", 13, _TEXT))
    for t, name in ((on, "note on"), (off, "note off")):
        _mark(img, texts, left + int(min(max(t / total, 0.0), 1.0) * (pw - 1)), y, y + whole_h, name)
    # numbered red ticks: where each close-up below is taken
    for k, (_, t) in enumerate(shots):
        tx = left + int(min(max(t / total, 0.0), 1.0) * (pw - 1))
        _mark(img, texts, tx, y + whole_h - 14, y + whole_h, "", _CLIPPED)
        texts.append((tx + 3, y + whole_h - 15, str(k + 1), 11, _TEXT))
    texts.append((6, y + 22, "red ticks:", 11, _DIM_TEXT))
    texts.append((6, y + 36, "close-ups 1-3", 11, _DIM_TEXT))
    step = _ticks(total, pw)
    t = 0.0
    while t <= total + 1e-9:
        texts.append((left + int(min(max(t / total, 0.0), 1.0) * (pw - 1)), y + whole_h + 2, _clock(t, step), 11, _DIM_TEXT))
        t += step
    y += whole_h + 18
    for k, (name, t) in enumerate(shots):
        a = min(max(int(t * rate), 0), max(len(x) - span, 0))
        seg = x[a:a + span]
        peak = float(np.abs(seg).max()) if len(seg) else 0.0
        # each close-up is scaled to fit: it is there for the wave's shape, and a
        # quiet sustain would otherwise be a flat line
        gain = 0.9 / peak if peak > 1e-4 else 1.0
        _draw_wave(img, left, y, pw, shot_h, _stretch(seg * gain, pw), _WAVE)
        texts.append((6, y + 4, f"{k + 1} {name}", 12, _TEXT))
        # the window is 4 periods of the note played; an arp or a pitch macro can
        # put more (or fewer) cycles in it
        texts.append((6, y + 20, f"{span / rate * 1000:.1f} ms", 11, _DIM_TEXT))
        texts.append((6, y + 36, f"peak {20 * np.log10(max(peak, 1e-9)):.1f} dB", 11, _DIM_TEXT))
        texts.append((6, y + 52, "scaled to fit", 11, _DIM_TEXT))
        y += shot_h + gap
    timbre = (report or {}).get("timbre") or {}
    groups = [(f"{k} harmonics, dB", (timbre.get(k) or {}).get("harmonics_db") or [])
              for k in ("attack", "held") if k in timbre]
    _draw_bars(img, texts, left, y, pw, bars_h, groups or [("harmonics", [])])
    return _write(exe, img, texts, out_png)


def _loop_seam(x, loop, k=48):
    """(audio, index of the join, title, caption): k samples either side of where
    a loop (start, end, mode) wraps, in the order they play. Modes as Furnace's
    sample loop modes: 0 forward (end, then start), 1 backward (down to the start,
    then from the end down), 2 ping-pong (turns around at the end: no jump)."""
    s0, s1, mode = loop
    start, end = x[s0:min(s0 + k, s1)], x[max(s1 - k, s0):s1]
    if mode == 1:
        first, second = start[::-1], end[::-1]
        title, note = "loop seam", "loop start, played backward | its end, as it plays"
    elif mode == 2:
        first, second = end, end[::-1]
        title, note = "loop turnaround", "end of the loop | back the other way (ping-pong: no jump)"
    else:
        first, second = end, start
        title, note = "loop seam", "end of the loop | its start, as it plays"
    return np.concatenate([first, second]), len(first), title, note


def draw_sample(x, loop, span, out_png, *, clip=CLIP, width=1200, ffmpeg="ffmpeg"):
    """Picture of a sample (floats, one channel): the whole sample with the part
    measured shaded and the loop points marked, then a close-up of the loop seam
    (the end of the loop joined to its start, as it plays: a jump there clicks),
    or of the start of the measured part when there is no loop. clip: the level
    drawn as clipped (analysis.full_scale for the sample's depth)."""
    exe = find_ffmpeg(ffmpeg)
    x = np.asarray(x, np.float32).reshape(-1, 1)
    n = max(len(x), 1)
    left, pw = 120, width - 130
    whole_h, close_h, gap = 150, 150, 8
    img = np.empty((gap + whole_h + 18 + close_h + 18 + gap, width, 3), np.uint8)
    img[:] = _BG
    texts = []
    y = gap
    a, b = span
    _draw_wave(img, left, y, pw, whole_h, x, _MIX, clip)
    xa, xb = left + int(a / n * (pw - 1)), left + int(b / n * (pw - 1))
    shade = img[y:y + whole_h, xa:xb + 1]
    shade[:] = (shade * 0.7 + np.array(_WAVE) * 0.3).astype(np.uint8)
    texts.append((6, y + 4, "whole sample", 13, _TEXT))
    texts.append((6, y + 22, "shaded: measured", 11, _DIM_TEXT))
    if loop:
        for pos, name, dy in ((loop[0], "loop start", 0), (loop[1], "loop end", 16)):
            lx = left + int(min(pos, n - 1) / n * (pw - 1))
            _mark(img, texts, lx, y, y + whole_h, "", _CLIPPED)
            # labels go left of a line near the right edge, and the two are staggered
            texts.append((lx + 3 if lx < left + pw - 70 else lx - 62, y + 2 + dy, name, 11, _DIM_TEXT))
    texts.append((left, y + whole_h + 2, "0", 11, _DIM_TEXT))
    texts.append((left + pw - 90, y + whole_h + 2, f"{len(x)} samples", 11, _DIM_TEXT))
    y += whole_h + 18
    if loop:
        seam, cut, title, note = _loop_seam(x, loop)
    else:
        seam, cut = x[a:a + 96], None
        title, note = "measured part", f"samples {a}-{a + len(seam)}"
    if len(seam) >= 2:
        _draw_wave(img, left, y, pw, close_h, _stretch(seam, pw), _WAVE, clip)
        if cut:
            _mark(img, texts, left + int(cut / len(seam) * (pw - 1)), y, y + close_h, "", _CLIPPED)
    texts.append((6, y + 4, title, 13, _TEXT))
    texts.append((left, y + close_h + 2, note, 11, _DIM_TEXT))
    return _write(exe, img, texts, out_png)
