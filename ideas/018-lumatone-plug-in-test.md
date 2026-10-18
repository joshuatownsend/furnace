# 018 — Lumatone plug-in test with today's MIDI settings

> Brief for a hands-on test. No code. Michael (or Josh with Michael) runs it with the Lumatone and a copy of the fork, then fills in the results template at the bottom.
> Drift check: `git diff --stat 5e034e504..HEAD -- src/gui/settings/allSettings.cpp src/gui/gui.cpp src/gui/editControls.cpp src/engine/playback.cpp src/engine/engine.cpp src/gui/midiMap.cpp`.

- **Status**: NOT STARTED (waiting for a session with Michael and the Lumatone)
- **Verdict**: Advance
- **Score**: 8/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in, with a real user in the family
- **Effort (coarse)**: S (about an hour at the keyboard; no code)
- **Planned at**: 5e034e504 on 2026-10-18

## The idea

Plug Michael's Lumatone into Furnace as it is today and write down what works. No code changes. The answers decide how big ideas 19, 20 and 21 are:

- **19**: import a Lumatone layout, and enter microtonal notes as a note plus a per-row `E5xx` detune.
- **20**: make the Lumatone's key lights follow the song, sent over MIDI sysex.
- **21**: microtonal tuning tables in Furnace.

If plain 12-tone playing and recording already feel good, 19–21 are add-ons. If they don't, the first job is fixing basic input.

## Who wants this and why now

- **Michael**, Josh's son, composes in Furnace and posts to YouTube (youtube.com/@mysti_is_lost). He owns a Lumatone: a 280-key hexagonal MIDI keyboard. Each key sends its own MIDI channel and note number, set by a "mapping".
- Nobody has tried the Lumatone with Furnace yet. Ideas 19–21 all assume things about how Furnace treats it. This test checks those assumptions before anyone writes code.
- Michael isn't available right now, so this brief is a checklist he can run without Claude.

## What the Lumatone sends (checked against the factory files)

I downloaded Lumatone's current factory presets (`Lumatone-Factory-Presets-0325.zip` from lumatone.io/support/software) and read each mapping file. The keyboard is five sections ("boards") of 56 keys (manual, "Sections").

