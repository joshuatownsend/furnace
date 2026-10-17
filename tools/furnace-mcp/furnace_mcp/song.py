"""Furnace CLI wrapper and song JSON editing.

The server never links against Furnace. It shells out to a console-subsystem
furnace build (-noreport on every call) and edits the song as JSON:
.fur -> -jsonout -> edit -> -furout -> .fur.
"""

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import notation

_REPO = Path(__file__).resolve().parents[3]
_EXE_NAME = "furnace.exe" if os.name == "nt" else "furnace"
# multi-config generators (MSVC, Xcode) put the binary in Release/; single-config
# ones (make, Ninja, MinGW) put it at the top of the build directory
_DEFAULT_EXES = [_REPO / d / sub / _EXE_NAME
                 for d in ("build-gui", "build") for sub in ("Release", ".")]
_LOG_LINE = re.compile(r"^\x1b\[[0-9;]*m\[(\w+)\]\x1b\[m (.*)$")
_IGNORED_ERRORS = ("could not bind text domain",)


class FurnaceError(RuntimeError):
    pass


def furnace_exe():
    if os.environ.get("FURNACE_EXE"):
        candidates = [Path(os.environ["FURNACE_EXE"])]
    else:
        candidates = _DEFAULT_EXES
    for exe in candidates:
        if exe.is_file():
            return exe
    raise FurnaceError(
        "furnace binary not found (looked in " + ", ".join(map(str, candidates)) +
        "). Build the console-subsystem Release build or set FURNACE_EXE.")


