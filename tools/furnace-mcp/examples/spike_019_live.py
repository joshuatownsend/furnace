"""Idea 019, spike step 4: live microtonal keys through the engine prototype.

Three keys of the Lumatone Editor's 31-EDO preset, played into a blank YM2612
song with the fork's -livetest flag (MIDI events by engine tick, through a key
table) and rendered per channel:

    A  ch1 note 60  degree 0  -> C-4 E580   on 0.2 s, off 2.5 s
    B  ch1 note 61  degree 1  -> C-4 E5B2   on 0.5 s, off 1.5 s
    D  ch3 note 60  not in the table -> C-4  on 1.55 s, off 1.65 s
    C  ch2 note 91  degree 62 -> C-6 E580   on 1.7 s, off 2.3 s

A and B round to the same note. Released by note, letting go of B would stop
A too; released by key, A keeps sounding. C lands on B's old channel and must
not inherit B's detune; nor must D, a key the table doesn't have, which
plays its plain note on B's old channel just before C.

    python spike_019_live.py [out_dir]
"""
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from furnace_mcp import song as fsong, tuning  # noqa: E402
from furnace_mcp.analysis import detect_pitch, note_hz, read_wav  # noqa: E402
from furnace_mcp.notation import parse_note  # noqa: E402

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
DEMO = REPO / "demos/genesis/All Good Times.fur"
PRESET = HERE.parents[1] / "tests/fixtures/lumatone/A-008-31ET-bosanquet.ltn"
TICK = 1 / 60
KEYS = {"A": (1, 60, 0.2, 2.5), "B": (1, 61, 0.5, 1.5), "D": (3, 60, 1.55, 1.65), "C": (2, 91, 1.7, 2.3)}


def blank_song():
    """The demo's chips, one default FM instrument, 3.2 s of empty rows."""
    song = fsong.load(DEMO)
    song["instruments"] = [{"name": "live", "type": 1}]
    sub = song["subsongs"][0]
    nchans = len(sub["orders"])
    sub.update(speeds=[6], tickRate=60.0, virtualTempo=[150, 150], patternLength=32,
               orderLength=1, orders=[[0] for _ in range(nchans)],
               patterns=[[{"rows": [{} for _ in range(32)]}] for _ in range(nchans)])
    sub.pop("grooves", None)
    return song


def livetest_file(table, path):
    lines = [f"key {ch} {note} {fn} {e5}" for (ch, note), (fn, e5) in table.items()]
    for name, (ch, note, on, off) in KEYS.items():
        lines.append(f"on {round(on / TICK)} {ch} {note} 127")
        lines.append(f"off {round(off / TICK)} {ch} {note}")
    path.write_text("\n".join(lines) + "\n")


def window(x, rate, t0, t1):
    seg = x[int(t0 * rate):int(t1 * rate)]
    rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
    hz = detect_pitch(seg, rate).get("hz") if rms > 1e-2 else None
    return rms, hz


def run(out):
    table = tuning.key_table(tuning.read_ltn(PRESET), tuning.edo(31))
    for name, (ch, note, _, _) in KEYS.items():
        print(f"key {name}: ch{ch} note {note} -> {table.get((ch, note), 'not in the table')}")
    song = blank_song()
    src = out / "live.json"
    src.write_text(json.dumps(song))
    events = out / "live.txt"
    livetest_file(table, events)
    wav = out / "live.wav"
    for f in out.glob("live_c*.wav"):
        f.unlink()
    fsong.run(["-loops", 0, "-livetest", events, "-output", wav, "-outmode", "perchan",
               "-exportchans", "1-3", src])
    c4 = note_hz(parse_note("C-4"))
    spans = [(0.3, 0.45), (0.6, 1.4), (1.57, 1.64), (1.8, 2.2), (2.35, 2.45), (2.6, 3.0)]
    for f in sorted(out.glob("live_c*.wav")):
        x, rate = read_wav(f)
        x = x.mean(axis=1) if x.ndim > 1 else x
        cells = []
        for t0, t1 in spans:
            rms, hz = window(x, rate, t0, t1)
            if rms <= 1e-2:  # -40 dB: a release tail counts as gone
                cells.append(f"{t0:.2f}-{t1:.2f}s off")
            elif hz is None:
                cells.append(f"{t0:.2f}-{t1:.2f}s sound, no pitch")
            else:
                cells.append(f"{t0:.2f}-{t1:.2f}s {1200 * math.log2(hz / c4):+7.1f}c")
        print(f"{f.name}: " + " | ".join(cells))


def over_song(out):
    """Key B over a song: channel 1 plays C-4 with E590 (+12.5 cents) at 0 s,
    B takes the channel from 0.5 to 1.0 s, and the song plays C-4 again at
    2.0 s. That note must get the song's +12.5 back, not B's +39; with its own
    E5C0 it must get +50."""
    table = tuning.key_table(tuning.read_ltn(PRESET), tuning.edo(31))
    ch, note, _, _ = KEYS["B"]
    events = out / "over.txt"
    events.write_text(f"key {ch} {note} {table[ch, note][0]} {table[ch, note][1]}\n"
                      f"on {round(0.5 / TICK)} {ch} {note} 127\noff {round(1.0 / TICK)} {ch} {note}\n")
    c4 = note_hz(parse_note("C-4"))
    print("\nkey B over a song (channel 1):")
    for label, second, want in (("no E5xx", [], 12.5), ("E5C0", [{"code": 0xE5, "value": 0xC0}], 50)):
        song = blank_song()
        rows = song["subsongs"][0]["patterns"][0][0]["rows"]
        rows[0] = {"note": parse_note("C-4"), "ins": 0, "effects": [{"code": 0xE5, "value": 0x90}]}
        rows[20] = {"note": parse_note("C-4"), "ins": 0, "effects": second}
        src = out / "over.json"
        src.write_text(json.dumps(song))
        wav = out / "over.wav"
        fsong.run(["-loops", 0, "-livetest", events, "-output", wav, src])
        x, rate = read_wav(wav)
        x = x.mean(axis=1) if x.ndim > 1 else x
        got = [window(x, rate, a, b)[1] for a, b in ((0.1, 0.45), (0.6, 0.95), (2.1, 2.5))]
        cents = ["   -" if h is None else f"{1200 * math.log2(h / c4):+6.1f}" for h in got]
        print(f"  second note {label:8s} song {cents[0]}  key B {cents[1]}  song again {cents[2]}"
              f"  (want {want:+.1f} plus the chip's offset)")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    run(out)
    over_song(out)
