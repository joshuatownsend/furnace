# 019 — Lumatone layout import and microtonal input

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5e034e504..HEAD -- src/engine/playback.cpp src/engine/engine.cpp src/engine/engine.h src/engine/pitchTable.cpp src/gui/gui.cpp src/engine/fileOps/midi.cpp tools/furnace-mcp`.

- **Status**: Spike steps 1-4 done on branch `idea-019-lumatone` (2026-10-18); steps 5-7 wait for Michael. See "Spike results"
- **Verdict**: Advance
- **Score**: 7/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in, with a real user in the family
- **Effort (coarse)**: M (a small engine change is needed for live play; see "Corrections")
- **Planned at**: 5e034e504 on 2026-10-18

## The idea

Let Michael play his Lumatone in a microtonal tuning and hear it, and record it, in Furnace. Load a tuning (an EDO size or a Scala `.scl` file) and, optionally, his Lumatone mapping (`.ltn`). For each key (MIDI channel plus note) work out the nearest normal note and how far off it is, in cents. When recording, write that note plus an `E5xx` pitch effect on the row. When playing live, apply the same detune to the note.

Each tracker channel plays one note at a time, so a per-channel detune is enough. No change to the `.fur` format: `E5xx` is a standard effect, so the songs open in upstream Furnace and sound the same.

## Who wants this and why now

- **Michael**, Josh's son, plays a Lumatone (280 hex keys, MIDI) in 12-tone and microtonal tunings. He wants to record into Furnace patterns and play live.
- **Idea 18 comes first**: the plug-in test, which checks that the Lumatone works as a plain MIDI keyboard in Furnace in 12-tone. This brief assumes that passes.
- Furnace has no microtonal input today. I found no Scala, `.scl`, EDO or Lumatone code in `src/`, `doc/` or `tools/`.

## What Furnace already has

### E5xx: resolution and range

- **Linear pitch (the default, `song.cpp:1128`).** `E5xx` sets `chan[i].pitch=effectVal-0x80` (`playback.cpp:1458-1462`). The engine adds pitch to the note in units of 1/128 semitone: `pow(2,(nbase+384-7680)/(128*12))` (`engine.cpp:1920`).
  - One unit is **0.78 cents**.
  - The range is -128 to +127 units: **-100 to +99.2 cents**. The docs agree: "`00` is -1 semitone, `80` is base pitch, `FF` is nearly +1 semitone" (`doc/3-pattern/effects.md:30`).
  - Nearest-note mapping never needs more than ±50 cents (±64 units, `E540` to `E5C0`). So every EDO fits, and the rounding error is at most 0.39 cents. For 31-EDO (steps of 38.7 cents), 41-EDO (29.3) and 53-EDO (22.6) that is far finer than the step.
  - Most chips go through the shared pitch table, which interpolates in a straight line inside each semitone (`pitchTable.cpp:81-95`). That bends the curve by up to about 0.7 cents mid-semitone (my arithmetic). Negligible.
- **Non-linear pitch ("None" in compatibility flags, `compatFlags.cpp:311`).** One pitch unit is one raw register step (`engine.cpp:1935-1937`, `pitchTable.cpp:74-79`), so the cents change from note to note. Old imported songs may be set this way. The feature must require linear pitch, or warn.
- **E5xx stays set.** Nothing resets `chan[i].pitch` on a new note. The only write is `playback.cpp:1459`, and the channel state is only reset on a full reset (`engine.cpp:2206`). So recording must write `E5xx` on **every** note row, `E580` (no detune) included. Otherwise the next in-tune note keeps the last detune.

### Chips with coarse frequency registers

The engine asks for the right pitch, but the chip rounds it to its own register. On "period" chips, one register step is about 1731 / period cents (my arithmetic, not measured):

| Chip | Written A-4 sounds at | Period there | One step ≈ |
|---|---|---|---|
| SN76489 (10-bit) | 1748 Hz | about 64 | 27 cents |
| NES pulse (11-bit) | 881 Hz | about 127 | 14 cents |

So on the SN76489 from about written A-4 up, 53-EDO steps (22.6 cents) start to merge, and an octave higher even 31-EDO steps do. Lower notes are fine. FM chips and wavetable chips have much finer registers. Noise channels ignore fine pitch. Also, those chips sound one or two octaves above the written note (SN +2, NES and PCE +1), which changes where a Lumatone key lands. Measure all of this in the spike rather than trusting the table.

### Where MIDI notes go today

- **The GUI callback** (`gui.cpp:9297-9343`) sees each MIDI message first. It can cancel it or choose the instrument. It returns only an instrument number.
- **Recording** happens in the GUI's MIDI handler: `gui.cpp:5286-5296` calls `noteInput(msg.data[0]-12+60, ...)`. The MIDI channel is in `msg.type&15` there but is not passed on. `noteInput` (`gui.cpp:1653-1749`) writes the note, instrument and volume, and a latched effect into effect column 0 (`gui.cpp:1733-1734`).
- **Live sound** happens in the engine: `playback.cpp:2979-3033` turns each note into `autoNoteOn(...)` (`engine.cpp:3729-3795`). That function picks a free channel itself and never reads its channel argument. Note-off releases every channel playing that note number (`autoNoteOff`, `engine.cpp:3802-3806`); the MIDI channel is not checked (`:3801` is commented out).
- **Queued notes** become `DIV_CMD_NOTE_ON` in `playback.cpp:2142-2180`. `DivNoteEvent` has no pitch field (`engine.h:414-434`).
- **Pitch bend from the keyboard is ignored** for playing. The only `TA_MIDI_PITCH_BEND` use in the GUI is MIDI-learn (`gui.cpp:5268`), and the engine's switch has no case for it.
- **Direct channel mode** (`midiIsDirect`, `playback.cpp:2984-3012`) maps MIDI channel N to tracker channel N. That is the wrong meaning for a Lumatone, where the channel is part of the pitch. Rule it out.

### Effect columns

A free effect column is **not** guaranteed. New patterns have one effect column (`pattern.cpp:106`), the maximum is 8 (`defines.h:31`, checked at `song.cpp:529`), and column 0 already takes latched effects. The design should use a dedicated column and add it (raise the channel's effect column count) when microtonal input is switched on.

### Raw notes

`DIV_NOTE_RAW` writes an exact chip frequency (`gui.cpp:1690-1705`, `doc/8-advanced/raw-notes.md`). It is exact, but the value is chip-specific and does not transpose. Keep it as a fallback, not the plan.

## Corrections to the proposed shape

1. **"No engine change" is wrong for live play.** Recording can be GUI-only. But live notes are placed on a channel inside `autoNoteOn`, which returns only true or false, so the GUI cannot send the detune afterwards. Minimum change: look up the key in `playback.cpp` where the MIDI channel is in scope, carry the detune in `DivNoteEvent`, and send `DIV_CMD_PITCH` next to `DIV_CMD_NOTE_ON` (`playback.cpp:2177`) for every live note, zero detune included, since pitch persists. Also set the channel's `pitch`, so vibrato doesn't overwrite it. Small, but it touches the engine and a busy upstream file. No format change.
2. **Two code paths need the same table**: recording (GUI) and live sound (engine). Put the table in one place both can reach.
3. **Note-off by note number breaks.** In 31-EDO, about 2.6 keys share each normal note (for example C and C+39 cents both round to C). Releasing one key stops both, because `autoNoteOff` releases every channel with that note number. Live play must track notes by the original key (MIDI channel plus note), not by the rounded note.
4. **"Works on every chip" is half true.** Every chip I checked accepts `DIV_CMD_PITCH` (for example `genesis.cpp:1208`, `nes.cpp:653`, `sms.cpp:407`). Not every chip can hold the detune (see the table above), and non-linear songs don't work at all.
5. **The `.ltn` file is only half the mapping.** It says which MIDI channel and note each key sends. It does not say what pitch that is: that lives in the receiving synth. See the next section.

## The file formats

### Lumatone `.ltn`

Read from the Lumatone Editor source (`hsstraub/TerpstraSysEx.2014`, BSD-3-Clause, last pushed 2026-06-09), its parser `Source/KeyboardDataStructure.cpp:280-370`, and three of its presets (`Presets/Mappings/`, 12, 31 and 53-EDO).

- Plain text, INI-like. Sections `[Board0]` to `[Board4]`, 56 keys each, 280 in all.
- Per key `N` (0-55):
  - `Key_N=` the MIDI note (0-127);
  - `Chan_N=` the MIDI channel, 1-16. Anything else, including 0, means the key is disabled (`:318-321`);
  - `Col_N=` the key's LED colour as hex (`ff46d367`);
  - `KTyp_N=` key type, written only when the key is not a plain note key (`:442`). Skip keys that have it (CC faders and so on);
  - `CCInvert_N` a flag for fader keys.
- After the boards: global settings (aftertouch, velocity tables, fader and aftertouch curves). Ignore them.

**What a channel means varies by mapping.** In the presets:

- 53-EDO: every board uses notes 58-110 on its own channel 1-5. Each channel is one octave (53 steps).
- 31-EDO: boards 0-3 use channel 1 with notes 0-123, 31 apart per board. Board 4 repeats board 3's notes on channel 2, so channel 2 means "31 steps higher".
- 12-EDO: every board spans one octave of note numbers (24-35, 36-47, ...) spread over channels 1-6. The file doesn't say what the channel means here (probably octave; check). *Checked in the spike: the channel means nothing here; see "Spike results", step 1.*

So the import needs a rule, "steps per channel". Default to "one period per channel" (which fits the 31 and 53 presets), and let Michael change it. How his current synth reads channels is an open question.

### Scala `.scl`

From the Scala format page (huygens-fokker.org/scala/scl_format.html):

- Lines starting with `!` are comments.
- Line 1: a description. Line 2: the number of notes.
- Then one pitch per line: a value with a `.` is cents, otherwise a ratio (`3/2`; a bare `2` means `2/1`). The `1/1` start note is implicit. The last value is the period, usually `2/1`.

Scala also has `.kbm` files: which key is scale degree 0 and what reference frequency to use. Lumatone users often have one. Without it, default to MIDI note 60 as degree 0 at Furnace's C-4, using the song's A-4 tuning.

An EDO size alone is the simple case: step `k` is `k × 1200 / N` cents.

### The mapping math

degree = f(channel, note) → cents above the reference → nearest 12-tone note and remainder → `E5xx` = `0x80 + round(remainder × 1.28)`.

When the remainder is exactly ±50 cents (24-EDO quarter tones), always round to the note below and write `+50` (`E5C0`), so spellings stay consistent.

## Alternatives, and why 19 goes first

- **Pitch bend from the keyboard.** As far as I found, the Lumatone sends plain notes on channels; tuning lives in the synth. Furnace ignores pitch bend for playing anyway (see above).
- **MPE.** Same problem: needs per-note bend handling Furnace doesn't have. I did not confirm whether the Lumatone has an MPE mode.
- **MTS-ESP.** A separate program broadcasts the tuning and Furnace asks it for each note's frequency. Clean for live play, but it needs a per-note frequency path in the engine and a third-party client library (license to check). That is idea 21's work.
- **Per-song tuning tables (idea 21).** Exact, and no effect column needed, but it changes the engine and the `.fur` format, and upstream Furnace wouldn't play those songs right.

19 goes first because it changes no format, works with upstream Furnace, and tells us cheaply whether `E5xx` detune sounds good enough on Michael's chips before paying for 21.

## Where the code lives

- **C++ GUI and engine**, for live play and recording. Live play can't be done outside the app.
- **furnace-mcp (Python)**, for offline work and for the spike: parse `.ltn`, `.scl` and EDO into a key table; turn a MIDI file Michael recorded elsewhere into rows with `E5xx`, written with `write_rows`; render test scales and measure them. The existing MIDI file import (`src/engine/fileOps/midi.cpp`) skips `E5xx` on purpose (`doc/2-interface/formats.md:72`); a tuning option there is a later choice.

## Trade-offs and risks

- **One effect column per channel** goes to tuning. Songs get a little wider.
- **Coarse chips** will merge close microtonal steps in high octaves. Some chips Michael likes may not suit fine EDOs.
- **Engine change in a busy upstream file** (`playback.cpp`). Keep it small and fork-marked.
- **Vibrato and pitch slides.** `E5xx` adds to vibrato (`playback.cpp:1461`). Slides that end on a note may land on the 12-tone pitch plus the old detune. Check in the spike.
- **Channel convention guesswork.** If the "steps per channel" rule is wrong, every note is wrong. It must be visible and easy to change.
- **Latency and polyphony.** Live play uses Furnace's channel picking (`engine.cpp:3767-3794`). Chords bigger than the song's channel count steal notes, as today.

## Open questions

1. Which synth or software does Michael use with the Lumatone now, and how does it read MIDI channels (one octave per channel, 128 notes per channel, something else)? Does he use `.scl` and `.kbm` files?
2. Which tunings does he actually play? 31-EDO? 53? Non-EDO scales?
3. Which chips does he compose for? This decides whether coarse registers matter.
4. Record only, live only, or both? Live is the part that needs the engine change.
5. Is giving up one effect column per channel acceptable?
6. Does `E5xx` detune sound right to him, especially on his chips' high notes?
7. Should key colours from the `.ltn` show up anywhere (idea 007 channel colours)? Nice-to-have only.

## Spike plan

Steps 1-4 need nothing from Michael. Steps 5-7 need Michael and the keyboard, after idea 18 has passed.

1. **Parse the formats in furnace-mcp** (no Michael). Read `.ltn`, `.scl` and an EDO size into a key table: (channel, note) → note plus `E5xx`. Test it on the Lumatone Editor's preset mappings (BSD-3). *You'll know when* the 31 and 53-EDO presets, read with "one period per channel", give each key the same pitch as its neighbour pattern predicts (board to board, one octave apart), and you know which channel rule the 12-EDO preset needs.
2. **Render test scales** (no Michael). Write a 31-EDO and a 53-EDO scale over three octaves with `E5xx` on an FM chip, NES and SN76489. Measure each note with the pitch code from the octave work (the YIN detector at `furnace_mcp/analysis.py:155`, probes at `song.py:532`). *You'll know when* you have a cents-error table per chip and octave.
3. **Check the side effects** (no Michael). Same song with vibrato, a pitch slide and a non-linear-pitch copy. *You'll know when* you can say which effects mix safely with `E5xx`.
4. **Prototype live detune on a branch** (no Michael). Add the detune to `DivNoteEvent`, send `DIV_CMD_PITCH` with the note, and release by original key. Drive it from a virtual MIDI port sending channels and notes from a preset. *You'll know when* two keys that round to the same note play and release independently, at the right pitches.
5. **Get Michael's setup** (Michael). His `.ltn`, his tuning files, and the answer to question 1. *You'll know when* the key table matches what his current synth plays, key for key, on a few test keys.
6. **Record a phrase** (Michael and the keyboard). Recording writes note plus `E5xx` on every note row in a dedicated effect column. *You'll know when* playback of the recorded pattern sounds like what he played.
7. **Play live** (Michael and the keyboard). Chords, fast runs, held notes. *You'll know when* Michael says it feels and sounds right, or names what is wrong.

## Spike results, steps 1-4 (2026-10-18)

Branch `idea-019-lumatone`: `aa0898e2b` (step 1), `f33c9ae9c` (steps 2-3), `710588ae9` (step 4). Not merged; nothing here is a finished feature.

### Step 1: reading the formats

`tools/furnace-mcp/furnace_mcp/tuning.py` reads `.ltn`, `.scl` and EDO sizes and maps each key to note plus `E5xx`. Tests: `tests/test_tuning.py`, with five Lumatone Editor presets as fixtures (12, 19, 24, 31, 53-EDO; BSD-3 licence alongside).

The check: each key gets a position on the hex grid (from the Lumatone Editor's `BoardGeometry.cpp`). If the channel rule is right, the pitch rises by the same number of steps for every move to the right, and the same for every move up, across all five boards. A wrong rule breaks that at the board edges.

| Preset | Keys | Channel rule that fits | Step right, step up |
|---|---|---|---|
| 12-EDO | 280 | **0: the channel means nothing**, plain MIDI notes | 2, 1 |
| 19-EDO | 280 | one channel, any rule | 3, 1 |
| 24-EDO | 262 | one channel, any rule | 4, 1 |
| 31-EDO | 278 | 31: one period per channel | 5, 2 |
| 53-EDO | 280 | 53: one period per channel | 9, 5 |

- Each multi-channel preset has exactly one rule that fits, out of 0-128, so the importer can **guess the rule** and only ask when it can't tell. `key_table` now does that.
- This answers the brief's question about the 12-EDO preset: the channel there is not an octave. The notes already run 0-127 over the keyboard.
- Some keys send the same channel and note as another key (15 in the 53-EDO preset), so a table has fewer entries than keys.
- **Not checked yet:** which key is C-4. The fit only proves the spacing. The reference key (default: channel 1, note 60 = C-4) is step 5, with Michael.
- `.kbm` files aren't read yet.

### Step 2: how well chips hold the detune

`examples/spike_019_scales.py` plays every 31 and 53-EDO step from written C-2 to C-6 and measures it. Numbers are cents after taking out the test note's overall offset, a few cents either way. The YM2612 read -2.6 here and -4.7 to -5.9 in steps 3 and 4, so the offset depends on the measuring window and may come from the default instrument rather than the chip. The errors relative to it don't change. "Best" is what the chip's own registers allow: the worst error if every step got the nearest period.

**31-EDO** (step 38.7 cents), worst error per written octave:

| Written octave | YM2612 FM | SN76489 | SN best | NES pulse | NES best |
|---|---|---|---|---|---|
| C-2 | 2.6 | 7.6 | 3.4 | 3.3 | 1.6 |
| C-3 | 1.7 | 9.8 | 6.7 | 5.2 | 3.4 |
| C-4 | 1.6 | 32.2 | 13.8 | 12.2 | 6.7 |
| C-5 | 1.8 | 82.0 (6 steps merge) | 25.5 | 34.6 | 14.5 |

**53-EDO** (step 22.6 cents): FM worst 2.8, nothing merges. SN worst 28.6 at C-4 (5 of 52 steps merge) and 89.1 at C-5 (26 of 53 merge). NES worst 14.9 at C-4 and 30.1 at C-5 (5 merge).

- **FM is fine everywhere**: within 3 cents in every octave, mean about 0.6.
- **SN76489 and NES are fine in the low octaves.** From written C-4 on the SN, and C-5 on the NES, close steps blur or merge.
- **Furnace makes period chips two to three times worse than they need to be.** Most detuned notes land on the nearest period, but some land one period off: degree 84 of 31-EDO on the SN plays period 65 off by 36 cents, where 9.5 was possible. The likely cause is the shared pitch table (`pitchTable.cpp`), which interpolates in a straight line inside each semitone and rounds the root and the slope separately. Computing the period directly might bring the SN and NES columns down to "best". The fix is untried. It would be a separate fork fix that also helps idea 021, and the script would measure it.

### Step 3: effects with a detune

`examples/spike_019_effects.py`, on the YM2612:

| Case | Wanted | Measured |
|---|---|---|
| A later note without `E5xx` | keeps the detune (+250) | +252.2 |
| Vibrato `0448` | centres on the detune (+25) | +22.7 (mean of short windows) |
| Tone portamento `0308`, `E5xx` on the target row | target plus its detune (+425) | +427.0 |
| Same, no `E5xx` on the target row | target plus the old detune (+450) | +452.1 |
| Note slide `E124` | lands with the detune (+425) | +427.0 |
| Arpeggio `0047` | not measured; the code adds `arp<<7` to base plus pitch, so the detune carries | — |

- **Vibrato, portamento and note slides all mix safely.** The one trap is the one the brief predicted: the detune stays set, so every note row needs its own `E5xx`, `E580` included.
- **Non-linear pitch breaks it.** With the compatibility flag "None", `E5C0` (+50 cents) plays about **+164 cents** on the YM2612, at every octave. The feature must require linear pitch, or refuse.

### Step 4: live detune in the engine

The prototype, about 100 lines, all marked "fork prototype (ideas/019)":

- `DivNoteEvent` carries a `pitch` (detune). When a live note starts, the engine sets the channel's pitch and sends `DIV_CMD_PITCH` the way `E5xx` does, vibrato term included.
- `DivChannelState` remembers the key (`midiKey`) that started its note. `autoNoteOff` releases by key when there is one.
- MIDI note input goes through a new `DivEngine::midiNoteIn()`, which looks the key up in the table (`setMicroKeys`). Without a table, nothing changes.
- **`-livetest <file>`** (CLI) feeds a key table and note events, timed by engine tick, into `-output`, so this can be tested without a keyboard or a virtual MIDI port. Export normally throws away live notes; with `-livetest` it keeps them.

`examples/spike_019_live.py` plays three keys of the 31-EDO preset into a blank YM2612 song and renders each channel separately:

| Key | Maps to | Channel 1 | Channel 2 |
|---|---|---|---|
| A: ch1 note 60, held 0.2-2.5 s | C-4 `E580` | C-4 the whole time, through B's release; off after 2.5 s | — |
| B: ch1 note 61, held 0.5-1.5 s | C-4 `E5B2` (+39.1) | — | +40.3 cents; off after 1.5 s |
| D: ch3 note 60, held 1.55-1.65 s | not in the table: plain C-4 | — | C-4 +1.7 cents: no leftover detune from B |
| C: ch2 note 91, held 1.7-2.3 s | C-6 `E580` | — | C-6 +1.6 cents: no leftover detune |

While a table is on, keys missing from it play their plain note with the detune cleared, and every key releases by key. A and B round to the same note. Released by note, as before the prototype, letting go of B would have stopped A as well. Released by key, A keeps playing. All 178 furnace-mcp tests pass on the prototype build.

**Live keys over a playing song**: a live key's detune would otherwise stay on the channel. The channel now keeps the song's own pitch, and the next pattern note puts it back unless that row sets a new one. Tested: song C-4 at +12.5, key B at +39 on the same channel, then the song's next C-4 plays +12.5 again, +50 when it has `E5C0`, and +39 when it asks for B's own detune with `E5B2`.

**Not done in step 4:** recording (the GUI side, step 6). Nothing has been tried with a real keyboard.

### Where this leaves the decision

- Nothing so far says drop it. Live play works with the small engine change. FM chips hold every EDO step easily. Period chips are fine in their low and middle octaves.
- **The open risk is Michael's chips.** If he writes high melodies on the SN76489 or NES in 53-EDO, steps will merge. The pitch-table fix would roughly halve that error, but it can't beat the chip's own registers.
- **Next, with Michael** (after 018): his `.ltn`, his tuning files, the synth he uses now (step 5), then recording and live play (steps 6-7).

## Decision criteria

- **Build it**: the cents-error table is good enough on Michael's chips, live play works with the small engine change, and Michael wants to use it. Productize as a settings panel (tuning, `.ltn`, steps per channel) plus the furnace-mcp converter (M).
- **Reshape it**: recording is fine but live detune is not worth the engine change. Ship the offline converter only (record elsewhere, convert with furnace-mcp) (S).
- **Drop it, or go to 21**: `E5xx` sounds wrong (coarse chips, effect clashes), or Michael needs exact non-12 tunings everywhere. Then idea 21 (per-song tuning tables or MTS-ESP) is the real path.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\019-lumatone-layout-microtonal-input.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: map Lumatone keys (MIDI channel + note) through an EDO or Scala tuning to a nearest note plus an E5xx detune, measure how well chips hold the detune, and prototype live detune and recording. Do not build beyond the spike; prototype work happens on a branch. Steps 1-4 need no one; ask Josh to set up a session with Michael and his Lumatone (after idea 18 passes) before steps 5-7.
```
