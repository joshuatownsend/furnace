# 016 — Sample editor: DC offset removal, SF2 and SFZ import

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/gui/sampleEdit.cpp src/gui/doAction.cpp src/gui/gui.h src/gui/guiConst.cpp src/engine/fileOpsIns.cpp src/engine/fileOpsSample.cpp src/engine/instrument.h tools/furnace-mcp`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 4/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in (OpenMPT has both; upstream #2174)
- **Effort (coarse)**: S for DC offset; M for SFZ plus SF2
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Two separate pieces that share a theme: better samples.

1. **DC offset removal.** One action that shifts a sample (or the selected part) so its average sits at zero. Recorded and resampled audio often sits a little above or below zero. That wastes headroom, causes clicks at loop points and note starts, and hurts low-bit chips the most.
2. **SF2 and SFZ import.** Load a soundfont preset as one Furnace sample instrument: its samples, their root notes and loops, and which keys use which sample.

No change to the `.fur` format for either.

## Who wants this and why now

- **OpenMPT** has both: "Remove DC Offset" in its sample editor, and SF2 and SFZ instrument loading. People who move from OpenMPT expect them.
- **Upstream #2174** (2024, 4 upvotes) asks for SFZ, SF2, SF3, SFOGG, ITI and DLS. The one reply suggests skipping envelopes and letting the user set them up. That is the right first cut.
- **Furnace's own FAQ** says to use OpenMPT or Polyphone to turn an SF2 into WAV files first (`doc/1-intro/faq.md:133-135`). So the workaround is a two-program round trip today.
- **Why now**: idea 005 merged (`7447298d4`, #12). `detect_sample_pitch` and `tune_sample` can check or fix the root note of every sample a soundfont brings in. Idea 11 adds other instrument loaders on the same path.

## What Furnace already has

### The sample editor (`src/gui/sampleEdit.cpp`)

- Actions today (`GUI_ACTION_SAMPLE_*` in `gui.h:1021-1030` and around): normalize, fade in and out, silence, invert, sign flip, reverse, filter, resample, trim (to selection, to loop, after loop, side noise), cut/copy/paste/mix, loop set and fix, and "create wave".
- **No DC offset removal.** I found none in the editor or in `doAction.cpp`. The only "DC offset correction" in the GUI is a display option of the oscilloscope (`chanOsc.cpp:174`). It changes how the scope is drawn, not the sample.
- **Workaround today:** the filter tool has a high-pass slider (`sampleEdit.cpp:1421-1490`). A high-pass removes DC, but it also thins the bass and changes the sound. Not the same thing.
- **The template is Normalize** (`doAction.cpp:1423-1470`): undo point, engine lock, work on the selection (`SAMPLE_OP_BEGIN`), 8-bit and 16-bit only, clamp, re-render. DC removal is the same shape: compute the average, subtract it, clamp. The button would sit next to Normalize (`sampleEdit.cpp:1297`).

### Multi-sample instruments already exist

- Every sample instrument has a per-key sample map: `DivInstrumentAmiga::noteMap[180]`, switched on by `useNoteMap` (`instrument.h:526-543`). Each of the 180 keys picks a sample (`map`) and the note it plays at (`freq`) (`instrument.h:554-576`).
- That is the shape of a soundfont preset: key ranges, each pointing at a sample with a root note. So the import is a "zone list → note map" builder plus two file readers.
- Fine tuning per sample goes into the sample's center rate, the same way WAV import handles root note and detune (`fileOpsSample.cpp:402-412`).

### Import plumbing is in place

- An instrument loader returns a list (`instrumentFromFile`, `fileOpsIns.cpp:1874`). A file with many presets already gets the "which ones to load?" picker (`gui.cpp:6852`), and samples created by a loader are rendered afterwards (`gui.cpp:6836-6839`).
- WAV, AIFF and FLAC (when built in) load through libsndfile (`fileOpsSample.cpp:27`). SFZ points at external sample files, so those load with code that already exists.

### No soundfont code

No SF2, SFZ or soundfont parser anywhere in `src/` or `extern/`. Only the FAQ entry above.

## Why this project, and why it is cheap (or not)

- **DC offset is tiny code**, but where it lives decides the cost:
  - **Sample-editor button.** Touches `sampleEdit.cpp` (7 commits upstream in 90 days, 31 in a year), plus the `gui.h` enum, `guiConst.cpp` action list and `doAction.cpp`. Each is a few lines, but they are busy upstream files. Upstream may well take a clean PR, which would remove the cost.
  - **MCP tool only**, like idea 005. furnace-mcp already reads sample audio (`furnace_mcp/song.py:599 sample_pcm`) and writes songs back. Zero merge cost, but no button for anyone who is not using Claude.
  - 005 chose the MCP route for the same reason. This is Josh's call; see the open questions.
- **SFZ and SF2 are new loader code**, which is the cheap kind: `fileOpsIns.cpp` saw 0 upstream commits in 90 days. The dialog filter is a one-line edit in `gui.cpp`.

## Format notes

### SFZ (text)

- Plain text with headers (`<control>`, `<global>`, `<group>`, `<region>`) and `opcode=value` pairs. Spec: sfzformat.com.
- The opcodes we need: `sample=` (a file path relative to the `.sfz`, or to `default_path`), `lokey`/`hikey`/`key`, `pitch_keycenter`, `tune`, `transpose`, `loop_mode`, `loop_start`/`loop_end`, `lovel`/`hivel`.
- Settings from `<global>` and `<group>` carry down into each `<region>`.
- Notes can be names (`c4`) or numbers; octave numbering differs between tools (`octave_offset`). Check against Furnace's C-4.

### SF2 (binary RIFF)

- `RIFF sfbk` with three lists: `INFO`, `sdta` (one big block of 16-bit samples, `smpl`), and `pdta` (the "hydra": `phdr pbag pmod pgen inst ibag imod igen shdr`). Spec: SoundFont 2.04.
- A preset points to instruments; each instrument has zones with generators. We need `keyRange`, `velRange`, `sampleID`, `overridingRootKey`, `sampleModes` (loop), `coarseTune` and `fineTune`. Each sample header (`shdr`) gives start, end, loop start, loop end, sample rate, original pitch and pitch correction.
- **SF3** is SF2 with Ogg Vorbis samples. It will not work in the fork's build: `ENABLE_EXTERNAL_LIBS=OFF` in `build-gui/CMakeCache.txt`, so there is no Vorbis decoder.

### Parsers we could reuse

| Library | License | Notes |
|---|---|---|
| TinySoundFont (`schellingb/TinySoundFont`) | MIT | Single header. Reads SF2 presets, zones and samples. Active (pushed 2026-07). We need only its loader, not its synth. |
| sfizz (`sfztools/sfizz`) | BSD-2-Clause | Full SFZ engine. Large, and quiet since 2025-03. Too big for this; an SFZ reader of our own is a few hundred lines. |
| Polyphone | GPL-3 | Not compatible with GPL-2+. Do not copy. |

MIT and BSD-2 are both fine with Furnace's GPL-2.0-or-later.

## Trade-offs and risks

- **Soundfonts are big.** A General MIDI soundfont is many megabytes. Most chips have small sample memory (SNES 64 KB, many others less). Import one preset at a time, and show the memory use before adding it.
- **What gets lost.** Furnace's note map has no velocity layers, so we keep one layer per key (say which). SF2 envelopes, filters, LFOs and modulators are dropped at first, as #2174's reply suggests. Stereo samples become mono (Furnace samples are mono).
- **Root note and octave.** SFZ tools disagree on octave numbering, and Furnace has its own. A wrong offset makes every key one octave off. `detect_sample_pitch` can catch this in the spike.
- **DC removal on short loops.** Removing the average of a whole sample can still leave a looped section offset. Work on the selection, so a user can fix the loop part alone.
- **Merge cost** if the DC button goes into the sample editor (see above).

## Open questions

1. DC offset: a sample-editor button, an MCP tool, or both? 005 went MCP-only to avoid `sampleEdit.cpp`.
2. Which comes first: DC offset (small, sure), or soundfont import (bigger, more asked for)?
3. Which soundfonts do people actually want to use? A small free SFZ set is a good test. A GM SF2 tests the memory problem.
4. With velocity layers, keep the loudest, the softest, or the middle one?
5. Should soundfont import stay with idea 11 as one "import" PR, or ship on its own?

## Spike plan

1. **DC offset in Python** (no C++). In the scratchpad, read a few demo songs' samples with `sample_pcm` and print each sample's average. *You'll know when* you know how common a real offset is in actual songs, and how big (in percent of full scale).
2. **DC offset prototype** (on a branch, or as an MCP tool, per question 1). Copy the Normalize action's shape: average over the selection, subtract, clamp, 8-bit and 16-bit. *You'll know when* a test sample with a known offset comes back with an average of zero, and undo restores it.
3. **Note map builder** (on a branch). A small function that takes a list of zones (low key, high key, sample, root key, cents) and fills `noteMap[180]`, `useNoteMap` and the sample center rates. *You'll know when* a hand-made zone list plays the right sample on each key, in tune.
4. **SFZ reader** on top of step 3. Parse headers and the opcodes above; load each `sample=` file with the existing sample loader. *You'll know when* a small free SFZ piano loads as one instrument, plays across the keyboard, and `detect_sample_pitch` agrees with each sample's `pitch_keycenter`.
5. **SF2 reader** on top of step 3, using TinySoundFont's loader or a small reader of our own. *You'll know when* one preset from a free SF2 loads with its loops and key splits, and the picker lists every preset in the file.
6. **Memory check.** Import a big GM preset onto a small-memory chip. *You'll know when* you can say what the user sees: a clear size warning, or a silent failure.

## Decision criteria

- **Build it**: DC removal works and is reversible; SFZ loads a real instrument in tune. Ship DC removal first (S), then SFZ, then SF2 (M together), each as an upstream-friendly PR.
- **Reshape it**: soundfonts load but are rarely usable on chips (too big, too many layers). Ship DC removal plus SFZ only, since SFZ users choose their own small sample sets (S).
- **Drop the soundfont half**: the note-map approach can't hold real presets without losing too much. Keep DC removal, and point the FAQ at idea 005's tools for tuning WAVs exported from Polyphone.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\016-sample-editor-dc-offset-sf2-sfz.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: (1) DC offset removal for 8- and 16-bit samples, modeled on GUI_ACTION_SAMPLE_NORMALIZE in src/gui/doAction.cpp; (2) SFZ then SF2 import as sample instruments, built on DivInstrumentAmiga::noteMap in src/engine/instrument.h. Ask Josh first whether DC removal goes in the sample editor (sampleEdit.cpp is an upstream churn hotspot) or as a furnace-mcp tool. Do not copy GPL-3 code (Polyphone); MIT (TinySoundFont) and BSD-2 (sfizz) are fine. Prototype on a branch; do not build beyond the spike.
```
