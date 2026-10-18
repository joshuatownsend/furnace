# 012 — DAW plugin

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/engine/engine.cpp src/engine/engine.h src/engine/playback.cpp src/engine/sysDef.cpp src/audio src/main.cpp CMakeLists.txt`.

- **Status**: BRIEF WRITTEN
- **Verdict**: Validate
- **Score**: 5/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in (the top upstream request), new ground for the fork
- **Effort (coarse)**: L for a real plugin. S for the no-code check in step 1, M for a one-instance prototype.
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Load Furnace's chip emulators into a DAW as an instrument plugin. The DAW sends MIDI notes, and the plugin plays them on a Furnace instrument or song and returns audio. One plugin instance per track. The song or instrument is saved with the DAW project.

This brief is a design spike. It ends in a go, reshape or drop decision, and it starts with a check that costs no code.

## Who wants this and why now

- **Upstream discussion #1804** ("DAW-compatible (VST, CLAP, LV2) Synth Plugin?", 2024-03-18): 13 upvotes, 5 comments. One commenter would pay for an AU/VST version to use in Logic. Another mocked up a small "pick a chip, pick an instrument" plugin window. One pushes back: MIDI cannot carry many tracker playing tricks.
- **#2311** (the piano-roll thread, idea 013) has a commenter saying a DAW plugin is the better answer than a piano roll: Furnace stays a tracker, and DAW users get the chips.
- **Not Josh's own workflow** (portfolio card). Nobody in the family has asked for it yet. Does Michael use a DAW alongside Furnace? Ask (question 1).
- **Why now:** the license question got easier in late 2025 (see below), and the fork already runs the engine without a window for idea 003.

## What Furnace already has

- **It is already a MIDI-driven synth.** The engine reads MIDI input inside its audio callback (`src/engine/playback.cpp:2961`). With no song playing, a note starts the engine in "freelance" mode and plays it (`playback.cpp:2993–2996`). "Direct" mode maps MIDI channel N to tracker channel N (`playback.cpp:2984–2987`, flag at `src/engine/engine.h:715`). The GUI picks the instrument through a MIDI callback (`src/gui/gui.cpp:9297`).
- **One audio entry point.** Every backend calls one function, `DivEngine::nextBuf(in, out, inChans, outChans, size)` (`playback.cpp:2908`), through `process()` (`src/engine/engine.cpp:48`) set at `engine.cpp:4259`. A plugin's process call maps onto it directly.
- **Backends are small classes.** `TAAudio` holds the callback pointer and a `TAMidiIn` (`src/audio/taAudio.h:170–184`). `TAMidiIn` has a plain queue the engine drains (`taAudio.h:139–142`). Existing backends: SDL, JACK, PortAudio, ASIO, pipe to stdout (`src/audio/pipe.cpp:52`), and a dummy (`engine.cpp:4234`).
- **Runs without a window.** The CLI uses the dummy backend for export and info (`src/main.cpp:606–691`). But `-DBUILD_GUI=OFF` does not build with MSVC on Josh's machine (upstream `main.cpp` calls SDL without including it), so a plugin build must link the engine without that path.
- **Stems for a DAW today.** `-outmode perchan` writes one WAV per channel (`main.cpp:469`), and the fork's `-exportchans` picks channels (`main.cpp:101`, `:478`). Drag the files into any DAW.
- **MIDI file import.** Upstream `loadMIDI` (`src/engine/fileOps/midi.cpp:423`) turns a .mid into a song, which the CLI can render.

## Prior art: someone already did a prototype

`agrecascino/furnacevst` (a fork, last pushed 2023-01-01, 5 stars) built a VST 2.4 plugin in about 900 lines:

- a `TAAudioVST` backend whose `onProcess` drains MIDI and calls the engine callback from the host's process call (`src/audio/vstAudio.cpp`, 113 lines),
- a `TAMidiIn` subclass fed by host MIDI events (`src/audio/vstmidi.cpp`),
- the plugin entry (`src/vst/plugin.cpp`, 351 lines), a CMake `AS_VST` option that builds a DLL, and `#ifdef VSTTARGET` lines in `engine.cpp` that force the backend and low latency.

Copy the shape, not the code: it used the VST 2.4 SDK, which Steinberg no longer distributes. It was abandoned, and I could not find any working Furnace plugin. The portfolio card's "this starts from nothing" is too strong: there is a pattern to follow.

## Plugin format and license

Furnace is "GPL version 2 or later" (`LICENSE`, `src/main.cpp:8`). "Or later" lets us distribute a build under GPLv3, and upstream already does that: its `LICENSE` says enabling ASIO makes a GPLv3 binary. So license is not the blocker it looked like.

| Option | License | Notes |
|---|---|---|
| CLAP | MIT | Plain C API, small. Hosted by Bitwig, Reaper and others. Not hosted by every DAW (check Ableton and Logic before relying on it). |
| VST3 SDK | MIT since VST 3.8 (Steinberg, 2025-10-29) | The kickoff note "GPLv3 or proprietary" is out of date. Widest DAW support on Windows. |
| clap-wrapper | MIT | Wraps one CLAP build as VST3, AUv2, AUv3 and a standalone app (its README). |
| DPF | ISC | One codebase for LV2, VST2, VST3 and CLAP. |
| LV2 | ISC | Linux-first. Not useful for Josh on Windows. |
| JUCE | AGPLv3 or paid | Heavy, and AGPL raises questions with emulator cores under "various licenses" (`LICENSE`). Avoid. |

