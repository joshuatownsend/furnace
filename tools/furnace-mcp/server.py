"""Furnace MCP server: lets Claude read, edit, render and export Furnace songs.

Run with:  uv run --project tools/furnace-mcp tools/furnace-mcp/server.py
Edits are saved in place; the first edit to a file in a session copies it to
<name>.bak<ext> first.
"""

import functools
import hashlib
import json
import math
import os
import shutil
import tempfile
import time
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from furnace_mcp import analysis, notation, scheme as fscheme, song as fsong, video

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
_loaded_rev = {}  # path -> file revision when its song was last read


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


def _revision(path):
    """The file's contents, hashed. Modification times can't be trusted here:
    on coarse-timestamp filesystems (FAT/exFAT, some network shares) two saves
    within one tick keep the same time. Streamed, since sample-heavy songs can
    be large."""
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _load(path):
    key = str(path)
    # taken before loading: if the file changes in between, the revision is
    # the older one and the next save is refused rather than overwriting
    rev = _revision(path)
    _loaded_rev[key] = rev
    hit = _cache.get(key)
    if hit and hit[0] == rev:
        return json.loads(hit[1])
    song = fsong.load(path)
    _cache[key] = (rev, json.dumps(song))
    return song


def _save(path, song):
    _check_not_dirty(path)
    # the song must still be the revision this edit was made on; otherwise
    # (e.g. the user saved in Furnace meanwhile) writing would discard that save
    if _revision(path) != _loaded_rev.get(str(path)):
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


_pitch_cache = {}  # probe song -> what its written A-4 sounded like


def _octaves(n):
    return f"{n} octave{'s' if n != 1 else ''}"


