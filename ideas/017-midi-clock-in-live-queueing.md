# 017 — MIDI clock in and live pattern queueing

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/audio/rtmidi.cpp src/audio/taAudio.h src/audio/sdlAudio.cpp src/engine/playback.cpp src/engine/engine.cpp src/engine/engine.h src/gui/gui.cpp src/gui/midiMap.cpp src/gui/settings/allSettings.cpp src/gui/orders.cpp`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 4/10 (from the portfolio card; /ideate has not re-scored this)
- **Lenses**: outside-in (upstream #918, LSDj and OpenMPT)
- **Effort (coarse)**: M for clock in with tempo follow; S for live queueing on its own
- **Planned at**: f491976c9 on 2026-10-18

## How 010 and 017 split

Card 10 was "MIDI input fixes and clock sync", and card 17 was "MIDI clock in and live queueing". Both claimed clock. I split them by where the code lives:

- **010**: playing and recording notes from a keyboard (bugs, auto note-off, count-in). GUI code and small engine fixes. No timing.
- **017 (this brief)**: transport and sync. Clock in, start/stop/continue, song position pointer, following an outside tempo, and queueing the next pattern while playing. Owns upstream #918.

Keep them separate. 017 has one real design question (how to follow an outside tempo); 010 is small patches. The shared code is the engine's MIDI input loop (`playback.cpp:2961-3039`): 017 adds cases for system messages there, 010 edits the note cases. Do 010 first. Live queueing does not need clock at all and can ship on its own.

## The idea

Two features that make Furnace usable next to other gear:

1. **Clock in.** Let another device or program (a DAW, a drum machine, LSDj through a MIDI adapter) drive Furnace: start, stop, continue, jump to a song position, and follow its tempo.
2. **Live pattern queueing.** While the song plays, pick the next order to play. Furnace finishes the current pattern and then jumps there, so you can perform a song live, the way OpenMPT and Renoise users do.

## Who wants this and why now

- **Upstream #918**, "Sync to MIDI clock" (discussion, 2023-01-02, 5 upvotes, no replies). The author feeds MIDI into Furnace from a DAW. Matching BPM "sort of works", but two programs' idea of 120 BPM differ, "and drifts over time". They add: "MIDI Start/Stop works already", but they want it as "an official tickbox in the MIDI tab instead of having Furnace 'learn' it." The same text was filed as issue #820 and closed in 2023.
- **Upstream #2715**, "MIDI timing improvements" (issue, closed 2025-10-22). Asks for clock in again and reports that clock out drifts. tildearrow: "Drift issue is real though. MIDI events are not delayed properly (yet)."
- **Other trackers.** LSDj can follow or lead other gear over the Game Boy link cable (with an Arduinoboy-type adapter for MIDI). OpenMPT can start and stop from MIDI and queue patterns live.
- I found no upstream thread asking for live pattern queueing by name; that half is from other trackers, not Furnace users. Josh and Michael have not asked for either half yet.

## What Furnace does today

### Clock out exists

- **Clock** (`0xF8`): `runMidiClock` sends 24 per beat (`playback.cpp:2740-2778`), when **Send MIDI clock** is on (`allSettings.cpp:1498-1500`). Tempo comes from the highlight, speeds, tick rate and virtual tempo (`playback.cpp:2753-2765`). It does not run in live-only ("freelance") play (`:2742`).
- **Start** (`0xFA`) on play (`engine.cpp:2060`), **stop** (`0xFC`) on stop (`engine.cpp:2145`, `:2199`). **Continue** (`0xFB`) is never sent.
- **Song position pointer** (`0xF2`) on play, when clock out is on (`engine.cpp:1995`). Likely bug: it sends `(curMidiClock>>7)` first and `curMidiClock&0x7f` second. The MIDI spec puts the low 7 bits first, and counts in 16th notes (6 clocks), while `curMidiClock` counts clocks (`playback.cpp:2747`). So a receiver may get the wrong position when play starts mid-song. Check it with a MIDI monitor in spike step 1.
- **Timecode** (MTC) also exists (`playback.cpp:2781-2893`).

So Furnace can already lead. LSDj or a drum machine set to follow external clock should already work (untested).

### Clock in is blocked one layer down

- **RtMidi drops clock before Furnace sees it.** `init()` calls `port->ignoreTypes(false,true,true)` (`rtmidi.cpp:143`). The second flag tells RtMidi to drop timing messages: `0xF8` clock and `0xF1` MTC (`extern/rtmidi/RtMidi.cpp:957`, `:947-949`). So "nothing receives it" is true, and the first fix is one flag.
- **Start, stop and continue do get through.** RtMidi only filters clock, MTC and active sensing. That is why #918 says start/stop "works already": the user bound them with MIDI learn. Learn stores type `0xF`, "channel" `0xA` for start (`gui.cpp:5261-5263`), and `MIDIMap::at` maps type `0xF` to row 7 of an 8-row table (`midiMap.cpp:7`, `:259`), so a bind to the **Play** or **Stop** action works.
- **The engine ignores system messages.** Its input switch is on `msg.type&0xf0` (`playback.cpp:2982`). Every system message masks to `0xF0` and matches no case. Only note on, note off and program change are handled.
- **Timestamps are thrown away.** `gather()` stores RtMidi's delta time in `m.time` (`rtmidi.cpp:56`), and nothing reads it. `gather()` runs once per audio buffer (`sdlAudio.cpp:52`; also `pa.cpp:51`, `asio.cpp:84`, `jack.cpp:70`, `pipe.cpp:37`). So clocks arrive in bursts, one burst per buffer (about 10 ms at common settings), and their arrival order says nothing about their spacing. This is the "not delayed properly" that tildearrow mentioned.

### Live queueing does not exist

I checked; the card said "unverified". What exists:

- **Clicking an order while playing jumps now.** `setOrder` restarts playback at that order (`engine.cpp:3826-3840`, via `playSub`). No waiting for the pattern to end.
- **`changeOrd`** is the engine's pending jump (`engine.h:776-785`). `Bxx` and `Dxx` set it (`playback.cpp:683-716`), and it is applied after the current **row** (`playback.cpp:1902-1925`), not after the pattern.
- **Repeat pattern** holds the current pattern (`engine.h:692`, `playback.cpp:37`, `:1904-1906`).

So a queue is: store a "next order" in the engine, and when the row counter reaches the end of the pattern (`playback.cpp:1928-1935`, where it calls `nextOrder()`), go there instead. It also needs a GUI way to set it (for example Shift+click in the orders list) and a mark showing what is queued. A MIDI learn action ("queue order N", or "queue next/previous") would let a pad controller trigger it. Small.

## The design question: how to follow outside tempo

Furnace's timing is ticks, not beats. The engine runs ticks at the tick rate (`divider`, Hz, `playback.cpp:1335-1341`) and moves one row every *speed* ticks. A beat is *highlight A* rows. Clock is 24 per beat. So one clock is `highlight × speed / 24` ticks, which is usually not a whole number (4 rows × speed 6 = 1 tick per clock; speed 3 = 0.5). Two ways:

- **A. Measure and retune.** Measure the time between clocks from their timestamps, smooth it, and set the tick rate so Furnace's tempo matches (the inverse of `playback.cpp:2763`). Speeds and grooves stay as written. Correct the phase gently at each beat so drift can't build up. Cheaper, and works with any speed. The risk is wobble if the smoothing is wrong.
- **B. Drive ticks from clocks.** Each clock advances the engine by a fixed number of ticks. Locked hard to the master, with no drift. But it needs a whole number of ticks per clock, so it only fits some speed and highlight settings, and grooves break it.

Recommend A for the spike, with B as the fallback if A can't hold phase. Either way:

- Tempo changes in the song (`Fxx`, `Cxx`, virtual tempo) fight the master. While following, the master's tempo should win; the song's tempo effects could scale relative to it, or be ignored. A product choice.
- **Start** = play from the top. **Continue** = play from where it stopped. **Song position pointer** = jump to a 16th-note position, which maps to (order, row) by walking the order list with the same speed and highlight math. Songs with `Bxx` jumps or speed changes make that walk harder.
- Chip-synced songs (tick rate fixed at 50 or 60 Hz) are written for an exact tick rate. Retuning it changes how arpeggios and macros sound slightly. Expected and acceptable, but it should be noted in the setting.

## Testing without hardware

- **loopMIDI** (free) makes a virtual MIDI port on Windows; RtMidi's Windows backend sees it like a real device.
- **A clock source**: a second copy of Furnace with **Send MIDI clock** on, sending to the loopMIDI port, already sends start, stop, clock and song position. A short Python script with `mido` and `python-rtmidi` (not in the furnace-mcp venv yet) can send exact clock at any BPM, with jitter or tempo ramps on purpose. Any DAW with clock out also works.
- **Seeing it arrive**: the debug window's MIDI debug (`debugWindow.cpp:1002`) logs each message the engine sees (`playback.cpp:2964-2970`). Once clock is let through it logs every clock, so turn it off for timing tests.
- **Measuring sync**: record Furnace's audio while the script sends clock plus a click, or have Furnace send clock out to a second port and compare its clock times to the master's. No gear needed.
- **Live queueing** needs no MIDI at all, just the GUI.

What needs gear: LSDj as master (a Game Boy, the cart and an Arduinoboy-type MIDI adapter), a hardware drum machine, and how it feels on stage.

## Trade-offs and risks

- **Opening the clock gate floods the GUI.** Every input message also goes to the GUI callback, which queues it and wakes the GUI thread (`gui.cpp:9297-9309`). At 120 BPM that is 48 extra wake-ups a second, each run through `midiMap.at`. Handle clock in the engine and have the callback skip system real-time messages (return -3 early) unless MIDI learn is listening.
- **Audio thread work.** Clock handling runs inside the audio callback, so it must be cheap and must not lock.
- **Buffer size sets the floor for jitter.** Without timestamps, timing is only as good as one audio buffer. With timestamps (`m.time`), it can be better, but RtMidi's delta times on Windows are only roughly in milliseconds. Measure.
- **`playback.cpp` and `engine.cpp` are busy upstream.** Keep the change in its own functions, fork-marked. Clock-in is also something upstream has said it wants (#2715), so it may be worth offering.
- **Queueing and jump effects.** If the current pattern has a `Bxx` or `Dxx`, which wins: the queue or the effect? Suggested: the queue, and say so in the UI.
- **Nobody in the family has asked for this yet.** It scores 4/10 because the demand is upstream and from other trackers.

## Open questions

1. Who would use this first? Josh with a DAW, Michael with other gear, or nobody yet? This decides whether 017 is worth more than the one-line SPP check.
2. Tempo follow: A (measure and retune) or B (ticks from clocks)? The spike should answer this with measurements.
3. While following clock, what do the song's own tempo effects do: scale, or get ignored?
4. Should start/stop from MIDI be a tickbox (as #918 asks), or is MIDI learn enough with a preset?
5. Live queueing: queue one order at a time, or a list? Shift+click, a pad controller, or both?
6. Is the song position pointer out bug (`engine.cpp:1995`) real? Fix it upstream either way if so.

## Spike plan

Steps 1-6 need no hardware. Step 7 needs gear.

1. **Check clock out** (no hardware). Send clock from Furnace to loopMIDI and watch it in a MIDI monitor (or the Python script). Play from the top and from a later order. *You'll know when* you can say whether the song position pointer has the wrong byte order and units, and how far clock out drifts over five minutes.
2. **Let clock in** (no hardware). On a branch, clear the timing flag in `ignoreTypes` (`rtmidi.cpp:143`), skip system real-time messages in the GUI callback, and count clocks in the engine. *You'll know when* the engine counts 24 clocks per beat from the script at 120 BPM, and the GUI does not wake for them.
3. **Start, stop, continue** (no hardware). Handle `0xFA`, `0xFB` and `0xFC` in the engine behind one setting. *You'll know when* the script starts, stops and continues Furnace with no MIDI learn binds.
4. **Tempo follow, shape A** (no hardware). Estimate tempo from `m.time` and retune the tick rate. Test with steady clock, jittered clock and a tempo ramp. *You'll know when* you have a table of phase error over two minutes per case, at two buffer sizes, and can say whether A holds.
5. **Song position pointer in** (no hardware). Map it to (order, row) for a simple song, then one with a speed change. *You'll know when* "continue from bar 9" lands on the right row.
6. **Live queueing** (no hardware). Add a queued order to the engine, applied where `nextOrder()` runs, plus Shift+click in the orders list. *You'll know when* you can queue order 5 while order 2 plays and it starts exactly after order 2's last row, with no gap.
7. **Real gear** (someone with a DAW, drum machine or LSDj setup). *You'll know when* Furnace follows a real master for a full song without audible drift.

## Decision criteria

- **Build it**: shape A holds phase within a few milliseconds through jitter and ramps, and someone in question 1 will use it. Ship clock in with start/stop/continue/SPP as one setting, and live queueing separately (M plus S).
- **Reshape it**: tempo follow is unreliable, but start/stop/SPP work. Ship transport only (no tempo follow) and live queueing (S). Offer the SPP-out fix upstream if step 1 confirms it.
- **Split it**: nobody wants clock sync yet. Ship live queueing alone (S), and park clock in with the step 1-2 findings written up.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\017-midi-clock-in-live-queueing.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Check the drift line first and re-verify any cited code that changed. Scope: MIDI clock in (RtMidi currently drops 0xF8 at rtmidi.cpp:143), start/stop/continue, song position pointer in, tempo follow (measure-and-retune first), the possible song-position-pointer-out bug, and live pattern queueing. Note input bugs belong to idea 010, not this one. Test with a loopMIDI virtual port and a scripted Python clock sender; steps 1-6 need no hardware. Prototype on a branch. Ask Josh open question 1 before productizing anything beyond queueing.
```
