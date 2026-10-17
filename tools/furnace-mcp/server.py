"""Furnace MCP server: lets Claude read, edit, render and export Furnace songs.

Run with:  uv run --project tools/furnace-mcp tools/furnace-mcp/server.py
Edits are saved in place; the first edit to a file in a session copies it to
<name>.bak<ext> first.
"""

import functools
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from furnace_mcp import analysis, notation, song as fsong

mcp = MCPServer(
    "furnace",
    instructions=(
        "Tools for Furnace chiptune tracker songs (.fur; also .json and anything Furnace imports). "
        "Every tool takes an optional path. Leave it out to work on the song the user has open "
        "in Furnace: when they say 'the song', 'this song', or name no file, that is the one they "
        "mean, so edit it rather than starting a new file. Furnace reloads it after each edit. "
        "Call current_song to see which file that is. "
        "Start with inspect_song, then read_patterns over a small window of orders. "
        "Patterns are shared: an order row points each channel at a pattern index, and editing "
        "a pattern changes every order that uses it. Render short order ranges to check edits. "
        + notation.LEGEND
    ),
)

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_EDIT = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

# Errors Claude can act on (bad input, missing file, furnace rejecting the song)
# go back as messages; anything else stays a generic crash.
_EXPECTED = (notation.NotationError, fsong.FurnaceError, IndexError, ValueError,
             FileNotFoundError, KeyError)


def _tool(annotations):
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*a, **kw):
            try:
                return fn(*a, **kw)
            except _EXPECTED as e:
                raise ToolError(str(e)) from e
        return mcp.tool(annotations=annotations)(inner)
    return wrap


_cache = {}
_backed_up = set()
_loaded_rev = {}  # path -> file mtime when its song was last read


def _path(p):
    """The song file to work on: p, or the song open in Furnace when p is empty."""
    path = fsong.open_song()[0] if not p else Path(p).expanduser()
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    return path


def _check_not_dirty(path):
    """Refuse to overwrite a song Furnace has unsaved edits to: the GUI would
    have to choose between its edits and ours."""
    try:
        open_path, modified, _ = fsong.open_song()
    except fsong.FurnaceError:
        return
    if modified and open_path.resolve() == path:
        raise ToolError(
            "Furnace has unsaved changes to this song. Ask the user to save it in "
            "Furnace (Ctrl+S) first, then retry.")


def _load(path):
    key = str(path)
    mtime = path.stat().st_mtime_ns
    _loaded_rev[key] = mtime
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return json.loads(hit[1])
    song = fsong.load(path)
    _cache[key] = (mtime, json.dumps(song))
    return song


def _save(path, song):
    _check_not_dirty(path)
    # the song must still be the revision this edit was made on; otherwise
    # (e.g. the user saved in Furnace meanwhile) writing would discard that save
    if path.stat().st_mtime_ns != _loaded_rev.get(str(path)):
        raise ToolError(
            "the song file changed on disk while this edit was being made (probably "
            "saved in Furnace). Nothing was written; read it again and redo the edit.")
    if path.suffix.lower() not in (".fur", ".json"):
        raise ValueError(f"can only save .fur or .json, not {path.suffix}; export a copy first")
    if str(path) not in _backed_up:
        # the song as it was before this session's first edit (replacing any
        # backup an earlier session left)
        shutil.copyfile(path, path.with_name(path.stem + ".bak" + path.suffix))
        _backed_up.add(str(path))
    before = _open_reloads(path)
    fsong.save(song, path)
    # re-read on next use: Furnace may have changed the song on the way to disk
    # (e.g. dropped unused patterns), and our view must match the file
    _cache.pop(str(path), None)
    if before is None:
        return ""
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        time.sleep(0.2)
        after = _open_reloads(path)
        if after is not None and after > before:
            return "\nFurnace reloaded the song; the change is on screen."
    return ("\nFurnace didn't reload the song within 3 s. If it is showing a reload "
            "question, the user should answer it; otherwise reopening the file shows the change.")


def _open_reloads(path):
    """Furnace's reload count if it has this file open, else None."""
    try:
        open_path, _, reloads = fsong.open_song()
    except fsong.FurnaceError:
        return None
    return reloads if open_path.resolve() == path else None


