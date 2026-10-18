# 022 — Show Claude the audio: waveform and spectrum images from the MCP tools

> Brief for a design spike. Build the first image behind an option, then test whether it helps. Do not make images the default until the test says so.
> Drift check: `git diff --stat f491976c9..HEAD -- tools/furnace-mcp`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 7/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in (a public report from another tool's author) plus inside-out (004's weak timbre result)
- **Effort (coarse)**: S–M for the first image and the test; S for each image after that
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Today the furnace-mcp tools tell Claude about sound in text: loudness, clipping, silence, brightness, pitch in cents, envelope times. Add an optional picture to the tools that render audio, so Claude can see the shape of the sound as well as read the numbers.

In order:

1. **`render(..., image=True)`**: one waveform per channel plus the mix, stacked, with a vertical line at each order boundary, labelled in hex like the order list. A spectrum strip under the mix.
2. **`preview_instrument(..., image=True)`**: the whole envelope, a close-up of a few cycles during the attack and the sustain, and the harmonic bars.
3. **`detect_sample_pitch(..., image=True)`**: the sample's waveform with the loop points marked and the measured part shaded.
4. **`export_video(..., preview=True)`**: about eight frames on one contact sheet, drawn by the existing video renderer, in seconds instead of a full render.

The text report stays. Exact numbers (pitch in cents, LUFS, clipping counts) still come from the analysis. The image adds what text is bad at: where in the song something happens, and what a wave looks like.

## Who wants this and why now

- **Josh and Claude, in every composing session** (idea 003). Claude edits patterns and instruments and checks its work with `render` and `preview_instrument`.
- **A public report.** The author of [fframes](https://github.com/dmtrKovalenko/fframes) (a Rust video framework, MIT) [wrote](https://x.com/neogoose_btw/status/2111523195006468408) that "models working with audio perform better and finish work faster if you give them visual waveform not just text summary. Significantly better." fframes now has `audio analyze --waveform w.png`, which draws a waveform with the video's scene lines and cue ticks. This is one person's report, not a measurement, which is why this brief is a test first.
- **Our own weak spot.** The 004 blind test (ideas/004-headless-listen-report.md, "Spike results") got **1 of 3**: from the text reports alone, a fresh agent could not tell which of three instrument edits was made. Pitch and envelope were reliable; tone was not. A close-up of the wave and a harmonic bar chart are a natural thing to try on exactly that failure.

## Why this project, why cheap

- **No new dependencies.** The server uses the `mcp` 2.x library, which can return images from a tool (`mcp.server.mcpserver` exports `Image`; `mcp.types` has `ImageContent`). numpy is already a dependency and ffmpeg is already required for `export_video`.
- **Drawing is easy with what we have.** ffmpeg can draw a waveform or spectrum image straight from a WAV (`showwavespic`, `showspectrumpic`). For order lines and labels, drawing with numpy and writing the PNG with the standard library is a few dozen lines. `video.py` already draws text through ffmpeg `drawtext` with Furnace's own font (`_FONT`, `video.py:28`).
- **The audio is already there.** `render` writes the mix WAV and, with `per_channel`, one WAV per channel (`server.py`, `render`). `fsong.excerpt` knows the order range. The order boundary times come from the same row and tick timing that `-info` reports.
- **It touches only `tools/furnace-mcp`.** No Furnace C++ changes, so no upstream merge cost.

## Why not use fframes itself

fframes' waveform command works on videos built as fframes projects, and it needs a Rust toolchain. Our scope videos already work with Python and ffmpeg (idea 014). Adopting fframes would add a second video pipeline for a feature we can draw ourselves. Its useful parts are ideas to copy: the waveform with scene lines (our order lines), and `strip`, a contact sheet of frames (item 4).

## Trade-offs and risks

- **Tokens.** Each image costs Claude roughly 1–2k tokens at a typical size. Images must be opt-in, with a default size that stays readable but small (for example 1200 px wide).
- **Too many channels.** A 20-channel Genesis plus SN song is a tall stack. Drop silent channels, as the video already does, and cap the image height.
- **The claim may not hold here.** Chip audio is simple waveforms; text may already be enough for most tasks. The test decides.
- **False confidence.** A picture can look right while the pitch is off by 20 cents. The tool descriptions must say: use the image for shape and timing, the text for exact values.
- **Claude Code must pass the image through.** The `mcp` library supports images, but check that Claude Code shows a tool's image to the model in this setup before building more than item 1.

## Open questions

1. Does Claude Code hand an MCP tool's image to the model here? (Spike step 1.)
2. Which size and layout read best: stacked channels, or the mix only with per-channel colors?
3. Is a spectrogram worth its tokens, or does a short spectrum strip under the mix do the job?
4. For `preview_instrument`, which close-ups help most: one cycle, a few cycles, or the attack's first 50 ms?
5. Should images be saved next to the WAVs in `%TEMP%\furnace-mcp` so Josh can open them too? (Likely yes; it's free.)

## Spike plan

1. **Check the plumbing.** Make a throwaway tool that returns a small PNG. Call it from a Claude Code session and ask Claude to describe the picture. *You'll know when* Claude describes what is actually in the image.
2. **Build item 1** behind `render(..., image=True)`: stacked waveforms with order lines and hex labels, and a spectrum strip under the mix. Save the PNG beside the WAV and return it with the text report. Test that the order lines land on the right samples for a song with a speed change. *You'll know when* the image of a known demo shows each order boundary where the audio changes.
3. **Write six test tasks with known answers**, on demo songs or copies with one planted change:
   - which channel clips
   - which order a part drops out in
   - which channel is too quiet against the others
   - which of three instrument edits was made (repeat 004's three trials)
   - whether a loop point clicks
   - which of two renders has the faster attack

   *You'll know when* each task has one right answer written down before any trial.
4. **Run the A/B blind test.** For each task, one fresh agent gets the text report only and another gets text plus the image. Neither sees the answer. Count right answers and tool calls. *You'll know when* you have two scores out of six (or nine, with the three 004 trials), and the tool-call counts.
5. **Decide**, then build items 2–4 only if the test supports them. Item 2 is the one aimed at 004's tone problem, so the instrument-edit trials matter most.

## Decision criteria

- **Build it**: images win at least two more tasks than text alone, or win the instrument-edit trials (2 of 3 or better where text got 1 of 3), at a token cost Josh accepts. Then add items 2–4 and consider making images the default for `preview_instrument`.
- **Reshape it**: images help only on timing questions (where in the song), not on tone. Keep item 1, skip item 2, and look again at the timbre metrics from 004.
- **Drop it**: no difference, or images make answers worse. Keep the plumbing check's result in this brief and stop.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\022-show-claude-the-audio.md in full before doing anything. It is a design-spike brief: run the spike steps in order, answer the open questions, and report against its decision criteria. Scope: add an optional waveform-and-spectrum image to the furnace-mcp render tool and blind-test whether it helps Claude answer questions about the audio. Work only in tools/furnace-mcp, on a branch. Do not build items 2-4 until the blind test says to. Use fresh agents for the blind trials so no agent grades its own work.
```