def run(args, timeout=600):
    """Run furnace with -noreport. Returns stdout with log lines removed."""
    cmd = [str(furnace_exe()), "-noreport", "-loglevel", "warning", *map(str, args)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise FurnaceError(f"furnace timed out after {timeout}s")
    out, errors = [], []
    for line in (p.stdout + p.stderr).splitlines():
        m = _LOG_LINE.match(line)
        if m:
            level, msg = m.groups()
            if level == "ERROR" and not any(s in msg for s in _IGNORED_ERRORS):
                errors.append(msg)
        else:
            out.append(line)
    if p.returncode != 0:
        detail = "; ".join(errors) or "\n".join(out[-5:])
        raise FurnaceError(f"furnace exited {p.returncode}: {detail}")
    return "\n".join(out)


def info(path, subsong=None):
    args = ["-info"]
    if subsong is not None:
        args += ["-subsong", subsong]
    return run([*args, path]).strip()


def load(path):
    """Load any song furnace can open, as the JSON dict -jsonout produces."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "song.json"
        run(["-jsonout", out, path])
        return json.loads(out.read_text(encoding="utf-8"))


def save(song, path):
    """Write the song to path (.fur or .json). Furnace validates it on the way."""
    path = Path(path)
    # the finished file is staged next to the song so the final rename stays
    # on one filesystem (the temp dir may be on another drive)
    tmp = path.with_name(f".{path.stem}.furnace-mcp-tmp" +
                         (".json" if path.suffix.lower() == ".json" else ".fur"))
    try:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "song.json"
            src.write_text(json.dumps(song), encoding="utf-8")
            if tmp.suffix == ".json":
                run(["-info", src])  # load check: rejects anything loadJSON rejects
                shutil.copyfile(src, tmp)
            else:
                run(["-furout", tmp, src])
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def render(song, wav_path, per_channel=False):
    """Render a song dict to WAV. Returns [(channel or None, path)].

    Per-channel renders name files <stem>_cNN.wav (1-based) and can skip
    channels, so the channel comes from the file name, not the position."""
    wav_path = Path(wav_path)
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "song.json"
        src.write_text(json.dumps(song), encoding="utf-8")
        args = ["-loops", 0, "-output", wav_path]
        if per_channel:
            args += ["-outmode", "perchan"]
        run([*args, src], timeout=1800)
    if per_channel:
        out = []
        for f in wav_path.parent.glob(wav_path.stem + "_c*.wav"):
            m = re.fullmatch(re.escape(wav_path.stem) + r"_c(\d+)\.wav", f.name)
            if m:
                out.append((int(m.group(1)) - 1, f))
        return sorted(out)
    return [(None, wav_path)]


# --- the song open in Furnace -------------------------------------------

def furnace_config_dir():
    """Where the Furnace GUI keeps its config (DivEngine::initConfDir)."""
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "furnace"
    if sys.platform == "darwin":
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home()
        return Path(base) / "Library" / "Application Support" / "Furnace"
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "furnace"


def _process_running(pid):
    if os.name == "nt":
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # access denied: it exists
        try:
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_state(f):
    # Furnace replaces the file by renaming it; on Windows a read can collide
    # with the rename, so retry briefly before giving up
    for attempt in range(10):
        try:
            return f.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            raise
        except OSError:
            if attempt == 9:
                raise
            time.sleep(0.05)


def open_song():
    """(path, has_unsaved_changes, reload_count) for the song open in the Furnace GUI.

    Each fork GUI process writes <config>/open-song-<pid>.txt (path; 0/1 for
    unsaved changes; how many times it reloaded the song after an outside
    change; when its window last gained focus, in ms) and deletes it on exit.
    Files whose process is gone were left by a crash and are ignored; with
    several Furnace windows open, the one focused last wins. Raises
    FurnaceError if nothing usable is open."""
    best = None
    for f in furnace_config_dir().glob("open-song-*.txt"):
        m = re.fullmatch(r"open-song-(\d+)\.txt", f.name)
        if not m or not _process_running(int(m.group(1))):
            continue
        try:
            lines = _read_state(f)
        except FileNotFoundError:
            continue  # that Furnace just exited
        if len(lines) < 4 or not lines[3].strip().isdigit():
            continue
        focus = int(lines[3])
        if best is None or focus > best[0]:
            best = (focus, lines)
    if best is None:
        raise FurnaceError(
            "Furnace isn't running (or is an older build without open-song sync). "
            "Ask the user which song file to use.")
    lines = best[1]
    path = lines[0].strip()
    modified = lines[1].strip() == "1"
    reloads = int(lines[2]) if lines[2].strip().isdigit() else None
    if not path:
        raise FurnaceError(
            "the song open in Furnace has never been saved (or is a recovery backup), "
            "so it has no file to edit. Ask the user to save it (File > Save As) first.")
    return Path(path), modified, reloads


# --- song structure -------------------------------------------------------

def subsong(song, index):
    subs = song.get("subsongs") or []
    if not 0 <= index < len(subs):
        raise IndexError(f"sub-song {index} does not exist (song has {len(subs)})")
    return subs[index]


def channel_labels(song):
    """One label per channel, e.g. 'YM2612 #3' (chip short name + 1-based index)."""
    labels = []
    for chip in song.get("chips", []):
        name = chip.get("name", "chip")
        words = re.sub(r"\s*\(.*?\)", "", name).split()
        # the part number names the chip best: "Yamaha YM2612 ..." -> YM2612
        short = next((w for w in words if re.search(r"[A-Za-z]", w) and re.search(r"\d", w)), name)
        for k in range(chip.get("channels", 0)):
            labels.append(f"{short} #{k + 1}")
    return labels


def _parse_channels(spec, nchans):
    if spec is None or spec == "":
        return list(range(nchans))
    if isinstance(spec, int):
        spec = [spec]
    if isinstance(spec, str):
        out = []
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-")
                out += range(int(a), int(b) + 1)
            elif part:
                out.append(int(part))
        spec = out
    for c in spec:
        if not 0 <= c < nchans:
            raise IndexError(f"channel {c} out of range (0-{nchans - 1})")
    return list(spec)


def _pattern(sub, ch, index, create=False):
    pats = sub.setdefault("patterns", [])
    while len(pats) <= ch:
        pats.append([])
    chpats = pats[ch]
    if index >= len(chpats) or chpats[index] is None:
        if not create:
            return None
        while len(chpats) <= index:
            chpats.append(None)
        chpats[index] = {"rows": []}
    return chpats[index]


def _effect_cols(sub, ch):
    cd = sub.get("channelData") or []
    return cd[ch].get("effectColumns", 1) if ch < len(cd) else 1


def read_patterns(song, sub_index=0, order_start=0, order_end=None, channels=None, skip_empty=True):
    """Tracker text for a window of orders x channels. skip_empty drops rows that are
    empty in every shown channel (row numbers stay, so gaps are visible)."""
    sub = subsong(song, sub_index)
    nchans = len(sub.get("orders") or [])
    chans = _parse_channels(channels, nchans)
    olen = sub.get("orderLength", 0)
    if order_end is None:
        order_end = order_start
    order_end = min(order_end, olen - 1)
    if not 0 <= order_start <= order_end:
        raise IndexError(f"order range {order_start}-{order_end} invalid (song has {olen} orders)")
    plen = sub.get("patternLength", 64)
    labels = channel_labels(song)
    cols = {c: _effect_cols(sub, c) for c in chans}
    out = []
    for o in range(order_start, order_end + 1):
        pats = [sub["orders"][c][o] for c in chans]
        out.append(f"== order {o:02X} ==")
        out.append("row | " + " | ".join(
            f"ch{c} {labels[c] if c < len(labels) else ''} pat {p:02X}" for c, p in zip(chans, pats)))
        grid = []
        for c, p in zip(chans, pats):
            pat = _pattern(sub, c, p)
            rows = (pat or {}).get("rows", [])
            grid.append([notation.format_row(rows[r] if r < len(rows) else {}, cols[c]) for r in range(plen)])
        for r in range(plen):
            if skip_empty and all(col[r].replace(".", "").strip() == "" for col in grid):
                continue
            out.append(f"{r:02X}  | " + " | ".join(col[r] for col in grid))
    return "\n".join(out)


def write_rows(song, sub_index, channel, pattern, start_row, text):
    """Replace rows of one channel's pattern from tracker text.

    Returns the order indices that play this pattern on this channel."""
    sub = subsong(song, sub_index)
    nchans = len(sub.get("orders") or [])
    if not 0 <= channel < nchans:
        raise IndexError(f"channel {channel} out of range (0-{nchans - 1})")
    if not 0 <= pattern <= 255:
        raise IndexError("pattern index must be 0-255")
    plen = sub.get("patternLength", 64)
    lines = text.strip("\n").split("\n")
    if start_row < 0 or start_row + len(lines) > plen:
        raise IndexError(f"rows {start_row}..{start_row + len(lines) - 1} exceed pattern length {plen}")
    parsed = []
    for i, line in enumerate(lines):
        # tolerate a leading row number like "1F |" or "1F  "
        line = re.sub(r"^\s*[0-9A-Fa-f]{2}\s*\|\s*", "", line)
        try:
            parsed.append(notation.parse_row(line))
        except notation.NotationError as e:
            raise notation.NotationError(f"line {i + 1}: {e}")
    pat = _pattern(sub, channel, pattern, create=True)
    rows = pat.setdefault("rows", [])
    while len(rows) < plen:
        rows.append({})
    for i, row in enumerate(parsed):
        rows[start_row + i] = row
    need = max((len(r.get("effects", [])) for r in parsed), default=0)
    cd = sub.get("channelData") or []
    if channel < len(cd) and need > cd[channel].get("effectColumns", 1):
        cd[channel]["effectColumns"] = need
    return [o for o in range(sub.get("orderLength", 0)) if sub["orders"][channel][o] == pattern]


def set_order(song, sub_index, order, patterns):
    """Set pattern indices for one order row. order == orderLength appends a row.

    patterns: {channel: pattern} (unlisted channels keep their value, or 0 on a new row)."""
    sub = subsong(song, sub_index)
    olen = sub.get("orderLength", 0)
    orders = sub["orders"]
    if not 0 <= order <= olen:
        raise IndexError(f"order {order} out of range (0-{olen}; {olen} appends)")
    if order == olen:
        if olen >= 256:
            raise IndexError("song already has 256 orders")
        for ch in orders:
            ch.append(0)
        sub["orderLength"] = olen + 1
    for ch, p in patterns.items():
        ch = int(ch)
        if not 0 <= ch < len(orders):
            raise IndexError(f"channel {ch} out of range")
        if not 0 <= p <= 255:
            raise IndexError("pattern index must be 0-255")
        orders[ch][order] = p
        _pattern(sub, ch, p, create=True)
    return [orders[c][order] for c in range(len(orders))]


def excerpt(song, sub_index, order_start, order_end):
    """A copy of the song that plays only orders order_start..order_end of one sub-song."""
    sub = subsong(song, sub_index)
    olen = sub.get("orderLength", 0)
    order_end = min(order_end, olen - 1)
    if not 0 <= order_start <= order_end:
        raise IndexError(f"order range {order_start}-{order_end} invalid (song has {olen} orders)")
    out = {k: v for k, v in song.items() if k != "subsongs"}
    s = dict(sub)
    s["orders"] = [ch[order_start:order_end + 1] for ch in sub["orders"]]
    s["orderLength"] = order_end - order_start + 1
    out["subsongs"] = [s]
    return out


# --- instruments ----------------------------------------------------------

def instrument(song, index):
    ins = song.get("instruments") or []
    if not 0 <= index < len(ins):
        raise IndexError(f"instrument {index} does not exist (song has {len(ins)})")
    return ins[index]


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        elif k == "operators" and isinstance(v, list) and isinstance(dst.get(k), list) and all(
                isinstance(x, dict) for x in v):
            # merge by position; operators the update leaves out stay as they are
            ops = dst[k]
            for i, s in enumerate(v):
                if i < len(ops) and isinstance(ops[i], dict):
                    _merge(ops[i], s)
                elif i < len(ops):
                    ops[i] = copy.deepcopy(s)
                else:
                    ops.append(copy.deepcopy(s))
        else:
            dst[k] = copy.deepcopy(v)


def update_instrument(song, index, changes, replace=False):
    """Merge changes into instrument index (or append when index == count)."""
    ins = song.setdefault("instruments", [])
    if index == len(ins):
        ins.append({"name": "New Instrument", "type": 0})
    inst = instrument(song, index)
    if replace:
        ins[index] = copy.deepcopy(changes)
    else:
        _merge(inst, changes)
    song.setdefault("songInfo", {})["instrumentCount"] = len(ins)
    return ins[index]


# --- one-note previews (idea 004) -----------------------------------------

PREVIEW_ROW_SECONDS = 0.1  # speed 6 at 60 Hz, virtual tempo 1:1


def instrument_channel(song, index, sub_index=0):
    """The channel that plays instrument index most often (None if it's unused).
    Only patterns the order list plays count, once per time they're played:
    songs keep stale patterns that would point at the wrong channel or chip."""
    sub = subsong(song, sub_index)
    patterns = sub.get("patterns") or []
    counts = {}
    for ch, order in enumerate(sub.get("orders") or []):
        pats = patterns[ch] if ch < len(patterns) else []
        for o in range(sub.get("orderLength", len(order))):
            pat = pats[order[o]] if order[o] < len(pats) else None
            for row in (pat or {}).get("rows") or []:
                if row.get("ins") == index:
                    counts[ch] = counts.get(ch, 0) + 1
    return max(counts, key=counts.get) if counts else None


def preview_song(song, index, note, channel, hold_rows=8, release_rows=8, volume=None, sub_index=0):
    """A copy of the song that plays one note of instrument index on channel and
    nothing else: note at row 0, note off after hold_rows, then release_rows of
    silence. Timing is pinned so a row lasts exactly PREVIEW_ROW_SECONDS."""
    instrument(song, index)
    sub = subsong(song, sub_index)
    nchans = len(sub.get("orders") or [])
    if not 0 <= channel < nchans:
        raise IndexError(f"channel {channel} out of range (0-{nchans - 1})")
    if not 0 <= note <= 179:
        raise ValueError(f"note {note} out of range (0-179)")
    length = hold_rows + release_rows
    if hold_rows < 1 or release_rows < 0 or length > 256:
        raise ValueError("hold_rows must be at least 1, and hold + release at most 256 rows")
    out = {k: copy.deepcopy(v) for k, v in song.items() if k != "subsongs"}
    s = {k: copy.deepcopy(v) for k, v in sub.items() if k not in ("patterns", "orders")}
    s.update(speeds=[6], tickRate=60.0, virtualTempo=[150, 150], patternLength=length,
             orderLength=1, orders=[[0] for _ in range(nchans)],
             patterns=[[] for _ in range(nchans)])
    s.pop("grooves", None)
    rows = [{} for _ in range(length)]
    rows[0] = {"note": note, "ins": index}
    if volume is not None:
        rows[0]["vol"] = volume
    if hold_rows < length:
        # === rather than OFF: OFF stops macros, === runs their release part too
        rows[hold_rows] = {"note": 254}
    s["patterns"][channel] = [{"rows": rows}]
    out["subsongs"] = [s]
    return out, hold_rows * PREVIEW_ROW_SECONDS
