# 020 — Lumatone key lights that follow the song

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/audio/rtmidi.cpp src/audio/taAudio.h src/engine/engine.cpp src/engine/engine.h src/engine/playback.cpp src/gui/pattern.cpp src/gui/piano.cpp src/gui/gui.cpp src/gui/doAction.cpp src/gui/settings/allSettings.cpp src/engine/song.h`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 6/10 (my estimate; /ideate has not scored this)
- **Lenses**: new ground, with a real user in the family
- **Effort (coarse)**: M (GUI-side only, no engine or format change; most of the risk is the keyboard's speed)
- **Planned at**: f491976c9 on 2026-10-18

## The idea

While a song plays, light each Lumatone key as its note sounds, in that channel's colour. When the note stops, put the key back to its layout colour. Michael films the keyboard for his YouTube videos, so the lit keys show the music being played, next to the scopes from idea 14.

Everything is sent from Furnace to the Lumatone as MIDI system exclusive (sysex) messages, one per key change.

## Who wants this and why now

- **Michael**, Josh's son, owns a Lumatone (280 hex keys, each with its own RGB LED) and posts Furnace songs to YouTube (youtube.com/@mysti_is_lost). A keyboard that plays the song in light is good video.
- **Idea 18 comes first.** It checks that the Lumatone works with Furnace at all and whether Michael cares about lights (its question 8 and step 12). If he doesn't, park this.
- **Idea 19 shares the hard part.** Lighting a key means knowing which key plays a given note. That is 019's `.ltn` parser, run backwards.
- Nothing in Furnace drives lights today. The "Light Show (use for Launchpad)" MIDI output mode is a settings radio button only (`allSettings.cpp:1487-1488`); the engine checks only for Melodic mode (`playback.cpp:405`) and never reads `DIV_MIDI_MODE_LIGHT_SHOW` (`engine.h:147`).

## The Lumatone's colour command

The only public spec I found is the Lumatone Editor source (`hsstraub/TerpstraSysEx.2014`, BSD-3-Clause, last pushed 2026-06-09). I read `master` and the newest branch, `isomorphicassign/lumatonecontroller-2` (2026-05-27). Lumatone's own site has firmware downloads (latest 1.3) but no sysex documentation.

### The message

From `Source/LumatoneFirmwareDefinitions.h:20-59` and `Source/TerpstraMidiDriver.cpp:98-103`, `:726-746`:

```text
F0 00 21 50  bb  01  kk  rH rL  gH gL  bH bL  F7
```

| Bytes | Meaning |
|---|---|
| `00 21 50` | Lumatone's manufacturer ID (`MANUFACTURER_ID_0..2`) |
| `bb` | Board (section) 1-5 (`BOARD_OCT_1..5`). 0 is the "server" for global commands. |
| `01` | `SET_KEY_COLOUR` |
| `kk` | Key 0-55 on that board |
| `rH rL` ... | Each colour channel is 8 bits, split into two 4-bit halves (high, low), because sysex data bytes can't go above 0x7F |

- 14 bytes on the wire per key.
- Board and key match the `.ltn` file: `.ltn` section `[BoardN]` is sysex board `N+1`, and `Key_K` is key `K` (the editor sends `setSelection + 1`, `EditActions.cpp:185`).
- **Firmware before 1.0.11** takes a shorter form: one 7-bit byte per colour, `F0 00 21 50 bb 01 kk r g b F7` (`TerpstraMidiDriver.cpp:122-134`, built by `createTerpstraSysEx`, `:710-724`). The editor picks by firmware version (`LumatoneController.cpp:135-152`). Michael's firmware decides which one we send. `GET_FIRMWARE_REVISION` is command `0x31`.
- **There is no "set many keys" command.** The command list ends at `0x4F` on both branches. A full repaint is 280 messages.
- **Saving is a separate command.** `SAVE_PROGRAM` (`0x02`, `TerpstraMidiDriver.cpp:137-140`) writes the current state into a preset. Furnace must never send it. I could not confirm from the source whether a colour change survives a power cycle without it. The spike checks.

### Replies and pacing

- The keyboard answers each command with the same header plus a status byte at position 5: `00` not recognised, `01` OK, `02` busy, `03` error, `04` "not in MIDI state" (`LumatoneFirmwareDefinitions.h:42`, `:181-185`).
- The editor keeps **one message in flight**. It waits for the answer, gives up after 2000 ms, and waits 500 ms before retrying when the keyboard says busy (`TerpstraMidiDriver.cpp:1379-1468`, `:1501-1505`; `TerpstraMidiDriver.h:508-509`).
- The source says nothing about normal answer time, and nothing about whether the firmware copes with messages sent without waiting. This is the biggest unknown in the idea.

### Other useful commands

- `GET_RED/GREEN/BLUE_LED_CONFIG` (`0x13-0x15`) read a board's current colours. `GET_CHANNEL_CONFIG` and `GET_NOTE_CONFIG` (`0x16`, `0x17`) read its key mapping (`LumatoneFirmwareDefinitions.h:85-89`). So Furnace could read the layout off the keyboard instead of needing Michael's `.ltn` file.
- `SET_LIGHT_ON_KEYSTROKES` (`0x07`) turns on the firmware's own "light the key I press" effect. That is a different feature, for live playing, not for playback.

## What Furnace already has

### Sending sysex

- **The send path works.** `TAMidiOutRtMidi::send` passes sysex bytes straight to RtMidi (`rtmidi.cpp:178-196`). `TAMidiMessage` carries them in `sysExData` / `sysExLen` (`taAudio.h:110-128`).
- **Furnace already sends sysex in two places**: the MIDI time code full frame on play (`engine.cpp:1997-2058`) and the TX81Z voice request (`doAction.cpp:217-226`). The second goes through `DivEngine::sendMidiMessage` (`engine.cpp:3965-3977`), which the GUI can call. (Brief 018 says "Furnace sends no sysex". That is wrong: it sends no *light* sysex.)
- **Sysex input works too**, so the keyboard's answers will arrive. The input port is opened with sysex not ignored (`rtmidi.cpp:143`), and the GUI's MIDI handler sees each message (`gui.cpp:5238-5250`). Side effect: that handler prints every incoming sysex as hex to the console (`gui.cpp:5245-5250`), so a hundred answers a second would flood it. Silence it for Lumatone answers.
- **There is one MIDI output device** (`midiOutDevice`, `engine.cpp:4298-4302`). If it points at the Lumatone for lights, Furnace can't also send Melodic notes to another synth. Fine for Michael; worth saying in the UI.

### Knowing which notes are playing

- **The GUI already works this out every frame.** `updateKeyHitPre` (`pattern.cpp:2304-2364`, called from `gui.cpp:6101`) reads each channel's current note and key-on state (`getChanState(i)->note`, `->keyOn`) to light the on-screen piano. Muted channels are skipped. Channel feedback styles 2-4 track held notes, not just note starts.
- **Channel colours exist.** Each sub-song stores a colour per channel (`chanColor`, `song.h:126`), with a fallback to the theme colour by channel type (`channelColor`, `gui.cpp:1172-1194`; the piano does the same in `pianoKeyColor`, `piano.cpp:35-38`). Idea 007's themes feed the fallback.

### The hook: GUI side, not engine side

Two places could drive the lights:

1. **Engine side**, in `DivEngine::dispatchCmd`'s MIDI output code next to Melodic mode (`playback.cpp:400-505`). It sees every note command at the exact time. But it runs on the audio thread, sees every arpeggio and retrigger, and `sendMidiMessage` takes the engine lock (`BUSY_BEGIN`, `engine.cpp:3973`).
2. **GUI side**, next to `updateKeyHitPre`. Once a frame (about 60 times a second), compare the set of lit keys with last frame and send only the changes.

Go GUI side, but read `getChanState(i)->note` and `->keyOn` directly rather than reuse `pianoKeyHit`: what the piano records depends on the user's channel feedback style (style 1 records only note starts, `pattern.cpp:2319-2327`). GUI side limits itself to the frame rate, merges changes that cancel out within a frame, keeps the audio thread untouched, and needs no engine change. Lights a frame late (about 16 ms) won't show on video.

## How fast is fast enough

I counted note starts in 12 demo songs from six chip folders (`demos/`, via furnace-mcp; jumps ignored, so approximate):

| Song | Channels | Average notes/s | Busiest second |
|---|---|---|---|
| genesis/RubyIllusions_Genesis | 10 | 47 | 86 |
| msx/2024 BOTB MSX-MUSIC GRINDCORE | 12 | 36 | 92 |
| arcade/Eternal_Forest_TaitoArcade | 16 | 33 | 59 |
| nes/delarosamazapan | 11 | 27 | 60 |
| gameboy/contested | 4 | 24 | 34 |
| specs2/Tim_Follin | 8 | 7 | 12 |

The other six fall inside the same range.

- Each note change is up to two messages: light the new key, restore the old one. A busy song needs about **180 messages a second** at its peak, about 2.5 KB/s.
- **Over USB** the wire is not the limit. **Over 5-pin MIDI** (31250 baud, about 3 KB/s) a busy second nearly fills the cable.
- **The keyboard's answer time is the real limit.** With one message in flight, a 5 ms answer allows 200 messages a second (just enough). A 20 ms answer allows 50 (not enough).
- **Duplicate keys multiply it.** In Classic Mode middle C sits on four keys (brief 018). Lighting every copy is four times the traffic.
- Drum and noise channels should not light keys. That cuts the count a little.

So the design needs a send queue that **keeps only the latest colour per key** and drops stale ones. A key that goes on and off before its turn costs nothing. When the queue falls behind, lights lag or skip notes, but they never pile up.

## Trade-offs and risks

- **Unknown keyboard speed.** If answers are slow, busy songs will show only some notes. Fallbacks: light one copy of each note only, skip drum channels, or light only the lead channels Michael picks.
- **Inverse mapping.** A Furnace note may sit on several keys (Classic Mode) or on none (a microtonal layout where the note is between keys). Choosing which keys to light is a product decision.
- **Microtonal songs.** With idea 019 a note is a 12-tone note plus an `E5xx` detune. To light the right key, the lights code must use note plus detune, not the note alone. The channel's detune is in `getChanState(i)->pitch` (`engine.h:258`).
- **Restoring colours.** Furnace needs the layout's colours to restore keys. Either from the `.ltn` (`Col_N`, see 019) or read off the keyboard (`0x13-0x15`). If Furnace stops (crash, stop button) while keys are lit, they stay lit until it repaints.
- **Preset damage.** If colour changes persist without `SAVE_PROGRAM`, a crash could leave Michael's preset with stray colours. Check before any long test.
- **Firmware drift.** The firmware is at 1.3. The editor source lists commands up to the 1.1.0 era. Newer firmware may have added faster commands the public source doesn't show.
- **Upstream conflict.** Upstream may one day build Launchpad light show. Keep this as a separate "Lumatone lights" setting, not inside the Light Show code path.

## Open questions

1. Does Michael want this at all (018 question 8, step 12)?
2. Which firmware version is on his keyboard? (Decides the message form.)
3. How long does the keyboard take to answer a colour command? Does it accept a burst without waiting?
4. Do colour changes survive power off without `SAVE_PROGRAM`?
5. When a note is on several keys, light all of them, the one nearest the last lit key, or one fixed copy?
6. Which colour: the channel colour, the instrument colour, or brighter or dimmer versions of the layout colour? Should volume set brightness (as the piano does with feedback style 2)?
7. Should the GUI also draw a "virtual Lumatone" that shows the same lights? It would let him check a song without the keyboard, and could go into video exports later (idea 14).

## Spike plan

Steps 1-4 need nothing from Michael. Steps 5-7 need Michael and the keyboard, after idea 18 has passed.

1. **Build the bytes and check them** (no Michael). Write a function that turns (board, key, colour) into the message, in both firmware forms. Compare against the editor's builders (`TerpstraMidiDriver.cpp:122-134`, `:726-746`) for a handful of keys. *You'll know when* your bytes match what the editor code would produce, byte for byte.
2. **Dry-run log** (no Michael). Add a debug setting that, while a song plays, works out the lit keys each frame from `updateKeyHitPre`'s data and logs the messages it would send, instead of sending them. Use one of the Lumatone factory mappings (Classic Mode) for the key layout. *You'll know when* the log for a known song shows the right keys lighting and restoring, and you have message-per-second counts for the busy demos above.
3. **Fake keyboard** (no Michael). A small furnace-mcp or Python script on a virtual MIDI port (loopMIDI on Windows) that answers each colour command after a set delay (2, 5, 20 ms). Run Furnace's sender against it. *You'll know when* you can say how far lights lag at each delay, and that the "latest colour per key" queue keeps lag bounded.
4. **Inverse mapping** (no Michael). From a `.ltn` file, build note → keys for Classic Mode and for one microtonal preset (31-EDO), using 019's parser. *You'll know when* every note in a test song maps to the keys the preset's own colours suggest, and you know how many notes have no key.
5. **Measure the real keyboard** (Michael and the keyboard). Read the firmware version. Send one colour, time the answer. Then send 50 in a row without waiting, and see what comes back. Power-cycle and see whether colours stuck. *You'll know when* you have the answer time, the burst behaviour and the persistence answer (open questions 2-4).
6. **Play a song** (Michael and the keyboard). A slow song first, then the busiest one he likes. Film it. *You'll know when* the video shows the lights following the music, or you can say which songs are too busy.
7. **Ask Michael** (Michael). Questions 5-7. *You'll know when* you have his choices.

## Decision criteria

- **Build it**: the keyboard answers fast enough for Michael's songs (or the fallbacks are fine for him), colours don't persist by accident, and he wants it in his videos. Productize as a "Lumatone lights" section under MIDI output: device, layout source (`.ltn` or read from keyboard), colour rule, channels to light (M).
- **Reshape it**: the keyboard is too slow for full songs. Light only the channels he picks, or only note starts with a fixed fade (S-M). Or skip the hardware and build the on-screen "virtual Lumatone" for videos instead (S-M, no keyboard needed).
- **Drop it**: Michael doesn't care about lights, or colour commands persist into presets in a way that can't be made safe.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\020-lumatone-key-lights.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Check its drift line first and re-verify any cited code that changed. Scope: build the Lumatone key-colour sysex (from the BSD-3 Lumatone Editor source), drive it once per frame from the GUI's existing key-hit data, measure lag against a fake keyboard, and map notes back to keys from a .ltn layout. Do not build beyond the spike; prototype work happens on a branch, and the sender must never send SAVE_PROGRAM (0x02). Steps 1-4 need no one; ask Josh to set up a session with Michael and his Lumatone (after idea 18 passes) before steps 5-7.
```
