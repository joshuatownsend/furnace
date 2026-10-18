# Fork README: setup and usage

How to set up and use what this fork adds to [Furnace](https://github.com/tildearrow/furnace). For a list of the changes, see [fork_whats_new.md](fork_whats_new.md). For everything else, the upstream [README](README.md) and the [manual](doc/README.md) apply.

## Contents

1. [Setup](#setup)
2. [Color themes](#color-themes)
3. [Oscilloscope videos](#oscilloscope-videos)
4. [Composing with Claude](#composing-with-claude)
5. [Songs as JSON](#songs-as-json)
6. [Command line](#command-line)
7. [The Bally Astrocade chip](#the-bally-astrocade-chip)
8. [Tuning samples](#tuning-samples)
9. [Wave editor harmonics](#wave-editor-harmonics)
10. [Troubleshooting](#troubleshooting)

---

## Setup

### What you need

| For | You need | Install (Windows) |
|---|---|---|
| Building Furnace | Git, CMake, a C++ compiler | Visual Studio 2019 or later Build Tools (CMake comes with them) |
| Color themes, JSON songs, Astrocade | The fork's Furnace build | See below |
| Composing with Claude | The build, plus [uv](https://docs.astral.sh/uv/) and [Claude Code](https://claude.com/claude-code) | `winget install astral-sh.uv` |
| Oscilloscope videos | The build, uv, and [ffmpeg](https://ffmpeg.org) | `winget install Gyan.FFmpeg` |

uv installs the Python and packages the tools need on first run (Python 3.11 or later, `mcp` and `numpy`); there is no separate `pip install`.

### Get the source

Clone with submodules (a .zip download won't build):

```
git clone --recursive https://github.com/joshuatownsend/furnace.git
cd furnace
```

If you cloned without `--recursive`: `git submodule update --init --recursive`.

### Build

The Claude tools and the video exporter drive Furnace from the command line, so on Windows build it **with a console** (`CONSOLE_SUBSYSTEM=ON`); otherwise the command line prints nothing. The same build is the normal GUI app.

**Windows** (from a Developer Command Prompt, or use the CMake that ships with Visual Studio Build Tools):

```
cmake -S . -B build-gui -G "Visual Studio 16 2019" -A x64 -DCONSOLE_SUBSYSTEM=ON
cmake --build build-gui --config Release -j 6
```

The app is `build-gui\Release\furnace.exe`. A full build takes 20 minutes or more; more than about 6 parallel jobs can run out of memory. With Visual Studio 2022, use `-G "Visual Studio 17 2022"`.

**Linux and macOS:** build as the upstream README describes, into `build-gui/` or `build/`. Console output works there without extra flags.

The tools look for the binary in `build-gui/Release/`, `build-gui/`, `build/Release/` and `build/`. To use one somewhere else, set `FURNACE_EXE` to its full path.

### Check it works

```
build-gui\Release\furnace.exe -noreport -info "demos\genesis\All Good Times.fur"
```

You should see the song's name, its duration, its instruments, and a CHANNELS list. Pass `-noreport` on every command-line call: without it, an error opens a message box that waits for a click.

---

## Color themes

Open **Settings** (Ctrl+,) and pick the **Color** category. You can also type `preset` or `contrast` in the settings search box.

### Switch to a light or dark theme

1. Click **Light** (or **Dark (default)**) next to **Presets:**.
2. Furnace asks first, because a preset replaces every color. To keep your current colors, click **Export** first and save the scheme file.
3. Click **Yes**, then **OK** to keep the change, or **Cancel** to undo it.

You can also pick Dark or Light under **Color scheme type** (with Guru mode off). If the windows don't match your choice, Furnace offers to load the matching preset.

### Check that text is readable

The **Contrast** line under the presets says either that every text color checked meets WCAG AA (4.5:1), or which ones don't. Each failing color shows a sample of the text on its hardest background, with the ratio, so you know which color to change. The line updates as you edit colors.

Some colors are left out on purpose:
- the dimmed placeholder dots in empty pattern cells
- rows of the previous and next pattern, which Furnace draws faded

The check doesn't yet cover child windows, inactive or collapsed title bars, or unfocused tabs.

### Check a scheme file

Run the same check on an exported scheme (`.cfgc`, from **Color > Export**) or on Furnace's own `furnace.cfg`:

```
cd tools/furnace-mcp
uv run python -m furnace_mcp.scheme check path\to\my-scheme.cfgc
```

It lists each failing text color with its ratio and exits with code 1 if any fail. It reads the file's Guru mode and Dark/Light settings, so basic-mode button and tab colors are checked as Furnace draws them.

### Change the Light preset (developers)

The Light preset is generated, not hand-edited. To change it, edit `light_scheme` in `tools/furnace-mcp/furnace_mcp/scheme.py`, then regenerate the header and rebuild:

```
cd tools/furnace-mcp
uv run python -m furnace_mcp.scheme presets
```

`uv run pytest` fails if `src/gui/colorPresets.h` is out of date, or if the C++ and Python contrast checks list different colors.

---

## Oscilloscope videos

Makes an mp4 with one oscilloscope per channel and the song as its soundtrack, ready to upload to YouTube.

### Make a video

```
cd tools/furnace-mcp
uv run python -m furnace_mcp.video "C:\music\my song.fur" "C:\music\my song.mp4"
```

Try a few orders first. A full 2.5-minute song takes about 4 minutes.

```
uv run python -m furnace_mcp.video "my song.fur" clip.mp4 --orders 2-5
```

### Options

| Option | What it does | Default |
|---|---|---|
| `--orders 2-5` | Only these orders, numbered in hex as in the order list | The whole song |
| `--subsong N` | Which sub-song | 0 |
| `--size 1280x720` | Video size (even numbers) | 1920x1080 |
| `--fps 30` | Frames per second | 60 |
| `--window-ms 40` | How much time each scope shows | 40 ms |
| `--color channel` | Each channel's custom color, else one color per chip | `mono`: the scope color from your scheme |
| `--scheme file.cfgc` | Use an exported color scheme | Furnace's current colors |
| `--no-labels` | Leave out the channel names | Names shown |

### What decides the look

- **Colors:** your Furnace color scheme (the window background, the scope wave color, the text color), unless you pass `--scheme`.
- **Labels:** the channel names Furnace shows, including your custom names. Rename a channel in Furnace to rename its scope.
- **Which channels:** channels that make no sound in the range are left out, and so are channels you hid from the **Channel Oscilloscope** window. Hide a channel there to drop it from the video.
- **Extended FM channels:** an extended FM channel (for example "FM 3" on Genesis with extended channel 3) becomes one scope, since its four operators make one sound.

### From Claude

Ask Claude to "make a scope video of orders 0 to 3". It uses the `export_video` tool, which takes the same options.

---

## Composing with Claude

The furnace-mcp server lets Claude open, read, edit, play back and measure your songs.

### Set it up

1. Build Furnace (see [Setup](#setup)) and install uv.
2. Open Claude Code in the repo folder. It reads the repo's `.mcp.json` and asks to enable the **furnace** server: approve it.
3. Ask Claude something like "inspect the song open in Furnace" to check it works.

To use the server from another folder or another MCP client, point it at:

```
uv run --project <repo>/tools/furnace-mcp python <repo>/tools/furnace-mcp/server.py
```

### Work on the song open in Furnace

1. Open a song in the fork's Furnace and save it (a song that has never been saved has no file to edit).
2. Ask Claude for a change. Every tool works on the song open in Furnace unless you name a file.
3. Furnace reloads the song within about a second and keeps your place.

- **Unsaved changes:** if you have unsaved changes in Furnace, Claude's edits are refused until you save.
- **Backups:** the first edit in a session keeps a backup as `<name>.bak.fur`.
- **Renders:** listen-report audio is saved to `%TEMP%\furnace-mcp`, or to the folder in `FURNACE_MCP_RENDERS`.

### What Claude can do

| Ask for | Tool |
|---|---|
| An overview: chips, channels, orders, tempo, instruments, and what a written note really sounds like on each chip | `inspect_song` |
| Pattern text to read or rewrite (`C-4 0C 7F EC01`) | `read_patterns`, `write_rows`, `set_order` |
| Instrument changes | `read_instrument`, `write_instrument` |
| "How does it sound?": loudness, clipping, silence and brightness, per channel if you like | `render` |
| A check of one instrument: pitch in cents, envelope, loudness and harmonics | `preview_instrument` |
| A file: .fur, JSON, VGM, S98, WAV or text | `export` |
| A scope video | `export_video` |
| A sample's real pitch, or tuning it to C | `detect_sample_pitch`, `tune_sample` |

**Tips:**
- **Notes:** Claude writes notes in Furnace's numbering: C-4 is middle C, and `c_1` is octave −1.
- **Octaves:** some chips sound in a different octave from the written note; an SN76489 plays two octaves up. `inspect_song` reports this per chip, so ask Claude to inspect the song before it writes parts.
- **Trust the numbers for pitch and envelope:** `preview_instrument` measures both reliably. Judge tone by ear.

### Example songs

- `tools/furnace-mcp/examples/victory_fanfare.fur`: a short Genesis (YM2612 + SN76489) fanfare, made with these tools. Copy it before editing, because edits save in place.
- `tools/furnace-mcp/examples/neon_midway.fur`: a 1970s console tune for the Bally Astrocade. It's built by `neon_midway.py`, so edit the script and rerun it (`uv run python examples/neon_midway.py`) rather than editing the .fur.

### Run the tests

```
cd tools/furnace-mcp
uv run pytest
```

The tests that need the Furnace binary or ffmpeg are skipped when either is missing.

---

## Songs as JSON

A song saved as JSON can be edited as text and opened again.

1. **Export:**
   - **GUI:** use JSON export.
   - **Command line:** `furnace.exe -noreport -jsonout song.json song.fur`. Add `-jsonpretty` for indented, readable output.
2. **Edit:** change the JSON by hand, with a script, or by asking Claude.
3. **Open:**
   - **GUI:** open the `.json` file in Furnace's **Open** dialog. JSON files are included in the default file filter.
   - **Command line:** convert it back with `furnace.exe -noreport -furout song.fur song.json`.

If the JSON is broken, Furnace says what's wrong instead of opening it. `tools/furnace-mcp/examples/neon_midway.py` shows how to write a whole song as JSON from a script.

---

## Command line

All examples use `furnace.exe -noreport`; on Linux and macOS the binary is `furnace`. The full list of flags is in [doc/8-advanced/command-line.md](doc/8-advanced/command-line.md).

### Song information

```
furnace.exe -noreport -info song.fur
furnace.exe -noreport -info -subsong 1 song.fur
```

This prints:
- name, author and system
- duration, ticks, rows and loop point
- instruments and samples
- a CHANNELS list: each channel's name as the pattern view shows it, and its type

### Convert and export

| Want | Command |
|---|---|
| .fur (for example from an imported .mod or .dmf) | `-furout out.fur in.mod` |
| JSON | `-jsonout out.json in.fur` (add `-jsonpretty` to indent) |
| S98 | `-s98out out.s98 in.fur` |
| VGM | `-vgmout out.vgm in.fur`, with `-vgmver 150`…`172`, `-noloop`, `-vgmhints` |
| WAV of the mix | `-output out.wav in.fur` |
| One WAV per channel | `-output out.wav -outmode perchan in.fur` (writes `out_c01.wav`, `out_c02.wav` …) |
| Only some channels | add `-exportchans 1-4,7` (numbered like the files, from 1) |

`-loops 0` exports the song once without repeating. Asking `-exportchans` for any operator of an extended FM channel exports that channel's single file, under its first operator.

---

## The Bally Astrocade chip

1. In a new song or **Chip Manager**, add **Bally Astrocade**.
2. It has three tone channels and a noise channel. All four use the standard instrument editor.
3. Effects:
   - `10xx`: set the master oscillator, which all three tones share.
   - `11xx`: vibrato.
   - `12xx`: modulation source (vibrato or noise).

Listen to `tools/furnace-mcp/examples/neon_midway.fur` for an example. Lead notes around C-6 play slightly flat; that's the chip's 8-bit dividers, not a bug.

Songs using fork chips (file IDs `0x1000` and up) open only in this fork, not in upstream Furnace.

---

## Tuning samples

Ask Claude in a session with the Furnace tools (see [Composing with Claude](#composing-with-claude)):

1. **"What pitch is sample 3?"** Claude runs `detect_sample_pitch`. It reports what a written C-4 plays, for example "D#4, +14 cents", and how sure it is. Below 0.7 confidence, check by ear.
2. **"Tune sample 3."** Claude runs `tune_sample`. It changes the sample's rate (the **Hz** box in the sample editor) so a written C-4 plays the nearest C. The rate moves by at most half an octave.
3. **"Tune sample 3 so C-4 plays A-3."** Claude passes `c4_plays` to transpose to that note instead.

Notes:
- **Loops:** if the sample loops, the loop is measured, since that's what you hear while a note holds. If the attack before the loop is pitched differently, the report says so.
- **No clear pitch:** drums, noise and chords are reported as having no clear pitch, and `tune_sample` won't touch them.
- **Instrument macros:** if an instrument using the sample has an arpeggio or pitch macro, the report points it out. A tuned sample can still sound off through that instrument.
- **Sample depths:** only 8-bit and 16-bit samples can be analysed.
- **Fixed-rate chips:** chips that play samples at a fixed rate, such as YM2610 ADPCM-A and MSM6295, ignore the sample's rate, so tuning it changes nothing there.
- **Saving:** as with other edits, save your song in Furnace first. Furnace reloads after the change.

---

## Wave editor harmonics

1. Open a wavetable in the **Wavetable Editor**. If the generator panel is hidden, click the arrow button at the top right to show it.
2. Pick the **Harmonics** tab, next to Shapes, FM and WaveTools.
3. Read the result:
   - The bar graph runs from harmonic 1 (the fundamental) on the left. A wave of length N has N/2 harmonics.
   - The table lists each harmonic's amplitude and phase. 1.000 is a full-height sine.
   - If the wave has more than 16 harmonics, a line shows how much of its energy is above the 16th.
4. To edit the wave by its harmonics, click **Copy to Shapes**, then switch to **Shapes**:
   - The Amplitude/Phase sliders now hold harmonics 1-16, on a sine shape.
   - The wave doesn't change until you move a slider. It is then rebuilt from those 16 harmonics, so anything above the 16th is lost.
   - If a harmonic is louder than 1.000 (a full-height square wave's first harmonic is about 1.27), all of them are scaled down to fit the sliders.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| The Claude tools say "furnace binary not found" | Build into `build-gui/` (see [Build](#build)) or set `FURNACE_EXE` |
| The command line prints nothing on Windows | Rebuild with `-DCONSOLE_SUBSYSTEM=ON` |
| A message box pops up and the command hangs | Add `-noreport` |
| "Unknown option exportchans", or videos fail on an old build | Rebuild Furnace from this fork |
| Video: "ffmpeg not found" | Install ffmpeg, then open a new terminal so `PATH` picks it up |
| Video has no channel names | `res/fonts/IBMPlexSans-Regular.otf` is missing from the checkout |
| Claude's edits are refused | Save the song in Furnace first; edits wait while it has unsaved changes |
| Furnace doesn't reload Claude's edit | Make sure you are running the fork's build; upstream Furnace doesn't watch the file |
| The headless build (`-DBUILD_GUI=OFF`) fails on Windows | Known upstream issue with MSVC; use the console GUI build instead |
