"""End-to-end tests through the MCP protocol (in-memory client) against the real
furnace binary. Skipped when the binary isn't built."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client

from furnace_mcp import song as fsong
from server import mcp

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "demos" / "genesis" / "All Good Times.fur"

try:
    fsong.furnace_exe()
    HAVE_FURNACE = True
except fsong.FurnaceError:
    HAVE_FURNACE = False

pytestmark = [pytest.mark.anyio,
              pytest.mark.skipif(not HAVE_FURNACE, reason="furnace binary not built")]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def demo(tmp_path):
    p = tmp_path / "song.fur"
    shutil.copyfile(DEMO, p)
    return str(p)


def text(result):
    assert not result.is_error, result.content
    return "".join(c.text for c in result.content)


async def test_tools_listed():
    async with Client(mcp) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"current_song", "inspect_song", "read_patterns", "write_rows", "set_order",
                     "read_instrument", "write_instrument", "render", "preview_instrument",
                     "export", "export_video", "detect_sample_pitch", "tune_sample", "piano_roll"}


async def test_piano_roll_writes_a_page(demo, tmp_path):
    out = tmp_path / "roll.html"
    async with Client(mcp) as c:
        r = text(await c.call_tool("piano_roll", {"output": str(out), "order_end": 0, "path": demo}))
        bad = await c.call_tool("piano_roll", {"output": str(tmp_path / "roll.png"), "path": demo})
    assert r.startswith(f"wrote {out}: ") and "1 orders" in r
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert bad.is_error and "html" in bad.content[0].text


async def test_inspect(demo):
    async with Client(mcp) as c:
        out = text(await c.call_tool("inspect_song", {"path": demo}))
    assert "YM2612" in out and "duration: 142.8" in out and "0C 'Slap'" in out


async def test_inspect_song_without_samples():
    # Furnace's JSON export writes "samples": null when a song has none
    song = str(REPO / "tools" / "furnace-mcp" / "examples" / "neon_midway.fur")
    async with Client(mcp) as c:
        out = text(await c.call_tool("inspect_song", {"path": song}))
    assert "Bally Astrocade" in out and "06 'Open Hat'" in out


async def test_inspect_reports_each_chips_octave(demo):
    async with Client(mcp) as c:
        out = text(await c.call_tool("inspect_song", {"path": demo}))
    line = next(l for l in out.splitlines() if l.startswith("pitch"))
    # FM plays as written; Furnace's SN76489 sounds two octaves above the note
    assert "(channel 0): 4" in line and "as written" in line.split(";")[0], line
    assert "SN76489 (channel 9): 17" in line and "2 octaves up" in line, line


async def test_inspect_reports_the_ay_octave():
    async with Client(mcp) as c:
        out = text(await c.call_tool("inspect_song", {"path": str(REPO / "demos" / "ay8910" / "AY-3-8910_Jam.fur")}))
    assert "AY-3-8910 (channel 0)" in out


async def test_inspect_does_not_probe_a_sample_chip():
    # a probe would measure sample 0's tuning, not the chip's octave
    async with Client(mcp) as c:
        out = text(await c.call_tool("inspect_song", {"path": str(REPO / "demos" / "amiga" / "Ibiza.fur")}))
    line = next(l for l in out.splitlines() if l.startswith("pitch"))
    assert "not measured (a sample chip" in line and "Hz" not in line, line


async def test_write_read_render(demo):
    async with Client(mcp) as c:
        rows = "A-4 0C 7F\n" + "...\n" * 62 + "OFF"
        res = await c.call_tool("write_rows", {"path": demo, "channel": 0, "pattern": 0x40, "rows": rows})
        assert res.is_error and "set_order first" in res.content[0].text
        silent = {str(ch): 0x41 for ch in range(13)}
        text(await c.call_tool("set_order", {"path": demo, "order": 0, "patterns": silent | {"0": 0x40}}))
        out = text(await c.call_tool("write_rows", {"path": demo, "channel": 0, "pattern": 0x40, "rows": rows}))
        assert "played at orders: 00" in out
        out = text(await c.call_tool("read_patterns", {"path": demo, "channels": "0"}))
        assert "00  | A-4 0C 7F" in out and "3F  | OFF" in out
        out = text(await c.call_tool("render", {"path": demo, "order_start": 0, "order_end": 0}))
    # the song file was saved as .fur, and A-4 on the YM2612 is 440 Hz
    assert Path(demo).with_name("song.bak.fur").exists()
    strongest = int(out.split("strongest ")[1].split(" Hz")[0])
    assert 430 <= strongest <= 450, out


async def test_instrument_merge(demo):
    async with Client(mcp) as c:
        text(await c.call_tool("write_instrument", {
            "path": demo, "instrument": 12, "changes": {"name": "Slap 2", "fm": {"fb": 3}}}))
        out = text(await c.call_tool("read_instrument", {"path": demo, "instrument": 12}))
    assert '"Slap 2"' in out and '"fb": 3' in out and '"alg": 3' in out


async def test_bad_rows_are_reported(demo):
    async with Client(mcp) as c:
        res = await c.call_tool("write_rows", {"path": demo, "channel": 0, "pattern": 1, "rows": "H-4 01"})
    assert res.is_error and "bad note" in "".join(x.text for x in res.content)


async def test_append_order_and_export(demo, tmp_path):
    async with Client(mcp) as c:
        out = text(await c.call_tool("set_order", {"path": demo, "order": 39, "patterns": {"0": 5}}))
        assert out.startswith("order 27: 05")
        vgm = tmp_path / "out.vgm"
        text(await c.call_tool("export", {"path": demo, "output": str(vgm)}))
    assert vgm.stat().st_size > 1000


@pytest.fixture
def furnace_open(tmp_path, monkeypatch, demo):
    """Pretend the Furnace GUI has `demo` open (what the fork's GUI publishes)."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(fsong, "furnace_config_dir", lambda: cfg)

    def set_state(path=demo, modified=False, pid=os.getpid(), focus=1000):
        (cfg / f"open-song-{pid}.txt").write_text(
            f"{path}\n{int(modified)}\n0\n{focus}\n", encoding="utf-8")
    set_state()
    return set_state


async def test_path_defaults_to_open_song(demo, furnace_open):
    async with Client(mcp) as c:
        assert text(await c.call_tool("current_song", {})).startswith(str(Path(demo).resolve()))
        text(await c.call_tool("set_order", {"order": 0, "patterns": {"0": 0x40}}))
        text(await c.call_tool("write_rows", {"channel": 0, "pattern": 0x40, "rows": "C-4 0C 7F"}))
        out = text(await c.call_tool("read_patterns", {"channels": "0", "order_start": 0}))
    assert "pat 40" in out and "00  | C-4 0C 7F" in out
    out_song = fsong.load(demo)
    assert out_song["subsongs"][0]["patterns"][0][0x40]["rows"][0]["note"] == 108


async def test_unsaved_changes_block_edits(demo, furnace_open):
    furnace_open(modified=True)
    async with Client(mcp) as c:
        res = await c.call_tool("write_rows", {"channel": 0, "pattern": 1, "rows": "C-4 0C 7F"})
        assert res.is_error and "unsaved changes" in res.content[0].text
        # reading is still fine
        text(await c.call_tool("inspect_song", {}))


async def test_no_furnace_running(tmp_path, monkeypatch):
    monkeypatch.setattr(fsong, "furnace_config_dir", lambda: tmp_path)
    async with Client(mcp) as c:
        res = await c.call_tool("inspect_song", {})
    assert res.is_error and "Ask the user which song" in res.content[0].text


async def test_unsaved_new_song(tmp_path, monkeypatch):
    monkeypatch.setattr(fsong, "furnace_config_dir", lambda: tmp_path)
    (tmp_path / f"open-song-{os.getpid()}.txt").write_text("\n1\n0\n1000\n")
    async with Client(mcp) as c:
        res = await c.call_tool("current_song", {})
    assert res.is_error and "never been saved" in res.content[0].text


async def test_crashed_furnace_is_ignored(furnace_open):
    # a state file left behind by a Furnace process that no longer exists
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    for f in fsong.furnace_config_dir().glob("open-song-*.txt"):
        f.unlink()
    furnace_open(pid=dead.pid)
    async with Client(mcp) as c:
        res = await c.call_tool("set_order", {"order": 0, "patterns": {"0": 0x40}})
    assert res.is_error and "isn't running" in res.content[0].text


async def test_last_focused_furnace_wins(demo, tmp_path, furnace_open):
    other = tmp_path / "other.fur"
    shutil.copyfile(DEMO, other)
    # two live processes: this one, and its parent
    furnace_open(path=other, pid=os.getppid(), focus=2000)
    async with Client(mcp) as c:
        assert text(await c.call_tool("current_song", {})).startswith(str(other.resolve()))
        furnace_open(path=demo, pid=os.getpid(), focus=3000)
        assert text(await c.call_tool("current_song", {})).startswith(str(Path(demo).resolve()))


async def test_partial_operator_update_keeps_other_operators(demo):
    before = fsong.instrument(fsong.load(demo), 12)["fm"]["operators"]
    async with Client(mcp) as c:
        text(await c.call_tool("write_instrument", {
            "path": demo, "instrument": 12, "changes": {"fm": {"operators": [{"tl": 20}]}}}))
    after = fsong.instrument(fsong.load(demo), 12)["fm"]["operators"]
    assert after[0]["tl"] == 20 and after[1:] == before[1:]


async def test_backup_is_refreshed_each_session(demo, monkeypatch):
    import server
    bak = Path(demo).with_name("song.bak.fur")
    bak.write_bytes(b"stale backup from an earlier session")
    monkeypatch.setattr(server, "_backed_up", set())
    async with Client(mcp) as c:
        text(await c.call_tool("set_order", {"path": demo, "order": 0, "patterns": {"0": 5}}))
    assert bak.read_bytes() == Path(DEMO).read_bytes()


def _same_stamp_rewrite(p, data):
    """Replace p's contents keeping its size and modification time, like a
    second save within one tick of a coarse-timestamp filesystem."""
    st = p.stat()
    assert len(data) == st.st_size
    p.write_bytes(data)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert p.stat().st_mtime_ns == st.st_mtime_ns


def test_save_refuses_a_song_changed_since_it_was_read(demo):
    import server
    p = Path(demo).resolve()
    song = server._load(p)
    data = bytearray(p.read_bytes())
    data[-1] ^= 0xff  # "saved in Furnace", same size and time
    _same_stamp_rewrite(p, bytes(data))
    with pytest.raises(server.ToolError, match="changed on disk"):
        server._save(p, song)
    assert p.read_bytes() == bytes(data)


def test_touch_alone_is_not_a_change(demo):
    import server
    p = Path(demo).resolve()
    song = server._load(p)
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    server._save(p, song)


def test_load_sees_a_same_stamp_change(tmp_path):
    import server
    p = (tmp_path / "song.json").resolve()
    song = fsong.load(DEMO)
    song["songInfo"]["name"] = "AAAA"
    p.write_text(json.dumps(song), encoding="utf-8")
    assert server._load(p)["songInfo"]["name"] == "AAAA"
    _same_stamp_rewrite(p, p.read_bytes().replace(b'"AAAA"', b'"BBBB"'))
    assert server._load(p)["songInfo"]["name"] == "BBBB"


def test_preview_channel_ignores_unplayed_patterns():
    # channel 1 has a stale pattern full of the instrument that no order plays
    def pat(n):
        return {"rows": [{"ins": 5}] * n}
    sub = {"orderLength": 2, "orders": [[0, 0], [1, 1]],
           "patterns": [[pat(2)], [None, pat(1), pat(10)]]}
    assert fsong.instrument_channel({"subsongs": [sub]}, 5) == 0


def test_preview_releases_with_note_release(demo):
    # === (254) runs macro release stages; OFF (253) would cut them off
    preview, on, off = fsong.preview_song(fsong.load(demo), 12, 108, 0, hold_rows=8)
    notes = [r.get("note") for pats in preview["subsongs"][0]["patterns"] for p in pats if p
             for r in p.get("rows") or []]
    assert 254 in notes and 253 not in notes
    # an idle row before the note: the analysis takes its silence level from there
    rows = preview["subsongs"][0]["patterns"][0][0]["rows"]
    assert rows[0] == rows[2] == {} and rows[3]["note"] == 108 and (on, off) == pytest.approx((0.3, 1.1))


async def test_preview_before_and_after_an_edit_keeps_both_wavs(demo):
    def wav(out):
        return Path(out.split("wav: ")[1].splitlines()[0])
    async with Client(mcp) as c:
        before = wav(text(await c.call_tool("preview_instrument", {"path": demo, "instrument": 13})))
        text(await c.call_tool("write_instrument", {"path": demo, "instrument": 13, "changes": {"fm": {"fb": 7}}}))
        after = wav(text(await c.call_tool("preview_instrument", {"path": demo, "instrument": 13})))
    assert before != after and before.exists() and after.exists()


async def test_preview_rejects_notes_outside_the_pitch_range(demo):
    async with Client(mcp) as c:
        res = await c.call_tool("preview_instrument", {"path": demo, "instrument": 12, "note": "C-8"})
    assert res.is_error and "G#0 to B-7" in res.content[0].text


def test_save_stages_next_to_the_song(demo, monkeypatch):
    # the final rename must not cross drives, so nothing is staged in the temp dir
    seen = []
    real = os.replace
    monkeypatch.setattr(fsong.os, "replace", lambda a, b: (seen.append(Path(a)), real(a, b)))
    fsong.save(fsong.load(demo), demo)
    assert seen and seen[0].parent == Path(demo).parent and not seen[0].exists()



async def test_channels_come_from_furnace():
    chans = fsong.channels(fsong.load(DEMO))
    assert chans[2] == ("FM 3 OP1", fsong.EXT_OPERATOR) and chans[9] == ("Square 1", 1)
    assert len(chans) == 13


async def test_info_names_channels_from_the_sub_song_asked_for(tmp_path):
    song = fsong.load(DEMO)
    second = json.loads(json.dumps(song["subsongs"][0]))
    second["channelData"][0]["name"] = "Lead"
    song["subsongs"].append(second)
    src = tmp_path / "two.json"
    src.write_text(json.dumps(song), encoding="utf-8")
    assert "- 0: FM 1 [type 0]" in fsong.run(["-info", src])
    assert "- 0: Lead [type 0]" in fsong.run(["-info", "-subsong", 1, src])


async def test_exportchans_rejects_channels_the_song_lacks(tmp_path):
    with pytest.raises(fsong.FurnaceError, match="has 13 channels"):
        fsong.render(fsong.excerpt(fsong.load(DEMO), 0, 0, 0), tmp_path / "x.wav",
                     per_channel=True, channels=[13])


async def test_exportchans_renders_only_those_channels(tmp_path):
    song = fsong.excerpt(fsong.load(DEMO), 0, 2, 2)
    files = fsong.render(song, tmp_path / "ch.wav", per_channel=True, channels=[0, 9])
    assert [c for c, _ in files] == [0, 9]
    # channels 2-5 are the operators of extended FM channel 3: they export as one file under 2
    files = fsong.render(song, tmp_path / "op.wav", per_channel=True, channels=[3, 4])
    assert [c for c, _ in files] == [2]
    # a narrower render under a name used before returns only its own channels
    files = fsong.render(song, tmp_path / "ch.wav", per_channel=True, channels=[9])
    assert [c for c, _ in files] == [9]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
async def test_export_video(demo, tmp_path):
    out = tmp_path / "scopes.mp4"
    async with Client(mcp) as c:
        msg = text(await c.call_tool("export_video", {
            "path": demo, "output": str(out), "order_start": 2, "order_end": 2,
            "size": "320x180", "fps": 10, "color": "channel"}))
    # Furnace's own channel names; the extended channel's four operators are one scope
    assert "Square 1" in msg and "FM 1" in msg and "OP" not in msg, msg
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True)
    assert probe.stdout.split() == ["h264,320,180", "aac"]


