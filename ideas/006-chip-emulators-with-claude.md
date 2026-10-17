# 006 — Write new chip emulators with Claude

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/engine/sysDef.cpp src/engine/sysDef.h src/engine/dispatchContainer.cpp src/engine/platform/dummy.cpp`.

- **Status**: SPIKE DONE (2026-10-17, branch `idea/006-chip-recipe`); verdict: build it
- **Verdict**: Validate
- **Score**: 8/10 (band says Advance; held at Validate because the pilot chip, accuracy reference and ID strategy are all open)
- **Lenses**: inside-out (Signal 4, a pattern hand-rolled 100+ times) / outside-in (interview; upstream: new chips are the largest request theme)
- **Effort (coarse)**: M for the recipe, then M–L per chip
- **Planned at**: 5b9c00314 on 2026-10-15

## The idea

A repeatable way for Claude to add a sound chip to the fork. It has two parts:
- a written recipe: every file to touch, in order, with a known-good example for each;
- a verification harness: render a test song and compare it with a reference emulator's output.

Prove it on one pilot chip. After that, adding a chip becomes "pick a chip and a reference core; Claude follows the recipe".

## Who wants this and why now

- **Josh**, added mid-run on 2026-10-15: "I'd also like to be able to write new chip emulators using Claude". It extends his interview answer about "chip creation".
- **Upstream users**: new chips are the largest suggestion theme by count (about 100 threads, e.g. #873 with 27 comments; #2203 Yamaha PSS; #1748 N64; #1854 SunPlus SPU). Upstream turns many of them down ("Sound chip creator: out of scope", #1746). A personal fork doesn't share those constraints.

## Why this project, why cheap

- **The pattern is fixed and well-trodden.** Adding Watara Supervision (`9d279cead`) touched exactly 16 files, 916 lines:
  - sound core: `platform/sound/supervision.c/.h`, about 350 lines;
  - driver: `platform/supervision.cpp/.h`, about 500 lines;
  - small registrations: `song.h` (enum), `sysDef.cpp` (13 lines: name, ID, channels, effects), `dispatchContainer.cpp`, `instrument.h`, `insEdit.cpp`, `sysConf.cpp`, `presets.cpp`, `guiConst.cpp`, `sysPartNumber.cpp`, `debug.cpp`, `furIcons.h`, `CMakeLists.txt`.
- **There's a starting template**: the Dummy System (`src/engine/platform/dummy.cpp`, 211 lines; `sysDef.cpp:2824`).
- **Most Furnace chips are ports of existing open-source cores** (MAME, Mednafen, Nuked; e.g. `97402e6d4` "replace … core with MAME", `841af611b` "bring Mednafen core back"). Claude would be porting and wiring, not inventing an emulator from a datasheet.
- **Invented chips are accepted.** Klattsch, a Klatt speech synthesiser with no real hardware (`390137b35`, July 2026), shows a "chip" can be a synth design. That covers "chip creation" in the literal sense.

## Trade-offs and risks

- **Chip IDs are written into saved songs.** Each system has a one-byte file ID (Supervision `0xe3`).
  - At 5b9c00314, the IDs in use in `sysDef.cpp` run from `0x80` up to `0xe7` with gaps, plus `0xf0`, `0xf1`, `0xf5`, `0xfc` and `0xfd` (Dummy). Low IDs `0x01`–`0x49` are legacy DMF systems.
  - Upstream's next new chips will most likely take `0xe8` and up, so a fork range should sit elsewhere. Candidates are `0xf6`–`0xfb`, but re-scan `sysDef.cpp` before choosing. Upstream may still claim those IDs later.
  - Songs using fork chips will not open in upstream Furnace.
  - This needs an explicit decision before the first chip.
- **The enum lives in `song.h`.** Adding entries there conflicts with every upstream chip addition. Append at a clearly fork-marked spot.
- **Accuracy.** Without real hardware, "correct" means "matches the reference core". The pilot should be a chip with a trusted reference.
- **Licensing**: Furnace is GPL-2.0-or-later. A ported core must be GPL-compatible. Most MAME sound cores are BSD-3-Clause, which is fine; check each one.
- **Size**: a chip is about 1,000 lines touching 16 files. That's well within Claude's reach per chip, but it is real review work for Josh, who doesn't review C++. The harness has to carry the verification.
- **Upstream will never accept these** (AI policy). They are fork-only by design.

## Open questions

1. **Which pilot chip?** Ideally a simple PSG with a well-known open-source core that Furnace lacks, so the spike tests the recipe rather than emulation difficulty. Josh may have a chip he actually wants.
2. **Reference for verification**: run the reference core standalone on the same register writes and compare the output? Furnace's command-stream or VGM export could supply the register log.
3. **ID policy**: which reserved range, and how to make collisions with a future upstream ID visible on load?
4. **Real or invented?** Is the target real hardware (port a core) or invented chips like Klattsch (design a synth)? The recipe differs.
5. **How much GUI** does a minimal chip need? Can `insEdit.cpp` and `sysConf.cpp` changes be skipped for a first version?
6. **Can the recipe become a Claude Code skill** so later chips need only "add chip X using core Y"?

## Decisions (2026-10-17)

- **Chip IDs: `0x1000` and up**, chosen by Josh. Current `.fur` files store the chip ID in two bytes (`DivSysDef::id` is `unsigned short`, written at `fur.cpp:2599`, read at `fur.cpp:870`). Upstream has only ever assigned IDs below `0x100` (`papers/format.md`), so a range at `0x1000` should never collide. Songs that use a fork chip won't open in upstream Furnace, as with any choice.
- **JSON stores the enum value, not the file ID** (`json.cpp:78`, read at `json.cpp:1537`). The fork's enum entries come after upstream's, so every upstream chip addition would shift them. The pilot adds the file ID to JSON export and makes import prefer it.
- **Pilot chip: Bally Astrocade**, chosen by Josh. Three square voices, noise, and a master oscillator with vibrato. Reference core: MAME `astrocde.cpp`.
- **The enum moved**: it is in `src/engine/sysDef.h` now, not `song.h`. Supervision (`9d279cead`) and µPD1771C (`f14ff2579`, MAME core `97402e6d4`) both predate the reorganisation (`9b35ca77c`), so the recipe maps their touchpoints to current paths.

## Spike plan

1. **Write the recipe from evidence.** Read `9d279cead` (Supervision) and one more simple chip addition, and write `ideas/chip-recipe.md`: every touchpoint, what goes there, and a one-line example from Supervision. *You'll know when* the recipe lists all 16 touchpoints with no "figure it out" steps.
2. **Settle the ID policy on paper**: pick a range, check `sysDef.cpp` for conflicts, and note what happens when upstream reuses an ID. *You'll know when* Josh has approved a range.
3. **Pick the pilot chip** with Josh. Confirm its reference core's license and that it builds standalone. *You'll know when* the reference core renders a test tone outside Furnace.
4. **Follow the recipe** to add the pilot chip on a branch, without GUI polish. *You'll know when* the fork builds, the chip appears in the system picker, and a one-channel test song plays.
5. **Verification harness**: export the test song's register log, run it through the standalone reference core, and compare against Furnace's `-output` (pitch and level per note, or a sample-level match if the cores match). *You'll know when* you have a pass/fail number, not a judgement.
6. **Reflect**: note where the recipe was wrong or incomplete and update it. *You'll know when* a second chip could be started from the recipe alone.

## Spike results (2026-10-17)

**Verdict: build it.** The pilot chip passes both checks. The recipe needed one real correction, the pitch divider, which the check caught. The ID policy holds.

### What was built (branch `idea/006-chip-recipe`)
- `ideas/chip-recipe.md`: every touchpoint with its current path and line, the driver skeleton, build and smoke test, traps, and verification. Written from Supervision (`9d279cead`) and µPD1771C (`f14ff2579`, `97402e6d4`), mapped to HEAD, then corrected by the pilot.
- **Bally Astrocade, file ID `0x1000`:**
  - core `src/engine/platform/sound/astrocade.cpp/.h`, MAME's core with only the device plumbing removed;
  - driver `src/engine/platform/astrocade.cpp/.h`;
  - registered in 11 small edits (`sysDef.h/.cpp`, `dispatchContainer.cpp`, `CMakeLists.txt`, `guiConst.cpp`, `sysConf.cpp`, `about.cpp`, `main.cpp`, `papers/format.md`).
  - Channels: tones A, B and C, plus noise. Instrument type `DIV_INS_STD` (standard macros: volume, arpeggio, pitch).
  - Effects: `10xx` master oscillator, `11xx` vibrato speed and depth, `12xx` modulation source (vibrato or noise).
- **JSON chip identity:** export writes `fileID`, import prefers it (`json.cpp`). Fork chips in JSON no longer shift when upstream adds a chip.
- **Checks in `tools/chip-verify/astrocade/`:**
  - `fidelity.cpp`, run by `build.cmd`. It builds MAME's unmodified original (pinned to `d0f1c15`) against a small framework stand-in.
  - `wiring.py`.

### Results
- **Core fidelity: PASS.** 5 seeds × 20 s of chip time (35.8 M samples each, about 3,600 random register writes) gave 0 mismatched samples. A planted one-bit change (vibrato depth mask) failed with 29 M mismatches.
- **Driver wiring: PASS**, 28 segments:
  - Every note sits within 0.02 cents of an integer period's exact frequency.
  - The chosen period is the nearest one, or one step off in 2 of 25 notes; that one-step miss is Furnace's pitch-table rounding, shared with every period-based chip.
  - Volume steps match the linear mix to 0.01 dB. Noise is noise (spectral flatness 0.65).
  - All three effects work. `10xx` retunes the tones. `11C8` vibrato alternates the cycle length in the ratio 0.749 (0.750 expected). `12xx` noise modulation scatters cycle lengths by 22%.
  - The chip loads by its JSON `fileID` and survives a `.fur` save and reload with ID `0x1000`.
  - Planted wiring bugs failed the check: swapped tone B and C volume registers, and a driver ignoring `11xx` and `12xx`.
- **Regression:** the furnace-mcp tests pass (60/60). A 30-demo JSON round trip gave 30 of 30 renders byte-identical to the `.fur` renders, with `fileID` present in every export.

### Answers to the open questions
1. **Pilot chip:** Bally Astrocade (Josh).
2. **Reference:** the original MAME core compiled unmodified next to the port. A register-log comparison inside Furnace was unnecessary, because the core check covers the emulation and the render check covers the driver. Neither proves MAME matches real hardware.
3. **ID policy:** `0x1000` and up (Josh). It works because `.fur` stores IDs in 16 bits. Instrument types are different: one byte, numbered densely by upstream. So fork chips must use `DIV_INS_STD` or an existing type, never a new one.
4. **Real or invented:** real (a port). Invented chips skip the core-fidelity check, and "correct" means sounding right to Josh.
5. **GUI:** none beyond the picker list, a category list and the "no options" case in chip settings. The standard instrument editor covers the instrument.
6. **Skill:** feasible. The recipe plus the two checks make "add chip X using core Y" a repeatable request. Turning it into a Claude Code skill is the next step if Josh wants more chips.

### The recipe's one real miss
The pitch-table divider. The recipe's SN76489 analogy said to double the chip's divider; the correct move was to halve it. Doubling it played two octaves high, and the chip's own divider played one octave high. Only the render check showed it. The recipe now says to measure rather than reason.

### Not checked
- The GUI: the chip in the "add chip" picker, the oscilloscope and Register View. Josh can check it by eye in a GUI build.
- Long-song stability.
- Real hardware recordings.
- There is no docs page (`doc/7-systems/`) yet.

## Decision criteria

- **Build it** (as a standing workflow or skill): the pilot chip passes the harness, the recipe needed only small corrections, and the ID policy holds.
- **Reshape it**: real-chip ports work but verification is too fuzzy. Focus on invented chips (Klattsch-style), where "correct" is whatever sounds good to Josh.
- **Drop it**: each chip needs deep, non-repeatable work (large GUI changes or engine changes beyond the 16 touchpoints), so a recipe doesn't save much.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\006-chip-emulators-with-claude.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: write a repeatable recipe for adding a sound chip to this Furnace fork, settle a fork-only chip-ID policy with Josh, and prove both on one pilot chip with a reference-comparison check. Do not build beyond the spike; prototype work happens on a branch. Ask Josh to choose the pilot chip and approve the ID range before writing chip code.
```
