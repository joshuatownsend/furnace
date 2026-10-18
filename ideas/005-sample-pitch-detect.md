# 005 — Detect a sample's pitch automatically

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/gui/sampleEdit.cpp src/gui/tuner.cpp doc/9-guides/tuning-samples.md`.

- **Status**: BUILT on branch `idea-005-sample-pitch`, not merged yet. Reshaped as MCP tools only, `detect_sample_pitch` and `tune_sample`. See Result.
- **Verdict**: Validate (Josh chose Build it, reshaped)
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

## Result

Josh chose to build it, reshaped as MCP tools so `sampleEdit.cpp` stays untouched. The code is in `tools/furnace-mcp`:

- `detect_sample_pitch(sample)` reports what a written C-4 plays, as a note, cents and a 0-1 confidence. It says "no clear pitch" when there isn't one.
- `tune_sample(sample, c4_plays="")` sets the center rate.

**How it works.** A looped sample is measured on its loop, repeated as it plays. An unlooped one is measured from the end of the attack until it fades 30 dB below its peak.

YIN finds the period, and the harmonics' spectral peaks refine it. An odd-harmonic check fixes the octave-low errors that YIN makes on very short periods.

Two checks give "no clear pitch":
- Aperiodicity above 0.3, or less than 60% of the energy on the harmonics. This catches noise, hats and kicks.
- No strong partial below the third harmonic of the common period. This catches chords, which repeat together at a period below all their notes.

The tuner's FFT peak picker in `tuner.cpp` wasn't reused. It runs on live output in the GUI, and a single FFT peak falls for weak fundamentals.

**Accuracy against synthetic tones**, by brute-force sweep:
- rates 8000 to 44100 Hz
- pitches 41 to 1760 Hz
- lengths 0.08, 0.15 and 1.0 s
- 16-bit audio in the sweep; the tests repeat it at 8-bit

| Signal | Worst error (cents) |
|---|---|
| sine | 2.0 |
| sawtooth | 0.7 |
| fundamental 30 dB down | 0.7 |
| no fundamental | 0.1 |
| piano-like (decaying, stretched partials) | 1.2 |

Noise, decaying noise (hats), a pitch-swept kick, and equal-tempered major triads (sine and sawtooth) all gave "no clear pitch" in every case. The tests (`tests/test_sample_pitch.py`) require under 10 cents, at both 8 and 16 bits.

**The real proof: render a note, tune, render again.** These are measured with the idea-004 listen report, using the instrument with its macros removed.

| Sample and chip | Before | After |
|---|---|---|
| Ibiza piano (16-bit, looped) on RF5C68 | +14.0 cents from C-6 | −1.6 cents |
| Ibiza piano on Amiga | +13.8 | +1.5 |

The Amiga has integer periods, so it can be a cent or two off on its own.

The engine itself plays rates faithfully. A 32-sample sine at 5 rates × 4 notes on the RF5C68 landed within 2.1 cents of the formula, except where the chip's maximum rate capped the note.

Real demo samples:
- Detected pitches: The Amigamen strings at C-4 +3.5, its lead at C-4 −1.4, Sonic CD bass at D#1 +40.
- No clear pitch: every drum, hat and cymbal in Ibiza, The Amigamen and Sonic CD House.

**Open questions:**

2. *The tuner FFT on short samples.* It wasn't needed. The new detector stays within 2 cents down to 0.08 s, which is under the brief's 0.2 s, on synthetic tones at 8 and 16 bits.
3. *The field and the formula.* The field is `centerRate`, an integer: the sample editor's "Hz", the playback rate for a written C-4. Commit `98ea886f0` moved the nominal C-4 rate from 8363 to 8372 Hz. The engine scales a sample's pitch table by `centerRate / getCenterRate()` (`pitchTable.cpp:45`). `getCenterRate()` is 8363 when `compatFlags.oldCenterRate` is set: on pre-dev256 `.fur` files and MOD/S3M/XM/IT imports, which covers every demo checked.
   - With a measured period of T samples, a written C-4 plays `d = 1200·log2(32·centerRate / (nominal·T))` cents above C-4.
   - Tuning sets `centerRate · 2^(−d′/1200)`, where d′ is d reduced to the nearest octave.
   - The song's tuning cancels out (verified with renders at A=432).
   - The doc's own example comes out right: an E recorded at 22050 Hz gives 17501.
4. *GUI button, MCP tool, or both?* The MCP tool only, for now. A button in `sampleEdit.cpp` is a separate decision because of merge cost.

**Choices made:**
- Tuning picks the C nearest the sample's own pitch, so the rate moves half an octave at most. A recorded E then plays E on an E. Transposing to an exact C-4 can ask for rates above what a chip plays; `c4_plays` does it on request.
- If a loop starts late and the part before it is 5 cents or more off the loop, the report says so. Ibiza's "pianolow" loop is cut about 6 cents sharp of its attack.
- Both tools list the instruments on the sample and flag arp and pitch macros, since those shift the sample again. Ibiza's piano instrument has a −64 pitch macro.

**Limits:**
- Only 8- and 16-bit PCM are read. BRR (all the SNES demos), ADPCM and µ-law samples get "can't analyse depth N"; a BRR decoder would be a small follow-up.
- On a very low bass, the render check isn't trustworthy. The Sonic CD bass (40 Hz, 0.39 s, 8-bit) reads within ±4 cents across windows with the new detector. The idea-004 listen report reads the same sample about 10 cents higher at 33-40 Hz, so after tuning it measured +11 to +13 cents.