async def test_export_video_rejects_bad_input(demo, tmp_path):
    async with Client(mcp) as c:
        bad_ext = await c.call_tool("export_video", {"path": demo, "output": str(tmp_path / "a.gif")})
        bad_size = await c.call_tool("export_video", {"path": demo, "output": str(tmp_path / "a.mp4"),
                                                      "size": "321x180"})
    assert bad_ext.is_error and ".mp4" in bad_ext.content[0].text
    assert bad_size.is_error and "even" in bad_size.content[0].text


# --- sample pitch (idea 005) ----------------------------------------------

IBIZA = REPO / "demos" / "amiga" / "Ibiza.fur"


@pytest.fixture
def ibiza(tmp_path):
    p = tmp_path / "ibiza.fur"
    shutil.copyfile(IBIZA, p)
    return str(p)


async def test_detect_sample_pitch(ibiza):
    async with Client(mcp) as c:
        piano = text(await c.call_tool("detect_sample_pitch", {"path": ibiza, "sample": 9}))
        hat = text(await c.call_tool("detect_sample_pitch", {"path": ibiza, "sample": 2}))
    # a 16-bit looped piano, measured on its loop; its instrument's pitch macro is flagged
    assert "16-bit PCM" in piano and "the loop (6992-7280)" in piano, piano
    assert "plays C-6 +16." in piano and "25088 Hz" in piano and "pitch macro" in piano, piano
    assert "no clear pitch" in hat, hat
    assert not Path(ibiza).with_name("ibiza.bak.fur").exists()


