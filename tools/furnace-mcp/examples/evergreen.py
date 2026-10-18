"""Evergreen: a 1984-style synthpop ballad for the YM2151 that goes sour.

An original tune in the spirit of mid-80s synthpop ballads: bell arpeggios,
a slow-attack pad, a soft synth lead and LinnDrum-ish FM drums. It starts in
B-flat major and ends in B-flat minor: the last choruses replay the same hook
with its 3rd, 6th and 7th flattened, the pads detune and warble, and the
outro is the hook on a lone bell while the tempo winds down to a tape stop.

Builds the song as Furnace JSON and converts it to evergreen.fur next to this
script with furnace -furout. Edit the sections below and rerun:

    python evergreen.py [path/to/furnace]

Channels: 0 bass, 1-3 pad triad, 4 bell arp, 5 lead, 6 kick, 7 snare/hats
(the OPM noise generator only exists on channel 7; 10xx turns it on).
Speed 12 at 60 Hz: one row is a 16th note at 75 BPM; a pattern is 4 bars.
"""
import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from furnace_mcp.song import furnace_exe  # noqa: E402

ROWS = 64
PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
      "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
OFF = 253
BASS_CH, PAD_CH, BELL_CH, LEAD_CH, KICK_CH, DRUM_CH = 0, (1, 2, 3), 4, 5, 6, 7


def n(s):
    """'Bb4' -> Furnace note number (C-4 = 108)."""
    return 60 + 12 * int(s[-1]) + PC[s[:-1]]


def fx(code, value):
    return {"code": code, "value": value}


# effects
PORTA_DOWN, VIBRATO, VOL_SLIDE, SPEED, NOISE, LFO_SPEED, PM_DEPTH, FINE, STOP = (
    0x02, 0x04, 0x0A, 0x0F, 0x10, 0x17, 0x1F, 0xE5, 0xFF)

# ---------------------------------------------------------------- instruments

BASS, PAD, BELL, LEAD, KICK, SNARE, HAT, OHAT = range(8)


def op(ar, dr, sl, d2r, rr, tl, mult, dt=3, dt2=0, rs=0):
    """One OPM operator. dt 3 is no detune; tl 127 is silent."""
    return {"am": 0, "ar": ar, "d2r": d2r, "dam": 0, "dr": dr, "dt": dt, "dt2": dt2, "dvb": 0,
            "egt": 0, "enable": True, "ksl": 0, "ksr": 0, "kvs": 2, "mult": mult, "rr": rr,
            "rs": rs, "sl": sl, "ssgEnv": 0, "sus": 0, "tl": tl, "vib": 0, "ws": 0}


MUTE = op(31, 31, 15, 31, 15, 127, 1)


def opm(name, alg, fb, ops, fms=0, macros=()):
    """ops are in register order S1, S3, S2, S4 (see write_instrument)."""
    return {"name": name, "type": 33, "macros": list(macros), "fm": {
        "alg": alg, "fb": fb, "fms": fms, "ams": 0, "ops": 4, "operators": ops,
        "amsLFO": False, "block": 0, "fixedDrums": False, "fmsLFO": False, "kickFreq": 1312,
        "opllPreset": 0, "snareHatFreq": 1360, "tomTopFreq": 448, "tremLFO": False}}


def arp_macro(data):
    return {"code": 1, "length": len(data), "loop": 255, "release": 255, "mode": 0, "open": 0,
            "type": 0, "delay": 0, "speed": 1, "data": data}


