"""Idea 019, spike step 3: which effects mix safely with an E5xx detune?

Each case plays a few rows on the YM2612's first channel and measures one
window, in cents from C-4. Last, the same detune under non-linear pitch
(compatibility flag "None") at four octaves.

    python spike_019_effects.py [out_dir]
"""
import copy
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from furnace_mcp import song as fsong  # noqa: E402
from furnace_mcp.analysis import detect_pitch, note_hz, read_wav  # noqa: E402
from furnace_mcp.notation import NOTE_OFF, parse_note  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "demos/genesis/All Good Times.fur"
ROW = 0.1  # seconds: speed 6 at 60 Hz
C4 = parse_note("C-4")


def row(note=None, *effects):
    r = {"effects": [{"code": c, "value": v} for c, v in effects]}
    if note is not None:
        r.update(note=parse_note(note) if isinstance(note, str) else note, ins=0)
    return r


# (name, rows, (first row, last row) to measure, expected cents from C-4, what it shows)
CASES = [
    ("E5xx stays set", [row("C-4", (0xE5, 0xC0)), {}, {}, {}, row("D-4")], (5, 7), 250,
     "a later note without E5xx keeps the detune"),
    ("vibrato 0448", [row("C-4", (0xE5, 0xA0), (0x04, 0x48))] + [{}] * 7, (1, 7), 25,
     "vibrato swings around the detuned pitch"),
    ("portamento 0308, E5xx on the target", [row("C-4", (0xE5, 0xC0)), {}, {}, {},
     row("E-4", (0xE5, 0xA0), (0x03, 0x08))] + [{}] * 15, (16, 19), 425,
     "a tone portamento ends on the target plus its own detune"),
    ("portamento 0308, no E5xx on the target", [row("C-4", (0xE5, 0xC0)), {}, {}, {},
     row("E-4", (0x03, 0x08))] + [{}] * 15, (16, 19), 450,
     "...or plus the old detune when the target row has none"),
    ("note slide E124", [row("C-4", (0xE5, 0xA0)), {}, row(None, (0xE1, 0x24))] + [{}] * 9,
     (8, 11), 425, "E1xy slides up 4 semitones and keeps the detune"),
    ("arpeggio 0047", [row("C-4", (0xE5, 0xA0), (0x00, 0x47))] + [{}] * 3, None, None,
     "not measured; from the code, linear pitch adds arp<<7 to base+pitch (engine.cpp calcFreq), "
     "so the detune carries"),
]


def base_song():
    for ci, name, ch, out, on, _ in fsong.pitch_probes(fsong.load(DEMO)):
        if ci == 0:
            return out, ch, round(on / ROW)
    raise SystemExit("no FM chip")


def build(base, ch, on_rows, rows, linear=True):
    song = copy.deepcopy(base)
    song.setdefault("compatFlags", {})["linearPitch"] = 1 if linear else 0
    sub = song["subsongs"][0]
    nchans = len(sub["orders"])
    rows = [{} for _ in range(on_rows)] + [copy.deepcopy(r) for r in rows] + [{"note": NOTE_OFF}]
    sub.update(patternLength=len(rows), orderLength=1, orders=[[0] for _ in range(nchans)],
               patterns=[[] for _ in range(nchans)])
    sub["patterns"][ch] = [{"rows": rows}]
    cd = sub.setdefault("channelData", [{} for _ in range(nchans)])
    while len(cd) < nchans:
        cd.append({})
    cd[ch]["effectColumns"] = max(r.get("effects") and len(r["effects"]) or 1 for r in rows)
    return song


def cents_at(wav, t0, t1, frame=None):
    """Pitch over t0..t1 in cents from C-4; with frame, the mean of frame-second
    windows (a vibrato's centre: one long window catches it mid-swing)."""
    x, rate = read_wav(wav)
    x = x.mean(axis=1) if x.ndim > 1 else x
    spans = [(t0, t1)] if frame is None else [(t, t + frame) for t in
                                              [t0 + k * frame for k in range(int((t1 - t0) / frame))]]
    got = []
    for a, b in spans:
        hz = detect_pitch(x[int(a * rate):int(b * rate)], rate).get("hz")
        if hz:
            got.append(1200 * math.log2(hz / note_hz(C4)))
    return sum(got) / len(got) if got else None


def run(out):
    base, ch, on_rows = base_song()
    # the chip's overall offset (about -2.6 cents on this one), from a plain C-4
    (_, wav), = fsong.render(build(base, ch, on_rows, [row("C-4")] + [{}] * 3), out / "ref.wav")
    offset = cents_at(wav, (on_rows + 1) * ROW, (on_rows + 4) * ROW)
    print(f"plain C-4 measures {offset:+.1f} cents; taken out below\n")
    for i, (name, rows, window, want, note) in enumerate(CASES):
        if window is None:
            print(f"{name:42s} {note}")
            continue
        (_, wav), = fsong.render(build(base, ch, on_rows, rows), out / f"case{i}.wav")
        frame = 0.02 if "vibrato" in name else None
        got = cents_at(wav, (on_rows + window[0]) * ROW, (on_rows + window[1] + 1) * ROW, frame) - offset
        print(f"{name:42s} want {want:+5d}  got {got:+7.1f}   {note}")
    print("\nE5C0 (+50 cents) under linear and non-linear pitch:")
    for octave in (2, 3, 4, 5):
        note = f"C-{octave}"
        line = []
        for linear in (True, False):
            song = build(base, ch, on_rows, [row(note, (0xE5, 0xC0))] + [{}] * 3, linear)
            (_, wav), = fsong.render(song, out / f"nl{octave}{linear}.wav")
            c = cents_at(wav, (on_rows + 1) * ROW, (on_rows + 4) * ROW) - offset - 1200 * (octave - 4)
            line.append(f"{'linear' if linear else 'non-linear'} {c:+6.1f}")
        print(f"  {note}: " + "   ".join(line))


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    run(out)