def _play_c4(song, sample, wav):
    """Render a written C-4 of the first instrument on sample, its macros removed
    so only the sample's tuning counts; (Hz, note number nearest to it)."""
    from furnace_mcp import analysis
    ins = fsong.sample_instruments(song, sample)[0]
    s = json.loads(json.dumps(song))
    s["instruments"][ins]["macros"] = []
    preview, on, off = fsong.preview_song(s, ins, 108, fsong.instrument_channel(s, ins), hold_rows=8,
                                          release_rows=1)
    (_, out), = fsong.render(preview, wav)
    hz = analysis.analyze_note(out, 108, note_off_s=off, note_on_s=on)["pitch"]["hz"]
    return hz, analysis.note_of(hz)


async def test_tune_sample_plays_in_tune(tmp_path):
    # the real proof: render a note before and after tuning. Ibiza's piano sample
    # (16-bit, 16 cents sharp) on a Ricoh RF5C68, whose rates aren't rounded to
    # whole periods like the Amiga's
    song = fsong.load(REPO / "demos" / "misc" / "Sonic_CD_House_RF5C68.fur")
    song["samples"][4] = fsong.load(IBIZA)["samples"][9]
    p = tmp_path / "rf.fur"
    fsong.save(song, p)
    _, (note, before) = _play_c4(song, 4, tmp_path / "before.wav")
    async with Client(mcp) as c:
        out = text(await c.call_tool("tune_sample", {"path": str(p), "sample": 4}))
    assert "25327 -> 25088 Hz" in out and "C-4 now plays C-6" in out and "2 octaves up" in out, out
    tuned = fsong.load(p)
    assert tuned["samples"][4]["centerRate"] == 25088
    _, (note_after, after) = _play_c4(tuned, 4, tmp_path / "after.wav")
    assert note == note_after == 108 + 24 and before > 8, (note, before)
    assert abs(after) < 10, after


