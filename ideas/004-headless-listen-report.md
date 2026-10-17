# 004 — Headless "listen" report for rendered audio

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/gui/tuner.cpp src/main.cpp`.

- **Status**: IN PROGRESS (branch `idea/004-listen-report`, brief refreshed 2026-10-17 at `40684545c`)
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

## Decision criteria

- **Build it** (as an MCP tool): the reports move in the expected direction and Claude identifies at least 2 of 3 edits.
- **Reshape it**: pitch and envelope are reliable but timbre isn't. Use it for tuning and envelopes only, and keep Josh's ears for timbre.
- **Drop it**: the metrics don't track audible changes.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\004-headless-listen-report.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: test whether a text audio-analysis report lets Claude tell how a Furnace instrument edit changed the sound. Do not build beyond the spike; prototype work happens behind a flag or on a branch.
```
