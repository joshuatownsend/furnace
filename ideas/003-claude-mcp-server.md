# 003 — Compose and tune instruments with Claude through an MCP server

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/main.cpp src/engine/fileOps/json.cpp`. If these changed materially (for example, ideas 001/002 landed), update the plan before starting.

- **Status**: SELECTED
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

## Open questions

1. What does one real session look like for Josh? A new song from scratch, extending an existing one, or tuning one instrument?
2. Is the CLI round trip fast enough per edit (load + render seconds) for an interactive loop?
3. Which representation does Claude edit best: raw JSON, or a compact tracker text such as the `-txtout` format or a custom one?
4. Can instrument tuning converge with only text feedback from 004, or does it need Josh in the loop listening?
5. Which language should the MCP server use (Python or Node), and where does it live: in this repo under `tools/`, or separately?
6. How does Josh hear results: open the .fur in Furnace, or have the server play the rendered WAV?

## Spike plan

1. **Manual walkthrough, no code.** Pick a demo song, export it with `-txtout` (and `-jsonout` if 002 has landed), and ask Claude in a normal session to add a bass line. Hand-apply the edit in the GUI. *You'll know when* you have a rough idea of how much of Claude's output is musically usable.
2. **Time the loop.** Measure `furnace -output` render time for a 30-second song. *You'll know when* you have seconds per render.
3. **Thin MCP prototype** with three tools: `inspect_song` (wraps `-info`), `render` (wraps `-output`), `read_song` (wraps `-txtout` or `-jsonout`). Register it in Claude Code. *You'll know when* Claude can describe and render a demo song from chat.
4. **Write path.** If 001 is done, add `write_song`. If not, test patching a single instrument via `.fui` import as a stopgap. *You'll know when* Claude changes a song and the change is audible in Furnace.
5. **One tuning attempt**: "make instrument 3 brighter", using 004's report or a rough FFT done in the server. *You'll know when* you can say whether the text-only loop converged.

## Decision criteria

- **Build it**: Josh finds step 1's output worth continuing, each render takes a few seconds or less, and step 5 converges at least sometimes.
- **Reshape it**: composing works but tuning doesn't. Ship composing tools first and keep Josh in the loop for tuning.
- **Drop it**: step 1's output is musically unusable even with editing.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\003-claude-mcp-server.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: prove or disprove that Claude can compose and tune instruments in Furnace through a thin MCP server wrapping the Furnace CLI. Do not build beyond the spike; prototype work happens behind a flag or on a branch.
```
