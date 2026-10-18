# 023 — Finer pitch between notes on period chips

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 917239939..HEAD -- src/engine/pitchTable.cpp src/engine/dispatch.h src/engine/engine.cpp`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 6/10 (my estimate; /ideate has not scored this)
- **Lenses**: inside-out (found while measuring idea 019)
- **Effort (coarse)**: S–M (a small change in one file, but 73 chip drivers use it and existing songs may change)
- **Planned at**: 917239939 on 2026-10-18

## The idea

Under linear pitch, a note that sits between two semitones (an `E5xx` detune, vibrato, a pitch slide, a pitch macro) should get the chip's nearest period or frequency register value. On period chips (SN76489, NES and others) Furnace often picks the value next to it, so the note is off by up to about one register step more than it has to be.

## The evidence (idea 019, step 2)

`tools/furnace-mcp/examples/spike_019_scales.py` (on branch `idea-019-lumatone` until that merges) plays every 31 and 53-EDO step over four octaves and compares each note with the chip's nearest period. Worst error in cents, 31-EDO:

| Written octave | SN76489 measured | SN76489 best possible | NES measured | NES best possible |
|---|---|---|---|---|
| C-2 | 7.6 | 3.4 | 3.3 | 1.6 |
| C-3 | 9.8 | 6.7 | 5.2 | 3.4 |
| C-4 | 32.2 | 13.8 | 12.2 | 6.7 |
| C-5 | 82.0 | 25.5 | 34.6 | 14.5 |

Example: degree 84 of 31-EDO on the SN plays period 65 (36 cents off) where period 66 would be 9.5 cents off. Plain notes with no detune come out close to their best, so the problem is only between notes. FM (YM2612) is fine: within 3 cents everywhere.

## What the code does

`DivPitchTable::get` (`src/engine/pitchTable.cpp:69-123`) computes a linear-pitch frequency like this:

1. Look up the semitone's `root` and `diff` (distance to the next semitone) in a table built for one octave (`init`, `:160`).
2. Shift both down by the octave, **rounding each separately** (`:96-118`).
3. Return `root+((diff*fine)>>7)`: a straight line inside the semitone, **truncated** rather than rounded.

At high octaves `diff` is a few register steps, so rounding it to a whole number can move the slope by a large fraction. The straight line also ignores the curve of 1/period. Errors from all three add up. The likely result is the "one period off" in the table above. This is a reading of the code, not yet confirmed by a fix.

The exact path already exists: `DivEngine::calcFreq` with linear pitch (`engine.cpp:1910-1925`) does `pow()` and rounds once. Chips that use the pitch table skip it.

## Options

1. **Round instead of truncate, and keep `diff` at full precision** until the final step. Smallest change, same speed. Might recover most of the gap.
2. **Compute exactly**: `pow()` plus one rounding, as `calcFreq` does. Exact, but slower per tick on 73 drivers. The table was presumably added for speed, so measure the cost with `-benchmark render`.
3. **A finer table**: more entries inside each semitone. Exact enough and fast, but more memory.

## Risks

- **Existing songs change sound.** Vibrato, slides, `E5xx` and pitch macros on period chips would shift by a register step here and there. Small, but audible to a careful ear, and the CLI's byte-identical render checks over the demos would fail. Upstream would want a compatibility flag, and so should the fork, if this is meant to go upstream: old songs keep the old behaviour, new songs get the fix.
- **73 drivers** use the pitch table (`grep -l pitchTable src/engine/platform/*.cpp`). Some may depend on its quirks.
- **Upstream may know.** Search upstream issues for pitch table, vibrato or slide precision on SN and NES before building.

## Spike plan

1. **Confirm the cause.** In a scratch test, compute `get()`'s result and the exact period for each 31-EDO step on the SN, and check the "one period off" notes match. *You'll know when* the code explains every bad note in the table.
2. **Try option 1**, then option 2. Rerun `spike_019_scales.py`. *You'll know when* the SN and NES columns are near "best possible", or you know which option gets there.
3. **Measure the cost**: `-benchmark render` on a few demos before and after. *You'll know when* you have the slowdown in percent.
4. **Measure what old songs lose**: render the demo set before and after, and count the songs that change. Listen to the biggest changes. *You'll know when* you can say whether this needs a compatibility flag.
5. **Check upstream** for an existing issue or a reason for the current design.

## Decision criteria

- **Build it**: option 1 or 2 closes most of the gap at a small cost. Ship it behind a compatibility flag that is on for new songs, and offer it upstream.
- **Reshape it**: only option 2 works and it is slow. Use the exact path only when a channel has a detune (`E5xx` not `80`), which is what idea 019 needs.
- **Drop it**: the gain is small on real songs, or upstream rejects the idea and the fork doesn't want to carry it.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\023-pitch-table-rounding.md in full before doing anything. It is a design-spike brief: run the spike steps and report against its decision criteria. Scope: why DivPitchTable::get picks a period one step away from the nearest on period chips under linear pitch, and which fix closes the gap at what cost. Prototype on a branch; do not ship.
```
