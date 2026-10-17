# furnace-mcp

An MCP server that lets Claude read, edit, render and export Furnace songs. Fork-only spike for `ideas/003-claude-mcp-server.md`. It is outside the C++ build and shells out to the Furnace CLI.

## Setup

1. Build Furnace with the console subsystem (Windows): `-DCONSOLE_SUBSYSTEM=ON`, Release, in `build-gui/`. The server uses `build-gui/Release/furnace.exe` unless `FURNACE_EXE` points somewhere else.
2. Install [uv](https://docs.astral.sh/uv/).
3. Claude Code picks the server up from the repo's `.mcp.json` (approve it when asked). To run it by hand:

   ```
   uv run --project tools/furnace-mcp python tools/furnace-mcp/server.py
   ```

## Working on the song open in Furnace

The fork's Furnace (from this branch on) writes the path of the song it has open to `open-song.txt` in its config folder (`%APPDATA%urnace` on Windows), and reloads that file when it changes on disk. So:

- Every tool's `path` is optional. Leave it out and the tools work on the song open in Furnace. `current_song` says which file that is.
- After each edit, Furnace reloads the song and keeps your place. The tool result says "Furnace reloaded the song" once it has.
- If you have unsaved changes in Furnace, edits are refused until you save. If you edit in Furnace after Claude's change arrives, Furnace asks before reloading.
- A song that has never been saved has no file, so save it first.

## Tools

| Tool | What it does |
|---|---|
| `current_song` | Which file Furnace has open, and whether it has unsaved changes |
| `inspect_song` | Chips, numbered channels, orders, speed, duration, instruments, samples |
| `read_patterns` | A window of orders × channels as tracker text (`C-4 0C 7F EC01`) |
| `write_rows` | Overwrite rows of one channel's pattern from tracker text |
| `set_order` | Point an order row at pattern indices, or append a row |
| `read_instrument` / `write_instrument` | Instrument JSON; changes merge |
| `render` | Render an order range to WAV and return a listen report (loudness, clipping, silence, spectral centroid, band energy; optionally per channel) |
| `export` | fur, json, vgm, s98, wav, txt |

Notes use Furnace numbering: C-4 is middle C, and lowercase `c_1` is octave −1. Edits save the song in place. The first edit in a session copies it to `<name>.bak.fur`. Renders go to `%TEMP%/furnace-mcp` (or `FURNACE_MCP_RENDERS`).

## Tests

```
cd tools/furnace-mcp
uv run pytest
```

The end-to-end tests drive the server through the MCP protocol against the real binary and are skipped when it isn't built.