INSTRUMENTS = [
    # alg 1: S1+S3 into S2 into S4; S2 muted, so two modulators feed the carrier
    opm("Bass", 1, 2, [op(31, 10, 15, 3, 3, 54, 4, dt=5), op(30, 4, 11, 0, 6, 34, 1, dt=5),
                       MUTE, op(29, 9, 8, 7, 9, 0, 1)]),
    # alg 4: S1->S2, S3->S4; carriers detuned against each other for chorus,
    # fms 2 so 1Fxx (PM depth) makes it warble
    opm("Pad", 4, 6, [op(31, 0, 0, 0, 6, 34, 1, dt=6), op(31, 0, 0, 0, 6, 30, 1, dt=0),
                      op(13, 3, 2, 0, 5, 14, 1, dt=6), op(13, 3, 2, 0, 5, 14, 1, dt=0)], fms=2),
    opm("Bell", 4, 4, [op(31, 22, 7, 0, 15, 7, 4, dt=6), op(31, 9, 15, 0, 15, 17, 4),
                       op(31, 9, 15, 0, 7, 8, 1), op(31, 9, 15, 0, 7, 10, 2, dt=6)]),
    opm("Lead", 4, 5, [op(24, 4, 3, 0, 6, 33, 1), op(24, 4, 3, 0, 6, 40, 2),
                       op(20, 2, 2, 0, 6, 6, 1, dt=4), op(20, 2, 2, 0, 6, 8, 1, dt=2)]),
    # alg 7: every operator is a carrier. Kick is a sine dropping two octaves.
    opm("Kick", 7, 5, [op(31, 24, 15, 0, 15, 20, 1), MUTE, MUTE, op(31, 12, 15, 0, 15, 0, 1)],
        macros=[arp_macro([24, 16, 10, 6, 3, 1, 0])]),
    # on channel 7 with noise on, S4 is the noise source
    opm("Snare", 7, 0, [MUTE, MUTE, op(31, 18, 15, 0, 15, 8, 1), op(31, 15, 15, 0, 15, 0, 1)],
        macros=[arp_macro([5, 2, 0])]),
    opm("Hat", 7, 0, [MUTE, MUTE, MUTE, op(31, 24, 15, 0, 15, 4, 1)]),
    opm("Open Hat", 7, 0, [MUTE, MUTE, MUTE, op(31, 15, 15, 0, 13, 6, 1)]),
]

# ---------------------------------------------------------------- harmony

QUALITY = {"": (0, 4, 7), "m": (0, 3, 7)}


def chord(name):
    """'F/A' -> (pitch classes, bass pitch class)."""
    name, _, slash = name.partition("/")
    root = name[:2] if len(name) > 1 and name[1] in "#b" else name[:1]
    pcs = [(PC[root] + i) % 12 for i in QUALITY[name[len(root):]]]
    return pcs, PC[slash] if slash else pcs[0]


def voice(chords, start=("Bb3", "D4", "F4"), lo=n("G3"), hi=n("A4")):
    """Voice-lead triads across three pad channels: each chord takes the
    assignment of its tones to channels that moves the least."""
    prev = [n(s) for s in start]
    out = []
    for name in chords:
        pcs, _ = chord(name)
        best = None
        for perm in itertools.permutations(pcs):
            notes = []
            for p, pc in zip(prev, perm):
                cands = [m for m in range(lo, hi + 1) if m % 12 == (pc + 60) % 12]
                notes.append(min(cands, key=lambda m: abs(m - p)))
            cost = sum(abs(a - b) for a, b in zip(notes, prev))
            if best is None or cost < best[0]:
                best = (cost, notes)
        prev = best[1]
        out.append(prev)
    return out


def minorize(seq):
    """The same tune in the parallel minor: flatten D, G and A (3rd, 6th, 7th of B-flat)."""
    flat = {"D": "Db", "G": "Gb", "A": "Ab"}
    toks = []
    for tok in seq.split():
        note, dur = tok.split(":")
        if note != "-" and note[:-1] in flat:
            note = flat[note[:-1]] + note[-1]
        toks.append(f"{note}:{dur}")
    return " ".join(toks)


def minor_chords(chords):
    """Chord-for-chord parallel minor: majors on Eb, F and Bb become minor,
    and chords built on D, G, A drop a semitone (Dm -> Db, Gm -> Gb)."""
    out = []
    for c in chords:
        base, _, slash = c.partition("/")
        if base in ("Eb", "F", "Bb"):
            base += "m"
        elif base in ("Dm", "Gm", "Am"):
            base = base[0] + "b"
        if slash in ("D", "G", "A"):
            slash += "b"
        out.append(base + ("/" + slash if slash else ""))
    return out


