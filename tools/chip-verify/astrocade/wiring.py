"""Driver wiring check for the Bally Astrocade: render a test song through Furnace
and compare every note with the chip's formula.

A tone's frequency is clock / (2 * (master + 1) * period), where period is an
integer from 1 to 256. Each measured note must sit within MAX_CENTS of an integer
period's exact frequency (this checks the driver's register writes and the core
together), and that period must be the one nearest the note or one step away.
Furnace's pitch table builds one octave and shifts it with truncating integer
maths, so some notes land one period off; that is shared by every period-based
chip (the SN76489 too) and is listed, not failed.

Also checked: volume steps (the chip mixes linearly), the 10xx master oscillator
effect, 11xx vibrato (the pitch alternates between two master periods) and 12xx
noise modulation (the pitch turns random), all three tone channels, the noise channel, and that the song loads by
its JSON file ID and survives a .fur save and reload.

Usage: python wiring.py [path/to/furnace.exe]
Exit code 0 and a final PASS line when every check passes.
"""

import json
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
FURNACE = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "build-gui" / "Release" / "furnace.exe"

CLOCK = 315e6 / 88 / 2              # COLOR_NTSC is 315/88 MHz
DEFAULT_MASTER = 0x1F
FILE_ID = 0x1000
ROWS_ON, ROWS_OFF = 5, 1            # at speed 6 and 60 Hz a row is 0.1 s
MAX_CENTS = 1.0                     # measured vs. the period actually played
LEVEL_DB = 0.5                      # tolerance for volume steps


def note_hz(n):
    return 440.0 * 2 ** ((n - 117) / 12)


def note_name(n):
    return ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"][n % 12] + str(n // 12 - 5)


def build_segments():
    segs = []  # (channel, note, volume, master, label)
    for n in range(93, 145, 5):     # A-2 to C-7 on tone A
        segs.append((0, n, 15, DEFAULT_MASTER, "pitch"))
    for ch in (1, 2):               # the other two tones
        for n in (105, 117, 129, 136):
            segs.append((ch, n, 15, DEFAULT_MASTER, "pitch"))
    for v in (15, 10, 5, 1):        # volume steps
        segs.append((0, 117, v, DEFAULT_MASTER, "level"))
    for n in (117, 132):            # 10xx: a faster master oscillator
        segs.append((0, n, 15, 0x0F, "master"))
    segs.append((3, 117, 15, DEFAULT_MASTER, "noise"))
    # 11C8: slowest vibrato, depth 8. The master period alternates between 32 and
    # 24 clocks, so the tone's period alternates in the ratio 24/32.
    segs.append((0, 117, 15, DEFAULT_MASTER, "vibrato"))
    # 1201: noise adds a random 0-255 to every master period (depth: the noise
    # channel's volume, 15 here), so the pitch scatters
    segs.append((0, 117, 15, DEFAULT_MASTER, "noisemod"))
    return segs


FX = {"vibrato": (0x11, 0xC8), "noisemod": (0x12, 0x01)}


def build_song(segs):
    per = ROWS_ON + ROWS_OFF
    length = per * len(segs) + 2
    pats = [[{} for _ in range(length)] for _ in range(4)]
    master = DEFAULT_MASTER
    for i, (ch, n, v, m, kind) in enumerate(segs):
        r = 1 + i * per
        row = {"note": n, "ins": 0, "vol": v}
        if m != master:
            row["effects"] = [{"code": 0x10, "value": m}]
            master = m
        if kind in FX:
            # on, then back off at the note off
            code, val = FX[kind]
            row.setdefault("effects", []).append({"code": code, "value": val})
            pats[ch][r] = row
            pats[ch][r + ROWS_ON] = {"note": 253, "effects": [{"code": code, "value": 0}]}
            continue
        pats[ch][r] = row
        pats[ch][r + ROWS_ON] = {"note": 253}  # note off
    return {
        "chips": [{"id": 0, "fileID": FILE_ID, "channels": 4, "volume": 1.0, "panning": 0.0,
                   "frontRear": 0.0, "flags": {}}],
        "subsongs": [{
            "speeds": [6], "tickRate": 60.0, "virtualTempo": [150, 150],
            "patternLength": length, "orderLength": 1,
            "channelData": [{"effectColumns": 2} for _ in range(4)],
            "orders": [[0] for _ in range(4)],
            "patterns": [[{"rows": p}] for p in pats],
        }],
    }


def read_wav(path):
    with wave.open(str(path)) as w:
        rate, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32768
    return x.reshape(-1, ch).mean(axis=1), rate


def edge_frequency(x, rate):
    """Frequency of a square wave from its rising edges, interpolated to sub-sample."""
    x = x - x.mean()
    idx = np.nonzero((x[:-1] < 0) & (x[1:] >= 0))[0]
    if len(idx) < 3:
        return None
    t = idx + (-x[idx]) / (x[idx + 1] - x[idx])
    return (len(t) - 1) * rate / (t[-1] - t[0])


def edge_intervals(x):
    """Lengths of successive cycles, in samples."""
    x = x - x.mean()
    idx = np.nonzero((x[:-1] < 0) & (x[1:] >= 0))[0]
    t = idx + (-x[idx]) / (x[idx + 1] - x[idx])
    return np.diff(t)