**Recommendation: write a CLAP plugin, and use clap-wrapper for VST3 (Windows DAWs) and AU (Logic).** CLAP is the smallest API to learn and all three licenses are MIT, so the plugin can stay GPL-2-or-later. DPF is the fallback if we want LV2 too or clap-wrapper fights us. Before shipping, check each emulator core's own license is GPL-compatible; that is already true for the app, so it should hold for the plugin.

## Trade-offs and risks

- **One engine per process.** Plugin hosts load many instances into one process. The engine is a class, but some state is shared:
  - `sysDefs` is a static array (`engine.h:872`, `src/engine/sysDef.cpp:28`), but the "already registered" flag is per engine (`engine.h:721`). A second engine re-runs `registerSystems()` (`engine.cpp:4356`) and allocates over the array: 115 `new DivSysDef` calls (for example `sysDef.cpp:892`), while the first engine may be reading it.
  - Some emulator cores keep global tables filled on first use: `okim6258.cpp:32–35`, `pokey/mzpokeysnd.c:57–60`, `ymz280b.cpp:46`.
  - The logger is global (`src/ta-log.h:41`, `:59`).
  - Each engine reads and writes the user's `furnace.cfg` and `furnace.log` (`initConfDir` at `engine.cpp:4342`, log at `engine.cpp:4372`).
  Fixable (register once, behind a lock; skip the config file in plugin builds), but these are edits to busy engine files.
- **Real-time safety.** `nextBuf` takes a mutex (`playback.cpp:2925–2930`) and creates its render thread pool on first use (`playback.cpp:2953–2957`). Hosts expect the process call not to block. Probably fine for a prototype; a problem for a product.
- **Tempo and transport.** A plugin that plays whole songs must follow the DAW's tempo and position. Furnace has no clock input (see idea 17). An instrument-only plugin avoids this.
- **What MIDI cannot say.** Tracker effects (arpeggio, pitch slides, macros per row) have no MIDI equivalent. The plugin plays instruments well and songs badly. That is the #1804 pushback, and it is fair.
- **GUI.** A plugin window needs ImGui inside a host window. The first version can have no GUI at all: load a .fur file from a path.
- **Build.** A new CMake target that builds the engine as a DLL. The full GUI build takes 20+ minutes here. The engine is most of it.
- **Merge cost.** New files under `src/plugin/` and `src/audio/` are cheap. The engine fixes for multiple instances touch `engine.cpp`, `engine.h` and `sysDef.cpp`, which change often upstream.

## Open questions

1. Does Michael, or Josh, use a DAW? Which one (Ableton, FL Studio, Reaper, Logic)? That decides whether CLAP alone is enough.
2. What should the plugin play: one instrument on one chip, a whole .fur's instruments across its channels, or a whole song synced to the DAW?
3. Does the no-code route (step 1) feel good enough? If it does, the plugin only adds saving with the DAW project and many instances.
4. How many instances does a real project need? One per chip, or one per track?
5. Does the engine load a .fur and play MIDI correctly at 48 kHz, at buffer sizes from 32 to 2048 samples?
6. Do all emulator cores survive two engines in one process once `registerSystems` runs once?
7. Is a GUI-less first version (a file path setting) acceptable?

## Spike plan

1. **No-code check.** Install loopMIDI (a free virtual MIDI cable for Windows). Point the DAW's MIDI output at it and select it as Furnace's MIDI input. Load a .fur with a few instruments, use direct mode, and play from the DAW. Record Furnace's output back into the DAW. *You'll know when* Josh or Michael can say "good enough" or name what is missing (latency, no project saving, one instance only).
2. **Ask question 1 and 2.** *You'll know when* you have one target DAW and one target use (instrument or song).
3. **Build a one-instance CLAP prototype** on a branch. A new `src/plugin/clap.cpp` owns one `DivEngine`, sets a new `TAAudio` backend modelled on furnacevst's `vstAudio.cpp`, loads a .fur from a fixed path, feeds host note events into `midiIn->queue`, and calls the callback from `process()`. No GUI. *You'll know when* the target DAW (or Reaper, via clap-wrapper's VST3 if needed) plays notes from a .fur through the plugin.
4. **Load two instances.** Make `registerSystems` run once per process, then load two plugins with different chips. *You'll know when* both play at once for 10 minutes with no crash, and you have a list of any other shared state you hit.
5. **Measure.** Check CPU per instance for a heavy chip (OPN2 or OPL3) and a light one (SN76489), at a 64-sample buffer. *You'll know when* you can tell Josh how many instances a normal PC handles.
6. **Write up** the go / reshape / drop call and the cost of the full plugin (GUI, state saving, VST3 and AU wrapping). *You'll know when* Josh can pick one.

## Decision criteria

- **Go**: step 3 works, two instances run in step 4 without big engine surgery, and someone will use it in their DAW. Plan the full plugin (L): GUI, state saved in the DAW project, clap-wrapper builds.
- **Reshape**: step 1 is good enough, or nobody needs it inside the DAW. Ship a guide for loopMIDI plus Furnace, and lean on stems (`-outmode perchan`) and MIDI file rendering. Maybe add a CLI "render this .mid with this .fur's instruments" command (S).
- **Drop**: nobody in the family uses a DAW, or multiple instances need deep engine rewrites that would conflict with every upstream sync.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\012-daw-plugin.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: find out whether Furnace's engine can run as a CLAP instrument plugin in one DAW, starting with the no-code loopMIDI check in step 1, then a GUI-less one-instance CLAP prototype on a branch. Do not build beyond the spike: no plugin GUI, no VST3 or AU packaging, no engine changes beyond what step 4 needs. Ask Josh which DAW he and Michael use (question 1) before step 3.
```
