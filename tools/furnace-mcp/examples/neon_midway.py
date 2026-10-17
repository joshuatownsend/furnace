"""Neon Midway: an upbeat 1970s console tune for the Bally Astrocade.

Builds the song as Furnace JSON and converts it to neon_midway.fur next to
this script with furnace -furout. Edit the sections below and rerun:

    python neon_midway.py [path/to/furnace]

The default is the furnace-mcp lookup: FURNACE_EXE, else build-gui or build
in this repo.
A = lead, B = offbeat arpeggio chords, C = octave bass, NO = drums.
Speed 6 at 60 Hz: one row is a 16th note at 150 BPM; a pattern is 4 bars.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from furnace_mcp.song import furnace_exe  # noqa: E402

ROWS = 64
NAMES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
OFF = 253


def n(s):
    """'F#5' -> Furnace note number (C-4 = 108)."""
    return 60 + 12 * int(s[-1]) + NAMES[s[:-1]]


# instruments
LEAD, ARP_MAJ, ARP_MIN, BASS, HAT, SNARE, OPEN_HAT = range(7)


def macro(code, data, loop=255, release=255, speed=1, delay=0):
    return {"code": code, "length": len(data), "loop": loop, "release": release, "mode": 0,
            "open": 0, "type": 0, "delay": delay, "speed": speed, "data": data}


VOL, ARP = 0, 1
INSTRUMENTS = [
    {"name": "Lead", "type": 0, "macros": [
        macro(VOL, [15, 14, 13, 12, 12, 11, 11, 11, 10], loop=8),
    ]},
    {"name": "Arp Major", "type": 0, "macros": [
        macro(VOL, [13, 12, 10, 9, 8, 6, 5, 3, 2, 0]),
        macro(ARP, [0, 4, 7], loop=0),
    ]},
    {"name": "Arp Minor", "type": 0, "macros": [
        macro(VOL, [13, 12, 10, 9, 8, 6, 5, 3, 2, 0]),
        macro(ARP, [0, 3, 7], loop=0),
    ]},
    {"name": "Bass", "type": 0, "macros": [
        macro(VOL, [15, 14, 12, 11, 10, 10, 9, 9, 8], loop=8),
    ]},
    {"name": "Hat", "type": 0, "macros": [macro(VOL, [9, 5, 2, 0])]},
    {"name": "Snare", "type": 0, "macros": [macro(VOL, [15, 13, 11, 9, 7, 6, 5, 4, 3, 2, 1, 0])]},
    {"name": "Open Hat", "type": 0, "macros": [macro(VOL, [8, 7, 6, 5, 4, 3, 2, 2, 1, 1, 0])]},
]

MINOR = {"Em", "Bm", "Am"}


def root(chord):
    return chord.rstrip("m")


def melody(seq, vol=0x0F):
    """seq: 'G4:2 B4:2 -:4 ...' ('-' = rest/note off). Must fill 64 rows."""
    rows = [{} for _ in range(ROWS)]
    r = 0
    for tok in seq.split():
        note, dur = tok.split(":")
        rows[r] = {"note": OFF} if note == "-" else {"note": n(note), "ins": LEAD, "vol": vol}
        r += int(dur)
    assert r == ROWS, f"melody fills {r} rows"
    return rows


def arps(chords, vol=0x0B):
    """Offbeat chord stabs: the 'and' of every beat, plus a pickup on the last 16th of the bar."""
    rows = [{} for _ in range(ROWS)]
    for b, ch in enumerate(chords):
        ins = ARP_MIN if ch in MINOR else ARP_MAJ
        for off in (2, 6, 10, 14):
            rows[b * 16 + off] = {"note": n(root(ch) + "4"), "ins": ins, "vol": vol}
    return rows


def bass(chords, vol=0x0C):
    """Octave-jumping eighths, disco/70s style."""
    rows = [{} for _ in range(ROWS)]
    for b, ch in enumerate(chords):
        r = root(ch)
        low = n(r + "3") if NAMES[r] < NAMES["A"] else n(r + "2")  # A-2 is the chip's floor
        for i in range(8):
            rows[b * 16 + i * 2] = {"note": low + (12 if i % 2 else 0), "ins": BASS, "vol": vol}
    return rows


def drums(fill=False, sparse=False):
    rows = [{} for _ in range(ROWS)]
    hit = lambda ins, v: {"note": n("C4"), "ins": ins, "vol": v}
    for b in range(4):
        for r in (0, 2, 6, 8, 10, 14):
            rows[b * 16 + r] = hit(HAT, 0x0C)
        rows[b * 16 + 14] = hit(OPEN_HAT, 0x0B)
        if not sparse:
            rows[b * 16 + 4] = hit(SNARE, 0x0F)
            rows[b * 16 + 12] = hit(SNARE, 0x0F)
    if fill:
        for r, v in ((56, 0x0B), (58, 0x0C), (60, 0x0D), (61, 0x0E), (62, 0x0F), (63, 0x0F)):
            rows[r] = hit(SNARE, v)
    return rows


VERSE = ["G", "Em", "C", "D"]
BRIDGE1 = ["C", "D", "Bm", "Em"]
BRIDGE2 = ["C", "D", "G", "D"]

LEAD_INTRO = "-:16 -:16 -:16 D5:2 F#5:2 A5:2 D6:6 -:4"
LEAD_A1 = ("G4:2 B4:2 D5:4 B4:2 D5:2 G5:4 "
           "E5:6 D5:2 B4:4 G4:4 "
           "C5:2 E5:2 G5:4 E5:2 G5:2 C6:4 "
           "B5:4 A5:4 F#5:2 A5:2 D5:4")
LEAD_A2 = ("G5:2 F#5:2 G5:2 D5:2 B4:4 D5:4 "
           "E5:2 F#5:2 G5:4 B5:4 G5:4 "
           "A5:3 G5:3 E5:2 C5:4 E5:4 "
           "A5:2 G5:2 F#5:2 E5:2 F#5:4 -:4")
LEAD_B1 = ("E5:8 G5:4 E5:4 "
           "F#5:8 A5:4 F#5:4 "
           "D5:4 F#5:4 B5:8 "
           "G5:4 E5:4 B4:6 -:2")
LEAD_B2 = ("C5:2 E5:2 G5:2 C6:2 B5:4 G5:4 "
           "A5:2 F#5:2 D5:2 F#5:2 A5:4 D6:4 "
           "B5:4 G5:4 D5:4 G5:4 "
           "F#5:2 G5:2 A5:2 B5:2 A5:4 D5:4")

# (lead, chords, drum options)
SECTIONS = [
    (LEAD_INTRO, VERSE, dict(sparse=True, fill=True)),   # 0 intro
    (LEAD_A1, VERSE, dict()),                            # 1
    (LEAD_A2, VERSE, dict(fill=True)),                   # 2
    (LEAD_B1, BRIDGE1, dict()),                          # 3
    (LEAD_B2, BRIDGE2, dict(fill=True)),                 # 4
    (LEAD_A1, VERSE, dict()),                            # 5 (reuses patterns of 1)
    (LEAD_A2, VERSE, dict(fill=True)),                   # 6 (reuses 2, then loops to 1)
]


def build():
    pats = [[], [], [], []]
    orders = [[], [], [], []]
    cache = [{}, {}, {}, {}]

    def place(ch, rows):
        key = json.dumps(rows, sort_keys=True)
        if key not in cache[ch]:
            cache[ch][key] = len(pats[ch])
            pats[ch].append(rows)
        orders[ch].append(cache[ch][key])

    for i, (lead, chords, dopt) in enumerate(SECTIONS):
        place(0, melody(lead))
        place(1, arps(chords))
        place(2, bass(chords))
        d = drums(**dopt)
        if i == len(SECTIONS) - 1:
            # loop back to the first verse, skipping the intro
            d[63] = dict(d[63], effects=[{"code": 0x0B, "value": 1}])
        place(3, d)

    return {
        "songInfo": {"name": "Neon Midway", "author": "Claude", "tuning": 440.0},
        "chips": [{"id": 0, "fileID": 0x1000, "channels": 4, "volume": 1.0, "panning": 0.0,
                   "frontRear": 0.0, "flags": {}}],
        "instruments": INSTRUMENTS,
        "subsongs": [{
            "name": "", "speeds": [6], "tickRate": 60.0, "virtualTempo": [150, 150],
            "patternLength": ROWS, "orderLength": len(SECTIONS),
            "channelData": [{"effectColumns": 1} for _ in range(4)],
            "orders": orders,
            "patterns": [[{"rows": p} for p in ch] for ch in pats],
        }],
    }


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    furnace = Path(sys.argv[1]) if len(sys.argv) > 1 else furnace_exe()
    out = here / "neon_midway.fur"
    with tempfile.TemporaryDirectory() as d:
        song = Path(d) / "neon_midway.json"
        song.write_text(json.dumps(build()))
        # write to a temp file first: an open Furnace reloads the .fur when it changes
        tmp = Path(d) / "neon_midway.fur"
        r = subprocess.run([str(furnace), "-noreport", "-furout", str(tmp), str(song)],
                           capture_output=True, text=True, errors="replace")
        if r.returncode or not tmp.exists():
            sys.exit((r.stdout + r.stderr)[-2000:] + "\nfurnace -furout failed")
        out.write_bytes(tmp.read_bytes())
    print("wrote", out)