def _render_dir():
    d = Path(os.environ.get("FURNACE_MCP_RENDERS", Path(tempfile.gettempdir()) / "furnace-mcp"))
    d.mkdir(parents=True, exist_ok=True)
    return d


@_tool(_READ)
def current_song() -> str:
    """Which song file is open in Furnace, and whether it has unsaved changes there."""
    path, modified, _ = fsong.open_song()
    state = "has unsaved changes in Furnace (ask the user to save before editing)" if modified else "saved"
    return f"{path} ({state})"


@_tool(_READ)
def inspect_song(subsong: int = 0, path: str = "") -> str:
    """Summary of a song: name, chips, channels (with indices), sub-songs, orders,
    pattern length, speed, duration, instruments and samples."""
    p = _path(path)
    s = _load(p)
    sub = fsong.subsong(s, subsong)
    info = fsong.info(p, subsong)
    timing = info[info.find("TIMING"):].split("\n\n")[0] if "TIMING" in info else ""
    labels = fsong.channel_labels(s)
    si = s.get("songInfo", {})
    lines = [
        f"name: {si.get('name', '')} / author: {si.get('author', '')}",
        "chips: " + ", ".join(f"{c.get('name')} ({c.get('channels')} ch)" for c in s.get("chips", [])),
        "channels: " + ", ".join(f"{i}={l}" for i, l in enumerate(labels)),
        f"sub-songs: {len(s.get('subsongs', []))} (showing {subsong}: {sub.get('name', '')!r})",
        f"orders: {sub.get('orderLength')} (hex 00-{sub.get('orderLength', 1) - 1:02X}), "
        f"pattern length {sub.get('patternLength')} rows, speeds {sub.get('speeds')}, "
        f"tick rate {sub.get('tickRate')} Hz, virtual tempo {sub.get('virtualTempo')}, "
        f"highlights {sub.get('highlights')}",
        timing,
        "instruments: " + ", ".join(
            f"{i:02X} {ins.get('name', '')!r} (type {ins.get('type')})" for i, ins in enumerate(s.get("instruments", []))),
        "samples: " + ", ".join(
            f"{i:02X} {smp.get('name', '')!r}" for i, smp in enumerate(s.get("samples", []))),
        f"wavetables: {len(s.get('wavetables') or [])}",
    ]
    return "\n".join(l for l in lines if l)


@_tool(_READ)
def read_patterns(order_start: int = 0, order_end: int | None = None,
                  channels: str = "", subsong: int = 0, skip_empty: bool = True, path: str = "") -> str:
    """Pattern rows for orders order_start..order_end (inclusive, default one order)
    as tracker text. channels: e.g. "0,2,5-7" (default all). Each order header lists
    the pattern index each channel plays. Rows empty in every shown channel are
    skipped unless skip_empty=false. Keep windows small (1-4 orders)."""
    s = _load(_path(path))
    return notation.LEGEND + "\n" + fsong.read_patterns(s, subsong, order_start, order_end, channels or None, skip_empty)


@_tool(_EDIT)
def write_rows(channel: int, pattern: int, rows: str, start_row: int = 0,
               subsong: int = 0, path: str = "") -> str:
    """Overwrite rows of one channel's pattern, starting at start_row. rows: one line per
    row in tracker text, e.g. "C-3 01 7F ...." or "..." for an empty row; a leading
    "1F |" row number is ignored. Rows not given are left unchanged. The pattern must
    already be placed in an order on this channel (set_order); Furnace doesn't keep
    unused patterns. Saves the song."""
    p = _path(path)
    s = _load(p)
    used = fsong.write_rows(s, subsong, channel, pattern, start_row, rows)
    if not used:
        # Furnace only saves patterns some order plays (unless the user turned on
        # "save unused patterns"), so these rows would vanish on save.
        raise ToolError(
            f"no order plays pattern {pattern:02X} on channel {channel}, and Furnace drops "
            "unused patterns when it saves. Place it with set_order first, then write its rows.")
    note = _save(p, s)
    n = len(rows.strip("\n").split("\n"))
    where = ", ".join(f"{o:02X}" for o in used)
    return f"wrote {n} rows to channel {channel} pattern {pattern:02X} from row {start_row:02X}; played at orders: {where}" + note