def _pitch_line(s, subsong=0):
    """What a written A-4 sounds like on each chip of song s, measured."""
    a4 = float((s.get("songInfo") or {}).get("tuning") or 440.0)
    parts = []
    for ci, name, ch, probe, on, off in fsong.pitch_probes(s, subsong):
        if isinstance(probe, str):
            parts.append(f"{name}: not measured ({probe})")
            continue
        key = hashlib.sha1(json.dumps(probe, sort_keys=True).encode("utf-8")).hexdigest()
        if key not in _pitch_cache:
            (_, wav), = fsong.render(probe, _render_dir() / f"pitchprobe_{key[:12]}.wav")
            r = analysis.analyze_note(wav, fsong.PROBE_NOTE, note_off_s=off, a4=a4, note_on_s=on)
            pitch = r.get("pitch") or {}
            _pitch_cache[key] = None if r.get("silent") or not pitch.get("hz") or pitch.get("uncertain")                 else (pitch["hz"], pitch["cents"])
        got = _pitch_cache[key]
        if got is None:
            parts.append(f"{name}: not measured (the probe note had no clear pitch)")
            continue
        hz, cents = got
        octs = round(cents / 1200)
        rest = cents - 1200 * octs
        if octs == 0:
            what = "as written"
        else:
            what = (f"{_octaves(abs(octs))} {'up' if octs > 0 else 'down'}: write "
                    f"{_octaves(abs(octs))} {'lower' if octs > 0 else 'higher'} than the pitch you want")
        if abs(rest) >= 20:
            what += f" ({abs(rest):.0f} cents {'sharp' if rest > 0 else 'flat'})"
        parts.append(f"{name} (channel {ch}): {hz:.0f} Hz, {what}")
    return "pitch, what a written A-4 sounds like on each chip: " + "; ".join(parts) if parts else ""


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
    pattern length, speed, duration, instruments and samples, and what a written
    A-4 sounds like on each chip. Furnace keeps each chip's traditional octave
    naming, so a written note can sound octaves away from its name (an SN76489
    PSG plays two octaves up, NES one; FM chips as written): write parts at the
    octave the pitch line says. The first call per chip setup renders one probe
    note per chip (about a second each)."""
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
            f"{i:02X} {ins.get('name', '')!r} (type {ins.get('type')})" for i, ins in enumerate(s.get("instruments") or [])),
        "samples: " + ", ".join(
            f"{i:02X} {smp.get('name', '')!r}" for i, smp in enumerate(s.get("samples") or [])),
        f"wavetables: {len(s.get('wavetables') or [])}",
        _pitch_line(s, subsong),
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
    # the path hash keeps same-named songs in different folders apart
    tag = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:8]
    out = _render_dir() / f"{p.stem}_{tag}_s{subsong}_o{order_start:02X}-{end:02X}.wav"
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


@_tool(_READ)
def preview_instrument(instrument: int, note: str = "C-4", channel: int = -1,
                       hold_rows: int = 8, release_rows: int = 8, subsong: int = 0,
                       path: str = "") -> str:
    """Play one note of an instrument on its own and return a listen report: pitch
    (Hz and cents from the note played), envelope (attack, decay, sustain, release),
    peak loudness, the first 8 harmonics in dB relative to the strongest of them, and
    brightness (spectral centroid as a multiple of the fundamental). Use it to check
    an instrument edit: preview before, write_instrument, preview again, compare.
    The envelope is reliable, and so is pitch. When the pitch tracker can't find
    the note (all carriers above mult 1 can fool it), the report says "tracker
    unsure" and gives the tuning from the partials instead, against the note
    played. Harmonics and brightness show what changed, but
    don't predict their direction from FM theory (more feedback can make a patch
    darker): go by the measured change, and ask the user to confirm tone by ear.
    The note is held for hold_rows (0.1 s each), then released for release_rows.
    channel -1 picks the channel that uses the instrument most in the song (pass one
    explicitly for an unused instrument; it must be a channel of the instrument's
    chip). Doesn't change the song."""
    p = _path(path)
    s = _load(p)
    n = notation.parse_note(note)
    a4 = float((s.get("songInfo") or {}).get("tuning") or 440.0)
    if not 25 <= analysis.note_hz(n, a4) <= 4000:
        raise ValueError(f"{note} is {analysis.note_hz(n, a4):.1f} Hz; the listen report measures "
                         "pitch between 25 Hz and 4 kHz (G#0 to B-7 at A=440)")
    if channel < 0:
        found = fsong.instrument_channel(s, instrument, subsong)
        if found is None:
            raise ValueError(f"instrument {instrument:02X} isn't used in the song; pass a channel "
                             "that belongs to its chip (inspect_song lists the channels)")
        channel = found
    preview, on, off = fsong.preview_song(s, instrument, n, channel, hold_rows, release_rows,
                                      sub_index=subsong)
    tag = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:8]
    # the instrument's settings are in the name, so the preview after an edit
    # doesn't overwrite the one before it: both stay for an A/B by ear
    ver = hashlib.sha1(json.dumps([fsong.instrument(s, instrument), hold_rows, release_rows],
                                  sort_keys=True).encode("utf-8")).hexdigest()[:6]
    out = (_render_dir() / f"{p.stem}_{tag}_ins{instrument:02X}_{ver}_"
                           f"{note.replace('#', 's')}_c{channel}.wav")
    (_, wav), = fsong.render(preview, out)
    name = fsong.instrument(s, instrument).get("name", "")
    label = fsong.channel_labels(s)[channel]
    head = (f"instrument {instrument:02X} {name!r}, {note} on channel {channel} ({label}), "
            f"held {off - on:g} s then released\nwav: {wav}")
    return head + "\n" + analysis.format_note_report(analysis.analyze_note(wav, n, note_off_s=off, a4=a4,
                                                                                note_on_s=on))