async def test_tune_sample_8bit_and_again(tmp_path):
    p = tmp_path / "amigamen.fur"
    shutil.copyfile(REPO / "demos" / "amiga" / "The Amigamen.fur", p)
    async with Client(mcp) as c:
        out = text(await c.call_tool("tune_sample", {"path": str(p), "sample": 3}))
        assert "8-bit PCM" in out and "14716 -> 14687 Hz" in out and "notes play as written" in out, out
        again = text(await c.call_tool("tune_sample", {"path": str(p), "sample": 3}))
        assert "already in tune" in again, again
        # transposed: a written C-4 sounds C-3, at half the rate
        down = text(await c.call_tool("tune_sample", {"path": str(p), "sample": 3, "c4_plays": "C-3"}))
        assert "14687 -> 7343 Hz" in down and "1 octave down" in down, down
        # a note that isn't a C transposes by semitones
        up = text(await c.call_tool("tune_sample", {"path": str(p), "sample": 3, "c4_plays": "E-3"}))
        assert "7343 -> 9252 Hz" in up and "8 semitones down" in up, up  # E-3 is 8 below C-4
    assert fsong.load(p)["samples"][3]["centerRate"] == 9252


async def test_tune_sample_refuses_no_pitch_and_other_depths(ibiza):
    async with Client(mcp) as c:
        hat = await c.call_tool("tune_sample", {"path": ibiza, "sample": 2})
        brr = await c.call_tool("detect_sample_pitch", {
            "path": str(REPO / "demos" / "snes" / "Breezy.fur"), "sample": 1})
        missing = await c.call_tool("detect_sample_pitch", {"path": ibiza, "sample": 40})
    assert hat.is_error and "nothing was changed" in hat.content[0].text
    assert not Path(ibiza).with_name("ibiza.bak.fur").exists()
    assert brr.is_error and "depth 9 (BRR)" in brr.content[0].text
    assert missing.is_error and "out of range" in missing.content[0].text


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
async def test_render_image(demo):
    async with Client(mcp) as c:
        res = await c.call_tool("render", {"path": demo, "order_start": 1, "order_end": 2, "image": True})
    assert not res.is_error, res.content
    kinds = [type(x).__name__ for x in res.content]
    assert kinds == ["TextContent", "ImageContent"], kinds
    assert res.content[1].mime_type == "image/png"
    report = res.content[0].text
    png = Path(report.split("image: ")[1].splitlines()[0])
    assert png.is_file() and png.suffix == ".png"
    # the image needs per-channel renders, but their text reports come only with per_channel
    assert not any(line.startswith("ch") for line in report.splitlines()), report


