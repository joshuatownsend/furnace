# 021 — Microtonal tuning tables (EDO, Scala, maybe MTS-ESP)

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/engine/engine.cpp src/engine/engine.h src/engine/pitchTable.cpp src/engine/dispatch.h src/engine/platform/fmshared_OPM.h src/engine/song.h src/engine/song.cpp src/engine/fileOps/fur.cpp src/engine/fileOps/json.cpp src/gui/songInfo.cpp src/gui/gui.cpp src/gui/guiConst.cpp src/gui/compatFlags.cpp src/engine/playback.cpp src/engine/platform/tia.cpp src/engine/platform/genesis.cpp tools/furnace-mcp/furnace_mcp/song.py`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 6/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in (revived from the parked list, upstream discussion #881), with a real user in the family
- **Effort (coarse)**: L (the engine part is smaller than the card says; the note names, the editor and the file format are the bulk)
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Give each song an optional tuning table: the exact pitch of every note. Load it from an EDO size ("31 equal steps per octave") or a Scala `.scl` file, optionally with a `.kbm` keyboard map. Every chip then plays the table's pitches, with no per-row effects. Optionally, follow a live tuning broadcast by ODDSound's MTS-ESP.

There are two sizes of table:

- **12 notes per octave, retuned.** Meantone, just intonation, Pythagorean, any 12-note `.scl`. Note names stay as they are; `C-4` is still C, just tuned differently.
- **Any number of steps.** 19, 31, 53-EDO, Bohlen-Pierce (which repeats at 3/1, not the octave). Here a Furnace note is a scale step, so `C-4`, `C#4`, `D-4` mean steps 0, 1, 2. The names need to change.

## Who wants this and why now

- **Michael**, Josh's son, plays a Lumatone (280 hex keys) in 12-tone and microtonal tunings and posts Furnace songs to YouTube. Ideas 18 and 19 come first.
- **Upstream users have asked since 2022.** Discussion #881 (converted from issue #465, May 2022) has 7 comments asking for Scala import, an EDO setting or MTS-ESP. The one maintainer reply, to "has there been any progress?", is "None." (2024). Community workarounds use `E5xx` and an online `.scl` to Deflemask-effect converter. No upstream code, issue or PR is under way.
- **Why revive it now:** idea 19 makes the cheap path (note plus `E5xx` detune) real. This brief scopes the expensive path so we know when to switch.

## What Furnace does today

### One tuning number

- The song stores one float, the A-4 frequency (`song.h:312`, default 440 at `:424`). It is a bare float in the `.fur` header (`fur.cpp:2590`, read at `:848` and `:1227`) and `songInfo.tuning` in JSON (`json.cpp:44`, `:1504-1505`).
- The Song Info box clamps it to **220-880 Hz** (`songInfo.cpp:105-107`). The 400-500 Hz clamp the card mentions only applies inside the FM block/F-num calculation (`engine.cpp:1857-1859`).

### Where a note becomes a pitch

With linear pitch (the default, `song.cpp:1128`), a note is turned into "pitch units" of 1/128 semitone, and only later into Hz. There are four places that do the first step, and each one is just `note<<7`:

| Where | Used by |
|---|---|
| `DivEngine::calcBaseFreq`, linear branch (`engine.cpp:1847-1849`) | chips through `NOTE_PERIODIC` / `NOTE_FREQUENCY` |
| `DivEngine::calcBaseFreqFNumBlock`, linear branch (`engine.cpp:1897-1899`) | OPN-family FM chips (`NOTE_FNUM_BLOCK`, `dispatch.h:1691`) |
| `DivPitchTable::getBase`, linear branch (`pitchTable.cpp:174`) | the shared pitch table (66 of 82 chip files) |
| `NOTE_LINEAR` (`fmshared_OPM.h:25`) | OPM / OPZ / MSM5232 (`arcade.cpp`, `tx81z.cpp`, `msm5232.cpp`) |

The second step, units to Hz, happens in two places:

