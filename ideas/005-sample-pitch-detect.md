# 005 — Detect a sample's pitch automatically

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/gui/sampleEdit.cpp src/gui/tuner.cpp doc/9-guides/tuning-samples.md`.

- **Status**: SELECTED
- **Verdict**: Validate
- **Score**: 6/10 (see ideas/README.md)
- **Lenses**: inside-out (Signal 5, friction worth productizing)
- **Effort (coarse)**: S–M
- **Planned at**: 5b9c00314 on 2026-10-15

## The idea

A "Detect pitch" action in the sample editor. It analyses the loaded sample, finds its fundamental, and sets the sample's center rate so it plays in tune at C. It could also be an MCP tool for idea 003.

## Who wants this and why now

- The docs tell users to do this by hand: `doc/9-guides/tuning-samples.md:10-12` has them work out the semitone offset themselves or use an external calculator, then type the result in.
- Josh's interview mentions "tuning". Unknown whether he means samples. If he doesn't use recorded samples, this idea has little value for him.

## Why this project, why cheap

- `src/gui/tuner.cpp:37-59` already has an FFTW peak detector, used only on live output.
- The sample editor already sets the center rate in several places (`src/gui/sampleEdit.cpp:808`, `:852`, `:882`). Center-rate handling was reworked very recently (commit `98ea886f0`, "dev256 - new center rate").

## Trade-offs and risks

- **Noisy samples** (drums, noise, chords) have no clear pitch. The action must say "no clear pitch" rather than guess.
- **Merge cost**: `sampleEdit.cpp` is a 90-day churn hotspot, so a GUI change there will conflict on upstream syncs. An MCP-side tool (analyse, then set the rate via JSON) avoids that.
- **Sibling**: an external pitch tool plus manual entry, which is today's documented workflow.

## Open questions

1. Does Josh load recorded samples at all? If not, park this.
2. How accurate is the existing tuner FFT on short samples (under 0.2 s)?
3. What field does the "new center rate" (`98ea886f0`) store, and how do you convert from detected Hz?
4. GUI button, MCP tool, or both?

## Spike plan

1. **Ask Josh question 1.** *You'll know when* you know whether to continue.
2. **Read `98ea886f0`** to learn how the center rate is stored now. *You'll know when* you can write the Hz → center-rate formula.
3. **Run the tuner's peak detection offline** on three samples: a sine, a sampled piano note, a bass. *You'll know when* you have the detected pitch versus the true pitch, in cents.
4. **Prototype** the fix outside the GUI first: set the rate via JSON or a script, then render. *You'll know when* the sample plays in tune at C.

## Decision criteria

- **Build it**: Josh uses samples, and detection is within ±10 cents on pitched samples.
- **Reshape it**: build it as an MCP tool only, to avoid `sampleEdit.cpp` conflicts.
- **Drop it**: Josh doesn't use samples.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\005-sample-pitch-detect.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: check whether automatic sample pitch detection is accurate and wanted. Do not build beyond the spike; prototype work happens behind a flag or on a branch.
```
