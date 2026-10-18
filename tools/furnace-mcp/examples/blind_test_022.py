"""Build the blind-test material for ideas/022 step 3: planted songs on copies, the
exact tool outputs (render / preview_instrument), the pictures, and the answers,
written before any trial runs. Run from tools/furnace-mcp with PYTHONPATH=.:

    python examples/blind_test_022.py TASKS_DIR KEY_DIR

TASKS_DIR gets what the trial agents see (reports and pictures); KEY_DIR gets the
planted songs and answers.json. closeup() is the test-only stand-in for item 2."""

import copy, json, random, shutil, subprocess, sys, tempfile
from pathlib import Path

import anyio
import numpy as np
from mcp import Client

from furnace_mcp import notation, picture, song as fsong
from furnace_mcp.analysis import read_wav
from furnace_mcp.video import _FONT, find_ffmpeg
from server import mcp

DEMOS = Path("../../demos")
OUT = Path(sys.argv[1])  # what the trial agents see
KEY = Path(sys.argv[2])  # planted songs and answers: never shown to them
for d in (OUT, KEY):
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
C4 = notation.parse_note("C-4")
rng = random.Random(22)
answers = {}


def text(res):
    assert not res.is_error, res.content
    return res.content[0].text


async def render(c, path, a, b, tag):
    res = await c.call_tool("render", {"path": str(path), "order_start": a, "order_end": b,
                                       "per_channel": True, "image": True})
    t = text(res)
    png = Path(t.split("image: ")[1].splitlines()[0])
    shutil.copyfile(png, OUT / f"{tag}.png")
    # the image path in the text would leak nothing, but keep reports identical in both arms
    lines = [l for l in t.splitlines() if not l.startswith(("wav:", "image:"))]
    (OUT / f"{tag}.txt").write_text("\n".join(lines), encoding="utf-8")
    return t


def mix_of(t):
    return Path(t.split("wav: ")[1].splitlines()[0])


def save(song, name):
    p = KEY / name
    fsong.save(song, p)
    return p


def closeup(wav, on, off, f0, out):
    """Test-only stand-in for item 2: the whole note, plus a few cycles early in the
    attack, in the held part, and late in the hold."""
    x, rate = read_wav(wav)
    width, left = 1200, 120
    pw = width - left - 10
    panels = [("whole note", 0, len(x))]
    for name, t in (("attack +20 ms", on + 0.02), ("held +150 ms", on + 0.15), ("late hold", off - 0.1)):
        a = int(t * rate)
        panels.append((name, a, a + int(4 / f0 * rate)))
    h = 130
    img = np.empty((len(panels) * (h + 8) + 8, width, 3), np.uint8)
    img[:] = picture._BG
    texts = []
    for k, (name, a, b) in enumerate(panels):
        y = 8 + k * (h + 8)
        seg = x[a:b]
        if k:  # close-ups: interpolate up to the panel width
            seg = np.stack([np.interp(np.linspace(0, len(seg) - 1, pw * 4), np.arange(len(seg)), seg[:, c])
                            for c in range(seg.shape[1])], axis=1)
        picture._draw_wave(img, left, y, pw, h, seg, picture._WAVE)
        texts.append((6, y + 4, name, 13, picture._TEXT))
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "font.otf").write_bytes(_FONT.read_bytes())
        vf = []
        for i, (tx, ty, s, size, color) in enumerate(texts):
            (td / f"t{i}.txt").write_text(s, encoding="utf-8")
            vf.append(f"drawtext=fontfile=font.otf:textfile=t{i}.txt:expansion=none:fontcolor=0x{color}:fontsize={size}:x={tx}:y={ty}")
        subprocess.run([find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-s", f"{width}x{img.shape[0]}", "-i", "-", "-vf", ",".join(vf),
                        "-frames:v", "1", str(out.resolve())], input=img.tobytes(), check=True, cwd=td)


