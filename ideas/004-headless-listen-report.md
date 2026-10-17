# 004 — Headless "listen" report for rendered audio

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/gui/tuner.cpp src/main.cpp`.

- **Status**: BUILT as a pitch and envelope checker (retest 2 of 3, one hit coached; pitch fixed), in PR (branch `idea/004-listen-report`)
- **Verdict**: Validate
- **Score**: 7/10 (see ideas/README.md)
- **Lenses**: inside-out (Signal 4, data collected but not surfaced) / outside-in (interview)
- **Effort (coarse)**: M
- **Planned at**: 5b9c00314 on 2026-10-15

## The idea

Render a short passage (a note, an instrument preview, or a range of rows) and return a compact text report: detected pitch and how far off it is in cents, spectral centroid ("brightness"), the strongest harmonics, the attack/decay/sustain shape, peak and RMS loudness, and clipping. Claude can't hear, so this report is how it checks its own instrument edits.

## Who wants this and why now

- **Josh**: "chip creation/tuning through Claude" (interview, 2026-10-15). Tuning needs feedback, and this is the feedback.
- No upstream demand. Its value depends entirely on idea 003.

## Why this project, why cheap

- `src/gui/tuner.cpp:37-59` already detects peak frequency with FFTW, but only on the live output buffer in the GUI.
- FFTW is bundled in `extern/fftw`, and the CLI already renders audio (`src/main.cpp:637` `-output`).
- Smallest version: run the analysis inside the MCP server (idea 003) on the rendered WAV, using numpy or similar. No Furnace changes at all.

## Trade-offs and risks

- **Text metrics may not capture timbre well enough** to tune FM patches. Two patches can share a centroid and sound very different.
- **Where it lives**: in the MCP server (zero merge cost, but duplicates FFT code) or as a Furnace CLI flag (reuses tuner code, adds merge cost). Start in the server.
- **Sibling**: Josh listens and describes what he hears. That always works, but it's slower and keeps him in the loop.

## Refresh (2026-10-17, after 003 merged)

- **Drift**: `src/main.cpp` +185/−16 since planning. That is 002's export work, which this idea builds on. `src/gui/tuner.cpp` is unchanged.
- **Half of step 2 already exists.** 003's `render` tool runs `tools/furnace-mcp/furnace_mcp/analysis.py` on the rendered WAV. It reports peak, RMS, clipping, silence, spectral centroid, 85% rolloff, band energy and the strongest frequency below 5 kHz.
- **What's new for 004**:
  - real pitch detection, with the cents offset from the note played. The "strongest Hz" lands on a harmonic for many FM patches.
  - the top 8 harmonics, in dB relative to the fundamental.
  - an envelope estimate: attack, decay, sustain level and release.
- **A single isolated note needs no Furnace change.** The server builds a one-note song in memory from the source song's chips and instruments, then renders it with `-output` (001 made `.json` input possible). Timing is pinned: speed 6 at 60 Hz, so a row is exactly 0.1 s and the note-off time is known. The preview never goes through the save path, so it can't touch the open song.
- **Expected pitch**: Furnace note n is MIDI n − 48 (C-4 = 108 → 261.63 Hz; A-4 = 117 → 440 Hz, verified in 003).
- **Field names** (checked on Slap, instrument 0C of *All Good Times*): per-operator `mult`, `ar`, `dr`, `d2r`, `sl`, `rr`, `tl`, `dt`; patch-level `fm.alg` and `fm.fb`. Operators are in register order S1, S3, S2, S4. On algorithm 3 only `operators[3]` (S4) is a carrier, so a multiplier edit for the timbre test must go on a modulator. Slap's feedback is already 7 (the maximum), so the feedback test needs another instrument.
- **Blind test design**: Claude can't grade its own edits, since it knows which one it made. Each trial uses a fresh agent that sees only the before report, one after report and the list of three candidate edits. Three trials, so "2 of 3" is a real count.
- **Scope**: the analysis goes in `analysis.py`, and step 1 justifies one thin tool, `preview_instrument`. Nothing more until the decision.

## Open questions

1. Which metrics actually help Claude make a requested change ("brighter", "less buzzy", "punchier attack")?
2. Can Claude predict how an FM parameter change moves those metrics well enough to converge in 3–5 iterations?
3. ~~Does analysis need a single isolated note? That would need per-instrument preview rendering, which the CLI can't do today (`noteOn()` exists at `engine.h:1948` but isn't on the CLI).~~ Answered in the refresh: the server builds a one-note song and renders it, with no Furnace change.
4. Is pitch accuracy within a few cents enough to catch detuned samples (see idea 005)?

## Spike plan

1. **Render one instrument** by building a one-note song in the GUI and exporting it with `-output`. *You'll know when* you have a WAV of one sustained note.
2. **Write a script** that prints pitch, cents offset, centroid, the top 8 harmonics, ADSR estimates and peak/RMS. *You'll know when* the report fits in about 15 lines.
3. **Make three known edits** (raise an operator's multiplier, shorten the decay, raise feedback) and render each. *You'll know when* you can see whether the report changes in the expected direction for each edit.
4. **Blind test**: give Claude the before and after reports and ask which edit was made. *You'll know when* you have a hit rate out of 3.

## Spike results (2026-10-17)

**Setup.** Funk Gt (instrument 0D of *All Good Times*: algorithm 3, feedback 4, channel 6) at C-4 through the new `preview_instrument` tool, plus three edits:

- A: S2's multiplier, 2 → 5
- B: the carrier S4's decay rate, 13 → 20
- C: feedback, 4 → 7

**Did the reports move?** Yes. Every edit changed the report, but not always where theory says it would.

| | pitch | sustain | attack harmonics / brightness | held harmonics / brightness |
|---|---|---|---|---|
| before | +2.0 c | −25.8 dB | 0 3.2 −5.1 −5.2 … / 13.0x | 0 −4.1 4.3 −2 … / 6.14x |
| A (mult) | +2 c | ~same | h2 falls to −7.5 / 11.4x | changed |
| B (decay) | +2.2 c | **−50.3 dB** | similar / 18.0x | flat 0 −0.2 −0.6 … / 9.9x |
| C (fb) | +2 c | ~same | h8 up to −1.1 / **9.7x (darker)** | changed |

The first version of the report missed A and C completely. Their changes sit in the first 100 ms, so the timbre is now split into an attack window and a held window. Pitch did not move with any edit, as expected. Pitch was also within 1 cent on synthetic tones, including one with a missing fundamental (`tests/test_analysis.py`).

**Blind test: 1 of 3.** Each trial used a fresh agent that saw only the before report, one after report and the three candidate edits.

- **Trial 1 (true answer C, feedback): picked A.** Wrong. The agent reasoned that more feedback means brighter, but the measured attack got darker. The report was accurate; the agent's FM intuition was wrong for this patch.
- **Trial 2 (true answer A, multiplier): picked A.** Right, with medium confidence.
- **Trial 3 (true answer B, decay): picked C.** Wrong. The report was at fault. After the edit the held part is 50 dB down, nearly silent, so its "harmonics" are measuring the noise floor. They came out as a smooth flat slope, which the agent read as noise from heavy feedback. It did note the sustain drop, but trusted the bogus timbre more.

**Answers to the open questions.**

1. *Which metrics help?* Pitch in cents and the envelope (especially sustain level) are reliable and easy to read. Harmonics and brightness do move, but they need the attack/held split, and they are misleading when a window is near silent.
2. *Can Claude predict how an FM change moves the metrics?* Not reliably from intuition alone. In trial 1, "feedback brightens" was wrong for this patch. Converging over iterations would have to rely on measuring each step, not on predicting it.
3. Answered in the refresh.
4. *Is pitch good enough to catch detuned samples?* On synthetic tones and FM, yes: within 1 cent and stable across edits. Real samples (idea 005) were not tested.

**Verdict: reshape.** At 1 of 3, this misses the build bar of 2 of 3. Pitch and envelope did their job: both edits that turned on them showed up clearly in the report. Timbre is the weak part. One failure was a fixable report bug and the other a reasoning error, which matches the "reshape" criterion.

The reshaped tool:
- keeps `preview_instrument` for pitch and envelope;
- has the report drop the timbre line for any window more than about 40 dB below peak, saying "too quiet to measure" instead;
- frames harmonics and brightness as "what changed", for Josh to confirm by ear, rather than as a verdict.

A re-run of the blind test after that fix would tell whether timbre can be promoted. This spike can't claim that result in hindsight.

## Retest after the reshape (2026-10-17, `3059780ff`)

**The fix.** A timbre window more than 40 dB below the peak is now reported as "too quiet to measure tone", using the median 5 ms level as the sustain figure does. A first version used window RMS; it missed edit B, because the loud end of the decay at the start of the window dominated. When the note is already near silent at note-off, the release is reported as "n/a". The tool help now says which numbers to trust.

**Retest: 2 of 3.** Same Funk Gt reports, regenerated with the fix. Three fresh agents, candidates in a new order, plus the tool's guidance text exactly as it ships.

- Feedback (C): picked feedback. Right, medium confidence. **Caveat:** the guidance says "more feedback can make a patch darker", which came from trial 1 of this spike and points straight at this answer. This hit is coached.
- Multiplier (A): picked feedback. Wrong. It correctly saw that the change was in the attack window, then put it on S1 rather than S2.
- Decay (B): picked decay. Right, medium-high confidence. It used the sustain drop and the "too quiet" line.

**Reading.** Edits that show up in the envelope are identified reliably. Two different modulator edits, both of which show up as attack-window harmonic changes, are not told apart reliably. Without the coached hit this is 1 of 3, the same as before, so timbre is still not promoted. The report remains a pitch and envelope checker that also shows what changed in the tone, for Josh's ears to judge.

**Second patch: EP (19), which is not a valid trial set but did turn up findings.**
- *Pitch can fail.* EP's carriers run at mult 4 (S2) and mult 3 (S4). Speeding up S4's decay leaves mostly S2's 4f family, and the pitch tracker reported 345.5 Hz, "+481.6 cents", on a note whose pitch never changed. The earlier claim that pitch is reliable holds only when a carrier runs at mult 1. The tool help now says so.
- *Harmonics relative to the fundamental are unreadable when the fundamental is weak.* EP's held spectrum reads `0 19.9 34 26 …`. Normalizing to the strongest harmonic would read better.
- *Feedback 6 → 2 changed nothing measurable.* S1 sits at TL 37, so its feedback is inaudible. The report was correctly flat. This is a good sign for the metric, but it made the edit useless as a trial.

**Next fork, if pitch should be trusted on any patch:** use the known note. Report tuning as the magnitude-weighted deviation of the strongest partials from the nearest integer multiple of the expected frequency, and flag "pitch uncertain" when the tracker lands nowhere near expected × 2^k. Retest on EP.

## Pitch fix (2026-10-17)

Josh chose to fix pitch, then open a PR. The pitch tracker's answer is kept when it lands within 50 cents of an octave of the note played; the octave hint for Slap, an octave low, still works. Otherwise the report says "tracker unsure". It then gives the tuning from the partials: the magnitude-weighted offset of the strong partials from the nearest multiple of half the note's frequency (half, so mult 0 still fits), plus the share of energy that sits on that series.

On EP's decay edit, the report now reads "tracker unsure (found 345.53 Hz…); the partials sit −4.8 cents off the harmonic series of 261.63 Hz (100% of the energy is on it)". The −4.8 is real. The remaining carrier, S2, is at detune −3, while S4 (detune +3) dominated before the edit, at +0.7. Funk Gt, Slap and the other EP reports are unchanged. Tests cover the tuning from partials, with no energy at the fundamental, and an inharmonic tone.

Still open: harmonics are given relative to the fundamental. On patches with a weak fundamental that reads badly (EP B held: `0 1.3 19.8 72 …`). Measuring against the strongest harmonic instead is a small follow-up.

## Decision criteria

- **Build it** (as an MCP tool): the reports move in the expected direction and Claude identifies at least 2 of 3 edits.
- **Reshape it**: pitch and envelope are reliable but timbre isn't. Use it for tuning and envelopes only, and keep Josh's ears for timbre.
- **Drop it**: the metrics don't track audible changes.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\004-headless-listen-report.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: test whether a text audio-analysis report lets Claude tell how a Furnace instrument edit changed the sound. Do not build beyond the spike; prototype work happens behind a flag or on a branch.
```
