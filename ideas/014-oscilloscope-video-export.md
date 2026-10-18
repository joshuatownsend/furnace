# 014 — Oscilloscope video export

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat e9988cf35..HEAD -- src/gui/chanOsc.cpp src/gui/osc.cpp src/gui/oscTrigger.cpp src/main.cpp src/engine/export src/engine/dispatch.h`.

- **Status**: DONE (merged to master as #10, `ec521e616`, 2026-10-18; approach B, see Spike results)
- **Verdict**: Advance
- **Score**: 7/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in, with a real user in the family
- **Effort (coarse)**: M (a guess; I have not read the scope drawing code in detail)
- **Planned at**: e9988cf35 on 2026-10-17

## The idea

Turn a song into a video with one oscilloscope per channel, in time with the audio, ready to upload. Command line first, so it works without opening the GUI and can later be a tool for idea 003.

## Who wants this and why now

- **Michael**, Josh's son, uses Furnace and posts his songs on YouTube (youtube.com/@mysti_is_lost). Josh singled this idea out. How Michael makes his videos today is unknown. Ask.
- FamiStudio exports oscilloscope videos, which shows other chip musicians want it.
- Furnace has no video export. I found no video or ffmpeg code in `src/gui` (only SDL display calls), and `extern/` holds audio codecs only.

## What the fork already has

- **Per-channel audio export** on the command line: `--outmode perchan` (`src/main.cpp:463–475`, `DIV_EXPORT_MODE_MANY_CHAN` at `src/engine/engine.h:114–118`). Other modes are `one` and `persys`.
- **An on-screen channel scope**: `src/gui/chanOsc.cpp` (983 lines), with a trigger in `src/gui/oscTrigger.cpp` (derived from the unscope project, modified for Furnace). It has solid color and per-channel color modes (`chanOsc.cpp:342–376`).
- **A warning against reusing its data.** `DivDispatchOscBuffer` in `src/engine/dispatch.h` (around line 930) says the scope buffer is optimized, may be lower quality, and should not be used for per-channel export.
- **A software render backend** (`src/gui/render/renderSoftware.cpp`), but it draws to the SDL window surface (`:90`, `:129`). Capturing frames without a window is not free.
- **Headless tooling** from idea 004, which proves the project can run render-and-analyze steps outside the GUI.

## Three ways to build it

- **A. No code.** Export per-channel WAVs, then use stock ffmpeg: a `showwaves` filter per channel, tiled with `xstack`, with the song audio laid over it. Costs one command and a recipe.
- **B. A small renderer outside the app.** A script or tool reads the per-channel WAVs, finds a trigger point on each channel the way `oscTrigger.cpp` does, draws frames, and pipes them to ffmpeg. Channel colors can come from the color theme (idea 007).
- **C. Inside the app.** Run the real Chan Osc drawing code headless through the software renderer and capture frames. This matches the app's look exactly, but it is the largest change and touches busy GUI files.

Recommended order: A, then B if the look is wrong, and C only if Michael needs the exact Furnace look.

## Trade-offs and risks

- **ffmpeg is an outside program.** Call it if present. Do not bundle it. Check it is installed on Josh's and Michael's machines.
- **Wobbling scopes.** Without a trigger, waveforms jitter. A is likely to show this. B fixes it.
- **Size and time.** Many channels over a long song means many large files and slow renders. Measure it.
- **Sync.** Per-channel WAVs must line up sample for sample with the full mix, or the video drifts.
- **Merge cost.** A and B are new files or documentation. A `main.cpp` flag is a small edit to a busy file.

## Spike results (2026-10-17)

Built approach B as `export_video` in furnace-mcp and `python -m furnace_mcp.video` (see `tools/furnace-mcp/README.md`). I skipped approach A: stock `drawtext` crashes on this ffmpeg build without a font file, and `showwaves` has no trigger, so A would wobble by design.

- **Sync (question 3).** Per-channel WAVs are the same length as the mix, sample for sample, and line up at lag 0 (checked on `demos/nes/Byte-Sized Bop.fur`). They don't sum exactly to the mix because the NES APU mixes nonlinearly; that doesn't matter for scopes.
- **Stereo (question 4).** Every per-channel file has all the song's outputs (stereo here). The scope averages them to mono.
- **Colors (question 5).** From the Furnace color scheme: the GUI's `furnace.cfg`, or an exported scheme file. `mono` uses the scope wave color; `channel` uses each channel's custom color, else one color per chip. Channels hidden from Furnace's Channel Oscilloscope stay hidden; labels are Furnace's channel names, custom names included (the CLI's `-info` now lists channels with their types).
- **Steady scopes.** Each scope locks to the rising zero crossing nearest the frame time, with hysteresis so noise on the zero line doesn't trigger. A 441 Hz test tone holds within one sample.
- **Output (question 6).** 1920x1080, 60 fps, H.264 (yuv420p) + AAC in an mp4 with faststart, which is what YouTube asks for. ffmpeg 9.0.2 is on Josh's machine (winget). Labels use Furnace's UI font (`res/fonts/IBMPlexSans-Regular.otf`).
- **Speed (step 5).** Rendering each channel is the slow part: Furnace replays the whole song once per channel. A new CLI flag, `-exportchans 1-4,7`, lets the tool split channels across parallel furnace processes (half the cores). On `demos/genesis/All Good Times.fur` (142.8 s, 13 channels, 10 audible) a full video took 7 min 40 s with one process, 4 min 47 s with eight, and 4 min 0 s once drawing overlapped encoding; the mp4 files are identical. The file is 339 MB (crf 18); YouTube re-encodes it anyway. The extended FM channel's four operators export as one file, under the first operator, as they always did; `-exportchans` now asks for that file when given any of them. The parallel render is a stopgap: each process still replays the whole song, so the total CPU work is unchanged. The real fix is an engine export that writes every channel in one playthrough.
- **Where it lives (question 7).** In furnace-mcp: one module, an MCP tool for Claude, and a command line for everyone else. No GUI change.

Still open for Josh and Michael (questions 1 and 2): how Michael makes his videos now, and whether this look is right. The quickest check is to render one of his songs: `uv run python -m furnace_mcp.video his-song.fur out.mp4 --color channel`.

## Open questions

1. How does Michael make his videos now (screen capture of the app, another tool)? What does a video he likes look like? Ask for one example song and one video to match.
2. Does stock `showwaves` look acceptable, or does it wobble too much?
3. Do the per-channel WAVs match the full mix in length and start offset?
4. Do multi-output (stereo) chips export as one file per channel or per output?
5. Where do channel colors come from: the pattern view's channel colors or the theme?
6. Is Python or ffmpeg available on the machines that will run this? What output does YouTube need (1080p, 60 fps, H.264 with AAC in an mp4 is the usual choice)?
7. Should the finished tool live in `tools/`, in `furnace-mcp`, or as a CLI flag?

## Spike plan

1. **Ask Josh question 1** and get one of Michael's songs and one video he likes. *You'll know when* you have a target look to match.
2. **Export per-channel WAVs** for that song with `--outmode perchan` and check the file names. *You'll know when* you have one WAV per channel, all the same length as the full mix.
3. **Make a 30-second test video with approach A.** *You'll know when* Michael says the look is acceptable or not.
4. **If not, prototype approach B** with a rising-edge trigger and per-channel colors. *You'll know when* the scopes hold steady at 60 fps for 30 seconds.
5. **Time a full song** and note the file sizes. *You'll know when* you can tell Josh how long a full render takes.
6. **Recommend where the code lives**: a recipe, a script in `tools/`, a tool in `furnace-mcp`, or a CLI flag. *You'll know when* Josh can pick one.

## Decision criteria

- **Build it**: A or B looks right to Michael. Productize as a `tools/` script plus a doc (S), or a CLI flag (M).
- **Reshape it**: A looks right. Ship it as a documented recipe, with no code.
- **Drop it**: nothing beats screen recording to Michael's eye, or the render time is too long to be practical.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\014-oscilloscope-video-export.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: produce a test video with one oscilloscope per channel from a Furnace song using per-channel WAV export and ffmpeg, and find out whether it looks right. Do not build beyond the spike; prototype work happens behind a flag or on a branch. Ask Josh for Michael's example song and a video to match before step 3.
```