def _sample_pitch(s, index):
    """(sample, header line, detection, tuning or None) for sample index of song s."""
    smp = fsong.sample(s, index)
    x = fsong.sample_pcm(smp)
    loop = fsong.sample_loop(smp)
    seg, region = analysis.sample_segment(x, loop)
    rate = smp.get("centerRate") or 0
    if rate < 1:
        raise ValueError(f"sample {index:02X} has no center rate")
    det = analysis.detect_pitch(seg, rate)
    a4 = float((s.get("songInfo") or {}).get("tuning") or 440.0)
    tuning = None if det["hz"] is None else analysis.sample_tuning(
        rate, det["period"], fsong.nominal_center_rate(s), a4)
    looped = (f"loop {loop[0]}-{loop[1]} ({fsong.LOOP_MODES[loop[2]] if loop[2] < 3 else loop[2]})"
              if loop else "no loop")
    head = (f"sample {index:02X} {smp.get('name', '')!r}: {fsong.SAMPLE_DEPTHS.get(smp.get('depth'))}, "
            f"{smp.get('samples')} samples, center rate {rate} Hz, {looped}; measured on {region}")
    if tuning and loop and loop[0] >= 2048:
        # a loop that starts late holds the note, but the attack before it is
        # what short notes play, and a loop can be cut slightly off pitch
        body = analysis.detect_pitch(analysis.sample_segment(x[:loop[0]])[0], rate)
        if body["hz"]:
            diff = 1200 * math.log2(body["hz"] / det["hz"])
            if abs(diff) >= 5:
                head += (f"\nnote: the part before the loop plays {abs(diff):.0f} cents "
                         f"{'higher' if diff > 0 else 'lower'} than the loop (it is tuned to the loop)")
    return smp, head, det, tuning


def _plays(t):
    return f"{notation.note_name(t['plays_note'])} {t['plays_cents']:+.1f} cents ({t['plays_hz']:.2f} Hz)"


def _octave_advice(semis):
    if semis % 12:
        return (f"notes sound {abs(semis)} semitones {'up' if semis > 0 else 'down'} from how "
                "they're written")
    octs = semis // 12
    if not octs:
        return "notes play as written"
    return (f"notes sound {_octaves(abs(octs))} {'up' if octs > 0 else 'down'}: write "
            f"{_octaves(abs(octs))} {'lower' if octs > 0 else 'higher'} than the pitch you want")


def _sample_users(s, index):
    """Instruments that start on this sample, flagging arp/pitch macros (which
    shift it again on top of its tuning)."""
    out = []
    for i in fsong.sample_instruments(s, index):
        ins = s["instruments"][i]
        codes = {m.get("code") for m in ins.get("macros") or [] if m.get("data")}
        extra = " and ".join(n for c, n in ((1, "an arp macro"), (4, "a pitch macro")) if c in codes)
        out.append(f"{i:02X} {ins.get('name', '')!r}" + (f" (has {extra}, which shifts it further)" if extra else ""))
    return "used by instruments: " + ", ".join(out) if out else "no instrument starts on it"


@_tool(_READ)
def detect_sample_pitch(sample: int, path: str = "") -> str:
    """Measure the pitch of a sample (8- or 16-bit PCM): what a written C-4 plays,
    as a note and cents, with a confidence (0-1; below 0.7, check by ear). It
    measures the loop if the sample has one (that holds the note), else the
    steady part after the attack. Noise, drums and chords report "no clear
    pitch" instead of a guess. Also says what tune_sample would set the center
    rate to. Doesn't change the song."""
    s = _load(_path(path))
    _, head, det, t = _sample_pitch(s, sample)
    lines = [head]
    if t is None:
        lines.append(f"pitch: no clear pitch: {det['reason']}. Tune it by ear if it needs it.")
    else:
        lines.append(f"pitch: a written C-4 plays {_plays(t)}, confidence {det['confidence']:.2f}"
                     + (" (low: check by ear)" if det["confidence"] < 0.7 else ""))
        lines.append(f"tune_sample would set the center rate to {t['new_rate']} Hz: a written C-4 "
                     f"then plays {notation.note_name(108 + t['target_semitones'])}")
    lines.append(_sample_users(s, sample))
    return "\n".join(lines)


