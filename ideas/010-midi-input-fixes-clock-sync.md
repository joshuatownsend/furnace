# 010 — MIDI input fixes

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/gui/gui.cpp src/gui/midiMap.cpp src/gui/settings/allSettings.cpp src/gui/editControls.cpp src/engine/playback.cpp src/engine/engine.cpp src/audio/rtmidi.cpp`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 5/10 (from the portfolio card; /ideate has not re-scored this)
- **Lenses**: outside-in (upstream #2480) plus inside-out (bugs found while writing brief 018)
- **Effort (coarse)**: S (five small, separate patches)
- **Planned at**: f491976c9 on 2026-10-18

## How 010 and 017 split

The portfolio card for 010 covered both MIDI input fixes and MIDI clock sync, and card 17 also covered clock. I split them by where the code lives:

- **010 (this brief)**: playing and recording notes from a MIDI keyboard. Bugs, plus the two asks from upstream #2480 that are still missing. All of it is GUI code or small engine changes. No timing work.
- **017**: transport and sync. Clock in, start/stop/continue, song position pointer, following tempo, and queueing the next pattern live. That brief owns upstream #918.

They don't merge well. 010 is five small patches that can ship one at a time. 017 has one real design question (how to follow an outside tempo). The only shared code is the MIDI input loop in `playback.cpp:2961-3039`; 017 adds cases there, 010 edits the note cases. Do 010 first; it is cheaper and Michael's Lumatone test (018) may add items to it.

## The idea

Make a MIDI keyboard feel right in Furnace. Fix the input bugs found so far, and add the two #2480 asks that are still missing: writing a note-off when you let go of a key while recording, and a count-in before recording.

## Who wants this and why now

- **Upstream #2480**, "MIDI Input Quality of Life" (discussion, 2025-04-25, 7 upvotes). A DAW user of 20 years asks for three things:
  1. "Enable recording for multi-channel note previews, allowing the input of chords."
  2. "Count down before recording."
  3. "Automatically send `OFF` events when inputs are released."
  One reply (Soulchip) asks that the auto-OFF be a setting you can turn off, "because it could get annoying in some situations".
- **Ask 1 is done.** Upstream added **Chord** input mode on 2025-10-31 (`08a27be76` "GUI: chord input", `173f59dc7`). It is in the fork: the Mono / Poly / Chord button (`editControls.cpp:172-184`) and `gui.cpp:1659-1669`. Asks 2 and 3 are still missing (see below).
- **Michael and the Lumatone (ideas 18-21).** Brief 018 found the bugs below while reading the input code. Whatever his test turns up joins this list.
- The fork is in sync with upstream as of 2026-10-13 (the latest upstream commit in `git log`), so "missing" here means missing upstream too.

## What Furnace does today

### The input path

1. RtMidi reads the port. `gather()` copies each message into a queue, with its timestamp (`rtmidi.cpp:46-74`). It runs once per audio buffer (`sdlAudio.cpp:52`).
2. The engine drains the queue on the audio thread (`playback.cpp:2961-3039`). For each message it first calls the GUI's callback (`gui.cpp:9297-9343`), which copies the message to the GUI's own queue and returns an instrument, or -3 to cancel.
3. The engine then plays the note (`autoNoteOn`, `engine.cpp:3729-3795`) or, in direct mode, sends it to the matching channel.
4. On its next frame, the GUI thread reads its copy (`gui.cpp:5235-5392`) and, if **Edit** is on, writes the note into the pattern with `noteInput` (`gui.cpp:1653-1749`).

So sound and recording are decided in two places, on two threads, from the same message.

### Bugs and gaps

| # | What | Where | Size |
|---|---|---|---|
| A | **Per-column CC input uses the wrong setting.** The loop checks each column's own style (`valueInputSpecificStyle[i]`, `gui.cpp:5358`) but then switches on the global style (`valueInputStyle`, `:5372`). Global styles 1-3 are the key-based hex styles (`allSettings.cpp:29-37`); per-column 1-3 are dual CC, 14-bit CC and single CC (`allSettings.cpp:39-44`). So a per-column knob only works if the global style happens to be a key style, and then with whatever formula that number picks. Fix: switch on `valueInputSpecificStyle[i]`. | `gui.cpp:5372` | one line |
| A2 | Same panel: the per-column MSB/LSB labels test `==4` (`allSettings.cpp:1249`, `:1254`), but per-column dual CC is `1`. The "upper/lower nibble" labels never show. Cosmetic. | `allSettings.cpp:1249`, `:1254` | one line each |
| B | **Note-on with velocity 0 is not a release for recording.** Many keyboards send key-up as note-on with velocity 0. The engine treats it as note-off (`playback.cpp:3001-3010`). The GUI does not: it only resets the chord counter on a real note-off (`gui.cpp:5283-5284`) and ignores velocity-0 note-ons (`:5286-5288`). On such a keyboard, Chord mode never resets, so each new chord spreads further right. Fix: treat note-on velocity 0 as note-off in the GUI handler. | `gui.cpp:5283-5296` | small |
| C | **A key release stops every channel on that note.** `autoNoteOff` ignores the MIDI channel (`:3801` is commented out) and releases every channel whose `midiNote` matches (`engine.cpp:3797-3808`). With two keys on the same pitch (Lumatone Classic Mode, or a split keyboard), letting go of one cuts the other. Fix: store the MIDI channel with `midiNote` and match both. | `engine.cpp:3797-3808`, `:3770`, `:3791` | small, engine |
| D | **Direct mode drops channels past the last one, silently.** MIDI channel 9 on a 6-channel song does nothing (`playback.cpp:2986`, `:3005`, `:3014`). Options: wrap around, fall back to auto mode, or show a warning. A product choice. | `playback.cpp:2986-3016` | small |
| E | **No note-off on release when recording** (#2480 ask 3). The GUI note-off case only resets the chord counter (`gui.cpp:5283-5284`). `noteInput` can already write OFF (`key==GUI_NOTE_OFF`, `gui.cpp:1692-1694`); nothing calls it from MIDI. | `gui.cpp:5283` | S |
| F | **No count-in** (#2480 ask 2). I found no count-in, pre-roll or countdown code in `src/gui` or `src/engine`. A metronome exists (`editControls.cpp:410-414`, `doAction.cpp:172-173`) to build on. | new | S |
| G | **Recording ignores the MIDI channel.** Every note goes to the cursor's channel (`gui.cpp:1654`), or the next free ones in Chord mode (`:1660-1661`). The engine picks its own channel for sound (`engine.cpp:3767-3794`). The two choices are made separately (`getViableChannel`, `engine.cpp:3662`, is "a copy of the routine in autoNoteOn", its own comment says), so the channel you hear can differ from the one recorded. Not a bug fix; note it for E. | `gui.cpp:1654-1669` | (design note) |

### What E needs to work

To write OFF on the right cell, the GUI must remember where each held key was written: (MIDI channel, note) → (pattern channel, order, row). On release:

- If the song is **stopped**, the cursor has moved on by Edit Step, so the OFF would go on the next empty row of that channel. That is the "annoying" case Soulchip meant: step-entry users don't want an OFF after every note. Default: off when stopped.
- If the song is **playing** with follow on, write OFF at the current play row on that channel, rounded the same way notes are (`gui.cpp:1671-1682`). If the release lands on the same row as the note, skip it, or the note vanishes.
- **Chord mode**: each note of the chord gets its own OFF on its own channel.

It needs one setting, "Write note off on key release", with "only while playing" as the likely default.

### What F needs to work

A count-in plays the metronome for N beats (or one bar, from the highlight settings) before playback reaches the cursor, with Edit on. Two shapes:

- **Start early.** Start playback N beats before the cursor row and let the metronome run. Simple, but it plays the song before the cursor too, which a count-in usually avoids.
- **Clicks only.** Play N metronome clicks with the song silent, then start at the cursor. Cleaner, but needs a "metronome without song" mode.

Spike both on a branch and pick by feel.

## Testing without hardware

Almost all of this can be tested with no keyboard:

- **loopMIDI** (Tobias Erichsen, free) makes a virtual MIDI port on Windows. RtMidi's Windows backend sees it like a real device.
- A **Python sender** in the furnace-mcp venv (`mido` plus `python-rtmidi`, not installed yet) plays scripted messages into that port: chords, velocity-0 releases, two keys on the same note from different channels, CCs for a per-column knob.
- The **debug window's MIDI debug** (`debugWindow.cpp:1002`) logs every message the engine sees (`playback.cpp:2964-2970`).
- A second option is a test harness that pushes `TAMidiMessage`s straight into the input queue. That tests the engine path but not the GUI's, so prefer loopMIDI.

What needs a real keyboard: how velocity feels, latency, and the Lumatone's own behaviour (idea 18).

## Trade-offs and risks

- **`gui.cpp` and `playback.cpp` are busy upstream.** Keep each fix its own commit and mark fork code, so syncs stay cheap. A, A2 and B are plain bug fixes worth offering upstream.
- **C changes live-play behaviour** for anyone who relies on "release any copy of a note to stop it". Unlikely, but it is a change.
- **E needs a key → cell map in the GUI** that survives cursor moves, pattern changes and stop. Edge cases: releasing after Stop, releasing after the cell was overwritten, undo. Keep the map small and clear it on stop.
- **E and G interact.** If recording and sound pick different channels, the OFF goes where the note was written, not where it sounded. That is the right choice for the pattern, but the preview may differ until G is fixed.
- **Thread split.** The engine plays the note and the GUI records it, from separate copies of the message. Any fix that needs both (C plus E) must keep the two in step.

## Open questions

1. Should auto-OFF (E) be on by default, and only while playing? (Suggested: yes, only while playing.)
2. Direct mode past the last channel (D): wrap, fall back, or warn?
3. Count-in (F): start early, or clicks only? One bar or a set number of beats?
4. Should 010 also fix G (record on the channel that sounds)? It is bigger and touches both threads.
5. What else does Michael's Lumatone test (018) find? Its results may add rows to the table.
6. Offer A, A2, B and C upstream? They are plain bugs.

## Spike plan

1. **Set up a virtual port and a sender** (no hardware). Install loopMIDI, add `mido` and `python-rtmidi` to the furnace-mcp venv, and write a small script that sends a named scenario (chord, velocity-0 release, duplicate key, CC sweep). *You'll know when* Furnace lists the loopMIDI port and MIDI debug logs each scripted message.
2. **Reproduce A, B, C and D** before fixing anything. *You'll know when* each has a scenario that shows the bug: a per-column knob that does nothing, a chord that lands one channel further right each time, a held note cut by its twin, a silent channel 9.
3. **Fix A, A2 and B** on a branch. *You'll know when* the same scenarios now behave, and nothing else in the MIDI panel changed.
4. **Fix C** (release by MIDI channel plus note). *You'll know when* two keys on the same note from different channels hold and release independently, and a normal keyboard still releases correctly.
5. **Prototype E** (auto-OFF while playing). *You'll know when* a scripted phrase recorded during playback has an OFF at each release row, on the right channel, in Mono and Chord mode, and step entry with the song stopped writes no OFFs.
6. **Prototype F** both ways. *You'll know when* you can record from the first beat after a one-bar count-in, and you can say which shape feels better.
7. **Check with a real keyboard** (Josh, or Michael after 018). *You'll know when* someone has played and recorded a phrase with E and F on and says whether it feels right.

## Decision criteria

- **Build it**: A-D fix cleanly and E and F feel right in step 7. Ship A-D as bug fixes (offer upstream), then E and F as one feature with its settings (S overall).
- **Reshape it**: E's edge cases (cursor moves, undo) get messy. Ship A-D and F, and leave E for later.
- **Grow it**: 018 shows the Lumatone needs G (record on the sounding channel) or per-key tracking beyond C. Fold that in and re-estimate as M.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\010-midi-input-fixes-clock-sync.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Check the drift line first and re-verify any cited code that changed. Scope: MIDI note input bugs A-D (per-column CC switch, velocity-0 release, release by note only, direct-mode drop) and the two #2480 asks E (note-off on release while recording) and F (count-in). Clock, transport and live queueing are idea 017, not this one. Test with a loopMIDI virtual port and a scripted Python sender; no hardware needed until step 7. Prototype on a branch, one commit per fix. Ask Josh for decisions on open questions 1-3 before productizing.
```