def run(args):
    r = subprocess.run([str(FURNACE), "-noreport", *args], capture_output=True, text=True,
                       errors="replace", timeout=300)
    return r.returncode, r.stdout + r.stderr


def main():
    segs = build_segments()
    failures = []
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        song = d / "astrocade.json"
        song.write_text(json.dumps(build_song(segs)))
        wav = d / "astrocade.wav"
        code, log = run(["-output", str(wav), str(song)])
        if code != 0 or not wav.exists():
            print(log[-2000:])
            print("FAIL: render failed")
            return 1
        if "using dummy platform" in log:
            failures.append("the chip fell back to the Dummy platform")

        # the 16-bit file ID survives a .fur save and reload
        fur = d / "astrocade.fur"
        code, _ = run(["-furout", str(fur), str(song)])
        code2, info = run(["-info", str(fur)])
        if code or code2 or "Bally Astrocade" not in info:
            failures.append(".fur round trip lost the chip")
        else:
            print(".fur round trip: ok (chip ID 0x1000 written and read back)")

        x, rate = read_wav(wav)

    per = (ROWS_ON + ROWS_OFF) * 0.1
    levels = {}
    off_by_one = []
    print(f"{'ch':>2} {'note':>5} {'mst':>4} {'near':>4} {'used':>4} {'measured':>10} "
          f"{'vs used':>8} {'vs note':>8} {'bound':>6}")
    for i, (ch, n, v, m, kind) in enumerate(segs):
        start = 0.1 + i * per
        seg = x[int((start + 0.1) * rate):int((start + ROWS_ON * 0.1 - 0.05) * rate)]
        rms = float(np.sqrt(np.mean((seg - seg.mean()) ** 2)))
        if kind == "noise":
            f = edge_frequency(seg, rate)
            spec = np.abs(np.fft.rfft(seg - seg.mean()))
            flat = float(np.exp(np.mean(np.log(spec[1:] + 1e-12))) / np.mean(spec[1:]))
            ok = rms > 0.01 and flat > 0.2
            print(f"noise: rms {rms:.3f}, spectral flatness {flat:.2f} {'ok' if ok else 'FAIL'}")
            if not ok:
                failures.append("noise channel is silent or tonal")
            continue
        if kind == "vibrato":
            iv = np.sort(edge_intervals(seg))
            lo, hi = np.percentile(iv, 10), np.percentile(iv, 90)
            ok = abs(lo / hi - 24 / 32) < 0.02
            print(f"vibrato 11C8: cycle lengths {lo:.1f} and {hi:.1f} samples, ratio {lo / hi:.3f} "
                  f"(expect {24 / 32:.3f}) {'ok' if ok else 'FAIL'}")
            if not ok:
                failures.append(f"11xx vibrato: cycle ratio {lo / hi:.3f}, expected 0.750")
            continue
        if kind == "noisemod":
            iv = edge_intervals(seg)
            cv = float(iv.std() / iv.mean())
            # a clean tone's cycles vary by well under 1%
            ok = cv > 0.1
            print(f"noise modulation 1201: cycle-length spread {cv:.2f} (expect > 0.10) {'ok' if ok else 'FAIL'}")
            if not ok:
                failures.append(f"12xx noise modulation: cycle spread {cv:.3f}, expected > 0.1")
            continue
        want = note_hz(n)
        div = 2 * (m + 1)
        near = min(256, max(1, round(CLOCK / (div * want))))
        f = edge_frequency(seg, rate)
        if f is None:
            failures.append(f"ch {ch} {note_name(n)}: silent")
            print(f"{ch:>2} {note_name(n):>5} silent")
            continue
        used = round(CLOCK / (div * f))
        vs_used = 1200 * math.log2(f * div * used / CLOCK)
        vs_note = 1200 * math.log2(f / want)
        # the worst a period one step from the nearest can be off by, plus slack
        bound = 1200 * math.log2((used + 1.5) / used) + MAX_CENTS
        clamped = CLOCK / (div * 256) > want * 2 ** (1 / 24)
        ok = (abs(vs_used) <= MAX_CENTS and abs(used - near) <= 1
              and (clamped or abs(vs_note) <= bound))
        if ok and used != near:
            off_by_one.append(f"{note_name(n)} (master {m:02X}): {used} instead of {near}")
        print(f"{ch:>2} {note_name(n):>5} {m:>4X} {near:>4} {used:>4} {f:>10.2f} "
              f"{vs_used:>+8.2f} {vs_note:>+8.2f} {bound:>6.1f} {'' if ok else 'FAIL'}"
              f"{' (below range)' if clamped else ''}")
        if not ok:
            failures.append(f"ch {ch} {note_name(n)} master {m:02X}: period {used} "
                            f"({vs_used:+.2f} cents from it), nearest is {near}")
        if kind == "level":
            levels[v] = rms

    ref = levels.get(15)
    for v, rms in sorted(levels.items(), reverse=True):
        want_db = 20 * math.log10(v / 15)
        got_db = 20 * math.log10(rms / ref)
        ok = abs(got_db - want_db) <= LEVEL_DB
        print(f"volume {v:>2}: {got_db:+6.2f} dB (expect {want_db:+6.2f}) {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"volume {v}: {got_db:+.2f} dB, expected {want_db:+.2f}")

    if off_by_one:
        print("one period from the nearest (pitch-table rounding):", "; ".join(off_by_one))
    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print(f"PASS: {len(segs)} segments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
