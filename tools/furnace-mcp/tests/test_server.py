"""End-to-end tests through the MCP protocol (in-memory client) against the real
furnace binary. Skipped when the binary isn't built."""

import shutil
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
    assert names == {"inspect_song", "read_patterns", "write_rows", "set_order",
                     "read_instrument", "write_instrument", "render", "export"}


async def test_inspect(demo):
    async with Client(mcp) as c:
        out = text(await c.call_tool("inspect_song", {"path": demo}))
    assert "YM2612" in out and "duration: 142.8" in out and "0C 'Slap'" in out


async def test_write_read_render(demo):
    async with Client(mcp) as c:
        rows = "A-4 0C 7F\n" + "...\n" * 62 + "OFF"
        out = text(await c.call_tool("write_rows", {"path": demo, "channel": 0, "pattern": 0x40, "rows": rows}))
        assert "no orders yet" in out
        silent = {str(ch): 0x41 for ch in range(13)}
        text(await c.call_tool("set_order", {"path": demo, "order": 0, "patterns": silent | {"0": 0x40}}))
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
