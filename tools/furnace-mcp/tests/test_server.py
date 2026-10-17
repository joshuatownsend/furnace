"""End-to-end tests through the MCP protocol (in-memory client) against the real
furnace binary. Skipped when the binary isn't built."""

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
                     "read_instrument", "write_instrument", "render", "export"}


async def test_inspect(demo):
    async with Client(mcp) as c:
        out = text(await c.call_tool("inspect_song", {"path": demo}))
    assert "YM2612" in out and "duration: 142.8" in out and "0C 'Slap'" in out


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

    def set_state(path=demo, modified=False, pid=os.getpid()):
        (cfg / "open-song.txt").write_text(f"{path}\n{int(modified)}\n0\n{pid}\n", encoding="utf-8")
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
    (tmp_path / "open-song.txt").write_text(f"\n1\n0\n{os.getpid()}\n")
    async with Client(mcp) as c:
        res = await c.call_tool("current_song", {})
    assert res.is_error and "never been saved" in res.content[0].text


async def test_crashed_furnace_is_ignored(furnace_open):
    # a state file left behind by a Furnace process that no longer exists
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    furnace_open(pid=dead.pid)
    async with Client(mcp) as c:
        res = await c.call_tool("set_order", {"order": 0, "patterns": {"0": 0x40}})
    assert res.is_error and "isn't running" in res.content[0].text


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


def test_save_stages_next_to_the_song(demo, monkeypatch):
    # the final rename must not cross drives, so nothing is staged in the temp dir
    seen = []
    real = os.replace
    monkeypatch.setattr(fsong.os, "replace", lambda a, b: (seen.append(Path(a)), real(a, b)))
    fsong.save(fsong.load(demo), demo)
    assert seen and seen[0].parent == Path(demo).parent and not seen[0].exists()
