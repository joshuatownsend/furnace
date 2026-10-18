"""Idea 019, spike step 2: how well do chips hold an E5xx detune?

Plays every step of 31-EDO and 53-EDO from written C-2 to C-6, as nearest note
plus E5xx, on the first channel of an FM chip (YM2612), the NES pulse and the
SN76489. It measures each note and prints the error in cents per octave, and
how many neighbouring steps come out at the same pitch.

    python spike_019_scales.py [out_dir]
"""
import copy
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from furnace_mcp import song as fsong, tuning  # noqa: E402
from furnace_mcp.analysis import detect_pitch, note_hz, read_wav  # noqa: E402
from furnace_mcp.notation import NOTE_OFF, parse_note  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
CHIPS = [  # (label, demo, chip index)
    ("YM2612 FM", REPO / "demos/genesis/All Good Times.fur", 0),
    ("SN76489", REPO / "demos/genesis/All Good Times.fur", 1),
    ("NES pulse", REPO / "demos/nes/Byte-Sized Bop.fur", 0),
]
# period chips: (clock / divider, period offset) so f = clock / (period + offset)
PERIODS = {"SN76489": (3579545 / 32, 0), "NES pulse": (1789773 / 16, 1)}
LOW, OCTAVES = parse_note("C-2"), 4
ROWS_PER_NOTE = 2  # a row is 0.1 s
PAT = 256


def probe(path, chip):
    for ci, name, ch, out, on, _ in fsong.pitch_probes(fsong.load(path)):
        if ci == chip:
            if isinstance(out, str):
                raise SystemExit(f"{name}: {out}")
            return name, ch, out, on
    raise SystemExit(f"no chip {chip} in {path}")


def scale_song(base, ch, notes, on_rows):
    """base with the notes [(note, e5xx)] on channel ch, one every ROWS_PER_NOTE rows."""
    song = copy.deepcopy(base)
    assert song.get("compatFlags", {}).get("linearPitch", 1), "E5xx needs linear pitch"
    sub = song["subsongs"][0]
    rows = [{} for _ in range(on_rows)]
    for note, e5 in notes:
        rows.append({"note": note, "ins": 0, "effects": [{"code": 0xE5, "value": e5}]})
        rows += [{} for _ in range(ROWS_PER_NOTE - 1)]
    rows.append({"note": NOTE_OFF})
    npat = math.ceil(len(rows) / PAT)
    rows += [{} for _ in range(npat * PAT - len(rows))]
    nchans = len(sub["orders"])
    sub.update(patternLength=PAT, orderLength=npat,
               orders=[list(range(npat)) if c == ch else [0] * npat for c in range(nchans)],
               patterns=[[] for _ in range(nchans)])
    sub["patterns"][ch] = [{"rows": rows[i * PAT:(i + 1) * PAT]} for i in range(npat)]
    cd = sub.setdefault("channelData", [{} for _ in range(nchans)])
    while len(cd) < nchans:
        cd.append({})
    cd[ch]["effectColumns"] = max(1, cd[ch].get("effectColumns", 1))
    return song


def measure(wav, n_notes, on_s, row_s=0.1):
    x, rate = read_wav(wav)
    x = x.mean(axis=1) if x.ndim > 1 else x
    out = []
    for i in range(n_notes):
        t = on_s + i * ROWS_PER_NOTE * row_s
        seg = x[int((t + 0.06) * rate):int((t + ROWS_PER_NOTE * row_s - 0.02) * rate)]
        out.append(detect_pitch(seg, rate).get("hz"))
    return out


def run(out_dir):
    results = {}
    for label, path, chip in CHIPS:
        name, ch, base, on_s = probe(path, chip)
        on_rows = round(on_s / 0.1)
        for n in (31, 53):
            scale = tuning.edo(n)
            steps = range(0, OCTAVES * n + 1)
            notes = [tuning.nearest(tuning.cents(scale, d), LOW) for d in steps]
            song = scale_song(base, ch, notes, on_rows)
            (_, wav), = fsong.render(song, Path(out_dir) / f"{label.split()[0]}_{n}.wav")
            hz = measure(wav, len(notes), on_s)
            # the chip's octave naming: SN76489 sounds two octaves up, NES one
            shift = round(np.median([math.log2(h / note_hz(nt)) for h, (nt, e5) in zip(hz, notes)
                                     if h and e5 == 0x80]))
            ref = note_hz(LOW) * 2 ** shift
            rows = []
            for d, h in zip(steps, hz):
                want = tuning.cents(scale, d)
                rows.append((d, want, None if h is None else 1200 * math.log2(h / ref) - want))
            results[label, n] = (name, shift, rows)
    return results


def best_possible(label, shift, want):
    """Error of the nearest period the chip has, for a period chip."""
    if label not in PERIODS:
        return None
    clock, plus = PERIODS[label]
    ref = note_hz(LOW) * 2 ** shift
    p = max(1, round(clock / (ref * 2 ** (want / 1200)) - plus))
    return 1200 * math.log2(clock / (p + plus) / ref) - want


def report(results):
    print("Error in cents per written octave, after taking out the chip's overall offset: worst and "
          "mean over every step, and worst over the steps that land on a plain note (E580), which the "
          "chip gets wrong without any detune. Best possible = the worst error if each step got the "
          "chip's nearest period. Merged = neighbouring steps less than a quarter step apart.")
    for (label, n), (name, shift, rows) in results.items():
        offset = float(np.median([e for _, _, e in rows if e is not None]))
        rows = [(d, w, None if e is None else e - offset) for d, w, e in rows]
        print(f"\n{label} ({name}), {n}-EDO, sounds {shift:+d} octaves from written, "
              f"offset {offset:+.1f} cents")
        step = 1200 / n
        for o in range(OCTAVES):
            part = [r for r in rows if o * n <= r[0] < (o + 1) * n + (o == OCTAVES - 1)]
            errs = [abs(e) for _, _, e in part if e is not None]
            missing = sum(e is None for _, _, e in part)
            got = [w + e for _, w, e in part if e is not None]
            merged = sum(1 for a, b in zip(got, got[1:]) if b - a < step / 4)
            plain = [abs(e) for _, w, e in part if e is not None and abs(w / 100 - round(w / 100)) < 0.002]
            worst = f"{max(errs):5.1f}" if errs else "    -"
            mean = f"{np.mean(errs):5.1f}" if errs else "    -"
            plain = f"{max(plain):5.1f}" if plain else "    -"
            best = [best_possible(label, shift, w) for _, w, _ in part]
            best = f"  best possible {max(abs(b) for b in best):5.1f}" if best[0] is not None else ""
            print(f"  written C-{2 + o}..: worst {worst}  mean {mean}  plain notes {plain}{best}  "
                  f"merged {merged:2d}/{len(part) - 1}"
                  + (f"  no pitch {missing}" if missing else ""))


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    report(run(out))
