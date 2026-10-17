# 003 — Compose and tune instruments with Claude through an MCP server

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/main.cpp src/engine/fileOps/json.cpp`. If these changed materially (for example, ideas 001/002 landed), update the plan before starting.

- **Status**: IN PROGRESS (branch `idea/003-mcp-server`, brief refreshed 2026-10-16 at `268424509`)
- **Verdict**: Validate
- **Score**: 7/10 (see ideas/README.md)
- **Lenses**: inside-out (Signal 4, adjacent possible) / outside-in (interview)
- **Effort (coarse)**: M once 001 and 002 exist
- **Planned at**: 5b9c00314 on 2026-10-15

## The idea

A small MCP server, running as a separate process, that lets Claude work on Furnace songs. Proposed tools:
- `inspect_song`: summary, duration, chips.
- `read_song` / `write_song`: JSON.
- `edit_pattern`, `edit_instrument`.
- `render`: audio file plus a listen report (idea 004).
- `export`: VGM/S98/.fur.

Josh describes what he wants ("a punchy OPN2 bass, 4 bars of it under this melody"), Claude edits the song, renders it, checks it, and hands back a .fur to open in Furnace.

## Who wants this and why now

- **Josh's stated killer feature**: "drive music creation and chip creation/tuning through Claude with API/MCP" (interview, 2026-10-15).
- **Indirect**: upstream's piano-roll and DAW-user requests (#2311 "I really struggle with tracker", #2480) show people want to compose without the tracker grid. Describing music in words is another route around it.

## Why this project, why cheap

- The CLI already loads any supported file and renders audio (`src/main.cpp:637` `-output`), VGM (`:644`), ROM (`:647`) and text (`:649`).
- With 002 (`-jsonout`, `-furout`, richer `-info`) and 001 (JSON import), an MCP server only needs to shell out to the CLI. No in-process changes, so merge cost stays low.
- **On Windows**, the server must call a console-subsystem build. The default GUI build prints nothing to stdout, and the headless build doesn't compile with MSVC. Use `-DCONSOLE_SUBSYSTEM=ON` (see 002's maintenance notes). Pass `-noreport` on every call, or errors open a blocking message box.
- The engine also has `noteOn()` (`engine.h:1948`) and `synchronized()` (`engine.h:2172`) if live control is ever wanted (see sibling).

## Trade-offs and risks

- **No recurring use is evidenced yet.** Josh skipped the workflow and frustration questions, so the spike must establish what a real session looks like.
- **Claude can't hear.** Instrument tuning depends on idea 004's text report. Whether that's enough is the main technical question.
- **Musical quality.** Pattern data is note/instrument/volume/effect columns, which an LLM can write. Whether the result is musically good is a judgement only Josh can make.
- **Sibling, parked**: an in-process live server inside the running GUI, so edits play immediately. It needs a networking library (`extern/asio` is the Steinberg ASIO audio SDK, not networking) and edits to `gui.cpp`. Revisit only if the external version feels too slow.
- **Upstream**: will never accept this (CONTRIBUTING.md AI policy). It's fork-only by design.

## Refresh (2026-10-16, after 001 and 002 merged)

Drift check: `main.cpp` +193 lines, `json.cpp` +706 lines since planning. Both are additions this brief was waiting for, not conflicts. What changed for the plan:

- **Available now**: `-jsonout` / `-jsonpretty` (002), `.json` input (001), `-furout`, `-s98out`, `-vgmver`, `-info` with per-sub-song TIMING (`-subsong N`), `-outmode perchan` (one WAV per channel), and exit status 1 on any export failure. Step 4's `.fui` stopgap is no longer needed: the write path is JSON → `-furout`.
- **Measured on `demos/genesis/All Good Times.fur`** (143 s, 13 channels, Release build):
  - `-info`: 0.24 s. `-jsonout`: 0.42 s. `-txtout`: 0.37 s.
  - `-output` WAV: 24.8 s (about 6× real time). A full render is too slow for every edit. A 4–8 bar excerpt (a few seconds of audio) renders in about a second.
- **Size is the real constraint**: the JSON is 644 KB and `-txtout` is 1.1 MB, far too large for Claude to read whole. The server must give windowed views (a range of orders × chosen channels) in compact tracker text, and edit the JSON itself. This answers open question 3: neither raw JSON nor `-txtout`.
- **Note numbering**: JSON notes use Furnace numbers (60 = C-0, middle C = C-4 = 108; 253 off, 254 release, 255 macro release). The compact view shows note names, so Claude never handles raw numbers.
- **CLI log noise**: config-load logs print to stdout before `-loglevel` takes effect. The server strips ANSI-prefixed log lines.
- **No listen report yet**: 004 is not built. The server includes a small built-in analysis (peak, RMS, clipping, silence, spectral centroid and band energy, overall and per channel via `-outmode perchan`). That is enough for step 5's "brighter" test.
- **Decided (open question 5)**: Python with the official MCP SDK 2.x (`MCPServer`, stdio), run with `uv`, in this repo under `tools/furnace-mcp/`. The Furnace binary comes from `FURNACE_EXE`, defaulting to `build-gui/Release/furnace.exe`, the console-subsystem build. Fork-only, outside the C++ build.

### Prototype tool set

| Tool | Wraps | Notes |
|---|---|---|
| `inspect_song` | `-info` | Chips, channels, instruments, samples, timing. Log lines stripped. |
| `read_patterns` | `-jsonout` + server-side view | Order range × channels as tracker text (`C-4 0C 7F EC01`), with pattern indices per order. |
| `write_rows` | JSON edit → `-furout` | Writes rows into one channel's pattern from tracker text. Reports which other orders share that pattern. |
| `set_order` | JSON edit | Points an order row at pattern indices; can append orders. |
| `read_instrument` / `write_instrument` | JSON | Instrument JSON with default-noise (empty sample map, empty macros) removed; partial updates merge. |
| `render` | `-output` (excerpt via trimmed JSON) | Renders an order range, returns the WAV path and the analysis. |
| `export` | `-vgmout` / `-s98out` / `-furout` / `-jsonout` | |

Edits are made in place on the song file, after a one-time `.bak` copy per session.

## Prototype results (2026-10-16)

The prototype is in `tools/furnace-mcp/` and registered for Claude Code in `.mcp.json`. All eight tools work over stdio. There are 26 tests: notation units, plus end-to-end tests through the MCP protocol against the real binary.

- **Speed (step 2)**: `inspect_song` 0.6 s. `read_patterns` under 0.1 s (cached). `write_rows` 0.4 s. `render` of one order (4–5 s of audio) 1.2 s; with `per_channel`, about 8 s for 13 channels.
- **Pitch check**: on the YM2612, C-4 = 261 Hz and A-4 = 439 Hz, which confirms the note numbering end to end. On this song's SN76489, A-4 rendered at 1748 Hz, two octaves up, probably a chip clock or song setting. The listen report's `strongest_hz` is how Claude catches this kind of surprise, and it should check after writing a part on a chip it hasn't used yet.
- **Per-channel renders can skip channels**: the extended-channel-3 operator channels (3–5 here) don't render separately. The report lists them as "not rendered separately".
- **Tuning (step 5, first pass)**: "make 0C 'Slap' brighter" by lowering the modulator TL (alg 3, op 4 is the only carrier) moved the spectral centroid from 145 Hz to 341 Hz (−6) to 783 Hz (−12). Text feedback does track the change in the expected direction. Whether the result sounds good is still Josh's call (open question 4).
- **First real session (Josh, 2026-10-16)**: Josh opened a song in Furnace and asked for "horns/trumpet blasting a victory type tune". Claude made a new song instead, because the server couldn't see what Furnace had open. Fixed with **open-song sync**, chosen by Josh over "just name the file" and the parked live link. It's a small fork-only change in `src/gui/gui.cpp`: the GUI publishes the open file's path, unsaved state and a reload count to `<config>/open-song.txt`, and reloads the file when it changes on disk, asking first if there are unsaved edits. Tool paths now default to the open song, and edits are refused while Furnace has unsaved changes. Measured live: about 2 s from an edit to the reloaded song on screen.
- **Furnace drops unused patterns on save** (`saveUnusedPatterns` defaults off), so rows written to a pattern no order plays disappeared. `write_rows` now requires the pattern to be placed with `set_order` first, and the server re-reads the file after each save so its view matches the disk.
- **FM operator order**: the JSON stores 4-op FM operators in register order (S1, S3, S2, S4). The first session hit this while tuning a trumpet patch, and it's now in the instrument tools' descriptions.
- **Still needs Josh (steps 1 and 5)**: open a copy of a song in Claude Code with this server, ask for a part ("add a bass line under order 00–03", "make the lead brighter"), open the result in Furnace and judge it.

## Open questions

1. What does one real session look like for Josh? A new song from scratch, extending an existing one, or tuning one instrument?
2. ~~Is the CLI round trip fast enough?~~ Edits take under 1 s. A full render takes 25 s, so render excerpts (see Refresh).
3. ~~Which representation?~~ Windowed compact tracker text, generated by the server from JSON (see Refresh).
4. Can instrument tuning converge with only text feedback from 004, or does it need Josh in the loop listening?
5. ~~Language and location?~~ Python plus MCP SDK 2.x, under `tools/furnace-mcp/`.
6. How does Josh hear results: open the .fur in Furnace, or have the server play the rendered WAV?

## Spike plan

1. **Manual walkthrough, no code.** Pick a demo song, export it with `-txtout` (and `-jsonout` if 002 has landed), and ask Claude in a normal session to add a bass line. Hand-apply the edit in the GUI. *You'll know when* you have a rough idea of how much of Claude's output is musically usable.
2. **Time the loop.** Measure `furnace -output` render time for a 30-second song. *You'll know when* you have seconds per render.
3. **Thin MCP prototype** with three tools: `inspect_song` (wraps `-info`), `render` (wraps `-output`), `read_song` (wraps `-txtout` or `-jsonout`). Register it in Claude Code. *You'll know when* Claude can describe and render a demo song from chat.
4. **Write path.** `write_rows`, `set_order` and `write_instrument` edit the JSON and save it back with `-furout`. *You'll know when* Claude changes a song and the change is audible in Furnace.
5. **One tuning attempt**: "make instrument 3 brighter", using 004's report or a rough FFT done in the server. *You'll know when* you can say whether the text-only loop converged.

## Decision criteria

- **Build it**: Josh finds step 1's output worth continuing, each render takes a few seconds or less, and step 5 converges at least sometimes.
- **Reshape it**: composing works but tuning doesn't. Ship composing tools first and keep Josh in the loop for tuning.
- **Drop it**: step 1's output is musically unusable even with editing.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\003-claude-mcp-server.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: prove or disprove that Claude can compose and tune instruments in Furnace through a thin MCP server wrapping the Furnace CLI. Do not build beyond the spike; prototype work happens behind a flag or on a branch.
```