@_tool(_EDIT)
def set_order(order: int, patterns: dict[str, int], subsong: int = 0, path: str = "") -> str:
    """Point order row `order` at pattern indices, as {"channel": pattern}. Unlisted
    channels keep their pattern (0 on a new row). order == order count appends a row.
    Saves the song."""
    p = _path(path)
    s = _load(p)
    row = fsong.set_order(s, subsong, order, patterns)
    note = _save(p, s)
    return f"order {order:02X}: " + " ".join(f"{x:02X}" for x in row) + note


@_tool(_READ)
def read_instrument(instrument: int, path: str = "") -> str:
    """One instrument as JSON (Furnace's JSON export format: type, fm params and
    operators, macros, chip-specific blocks). 4-op FM "operators" are in register
    order S1, S3, S2, S4; see write_instrument."""
    s = _load(_path(path))
    return json.dumps(fsong.instrument(s, instrument), indent=1)


@_tool(_EDIT)
def write_instrument(instrument: int, changes: dict, replace: bool = False, path: str = "") -> str:
    """Change an instrument. changes is merged into the existing JSON (nested objects
    merge; "operators" merge per operator by position, so [{"tl": 20}] changes only
    operators[0] and leaves the rest; other lists are replaced). replace=true
    replaces it entirely. instrument == instrument count adds a new one. Saves the song.

    FM operator order: on 4-op chips (OPN/OPM/OPZ, 4-op OPL) "operators" is in
    register order S1, S3, S2, S4, not the algorithm order the GUI shows. So for
    alg 4 (S1->S2, S3->S4) the carriers are operators[2] and operators[3], and
    operators[0] modulates operators[2]. Check which ops are carriers before
    touching tl: lower modulator tl = brighter, lower carrier tl = louder."""
    p = _path(path)
    s = _load(p)
    ins = fsong.update_instrument(s, instrument, changes, replace)
    note = _save(p, s)
    return json.dumps(ins, indent=1) + note


@_tool(_READ)
def render(order_start: int = 0, order_end: int | None = None,
           per_channel: bool = False, subsong: int = 0, path: str = "") -> str:
    """Render orders order_start..order_end (inclusive; default the whole song, which
    is slow for long songs) to WAV and return a listen report: loudness, clipping,
    silence, spectral centroid and band energy. per_channel adds one report per channel.
    Note: effects that jump outside the range, or state set before order_start, may
    sound different in an excerpt."""
    p = _path(path)
    s = _load(p)
    sub = fsong.subsong(s, subsong)
    end = sub.get("orderLength", 1) - 1 if order_end is None else order_end
    ex = fsong.excerpt(s, subsong, order_start, end)
    out = _render_dir() / f"{p.stem}_s{subsong}_o{order_start:02X}-{end:02X}.wav"
    (_, wav), = fsong.render(ex, out)
    lines = [f"wav: {wav}", analysis.format_report("mix", analysis.analyze(wav))]
    if per_channel:
        chdir = out.with_name(out.stem + "_ch")
        shutil.rmtree(chdir, ignore_errors=True)
        chdir.mkdir()
        labels = fsong.channel_labels(s)
        files = fsong.render(ex, chdir / "ch.wav", per_channel=True)
        for i, f in files:
            label = labels[i] if i < len(labels) else ""
            lines.append(analysis.format_report(f"ch{i} {label}", analysis.analyze(f)))
        missing = sorted(set(range(len(labels))) - {i for i, _ in files})
        if missing:
            lines.append("not rendered separately: " + ", ".join(f"ch{i}" for i in missing))
    return "\n".join(lines)


@_tool(_EDIT)
def export(output: str, format: str = "", path: str = "") -> str:
    """Export the song. format: fur, json, vgm, s98, wav, txt (default: from the
    output extension). Writes output; does not change the song."""
    p = _path(path)
    out = Path(output).expanduser().resolve()
    fmt = (format or out.suffix.lstrip(".")).lower()
    flags = {"fur": "-furout", "json": "-jsonout", "vgm": "-vgmout", "s98": "-s98out",
             "wav": "-output", "txt": "-txtout"}
    if fmt not in flags:
        raise ValueError(f"unknown format {fmt!r}; use one of {', '.join(flags)}")
    fsong.run([flags[fmt], out, p], timeout=1800)
    return f"wrote {out} ({out.stat().st_size} bytes)"


if __name__ == "__main__":
    mcp.run()