# ---------------------------------------------------------------- parts


def empty():
    return [{} for _ in range(ROWS)]


def add_fx(row, *effects):
    row.setdefault("effects", []).extend(effects)


def melody(seq, ins, vol):
    """seq: 'Bb5:6 G5:2 -:4 ...' ('-' = note off). Must fill 64 rows."""
    rows = empty()
    r = 0
    for tok in seq.split():
        note, dur = tok.split(":")
        rows[r] = {"note": OFF} if note == "-" else {"note": n(note), "ins": ins, "vol": vol}
        r += int(dur)
    assert r == ROWS, f"melody fills {r} rows: {seq}"
    return rows


def pads(chords, vol=0x7F):
    """Three channels; a channel holds its note when the next chord keeps it."""
    voicings = voice(chords)
    chans = [empty() for _ in PAD_CH]
    for b, v in enumerate(voicings):
        for c in range(3):
            if b == 0 or v[c] != voicings[b - 1][c]:
                chans[c][b * 16] = {"note": v[c], "ins": PAD, "vol": vol}
    return chans


ARP_ORDER = [0, 1, 2, 3, 2, 1, 2, 3]


def arps(chords, vol=0x7A):
    """16th-note bell arpeggio over root, 3rd, 5th, octave."""
    rows = empty()
    for b, name in enumerate(chords):
        pcs, _ = chord(name)
        base = 60 + 12 * (5 if pcs[0] < 7 else 4) + pcs[0]
        tones = [base + ((pc - pcs[0]) % 12) for pc in pcs] + [base + 12]
        for i in range(16):
            rows[b * 16 + i] = {"note": tones[ARP_ORDER[i % 8]], "ins": BELL, "vol": vol}
    return rows


def bass(chords, style, vol=0x7C):
    """style: 'whole' (one note a bar) or 'drive' (80s ballad eighths)."""
    rows = empty()
    for b, name in enumerate(chords):
        _, pc = chord(name)
        note = 60 + 12 * (2 if pc >= 4 else 3) + pc
        hits = (0,) if style == "whole" else (0, 6, 8, 12, 14)
        for r in hits:
            rows[b * 16 + r] = {"note": note, "ins": BASS, "vol": vol}
    return rows


def drums(style, fill=False):
    """Returns (kick rows, snare/hat rows). styles: none, heartbeat, light, full, half."""
    kick, kit = empty(), empty()

    def k(r, v=0x7C):
        kick[r] = {"note": n("C2"), "ins": KICK, "vol": v}

    def snare(r, v=0x7C):
        kit[r] = {"note": n("A3"), "ins": SNARE, "vol": v, "effects": [fx(NOISE, 0x16)]}

    def hat(r, v=0x6C, ins=HAT):
        kit[r] = {"note": n("C4"), "ins": ins, "vol": v, "effects": [fx(NOISE, 0x1F)]}

    for b in range(4):
        o = b * 16
        if style == "heartbeat":
            k(o, 0x6E)
            k(o + 3, 0x64)
        elif style == "light":
            k(o), k(o + 8)
            for r in range(0, 16, 2):
                hat(o + r, 0x66)
        elif style == "full":
            k(o), k(o + 10)
            for r in (0, 2, 6, 8, 10):
                hat(o + r)
            hat(o + 14, 0x68, OHAT)
            snare(o + 4), snare(o + 12)
        elif style == "half":
            k(o), k(o + 14, 0x6A)
            hat(o + 4, 0x64), hat(o + 12, 0x64)
            snare(o + 8)
    if fill:
        for i, r in enumerate(range(56, 64)):
            snare(r, 0x6A + i * 2)
    return kick, kit


# ---------------------------------------------------------------- the song

INTRO = ["Bb", "F/A", "Gm", "Eb"]
VERSE_A = ["Bb", "F/A", "Gm", "Eb"]
VERSE_B = ["Eb", "Bb/D", "Cm", "F"]
CHORUS_A = ["Eb", "F", "Dm", "Gm"]
CHORUS_B = ["Eb", "F", "Bb", "Bb"]
BRIDGE_A = ["Gm", "Eb", "Cm", "D"]
BRIDGE_B = ["Ebm", "Bbm", "Gb", "F"]