- `DivEngine::calcFreq` (`engine.cpp:1908-1932`): `pow(2,(nbase+384-7680)/1536)` at `:1920`. 11 FM chip files call it.
- `DivPitchTable::get` (`pitchTable.cpp:71-134`): a 13-entry table for one octave (built at `:205-217`), shifted by octave, with straight-line steps inside each semitone.

Both of those take **any** unit value and don't care how far it is from the original note. `calcFreq` feeds it straight into `pow`; `DivPitchTable::get` splits it into a whole note (`>>7`) and a fraction (`&127`).

### The cheap engine change

So a tuning table can be one array per song: an offset, in 1/128-semitone units, for each of the 180 notes. Add `offset[note]` at the four `note<<7` places and every chip on those paths plays the table's pitch:

- Slides and portamento aim at the target note's tuned value, because the target goes through the same macros.
- `E5xx`, vibrato and pitch slides still work in 12-tone cents on top. That's fine for small bends.
- The offset can be any size. A 31-EDO table, with "note = step", puts step 179 about 11,000 cents below 12-tone note 179 (my arithmetic). The pitch code handles that (it only floors negative whole notes at 0, `pitchTable.cpp:81-84`).
- Accuracy: 1/128 semitone is 0.78 cents, the same as `E5xx`.

This needs linear pitch. Songs set to "None" (`compatFlags.cpp:311-312` in the GUI) must refuse a table or warn, as in 019.

### What the cheap change misses

- **Arpeggios on the 11 `calcFreq` FM chips** are added in 12-tone semitones after the base (`engine.cpp:1912-1917`; `genesis.cpp:905` passes `arpOff` in), so they skip the table. Pitch-table chips arpeggiate through `getBase` and are fine. Fix: look up the arpeggio note in the table too.
- **Chips that skip all four paths**: TIA (`tia.cpp:308`, `<<8`), the sample-only OKI chips, Klatt speech, and others (`klattsch.cpp`, `msm6258.cpp`, `msm6295.cpp`). Sample chips that use per-sample pitch tables are on the shared path and fine.
- **Previews**: sample and wavetable previews use their own 12-tone formula (`engine.cpp:2393`, `:2430`).
- **MIDI output (Melodic)** sends the 12-tone note (`playback.cpp:405-505`). A synth on the other end won't hear the tuning.
- **furnace-mcp's pitch probes** assume 12-tone (`furnace_mcp/song.py:532`).
- **Coarse registers are not fixed.** SN76489 and NES round the same way whether the pitch came from a table or from `E5xx` (see the table in 019). 021 is not a fix for coarse chips.

### Note names

Note names are fixed 3-character labels, 180 of them (`guiConst.cpp:51`), picked in `FurnaceGUI::noteName` (`gui.cpp:105-128`). For a 12-note retuned table nothing changes. For a 31-step table, the cell `C#4` would mean "step 1 of octave 4", which reads badly. Some tuning-aware name scheme is needed in the pattern editor, the piano, note input and the MIDI file importer. This is most of the L.

The range also shrinks. 180 notes is 15 octaves in 12-tone, 5.8 octaves in 31-EDO, and only 3.4 octaves in 53-EDO. Each chip's own usable range cuts that further; measure it in the spike.

## File format and upstream

- **Storage.** Two options:
  - A new `.fur` element. Upstream's loader skips element types it doesn't know (`fur.cpp:1021-1028`; the list is `song.h:45-58`, ending at `DIV_ELEMENT_MAX`=11). Pick a high number so a future upstream element can't collide.
  - A key in the compatibility-flags element, which is stored as `key=value` text (`song.cpp:1202-1349`). Upstream ignores keys it doesn't know.