@_tool(_EDIT)
def tune_sample(sample: int, c4_plays: str = "", path: str = "") -> str:
    """Tune a sample (8- or 16-bit PCM) by measuring its pitch and setting its
    center rate, the "Hz" in Furnace's sample editor. By default a written C-4
    then plays the C nearest the sample's own pitch: a recorded E then plays E on
    an E, and the rate moves by half an octave at most (rates far above the
    recording's can exceed what a chip plays). c4_plays (e.g. "C-4", "C-2")
    instead sets the note a written C-4 sounds, transposing the sample.
    Refuses samples with no clear pitch. Saves the song."""
    p = _path(path)
    s = _load(p)
    smp, head, det, t = _sample_pitch(s, sample)
    if t is None:
        raise ValueError(f"{head}\nno clear pitch ({det['reason']}), so nothing was changed. "
                         "Tune it by ear in the sample editor.")
    if c4_plays:
        a4 = float((s.get("songInfo") or {}).get("tuning") or 440.0)
        t = analysis.sample_tuning(smp["centerRate"], det["period"], fsong.nominal_center_rate(s),
                                   a4, c4_plays=notation.parse_note(c4_plays))
    new, old = t["new_rate"], smp["centerRate"]
    if not 100 <= new <= 384000:
        raise ValueError(f"that needs a center rate of {new} Hz, outside what Furnace accepts "
                         "(100-384000); pick a c4_plays nearer the sample's own pitch")
    target = notation.note_name(108 + t["target_semitones"])
    lines = [head, f"was: a written C-4 played {_plays(t)}, confidence {det['confidence']:.2f}"
             + (" (low: check by ear)" if det["confidence"] < 0.7 else "")]
    if new == old:
        lines.append(f"already in tune: a written C-4 plays {target}; nothing changed")
        return "\n".join(lines)
    smp["centerRate"] = new
    note = _save(p, s)
    lines.append(f"center rate {old} -> {new} Hz: a written C-4 now plays {target} "
                 f"({t['residual_cents']:+.2f} cents from rounding the rate to whole Hz); "
                 + _octave_advice(t["target_semitones"]))
    lines.append(_sample_users(s, sample))
    return "\n".join(lines) + note


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


@_tool(_EDIT)
def export_video(output: str, order_start: int = 0, order_end: int | None = None,
                 color: str = "mono", size: str = "1920x1080", fps: int = 60,
                 scheme: str = "", subsong: int = 0, path: str = "") -> str:
    """Make an oscilloscope video (mp4, H.264 + AAC, ready for YouTube): one scope
    per audible channel, steadied on rising edges, with the song as the soundtrack.
    Orders order_start..order_end (inclusive; default the whole song). Slow: each
    channel is rendered separately, then every frame is drawn, so a full song
    takes minutes; try a few orders first. color: "mono" (one wave color) or
    "channel" (each channel's custom color, else one color per chip). scheme: a
    color scheme file from Settings > Color > Export (default: the colors Furnace
    uses now). Channels hidden from Furnace's Channel Oscilloscope are left out.
    Needs ffmpeg on PATH. Writes output; does not change the song."""
    p = _path(path)
    out = Path(output).expanduser().resolve()
    if out.suffix.lower() != ".mp4":
        raise ValueError("output must be an .mp4 file")
    width, height = video.parse_size(size)
    colors = fscheme.read(Path(scheme).expanduser())[0] if scheme else None
    r = video.make_video(_load(p), out, sub_index=subsong, order_start=order_start,
                         order_end=order_end, width=width, height=height, fps=fps,
                         colors=colors, color_mode=color)
    return (f"wrote {r['path']} ({r['bytes']} bytes, {r['seconds']:.1f} s at {fps} fps, "
            f"{r['grid'][0]}x{r['grid'][1]} grid)\nchannels: {', '.join(r['channels'])}"
            + ("" if r["labels"] else "\nno channel labels: Furnace's UI font (res/fonts) is missing"))


if __name__ == "__main__":
    mcp.run()
