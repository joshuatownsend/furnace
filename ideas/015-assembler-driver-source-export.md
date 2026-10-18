# 015 — Assembler and driver source export

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/asm src/engine/cmdStream.cpp src/engine/cmdStreamOps.cpp src/engine/cmdStream.h papers/export-tech.md src/engine/export src/engine/exportDef.cpp src/main.cpp`. After each upstream sync, also run `git log --oneline f491976c9..upstream/master -- src/asm papers/export-tech.md src/engine/cmdStream*`: upstream owns this code and is changing it.

- **Status**: BRIEF WRITTEN
- **Verdict**: Validate
- **Score**: 5/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in
- **Effort (coarse)**: M-L (a guess; the pilot is M only if upstream's 6502 player works as described)
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Give homebrew developers music they can build into their own game. That means assembler source (or an include file) with the song data, plus a sound driver they call once per frame. The game keeps control: it can start and stop songs and change tempo, and later play sound effects.

This differs from idea 008. That idea makes a finished file for a music player. This one makes parts for a programmer.

Pilot target: **NES, ca65-compatible source, using upstream's own command-stream player** (`src/asm/6502/stream.s`) and the existing `-cmdout` export.

## Who wants this and why now

- **Homebrew developers who use Furnace for their game's music.** No named user yet. Josh's persona list does not include one, so the first open question is whether anyone close to Josh is in this group.
- **Other trackers already do this:**
  - FamiStudio ships an NES/Famicom sound engine for CA65, NESASM and ASM6, and exports music data for it and for FamiTone2 (famistudio.org/doc/export/, "FamiStudio / FamiTone2 Music").
  - Arkos Tracker 3 exports source "for any assembler" through its Disark tool, according to its release post on msx.org.
- **Upstream is building the pieces now.** See "What the fork already has".

## What the fork already has

The card says "no assembler source". That is not quite right:

- **TIunA (Atari 2600) already writes assembler source.** It produces `export.asm` (`src/engine/export/tiuna.cpp:612`), full of `.text x"..."` data lines (`tiuna.cpp:577-608`), for an outside driver at github.com/AYCEdemo/twin-tiuna (`src/engine/exportDef.cpp:98-107`). So the "data as source plus an outside driver" pattern is already here, for one chip.
- **ZSM is a data file for a driver library.** ZSMKit is an X16 music engine that games link in (`exportDef.cpp:84-96`).
- **Command stream export already exists.** `-cmdout <file>` (`src/main.cpp:753`, written at `main.cpp:1218-1232` by `saveCommand`) writes Furnace's own command stream (FCS). The format is in `papers/export-tech.md:256` onward. The docs call it a starting point for "writing a hardware sound driver" (`doc/2-interface/export.md:112-116`).
- **Upstream's 6502 player for that stream:** `src/asm/6502/stream.s` (1244 lines, by tildearrow). You define a few constants, call `fcsInit` once and `fcsTick` every frame, then call your own per-chip "dispatch" tick (`stream.s:1-20`).
- **An NES test ROM** that uses it: `src/asm/6502/nes/test.s` (687 lines). It has a minimal NES dispatch (`dispatchNoteOn` at `test.s:403`) and plays a checked-in 592-byte stream, `src/asm/6502/seq.bin` (`test.s:674`).
- **An SPC700 port** (`src/asm/spc700/stream.s`, 2026-03) and an Amiga test player (`src/asm/68k/amigatest/player.s`).
- **Instrument and macro data formats** for C64, SNES and Game Boy, plus compiled macros (`papers/export-tech.md:38-255`). The commits run from "macro compiler" (2026-02-08) to "instrument compilation, part 3" (2026-03-03).

None of the `src/asm` code is built by CMake. It uses WLA-DX (`src/asm/6502/nes/Makefile`), not ca65.

## Overlap with idea 008

The card says both ideas share one blocker, a per-chip player. That holds only for the driver route:

- **If 008 goes the register-log way** (its pilot), it needs only a tiny replayer and no music driver. The per-chip driver work then belongs entirely to 015.
- **Shared parts:** a 6502 toolchain in the repo (pre-assembled bytes, with `.s` source under `src/asm/6502/`), a way to test ROMs in Mesen, and the export-framework plumbing (`src/engine/export.h:58-109`).
- **A cheap shortcut that 015 should not take:** shipping 008's register log as `.byte` source. It would assemble, but a log is large and gives the game no control. That defeats the point of this idea.

## Trade-offs and risks

- **Upstream's player is behind its own format.** FCS gained raw-frequency commands `$b9`, `$ba` and `$bb` on 2026-06-19 (`b00df5eb2`, which says "usual tildearrow untested quality"; see `papers/export-tech.md:319-322`). The 6502 player was last changed on 2026-01-24 (`63c834a26`), and it treats `$b9` and `$ba` as no-ops (`stream.s:935-937`). A song that uses those commands will play wrong. This is the biggest risk, and spike step 1 tests it.
- **The stream is not the whole song.** The player reads commands. Instruments and macros need the compiled formats in `export-tech.md`, and the NES dispatch in `test.s` is a test, not a full driver (unverified how much of the NES instrument model it covers). Whether `saveCommand` already writes instrument data into the stream is unverified.
- **Moving target.** Upstream owns `src/asm` and changes it often. A fork-side driver risks heavy merge conflicts. Prefer adding an export wrapper around upstream's files and leaving the files themselves alone. Send fixes upstream.
- **Assembler choice.** Upstream uses WLA-DX. Most NES homebrew uses ca65. Converting the syntax by hand is a fork-only burden. The pilot should first try emitting data that both can read (plain `.byte` lines), and keep the player in WLA-DX syntax.
- **Size and CPU time.** Homebrew games care about both. Upstream's player has not been measured. Measure it in the spike.
- **The alternative is lossy.** Translating songs into FamiStudio's engine data would give developers a proven, widely used engine. But it means mapping Furnace's macros onto FamiStudio's envelopes, and FamiStudio's speed changes work in "FamiTracker tempo mode only". That is size L and loses features. Its engine has a permissive, notice-preserving license (header of `famistudio_ca65.s`), and FamiStudio itself is MIT, so either is GPL-2+ compatible.
- **Unverified licenses.** FamiTone2: I could not find its license; a NESdev forum post says the original FamiTone was public domain. Arkos Tracker 3's player license: not confirmed. Neither is on the pilot path.

## Open questions

1. Is there a real homebrew developer to design for (a friend, Michael later, Josh)? Which console and assembler do they use?
2. Does upstream's NES test ROM build and play `seq.bin` today with WLA-DX?
3. Does a fresh `-cmdout` stream from a simple 2A03 demo song play correctly in that test ROM, or do the new commands and missing instrument data break it?
4. How large are the player and the data, and how many CPU cycles does one frame take?
5. Will tildearrow accept fixes to `stream.s`, or is this code too early for outside changes? Ask on the upstream repo before sending any.
6. ca65 or WLA-DX for the output? Who would use the result decides this.

## Spike plan

1. **Build upstream's NES test as is.** Install WLA-DX, run `make` in `src/asm/6502/nes`, and open `test.nes` in Mesen. *You'll know when* the bundled `seq.bin` plays.
2. **Swap in a real stream.** Export a simple 2A03 song with `furnace -cmdout seq.bin demos/nes/<song>.fur`, rebuild, and listen. Try a song that uses portamento too. *You'll know when* you can say "plays right", "plays wrong because of `$b9`-`$bb`", or "plays wrong because of missing instrument data".
3. **Measure.** Read the ROM map for the player's size and use Mesen's profiler for cycles per frame. *You'll know when* you have two numbers for Josh.
4. **Emit source.** Write the stream as `.byte` lines with labels, in a scratch exporter registered beside TIunA, so `-romout song.s` produces a file a game can include. *You'll know when* the test ROM builds from that `.s` instead of `seq.bin` and sounds the same.
5. **Write up the gaps.** List what a homebrew developer would still need: full NES instrument support, an API to start and stop songs, sound effects. *You'll know when* Josh can choose between "contribute upstream", "wait for upstream" and "translate to FamiStudio instead".

## Decision criteria

- **Build it**: step 2 plays right, or nearly so, and step 3's numbers are reasonable for a game. Ship a thin source exporter around upstream's player and send player fixes upstream.
- **Reshape it**: the player is too early. Either wait for upstream's ROM export, keeping a watching brief with the drift check, or prototype FamiStudio data export for 2A03-only songs if a real developer needs NES music now.
- **Drop it**: no homebrew user turns up (question 1). This is a developer feature with no developer to test it.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\015-assembler-driver-source-export.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Run its drift check first. Scope: get upstream's 6502 command-stream player (src/asm/6502/stream.s with src/asm/6502/nes/test.s) building and playing a stream exported with furnace -cmdout from a simple NES demo song, measure its size and CPU cost, then try emitting the stream as includable assembler source. Do not edit upstream's src/asm files except on a scratch branch; do not build beyond the spike. Ask Josh question 1 (is there a real homebrew user) before step 4.
```