- **What upstream does with the file:** it opens and plays it in plain 12-tone, with no warning. Re-saving in upstream drops the table. That's a quiet failure, so the fork should also write a note in the song comments ("tuned with a fork tuning table: 31-EDO").
- **Sharing with upstream users:** a furnace-mcp "flatten" command can turn a tuned song into idea 19's form (12-tone note plus `E5xx` on every note row) for posting. Any pitch is within ±50 cents of a 12-tone note, so it always fits. It needs a free effect column, and slides become approximate.
- **JSON (idea 001):** add `songInfo.tuningTable` next to `songInfo.tuning`: the source (EDO size, or the `.scl` / `.kbm` text) plus the computed offsets, so Claude can write and read tuned songs. Store the source too, so the table can be rebuilt and edited.

## Parsing Scala

Don't write a parser. `surge-synthesizer/tuning-library` is MIT, header-only C++, reads `.scl` and `.kbm` and computes frequencies. It is maintained (last pushed 2026-10-17) and used by Surge XT. MIT is fine in GPL software. (#881 also points at `MarkCWirt/libscala-file`, MIT, which only reads `.scl`.)

The `.scl` and `.kbm` formats are summarised in 019.

## MTS-ESP

- **What it is.** One "master" program (ODDSound's free MTS-ESP Mini, or a DAW plug-in) publishes a tuning. Every "client" program asks it for the frequency of each MIDI note. It supports per-channel tables for keyboards with more than 128 keys, like the Lumatone.
- **License: fine.** The `ODDSound/MTS-ESP` repo is **0BSD** (`LICENSE`, "Permission to use, copy, modify, and/or distribute this software for any purpose"), which is GPL-compatible. A client compiles in two files, `Client/libMTSClient.h` and `.cpp`.
- **The runtime piece.** The client loads ODDSound's `libMTS` library at run time if it's installed (Windows: `Program Files\Common Files\MTS-ESP`). If it isn't, the client falls back to 12-tone and Furnace runs as normal. An open-source replacement for `libMTS` exists (`baconpaul/mts-dylib-reference`, MIT).
- **Precedent.** Surge XT, which is GPL-3.0, ships these client files in `libs/oddsound-mts`.
- **The catch.** MTS-ESP covers MIDI notes 0-127 (`MTS_NoteToFrequency(client, note, channel)`). A Furnace note is a MIDI note plus 48 (`gui.cpp:5290`), so only Furnace notes 48-175 are covered. Also, a song that follows a live master sounds different when exported from the command line, with no master running.
- **So:** use MTS-ESP to *fill* the song's table ("copy the current MTS-ESP tuning into this song"), and optionally to follow live while editing. Never let a song depend on it to sound right.

## When 021 is worth it over 019

019 (`E5xx` per row) is enough when Michael records and plays mostly 12-note-ish music with some detuned notes. 021 is worth its cost when:

- **He writes in a non-12 scale for real.** In 31-EDO with 019, about 2.6 keys share each 12-tone note name. The pattern says `C-4 E5B0` and `C-4 E580` for two different pitches. With 021, each step has its own note.
- **He wants clean patterns.** No effect column used up by tuning, and `E5xx` is free for musical bends again.
- **Slides and arpeggios should move in scale steps.** Portamento with 021 lands on the tuned target. With 019, a slide to a note lands on its 12-tone pitch plus whatever detune was last set.
- **He wants to retune a whole song.** Swap meantone for just intonation by changing one table, not every row.
- **The scale doesn't repeat at the octave** (Bohlen-Pierce). `E5xx` can still reach each pitch, but nothing in the song knows the scale.

021 does **not** help with coarse chip registers, and it does not work on non-linear-pitch songs.

## Trade-offs and risks

- **Note names are the real cost.** A 3-character cell per note, used across the pattern editor, piano, input and import. Getting this right for 31 or 53 steps is the L.
- **Silent wrong pitch in upstream.** Covered above; the song comment and the "flatten" command are the mitigations.
- **Busy upstream files.** `engine.cpp`, `pitchTable.cpp` and the OPM header change. Keep the change to one helper (`tunedBase(note)`) called from the four places, marked as fork code.
- **Range.** 53-EDO fits only 3.4 octaves in 180 notes. Enough for one melody, maybe not for a song with bass and lead.
- **Arpeggio and effect meaning.** `00xy` and the arpeggio macro become "steps", not semitones, in an N-step table. That's arguably right, but old instruments sound different in a tuned song.
- **Scope creep.** Per-instrument or per-chip tables, MPE, tuning changes mid-song. All out of scope.

## Open questions

1. After 019's spike, is `E5xx` good enough for Michael? (If yes, park 021.)
2. Does he need N-step scales (31, 53-EDO) or mostly retuned 12-note scales? The second is much cheaper (no name changes).
3. For N-step scales, what should a note cell show? Step number plus octave ("17 4")? Scala-style names from the `.scl` comments? Up-down arrow notation for 31-EDO?
4. Does he already use MTS-ESP (with a DAW or MTS-ESP Mini)? If not, skip it.
5. A new `.fur` element or a compatibility-flags key? (Decide during the spike; both load in upstream.)
6. Should the table be per song or per sub-song?

## Spike plan

Steps 1-5 need nothing from Michael. Step 6 needs Michael, ideally with the keyboard after idea 19's spike.

1. **Prototype the offset table** (no Michael). On a branch, add a 180-entry offset array to the song (not saved yet), a `tunedBase(note)` helper, and call it from the four `note<<7` places. Fill it from an EDO size with a debug command. *You'll know when* a 12-note "all zero" table plays every demo identically (render and compare against master), and a test table moves pitch on a pitch-table chip, an OPN chip and OPM.
2. **Measure it** (no Michael). Render 31-EDO and 53-EDO scales on an FM chip, NES and SN76489. Measure each note with furnace-mcp's pitch tools (`furnace_mcp/analysis.py:155`). Compare with 019's `E5xx` renders of the same scale. *You'll know when* you have a cents-error table per chip for both methods, and can say whether 021 sounds any different from 019 on those chips.
3. **Check effects** (no Michael). Portamento to a tuned note, `00xy` arpeggio on an OPN chip and on NES, vibrato, `E5xx` on top. *You'll know when* you can list which effects follow the table and which still need fixing (expect OPN arpeggios).
4. **Read Scala** (no Michael). Vendor `tuning-library` on the branch and fill the table from a `.scl` plus `.kbm` (a meantone and a 31-EDO file). *You'll know when* the table matches the library's own frequencies within 0.4 cents.
5. **Try MTS-ESP** (no Michael). Install MTS-ESP Mini, load a 31-EDO tuning, and copy it into the song's table through the client. *You'll know when* the copied table matches step 4's table for the same `.scl`, and Furnace runs normally with `libMTS` not installed.
6. **Show Michael** (Michael). Play him the same phrase made with 019 and with 021, and show him both patterns. Ask open questions 2-4. *You'll know when* he says which one he would rather write in, and which scales he needs.

## Decision criteria

- **Build it**: Michael writes in N-step scales or wants clean patterns, and steps 1-3 show the offset table works on his chips. Build in two stages: (a) the table, file storage, JSON, Scala import and a tuning panel, with 12-note scales only (M); (b) N-step note names and input (L). MTS-ESP "copy tuning" only if he uses it (S).
- **Reshape it**: only retuned 12-note scales are wanted. Ship stage (a) alone (M).
- **Drop it**: 019's `E5xx` is good enough for him, or the note-name problem has no answer he likes. Keep the furnace-mcp converter from 019 and park 021 again, with these findings attached.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\021-microtonal-tuning-tables.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Check its drift line first and re-verify any cited code that changed. Scope: prototype a per-song 180-entry pitch offset table added at the four note<<7 places, measure it against idea 019's E5xx approach on FM, NES and SN76489, read Scala files with surge-synthesizer/tuning-library (MIT), and try copying a tuning from MTS-ESP (0BSD client). Do not build beyond the spike; prototype work happens on a branch and saves nothing new to .fur. Steps 1-5 need no one; ask Josh to set up a session with Michael before step 6, ideally after idea 019's spike has run.
```