def _image_result(res):
    """(report text, PNG path) from a tool call that returned text plus an image."""
    assert not res.is_error, res.content
    assert [type(x).__name__ for x in res.content] == ["TextContent", "ImageContent"]
    assert res.content[1].mime_type == "image/png"
    report = res.content[0].text
    png = Path(report.split("image: ")[1].splitlines()[0]) if "image: " in report else None
    return report, png


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
async def test_preview_and_sample_images(demo, ibiza):
    async with Client(mcp) as c:
        report, png = _image_result(await c.call_tool(
            "preview_instrument", {"path": demo, "instrument": 13, "image": True}))
        assert "envelope:" in report and png.is_file()
        report, png = _image_result(await c.call_tool(
            "detect_sample_pitch", {"path": ibiza, "sample": 9, "image": True}))
        assert "a written C-4 plays" in report and png.is_file()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
async def test_export_video_preview(demo, tmp_path):
    out = tmp_path / "v.mp4"
    async with Client(mcp) as c:
        res = await c.call_tool("export_video", {"path": demo, "output": str(out), "order_start": 0,
                                                 "order_end": 0, "size": "640x360", "preview": True})
    assert not res.is_error, res.content
    assert [type(x).__name__ for x in res.content] == ["TextContent", "ImageContent"]
    assert out.with_suffix(".png").is_file() and not out.exists()
    assert "8 frames" in res.content[0].text


async def test_export_to_a_missing_folder_says_so(demo, tmp_path):
    async with Client(mcp) as c:
        for tool, out in (("export", "song.vgm"), ("export_video", "v.mp4")):
            res = await c.call_tool(tool, {"path": demo, "output": str(tmp_path / "nope" / out)})
            assert res.is_error and "doesn't exist" in res.content[0].text, res.content