HOOK_INTRO = ("Bb5:6 G5:2 Bb5:4 C6:4 "
              "A5:12 -:4 "
              "D5:6 C5:2 Bb4:4 G4:4 "
              "Bb4:12 -:4")
LEAD_VA = ("-:4 D5:2 F5:2 F5:4 Eb5:2 D5:2 "
           "C5:6 A4:2 C5:4 F5:4 "
           "-:2 G5:2 F5:2 D5:4 Bb4:6 "
           "Eb5:8 D5:4 C5:4")
LEAD_VB = ("-:4 G5:2 Bb5:2 Bb5:4 G5:2 F5:2 "
           "F5:6 D5:2 F5:4 Bb5:4 "
           "Eb5:4 G5:4 F5:4 Eb5:4 "
           "C5:4 D5:2 Eb5:2 F5:8")
LEAD_CA = ("Bb5:6 G5:2 Bb5:4 C6:4 "
           "A5:8 F5:4 -:2 C5:2 "
           "D5:2 F5:2 A5:4 A5:4 G5:2 F5:2 "
           "G5:12 -:4")
LEAD_CB = ("Bb5:6 G5:2 Bb5:4 Eb6:4 "
           "D6:6 C6:2 A5:4 F5:4 "
           "D6:12 C6:2 Bb5:2 "
           "Bb5:12 -:4")
LEAD_BA = ("G4:8 Bb4:4 A4:4 "
           "G4:12 -:4 "
           "Eb5:8 D5:4 C5:4 "
           "D5:8 F#5:8")
LEAD_BB = ("Gb5:8 F5:4 Eb5:4 "
           "Db5:8 -:8 "
           "Db5:4 Eb5:4 Gb5:8 "
           "F5:8 A5:8")
REST = "-:64"

# name, chords, lead, bass style, drum style, options
SECTIONS = [
    ("intro", INTRO, REST, "none", "none", dict(arp=True)),
    ("intro hook", INTRO, HOOK_INTRO, "whole", "heartbeat", dict(arp=True)),
    ("verse 1a", VERSE_A, LEAD_VA, "whole", "light", dict(arp=True)),
    ("verse 1b", VERSE_B, LEAD_VB, "whole", "light", dict(arp=True, fill=True)),
    ("chorus 1a", CHORUS_A, LEAD_CA, "drive", "full", dict(arp=True)),
    ("chorus 1b", CHORUS_B, LEAD_CB, "drive", "full", dict(arp=True, fill=True)),
    ("verse 2a", VERSE_A, LEAD_VA, "drive", "full", dict(arp=True)),
    ("verse 2b", VERSE_B, LEAD_VB, "drive", "full", dict(arp=True, fill=True)),
    ("chorus 2a", CHORUS_A, LEAD_CA, "drive", "full", dict(arp=True)),
    ("chorus 2b", CHORUS_B, LEAD_CB, "drive", "full", dict(arp=True)),
    # the turn: arp drops out, drums go half-time, pads start to drift
    ("bridge a", BRIDGE_A, LEAD_BA, "whole", "half", dict(sour=1)),
    ("bridge b", BRIDGE_B, LEAD_BB, "whole", "half", dict(sour=1, fill=True)),
    # the same chorus, in the parallel minor
    ("sour chorus a", minor_chords(CHORUS_A), minorize(LEAD_CA), "drive", "full",
     dict(arp=True, sour=2)),
    ("sour chorus b", minor_chords(CHORUS_B), minorize(LEAD_CB), "drive", "full",
     dict(arp=True, sour=2)),
    ("outro", minor_chords(INTRO), REST, "whole", "heartbeat", dict(sour=2, outro=True)),
]

# per sour level: pad fine-pitch offsets, global PM depth, lead vibrato
SOUR = {0: ((0x80, 0x80, 0x80), 0x00, 0x22),
        1: ((0x84, 0x7C, 0x80), 0x18, 0x33),
        2: ((0x8A, 0x76, 0x82), 0x40, 0x46)}