async def main():
    agt = fsong.load(DEMOS / "genesis" / "All Good Times.fur")
    async with Client(mcp) as c:
        # T1: which orders the mix clips in (the demo as is, orders 00-07)
        p = save(agt, "t1.fur")
        t = await render(c, p, 0, 7, "t1")
        x, rate = read_wav(mix_of(t))
        starts, _ = picture.order_starts(fsong.excerpt(agt, 0, 0, 7))
        clip_t = np.flatnonzero(np.abs(x).max(axis=1) >= picture.CLIP) / rate
        orders = sorted({int(np.searchsorted(starts, s, side="right")) - 1 for s in clip_t})
        answers["t1"] = {"clip_orders": [f"{o:02X}" for o in orders], "clipped_samples": len(clip_t),
                         "clip_times": [round(float(clip_t.min()), 2), round(float(clip_t.max()), 2)] if len(clip_t) else []}

        # T2: channel 0 (FM 1) drops out for order 04 only. Not channel 2: on this
        # song it is FM 3 in extended mode, whose audio is four operator channels
        s = copy.deepcopy(agt)
        sub = fsong.subsong(s, 0)
        # OFF first: an empty pattern would let the last note ring on
        fsong.write_rows(s, 0, 0, 0x7E, 0, "\n".join(["OFF"] + ["..."] * (sub["patternLength"] - 1)))
        fsong.set_order(s, 0, 4, {0: 0x7E})
        await render(c, save(s, "t2.fur"), 0, 7, "t2")
        answers["t2"] = {"channel": "ch0", "order": "04"}

        # T3: channel 6 (a melodic FM part) turned down: it gets its own copies of
        # its instruments with every operator's level 20 steps (about 15 dB) lower
        s = copy.deepcopy(agt)
        sub = fsong.subsong(s, 0)
        remap = {}
        for old in (13, 21, 22):
            ins = copy.deepcopy(s["instruments"][old])
            ins["name"] = ins.get("name", "") + " quiet"
            for op in ins["fm"]["operators"]:
                op["tl"] = min(127, op["tl"] + 20)
            remap[old] = len(s["instruments"])
            s["instruments"].append(ins)
        for pi in sorted(set(sub["orders"][6][:8])):
            for row in fsong._pattern(sub, 6, pi)["rows"]:
                if row and row.get("ins") in remap:
                    row["ins"] = remap[row["ins"]]
        await render(c, save(s, "t3.fur"), 0, 7, "t3")
        answers["t3"] = {"channel": "ch6"}

        # T4: 004's three edits of Funk Gt (ins 0D) at C-4 on channel 6
        edits = {"A": lambda i: i["fm"]["operators"][2].__setitem__("mult", 5),
                 "B": lambda i: i["fm"]["operators"][3].__setitem__("dr", 20),
                 "C": lambda i: i["fm"].__setitem__("fb", 7)}
        before_song = save(agt, "t4_before.fur")

        async def preview(path, tag):
            t = text(await c.call_tool("preview_instrument", {"path": str(path), "instrument": 13,
                                                              "note": "C-4", "channel": 6}))
            wav = Path(t.split("wav: ")[1].splitlines()[0])
            (OUT / f"{tag}.txt").write_text("\n".join(l for l in t.splitlines() if not l.startswith("wav:")),
                                            encoding="utf-8")
            return wav
        wav = await preview(before_song, "t4_before")
        _, on, off = fsong.preview_song(agt, 13, C4, 6)  # only the note times are used
        closeup(wav, on, off, 261.63, OUT / "t4_before.png")
        for trial, true in zip("123", ("C", "A", "B")):  # 004's order of true answers
            s = copy.deepcopy(agt)
            edits[true](fsong.instrument(s, 13))
            wav = await preview(save(s, f"t4_{trial}.fur"), f"t4_{trial}_after")
            closeup(wav, on, off, 261.63, OUT / f"t4_{trial}_after.png")
            answers[f"t4_{trial}"] = {"edit": true}

        # T5: a held strings note, the original loop vs a loop start moved to a jump
        am = fsong.load(DEMOS / "amiga" / "The Amigamen.fur")
        smp = fsong.sample(am, 3)
        xs = fsong.sample_pcm(smp)
        start, end, _ = fsong.sample_loop(smp)
        cand = np.arange(start, end - 2000)
        bad = int(cand[np.argmax(np.abs(xs[cand] - xs[end - 1]))])
        ab = ["good", "bad"]
        rng.shuffle(ab)
        for label, kind in zip("AB", ab):
            s = copy.deepcopy(am)
            # the instrument's volume macro cuts notes after 4 frames, before the loop:
            # drop it in both, so a held note plays through the loop
            fsong.instrument(s, 1)["macros"] = []
            if kind == "bad":
                fsong.sample(s, 3)["loop"]["start"] = bad
            prev, _, _ = fsong.preview_song(s, 1, C4, 0, hold_rows=30, release_rows=4)
            await render(c, save(prev, f"t5_{label}.fur"), 0, 0, f"t5_{label}")
        answers["t5"] = {"clicks": "AB"[ab.index("bad")], "bad_loop_start": bad,
                         "jump": round(float(abs(xs[bad] - xs[end - 1])), 3),
                         "good_jump": round(float(abs(xs[start] - xs[end - 1])), 3)}

        # T6: Funk Gt one note, carrier attack rate 31 vs 12
        ab = ["fast", "slow"]
        rng.shuffle(ab)
        for label, kind in zip("AB", ab):
            s = copy.deepcopy(agt)
            if kind == "slow":
                fsong.instrument(s, 13)["fm"]["operators"][3]["ar"] = 12
            prev, _, _ = fsong.preview_song(s, 13, C4, 6, hold_rows=12, release_rows=6)
            await render(c, save(prev, f"t6_{label}.fur"), 0, 0, f"t6_{label}")
        answers["t6"] = {"faster_attack": "AB"[ab.index("fast")]}
    (KEY / "answers.json").write_text(json.dumps(answers, indent=1), encoding="utf-8")
    print(json.dumps(answers, indent=1))

anyio.run(main)
