# What's new in this fork

This is Josh Townsend's personal fork of [Furnace](https://github.com/tildearrow/furnace). It adds composing and tuning with Claude, new chips, and tools for sharing songs. Everything below was merged between 2026-10-16 and 2026-10-18 (PRs #1 to #13). The plans and test write-ups behind each feature are in [`ideas/`](ideas/README.md).

## At a glance

| Area | What you get | PR |
|---|---|---|
| Color themes | Dark and Light presets, a Light option that works, a readability check | #11 |
| Oscilloscope videos | A YouTube-ready mp4 of a song, one scope per channel | #10 |
| Composing with Claude | An MCP server that reads, edits, renders and listens to songs | #3, #4, #5, #8, #9 |
| Songs as JSON | Export a song as text, edit it, open it again | #2 |
| Command line | Everything the export menu does, plus song timing and channel lists | #1, #10 |
| New chip | Bally Astrocade, with an example song | #6, #7 |
| Sample tuning | Claude measures a sample's pitch and tunes it | #12 |
| Wave editor | A Harmonics tab that shows what a wave is made of | #13 |

---

## Color themes

*Settings > Color* (#11)

- **Presets.** Two buttons at the top of the Color tab: **Dark (default)** and **Light**. A preset replaces every color, so Furnace asks first; export your scheme beforehand if you want to keep it. Your Guru mode and frame-shading settings are kept.
- **Light now means light.** Upstream's Dark/Light switch only restyled buttons and tabs, so "Light" gave light buttons on dark windows. Picking Light (or Dark) now offers to load the matching preset whenever the windows don't match.
- **Contrast check.** The Color tab tells you whether text is readable. It holds 31 text colors to the WCAG AA standard (4.5:1), each against every background it is drawn on:
  - menus, popups, title bars and tables
  - buttons, inputs, headers and tabs, normal, hovered and pressed
  - order numbers on the playing order and the song loop
  - pattern text on highlighted, play-head and edited rows, and under the selection and the cursor

  Any color that fails shows a sample of the text on its worst background, with the ratio.
- **The Light preset passes every check.** It is generated from the dark defaults: backgrounds are lightened and text is darkened along its own hue until it reads, so pattern colors keep their meaning.
- **Pressed buttons stay readable in Light.** Upstream darkened a pressed button to half brightness under dark text (about 2.4:1); the fork keeps it light.
- **For scheme makers:** `python -m furnace_mcp.scheme check my-scheme.cfgc` runs the same check on an exported scheme file.

Upstream's own dark defaults fail a few checks: white text on pressed buttons, and several effect colors under the hovered cursor. The check reports them; the fork leaves the Dark preset as upstream ships it.

## Oscilloscope videos

*For YouTube* (#10)

Turn a song into an mp4 with one oscilloscope per channel and the song as the soundtrack:

```
cd tools/furnace-mcp
uv run python -m furnace_mcp.video "song.fur" song.mp4
uv run python -m furnace_mcp.video "song.fur" clip.mp4 --orders 2-5 --color channel
```

- 1920x1080 at 60 fps, H.264 + AAC, the format YouTube expects. Change it with `--size` and `--fps`.
- **Steady scopes:** each scope locks onto the waveform the way Furnace's Channel Oscilloscope does.
- **Your colors:** the video uses your Furnace color scheme, or a scheme file given with `--scheme`. `--color channel` uses each channel's custom color, else one color per chip.
- **Furnace's labels:** each scope is labeled with Furnace's own channel name ("FM 1", "Square 2", or your custom name).
- Silent channels are left out, and so are channels you hid from the Channel Oscilloscope.
- **Speed:** a 2.5-minute Genesis song takes about 4 minutes, since channels render in parallel.
- **From Claude:** Claude can make one with the `export_video` tool.
- **Needs ffmpeg** on `PATH` (`winget install Gyan.FFmpeg`).

## Composing with Claude

*The furnace-mcp server* (#3, #4, #5, #8, #9)

An MCP server in [`tools/furnace-mcp`](tools/furnace-mcp/README.md) lets Claude work on your songs. Claude Code picks it up from the repo's `.mcp.json`.

- **Works on the song you have open.** Furnace tells the server which file is open. When Claude edits it, Furnace reloads it in about a second and keeps your place. Edits are refused while you have unsaved changes, and the first edit in a session saves a `.bak.fur` backup.
- **Tools:**
  - `inspect_song`: chips, channels, orders, speed, duration, instruments and samples. It also reports what a written note really sounds like on each chip; for example, an SN76489 sounds two octaves above the written note, a quirk of Furnace's octave naming that used to trip Claude up.
  - `read_patterns`, `write_rows` and `set_order`: read and write patterns as tracker text (`C-4 0C 7F EC01`).
  - `read_instrument` and `write_instrument`: instrument settings.
  - `render`: renders a range of orders and returns a listen report (loudness, clipping, silence, brightness), optionally per channel.
  - `preview_instrument`: plays one note and reports its pitch in cents, envelope, loudness and harmonics, so Claude can check its own instrument edits. Pitch and envelope are reliable. Judge tone by ear.
  - `export`: .fur, JSON, VGM, S98, WAV or text.
  - `export_video`: see above.
- **Example songs:** `examples/victory_fanfare.fur` (Genesis) and `examples/neon_midway.fur` (Astrocade).

## Songs as JSON

*Open what you export* (#2)

Furnace could already export a song as JSON, and now it can open one too. Export, edit the text (by hand, by script, or with Claude), and open it again. All 481 demo songs survive the round trip with identical audio. Bad files are rejected with a readable error, not a crash.

The fork's JSON export also writes settings that upstream's left out and that change playback: master volume, chip channel counts, grooves, and some instrument data. Each chip is saved by its permanent file ID, so fork chips load correctly.

## Command line

*`furnace.exe` without the GUI* (#1, #10)

- **New outputs:** `-furout` (save as .fur, for example to convert an imported module), `-s98out`, `-jsonout` and `-jsonpretty`.
- **VGM options:** `-vgmver` (1.50 to 1.72), `-noloop` and `-vgmhints`.
- **`-info`** now prints the song's duration, ticks, rows and loop point, and a CHANNELS list with each channel's name and type.
- **`-exportchans 1-4,7`** with `-outmode perchan` exports only those channels, numbered like the output files.
- All options are documented in [`doc/8-advanced/command-line.md`](doc/8-advanced/command-line.md).

## New chip: Bally Astrocade

*The first fork-only chip* (#6, #7)

- **Channels:** three tones and noise, with the standard instrument editor.
- **Effects:** `10xx` master oscillator, `11xx` vibrato, `12xx` modulation source.
- **Emulation:** the sound core is MAME's, and it matches the original sample for sample.
- **Pitch:** every note is within 0.02 cents of the chip's own tuning.
- **Example:** `tools/furnace-mcp/examples/neon_midway.fur`, an upbeat 45-second 1970s console tune.
- **Known chip limit:** lead notes around C-6 play slightly flat, because the hardware's 8-bit dividers share one oscillator.

Fork chips use file IDs from `0x1000` up, so they won't collide with chips upstream adds. [`ideas/chip-recipe.md`](ideas/chip-recipe.md) is the recipe for adding more chips.

## Sample tuning

*Two new Claude tools* (#12)

Upstream's [tuning guide](doc/9-guides/tuning-samples.md) has you work out a sample's pitch offset by hand. Now Claude can measure the sample and fix its rate for you:

- `detect_sample_pitch` reports what a written C-4 actually plays (note, cents and Hz), how sure it is, and which instruments use the sample. Drums, noise and chords get "no clear pitch" instead of a guess.
- `tune_sample` sets the sample's rate (the "Hz" in the sample editor) so a written C-4 plays the nearest C, or a note you name.
- **Accuracy:** within 2 cents on test tones. A real piano sample went from 14 cents sharp to under 2 cents off once tuned.
- **Watch for instrument pitch macros.** Some instruments shift the pitch again after the sample is tuned. Both tools point these out.
- Works on 8-bit and 16-bit samples. SNES (BRR) and ADPCM samples aren't analysed yet.

## Wave editor: Harmonics

*Wavetable Editor > Harmonics* (#13, upstream request #987)

- A bar graph and a table show the amplitude and phase of every harmonic in the current wave.
- If the wave has more than 16 harmonics, it shows how much of the sound sits above the 16th.
- **Copy to Shapes** loads harmonics 1 to 16 into the Shapes tab's Amplitude/Phase sliders. You can then rebuild the wave there and change one harmonic at a time.

## Fixes

- **Reloading the open song** (#3, #8):
  - Furnace now spots a changed file by its contents, not its timestamp, so two quick saves on a FAT drive or network share no longer slip past.
  - Touching a file without changing it no longer triggers a reload.
  - Reloads also work while the window is minimized.
- **Analysis** (#5): stereo channels with one side inverted (SNES, SID3) are no longer measured as silence. Harmonics are reported relative to the strongest one.
- **`inspect_song`** no longer crashes on songs without samples (#7).
- **Command line** (#1, #10):
  - The ambiguous `-o` shortcut is gone.
  - `-exportchans` fails with a clear message when given a channel the song doesn't have.

## Not done yet

- **Videos:** Michael hasn't tried one on his own songs yet.
- **Lumatone:** a plug-in test for Michael's keyboard ([`ideas/018`](ideas/018-lumatone-plug-in-test.md)) and a plan for microtonal input ([`ideas/019`](ideas/019-lumatone-layout-microtonal-input.md)) are written. No Lumatone code yet.
- **Sample tuning:**
  - There's no button in the sample editor yet; the tools are Claude-only.
  - SNES (BRR) and ADPCM samples aren't supported.
  - On chips that play samples at a fixed rate (YM2610 ADPCM-A, MSM6295), changing the rate does nothing, and the tools don't warn yet.
  - Instruments whose note map moves a note's pitch aren't flagged yet.
- **Perfect Palette:** a "Furnace scheme" export, and a link to perfectpalette.io in the Color tab, are open questions.
- **Contrast check gaps:** it doesn't yet cover child windows, inactive or collapsed title bars, or unfocused tabs. This only matters for hand-made schemes.
- **Astrocade:**
  - It has no page in the chip docs (`doc/7-systems`) yet.
  - It has been checked against MAME, not real hardware.
- **Building on Windows:** the headless build (`-DBUILD_GUI=OFF`) doesn't compile with MSVC. Build the GUI with `-DCONSOLE_SUBSYSTEM=ON` instead.