| Preset | Name | MIDI channels | Notes per board |
|---|---|---|---|
| 1 | Classic Mode | 1–6 inside every board, by key position | one octave each: 36–47, 48–59, 60–71, 72–83, 84–95 |
| 2 | Melodic Mode | channel 1 only | the same 37–92 on all five boards |
| 3 | Harmonic Mode | channel 1 only | overlapping ranges, 4–113 |
| 4 | Multi-Instrument | 1–6, a different range per channel | meant for six separate instruments |
| 5–9 | 19, 22, 24, 31, 53 EDO | mostly channel 1 (31 EDO's last board is channel 2) | microtonal; needs a retuned synth |
| 10 | 56 Polychromatic | 1–8 | microtonal |

What this means:

- **In Classic Mode the same pitch comes from several keys on different channels.** Middle C (MIDI note 60) is sent on channels 1, 2, 3 and 5 from four different keys of board 3. The channel says where the key sits, not which instrument it is.
- **Melodic Mode is the simplest test.** Everything is on channel 1, and pitch is only the note number.
- **Polyphonic aftertouch is on in every factory preset** (`AfterTouchActive=1`). Pressing harder sends extra messages.
- **Your unit may differ.** The manual says the factory presets change over time. Classic Mode keys are white and blue; Multi-Instrument uses six colours. If Lumatone Editor is installed, it can read the preset off the keyboard.
- **Changing presets:** press one of the ten preset buttons on top of the Lumatone. **Holding a preset button for five seconds overwrites that preset with the current mapping.** Tap, don't hold.

## What Furnace does with MIDI input today

All settings are in **settings → settings... → MIDI → MIDI input** (menu at `src/gui/gui.cpp:5870`, `:5904`; panel at `src/gui/settings/allSettings.cpp:1156–1453`). Settings take effect after **OK** or **Apply** (`src/gui/settings.cpp:176`, `:191`). Furnace saves one MIDI setup per device, in `midiIn_<device name>.cfg` in its config folder (`src/gui/settings.cpp:206`, `:259`).

The options on that panel:

- **MIDI input** device list, and **Re-scan MIDI devices** (`allSettings.cpp:1161–1185`).
- **Note input**: notes from the keyboard are written into the pattern (`:1193`).
- **Velocity input**: how hard you hit the key sets the volume column (`:1194`). The **Volume curve** slider shapes it (`:1266`). The value goes through each chip's own velocity mapping (`gui.cpp:1731–1733`).
- **Map MIDI channels to direct channels** (`:1198`), with **Program change pass-through** under it (`:1204`).
- **Program change is instrument selection** (`:1211`), and **Map Yamaha FM voice data to instruments** (`:1209`).
- **Value input style** (`:1215`): lets keys or knobs type hex values into effect columns. Seven choices (`allSettings.cpp:29–37`), from "Disabled/custom" to "Use single control change (imprecise)". A **Per-column control change** list (`:1236`) can tie a knob to one column, such as "Effect 1 value".
- **Actions**: MIDI learn. **+** adds a binding; the link button adds one and waits for the next key or knob (`:1279–1290`).

How it behaves:

- **Recording needs Edit on.** Notes are written only when the **Edit** checkbox in the edit controls is ticked (`gui.cpp:5288`, `editControls.cpp:753`). With Edit off, keys still make sound.
- **Every note is written to the channel the cursor is on.** The MIDI channel the key sends is ignored when recording (`gui.cpp:1654`, `:5286–5296`). After each note the cursor moves down by **Edit Step** rows when the song isn't playing (`gui.cpp:1745–1747`, `editControls.cpp:709`).
- **Chords depend on the Mono / Poly / Chord button** in the edit controls (`editControls.cpp:172–176`). There is no "polyphonic input" checkbox in MIDI settings; it is commented out (`allSettings.cpp:1197`).
  - **Mono** and **Poly**: each note overwrites the cursor row and steps down. A chord becomes a run of single notes down one channel.
  - **Chord**: the second, third... notes of a chord go into the next channels that can play the current instrument, on the same row (`gui.cpp:1660–1669`, `engine.cpp:3662`). The count resets on any key release (`gui.cpp:5283–5284`), so chords must be pressed together and released together.
- **Which channel sounds (not records)**:
  - **Direct off**: Furnace picks a free channel that can play the instrument, starting from the cursor's channel (`engine.cpp:3729–3795`). In Mono mode it reuses one channel. A key release stops **every** channel playing that note number, whatever MIDI channel it came from (`engine.cpp:3797–3808`).
  - **Direct on**: MIDI channel 1 plays song channel 1, MIDI channel 2 plays song channel 2, and so on. A key release stops that channel, whatever the note (`src/engine/playback.cpp:2984–3020`). MIDI channels past the song's last channel are dropped without a warning.
- **Pitch**: Furnace writes MIDI note `n` as note value `n + 48` (`gui.cpp:5290`). I haven't checked how that displays; the test records it.
- **Hex typing gotcha**: if **Value input style** is set to one of the three key-based styles and the cursor is on an instrument, volume or effect column, keys type hex digits instead of notes (`gui.cpp:5287`, `:5297–5316`). Keep the cursor on the note column, or leave the style on "Disabled/custom".
- **Aftertouch, pitch bend and other messages are ignored** unless bound with MIDI learn (`playback.cpp:2982–3031` only handles note on, note off and program change).
- **No detune or microtonal path.** A recorded note writes the note, instrument, volume and a latched effect, nothing else (`gui.cpp:1718–1737`). The only song-wide tuning is **Tuning (A-4)** in Song Info (`src/gui/songInfo.cpp:100`, `src/engine/song.h:312`). `E5xx` is "set pitch": `00` is one semitone down, `80` is normal, `FF` is nearly one semitone up (`doc/3-pattern/effects.md:30`).
- **MIDI output to the Lumatone exists but can't drive its lights.** **MIDI output** has "Off", "Melodic" and "Light Show (use for Launchpad)" (`allSettings.cpp:1456–1490`), but only Melodic does anything in the engine (`playback.cpp:405`). Furnace sends no sysex.

## Trade-offs and risks

- **Classic Mode may fight the "direct" setting.** Its channels 1–6 mark key position, so direct mode would spread one melody over song channels 1–6 depending on which key was hit. Expect direct mode to be wrong for Classic Mode and right only for a custom mapping (idea 19's job).
- **Duplicate keys.** Two keys with the same pitch release each other when direct mode is off. Players who reach for the nearer copy of a note may hit this.
- **One-channel recording.** Without Chord mode, Furnace records one note at a time into one channel. That's normal tracker behaviour, but may surprise a keyboard player.
- **Driver sharing on Windows.** Some Windows MIDI drivers let only one program open a device. If Lumatone Editor is open, Furnace may not see the keyboard. Close the Editor first.
- **Settings are per device.** If the Lumatone shows up under a different name (USB vs. 5-pin DIN interface), Furnace starts a fresh MIDI setup for it.

## Open questions

1. Does Furnace list the Lumatone, and does it play notes at the right pitch with no setup beyond choosing the device?
2. In Classic Mode, do the duplicate keys cause stuck or cut-off notes?
3. Is "Map MIDI channels to direct channels" useful with any factory preset, or only with a custom mapping?
4. Does Chord mode record Lumatone chords well enough, or does Michael want something else?
5. Does velocity feel right with the default **Volume curve**?
6. Does the flood of aftertouch messages slow Furnace down or cause glitches?
7. Does the Lumatone react at all to MIDI coming from Furnace (lights, notes)?
8. What does Michael want to do with the Lumatone in Furnace: play 12-tone parts faster, write microtonal music, or both? This sets the order of 19, 20 and 21.

## Test plan

Before you start: install the fork's Furnace build, open any song with at least six channels (an FM demo such as one from `demos/genesis/` works), and have a second song with only four channels ready (a Game Boy or NES demo). Close Lumatone Editor.

1. **Connect and pick the device.** Plug the Lumatone in by USB and turn it on. Tap preset button 1. In Furnace open **settings → settings... → MIDI → MIDI input**. Click **Re-scan MIDI devices**, choose the Lumatone in the **MIDI input** list, tick **Note input** and **Velocity input**, leave **Map MIDI channels to direct channels** off, set **Value input style** to "Disabled/custom", then click **OK**. *You'll know when* the Lumatone's name appears in the list. Write down the exact name.
2. **Play without recording.** Leave **Edit** off. Click an instrument and play single keys around the middle of the keyboard. *You'll know when* you hear notes. Write down whether the pitch moves the way the key colours suggest.
3. **Check the pitch.** Turn **Edit** on, put the cursor on a note column, and press the key Michael thinks of as middle C. *You'll know when* a note appears. Write down the note Furnace shows (for example `C-4`), and which board it came from.
4. **Record a melody.** With **Edit Step** at 1, play an eight-note tune. *You'll know when* eight notes sit on eight rows. Write down anything missing or doubled.
5. **Velocity.** Play one key softly, then hard, a few times. *You'll know when* the volume column changes. Write down the lowest and highest values, and whether it feels right. If not, move the **Volume curve** slider and try again.
6. **Chords.** Click the **Mono / Poly / Chord** button until it says **Chord**. Play a three-note chord, pressing and releasing all keys together. *You'll know when* three notes land on one row in three channels. Then try Poly and Mono and write down what each records.
7. **Duplicate keys (Classic Mode).** Find two keys with the same pitch on different rows (same colour, same note). Hold one, press and release the other. *You'll know when* you can say whether the first key kept sounding. Do this with direct mode off.
8. **Direct mode.** In MIDI settings tick **Map MIDI channels to direct channels**, click **OK**, and repeat steps 2, 6 and 7 on the six-channel song. Then open the four-channel song and play across one board. *You'll know when* you can say which song channels sounded and whether some keys went silent.
9. **Melodic Mode.** Turn direct mode off again. Tap preset button 2 and repeat steps 2, 4 and 6. *You'll know when* you can say which preset feels better in Furnace.
10. **Pressure.** In either preset, press keys hard and hold them while a song plays. *You'll know when* you can say whether Furnace stutters, lags or ignores it. Expected: no effect.
11. **A knob, if you want.** Set **Value input style** to "Use single control change (imprecise)", set **Control** to the CC number of the Lumatone's expression pedal or a fader (if set up), put the cursor on an effect value, and move it. *You'll know when* the value changes or clearly doesn't. Skip if there's no pedal. Set the style back to "Disabled/custom" afterwards.
12. **Lights (optional).** Under **MIDI output**, choose the Lumatone and pick **Melodic**, click **OK**, and play a song. *You'll know when* you can say whether any keys light up or play notes. Expected result unknown. Set MIDI output back to `<disabled>` afterwards.
13. **Ask Michael question 8.** *You'll know when* you have his answer in his own words.

## Results template

Copy this into a reply or a note and fill it in.

```text
Date / who ran it:
Furnace build (help > about..., or the commit):
Lumatone preset 1 name and key colours (Classic Mode = white/blue?):
Connection: USB / 5-pin DIN    Device name in Furnace:

1  Device listed?                         yes / no
2  Notes sound at the expected pitch?     yes / no   notes:
3  "Middle C" key writes:                 ____  (from board __)
4  8-note melody recorded cleanly?        yes / no   missing/doubled:
5  Velocity range written:                __ to __   feels right? yes / no
   Volume curve value used:
6  Chord mode, 3-note chord:              one row, three channels? yes / no
   Poly mode records:                     Mono mode records:
7  Duplicate key, direct OFF:             other key kept sounding? yes / no
8  Duplicate key, direct ON:              other key kept sounding? yes / no
   Direct ON, 6-channel song: which song channels sounded?
   Direct ON, 4-channel song: any keys silent?  yes / no   which rows:
9  Melodic Mode vs Classic Mode:          which is better and why:
10 Hard pressing / aftertouch:            no effect / stutter / lag
11 Knob or pedal to effect value:         works / doesn't / skipped
12 Lights or notes from Furnace output:   lights / notes / nothing / skipped
13 Michael wants: 12-tone speed / microtonal / both    in his words:

Anything else that felt wrong or slow:
```

## Decision criteria

Read the results like this:

- **Idea 19 (layout import + `E5xx` microtonal input)**
  - If steps 2–6 work and Michael wants microtonal (step 13): advance. Two building blocks are missing today: a way to turn (channel, note) into a Furnace note plus an `E5xx` value, and writing that `E5xx` on the row (recording writes no detune now).
  - If step 7 shows duplicate keys cutting each other off, the import must also solve note release per key, not just pitch.
  - If direct mode (step 8) is useless with every factory preset, idea 19 should bring its own channel meaning rather than reuse "direct channels".
- **Idea 20 (key lights follow the song)**
  - If step 12 shows nothing, it needs new sysex output code; Furnace sends none today and Light Show mode is empty. Size it M or larger.
  - If Michael doesn't care about lights (step 13), park it.
- **Idea 21 (tuning tables)**
  - Only advance if Michael wants microtonal music. Today the only tuning control is one A-4 reference per song.
  - If he only wants faster 12-tone entry, drop 21 and keep 19 to layout import only.
- **If steps 1–4 fail**, stop. Fixing basic Lumatone input comes before 19–21.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\018-lumatone-plug-in-test.md in full before doing anything. Michael (or Josh) has run its test plan with the Lumatone and pasted the filled-in results template. Check the brief's drift line first, and re-verify any cited code that changed. Then read the results against the decision criteria and write a short recommendation for ideas 19, 20 and 21: advance, reshape or park each, with a revised effort guess. Do not write code. If a result contradicts the "What Furnace does with MIDI input today" section, find out why in the code and say so.
```
