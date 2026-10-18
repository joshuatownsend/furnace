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

The fork's Furnace (from this branch on) writes the path of the song it has open to `open-song-<process id>.txt` in its config folder (`%APPDATA%\furnace` on Windows; with several Furnace windows open, the one you used last counts), and reloads that file when it changes on disk. So:

- Every tool's `path` is optional. Leave it out and the tools work on the song open in Furnace. `current_song` says which file that is.
- After each edit, Furnace reloads the song and keeps your place. The tool result says "Furnace reloaded the song" once it has.
- If you have unsaved changes in Furnace, edits are refused until you save. If you edit in Furnace after Claude's change arrives, Furnace asks before reloading.
- A song that has never been saved has no file, so save it first.

## Example songs

`examples/victory_fanfare.fur` is a short Genesis (YM2612 + SN76489) fanfare made with these tools: a timpani roll, then three FM trumpets, bass trombone, DAC timpani and cymbals, and a PSG snare. It's the song to test with. Edits save in place, so copy it somewhere else before editing and keep the repo copy unchanged.

`examples/neon_midway.fur` is an upbeat 1970s console tune for the Bally Astrocade (the fork-only chip): lead, offbeat arpeggio chords, octave bass and noise drums, 45 s, looping past the intro. `examples/neon_midway.py` is its source: it writes the song as Furnace JSON and converts it with `furnace -furout`, so edit the script and rerun it (`python neon_midway.py [furnace.exe]`) rather than editing the .fur.

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
| `preview_instrument` | Play one note of an instrument on its own and report pitch (cents from the note played), envelope, loudness, and attack and held harmonics. Doesn't change the song |
| `export` | fur, json, vgm, s98, wav, txt |
| `export_video` | An oscilloscope video (mp4) of an order range, one scope per channel, for YouTube. See below |

Notes use Furnace numbering: C-4 is middle C, and lowercase `c_1` is octave −1. Edits save the song in place. The first edit in a session copies it to `<name>.bak.fur`, replacing any backup from an earlier session. Renders go to `%TEMP%/furnace-mcp` (or `FURNACE_MCP_RENDERS`).

## Oscilloscope videos

`export_video`, or the same thing from the command line:

```
cd tools/furnace-mcp
uv run python -m furnace_mcp.video "../../demos/nes/Byte-Sized Bop.fur" bop.mp4
uv run python -m furnace_mcp.video song.fur clip.mp4 --orders 2-5 --color channel --size 1280x720 --fps 30
```

It renders the mix and each channel separately with the Furnace CLI, draws one scope per channel, and encodes an H.264 + AAC mp4 (1920x1080, 60 fps by default, the format YouTube expects). It needs [ffmpeg](https://ffmpeg.org) on `PATH` (`winget install Gyan.FFmpeg` on Windows). Details:

- Each scope waits for a rising edge, as Furnace's Channel Oscilloscope does, so a steady note holds still on screen. Each channel is scaled to its own peak in the range, so quiet channels still show.
- Channels that make no sound in the range are left out, and so are channels you hid from the Channel Oscilloscope in Furnace. A channel's custom name is its label.
- Colors come from your Furnace color scheme (`furnace.cfg`), or from a scheme file exported in Settings > Color (`--scheme`). `--color channel` uses each channel's custom color, else one color per chip.
- `--orders` takes hex order numbers, as in the order list. Rendering every channel takes time: a 3-minute song takes several minutes, so try a few orders first.

## Tests

```
cd tools/furnace-mcp
uv run pytest
```

The end-to-end tests drive the server through the MCP protocol against the real binary and are skipped when it isn't built.
