# 006 — Write new chip emulators with Claude

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/engine/sysDef.cpp src/engine/song.h src/engine/dispatchContainer.cpp src/engine/platform/dummy.cpp`.

- **Status**: SELECTED
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

## Spike plan

1. **Write the recipe from evidence.** Read `9d279cead` (Supervision) and one more simple chip addition, and write `ideas/chip-recipe.md`: every touchpoint, what goes there, and a one-line example from Supervision. *You'll know when* the recipe lists all 16 touchpoints with no "figure it out" steps.
2. **Settle the ID policy on paper**: pick a range, check `sysDef.cpp` for conflicts, and note what happens when upstream reuses an ID. *You'll know when* Josh has approved a range.
3. **Pick the pilot chip** with Josh. Confirm its reference core's license and that it builds standalone. *You'll know when* the reference core renders a test tone outside Furnace.
4. **Follow the recipe** to add the pilot chip on a branch, without GUI polish. *You'll know when* the fork builds, the chip appears in the system picker, and a one-channel test song plays.
5. **Verification harness**: export the test song's register log, run it through the standalone reference core, and compare against Furnace's `-output` (pitch and level per note, or a sample-level match if the cores match). *You'll know when* you have a pass/fail number, not a judgement.
6. **Reflect**: note where the recipe was wrong or incomplete and update it. *You'll know when* a second chip could be started from the recipe alone.

## Decision criteria

- **Build it** (as a standing workflow or skill): the pilot chip passes the harness, the recipe needed only small corrections, and the ID policy holds.
- **Reshape it**: real-chip ports work but verification is too fuzzy. Focus on invented chips (Klattsch-style), where "correct" is whatever sounds good to Josh.
- **Drop it**: each chip needs deep, non-repeatable work (large GUI changes or engine changes beyond the 16 touchpoints), so a recipe doesn't save much.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\006-chip-emulators-with-claude.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: write a repeatable recipe for adding a sound chip to this Furnace fork, settle a fork-only chip-ID policy with Josh, and prove both on one pilot chip with a reference-comparison check. Do not build beyond the spike; prototype work happens on a branch. Ask Josh to choose the pilot chip and approve the ID range before writing chip code.
```