def section(name, chords, lead, bass_style, drum_style, opt):
    sour = opt.get("sour", 0)
    detune, pm, vib = SOUR[sour]
    parts = {}
    parts[BASS_CH] = bass(chords, bass_style) if bass_style != "none" else empty()
    for c, rows in zip(PAD_CH, pads(chords)):
        add_fx(rows[0], fx(FINE, detune[c - PAD_CH[0]]))
        parts[c] = rows
    add_fx(parts[PAD_CH[0]][0], fx(PM_DEPTH, pm))
    if sour:
        add_fx(parts[PAD_CH[1]][0], fx(LFO_SPEED, 0xC0 if sour == 2 else 0xA8))
    parts[BELL_CH] = arps(chords) if opt.get("arp") else empty()
    parts[LEAD_CH] = melody(lead, LEAD, 0x7C)
    add_fx(parts[LEAD_CH][0], fx(VIBRATO, vib))
    parts[KICK_CH], parts[DRUM_CH] = drums(drum_style, opt.get("fill", False))

    if opt.get("outro"):
        # the hook on a lone bell, the heartbeat stops, the tempo winds down
        parts[BELL_CH] = melody(minorize(HOOK_INTRO), BELL, 0x7F)
        for r in range(48, 64):
            parts[KICK_CH][r] = {}
        for r, speed in ((0, 0x0C), (16, 0x0E), (32, 0x11), (48, 0x15), (56, 0x1C)):
            add_fx(parts[KICK_CH][r], fx(SPEED, speed))
        # tape stop: everything still sounding sags and fades in the last bar
        for c in (BASS_CH, *PAD_CH, BELL_CH):
            add_fx(parts[c][52], fx(PORTA_DOWN, 0x03), fx(VOL_SLIDE, 0x02))
        add_fx(parts[KICK_CH][63], fx(STOP, 0x00))
    elif name == "intro":
        add_fx(parts[KICK_CH][0], fx(SPEED, 0x0C))
    return parts


def build():
    pats = [[] for _ in range(8)]
    orders = [[] for _ in range(8)]
    cache = [{} for _ in range(8)]

    def place(ch, rows):
        key = json.dumps(rows, sort_keys=True)
        if key not in cache[ch]:
            cache[ch][key] = len(pats[ch])
            pats[ch].append(rows)
        orders[ch].append(cache[ch][key])

    for sec in SECTIONS:
        parts = section(*sec)
        for ch in range(8):
            place(ch, parts[ch])

    return {
        "songInfo": {"name": "Evergreen", "author": "Claude", "tuning": 440.0},
        "chips": [{"id": 19, "fileID": 130, "channels": 8, "volume": 0.8, "panning": 0.0,
                   "frontRear": 0.0, "flags": {"clockSel": "0"}}],
        "instruments": INSTRUMENTS,
        "subsongs": [{
            "name": "", "speeds": [12], "tickRate": 60.0, "virtualTempo": [150, 150],
            "patternLength": ROWS, "orderLength": len(SECTIONS), "highlights": [4, 16],
            "channelData": [{"effectColumns": 2} for _ in range(8)],
            "orders": orders,
            "patterns": [[{"rows": p} for p in ch] for ch in pats],
        }],
    }


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    furnace = Path(sys.argv[1]) if len(sys.argv) > 1 else furnace_exe()
    out = here / "evergreen.fur"
    with tempfile.TemporaryDirectory() as d:
        song = Path(d) / "evergreen.json"
        song.write_text(json.dumps(build()))
        # write to a temp file first: an open Furnace reloads the .fur when it changes
        tmp = Path(d) / "evergreen.fur"
        r = subprocess.run([str(furnace), "-noreport", "-furout", str(tmp), str(song)],
                           capture_output=True, text=True, errors="replace")
        if r.returncode or not tmp.exists():
            sys.exit((r.stdout + r.stderr)[-2000:] + "\nfurnace -furout failed")
        out.write_bytes(tmp.read_bytes())
    print("wrote", out)
