# furnace-mcp

An MCP server that lets Claude read, edit, render and export Furnace songs. Fork-only spike for `ideas/003-claude-mcp-server.md`. It is outside the C++ build and shells out to the Furnace CLI.

## Setup

1. Build Furnace with the console subsystem (Windows): `-DCONSOLE_SUBSYSTEM=ON`, Release, in `build-gui/`. The server uses `build-gui/Release/furnace.exe` unless `FURNACE_EXE` points somewhere else.
2. Install [uv](https://docs.astral.sh/uv/).
3. Claude Code picks the server up from the repo's `.mcp.json` (approve it when asked). To run it by hand:

   ```
   uv run --project tools/furnace-mcp python tools/furnace-mcp/server.py
   ```

## Tools

| Tool | What it does |
|---|---|
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
