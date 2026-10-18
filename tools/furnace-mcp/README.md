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
| `detect_sample_pitch` | Measure a sample's pitch (8- or 16-bit PCM): what a written C-4 plays, as a note and cents, with a confidence. Says "no clear pitch" for noise, drums and chords. Doesn't change the song |
| `tune_sample` | Set a sample's center rate (the sample editor's "Hz") from its measured pitch, so a written C-4 plays the nearest C (or the note given as `c4_plays`). See below |
| `export` | fur, json, vgm, s98, wav, txt |
| `export_video` | An oscilloscope video (mp4) of an order range, one scope per channel, for YouTube. See below |

Notes use Furnace numbering: C-4 is middle C, and lowercase `c_1` is octave −1. Edits save the song in place. The first edit in a session copies it to `<name>.bak.fur`, replacing any backup from an earlier session. Renders go to `%TEMP%/furnace-mcp` (or `FURNACE_MCP_RENDERS`).

## Tuning samples

`tune_sample` does what [doc/9-guides/tuning-samples.md](../../doc/9-guides/tuning-samples.md) describes by hand. A looped sample is measured on its loop, since that holds the note. An unlooped one is measured on its steady part after the attack. The tool then moves the center rate by up to half an octave, so a written C-4 plays the nearest C, and a recorded E then plays E on an E. The result says how many octaves notes sound away from how they're written. `c4_plays: "C-4"` transposes the sample so a written note sounds exactly as named. The rate this needs can be far above the recording's, and above what a chip plays.

The center rate is the playback rate for a written C-4, scaled so that a 32-sample cycle at 8372 Hz is a C-4. Songs saved before Furnace dev256, and MOD, S3M, XM and IT imports, keep the old 8363 Hz convention (`compatFlags.oldCenterRate`). The math is:

```
new rate = rate * 2^(-d/1200)
d = cents from 1200 * log2(32 * rate / (nominal * period)) to the nearest whole octave
```

Here `period` is the measured period in samples, and `nominal` is 8372, or 8363 in old songs. The song's tuning (A-4 = 440) cancels out.

Only 8- and 16-bit PCM can be read from the song's JSON. BRR, ADPCM and the other formats get a "can't analyse depth N" message. An instrument's arp or pitch macro shifts the sample again after tuning, so both tools list the instruments that use the sample and flag those macros.

## Oscilloscope videos

`export_video`, or the same thing from the command line:

```
cd tools/furnace-mcp
uv run python -m furnace_mcp.video "../../demos/nes/Byte-Sized Bop.fur" bop.mp4
uv run python -m furnace_mcp.video song.fur clip.mp4 --orders 2-5 --color channel --size 1280x720 --fps 30
```

It renders the mix and each channel separately with the Furnace CLI, draws one scope per channel, and encodes an H.264 + AAC mp4 (1920x1080, 60 fps by default, the format YouTube expects). It needs [ffmpeg](https://ffmpeg.org) on `PATH` (`winget install Gyan.FFmpeg` on Windows). Details:

- Each scope waits for a rising edge, as Furnace's Channel Oscilloscope does, so a steady note holds still on screen. Each channel is scaled to its own peak in the range, so quiet channels still show.
- Channels that make no sound in the range are left out, and so are channels you hid from the Channel Oscilloscope in Furnace. Labels are the channel names Furnace shows ("FM 1", "Square 2", or your custom name); an extended FM channel's four operators make one scope.
- Colors come from your Furnace color scheme (`furnace.cfg`), or from a scheme file exported in Settings > Color (`--scheme`). `--color channel` uses each channel's custom color, else one color per chip.
- `--orders` takes hex order numbers, as in the order list. Rendering every channel takes time (about 4 minutes for a 2.5-minute Genesis song), so try a few orders first. Channels render in parallel through the CLI's `-exportchans` flag, so rebuild Furnace if it says that flag is unknown.

## Tests

```
cd tools/furnace-mcp
uv run pytest
```

The end-to-end tests drive the server through the MCP protocol against the real binary and are skipped when it isn't built.
