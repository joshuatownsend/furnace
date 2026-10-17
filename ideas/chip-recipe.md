# Recipe: add a sound chip to the fork

Written against `e9988cf35` (HEAD of `idea/006-chip-recipe`). All `path:line` references are to that commit; re-grep a nearby symbol if the numbers have drifted.
First user: Bally Astrocade (3 square voices, noise, master oscillator with vibrato; core ported from MAME `astrocde.cpp`).

Evidence used: Watara Supervision (`9d279cead`, 16 files), NEC uPD1771C (`f14ff2579`, then re-cored from MAME in `97402e6d4`), klattsch (`390137b35`, post-refactor path check). Supervision and uPD1771C predate the giga-refactor (`9b35ca77c`), so several of their files moved; the table below gives the current locations.

Closest working example for the driver: `src/engine/platform/pv1000.cpp` (3 channels, macros, oscilloscope, one register file, no samples; 330 lines). Supervision (`supervision.cpp`, 657 lines) is the example for chip flags, stereo output and a MAME-style core. Do NOT use `dummy.cpp` as the template for a macro-driven chip: it never calls `std.setEngine()`, has no `getChanMacroInt()`, and so ignores instrument macros (`src/engine/platform/dummy.cpp:163-169`).

## 1. Before you start

### 1.1 License check
- Furnace is GPL-2.0-or-later (`src/engine/sysDef.h:1-17`). A ported core must be GPL-compatible. MAME cores are normally BSD-3-Clause; read the `// license:` line at the top of the exact file you port (the existing port starts `// license:BSD-3-Clause` / `// copyright-holders:...`, `src/engine/platform/sound/upd1771.cpp:1-2`). Stop and ask Josh if the line says anything else (GPL-3-only, "non-commercial", missing).
- Keep the original license and copyright-holder lines at the top of the ported file. Put the 18-line Furnace GPL header (copy from `src/engine/platform/supervision.h:1-18`) on the driver files only.
- Credits are required for BSD/MIT cores. See step 14.

### 1.2 How a MAME core is adapted
Pattern from `97402e6d4` and `src/engine/platform/sound/upd1771.h`:
- Host it in `src/engine/platform/sound/<chip>.cpp/.h` (C++ is fine; Supervision uses plain C, `supervision.c`).
- Replace the `device_t` / `device_sound_interface` base classes with a plain class. Delete `emu.h`, machine config, `DEFINE_DEVICE_TYPE`, `save_item`, `ROM_START` and anything that talks to a CPU or address map.
- Keep a small public API: `device_reset()`, register `write(offset, data)`, and `sound_stream_update(short* output, int len)` (`upd1771.h:22-30`).
- Expose per-voice output in a public array so the driver can feed the oscilloscope, like `short chout[4]` (`upd1771.h:32`, used at `scvtone.cpp:50-54`).
- Pass the clock in through a setter; do not read `clock()` from a device base.
- Replace MAME stream buffers (`stream_buffer`, `sound_stream`) with a plain output pointer and length.

### 1.3 Choose the chip's file ID
- Rule (Josh, 2026-10-17): fork-only chips use file IDs `0x1000` and up. Astrocade is `0x1000`; the next fork chip is `0x1001`.
- Why it works: the `.fur` writer stores the chip ID as 16 bits (`w->writeS(systemToFileFur(...))`, `src/engine/fileOps/fur.cpp:2599`) and the reader takes `unsigned short` (`fur.cpp:870`). `DivSysDef::id` is `unsigned short` (`src/engine/sysDef.h:108`). The lookup table is a `std::map<unsigned short,DivSystem>` (`src/engine/sysDef.cpp:30`), so sparse IDs are fine. Upstream has only used IDs below `0x100` (`papers/format.md:164-282`).
- The old 8-bit chip-ID path (`fur.cpp:1122`) is read-only legacy; it never sees a fork ID.
- A song that uses a fork chip will not open in upstream Furnace. That is accepted.
- List the IDs in use. The 4-digit ones are the fork's:
  ```
  grep -A1 "new DivSysDef" src/engine/sysDef.cpp | grep -oE ", 0x[0-9a-fA-F]{2,4}, [0-9]+, " | sort -u
  ```
  At HEAD this prints 114 entries and none with four hex digits. The highest upstream ID is `0xfd` (Dummy).
- DMF ID (second ID argument) is `0` for every fork chip. `0` means "not a DefleMask system"; the map skips it (`sysDef.cpp:2835-2837`).
- Record each fork ID in `papers/format.md` (step 15).

### 1.4 Enum position
- `DivSystem` lives in `src/engine/sysDef.h:153-273` (not `song.h`). The list ends `DIV_SYSTEM_KLATTSCH,` (`sysDef.h:269`), a blank line, then `DIV_SYSTEM_MAX` (`sysDef.h:271`).
- Add one marked block between those two lines, and put every later fork chip in the same block:
  ```
    DIV_SYSTEM_KLATTSCH,

    // fork-only chips (file IDs 0x1000 and up; see ideas/chip-recipe.md)
    DIV_SYSTEM_ASTROCADE,

    DIV_SYSTEM_MAX
  ```
- Enum values are NOT written to `.fur` (the file stores the file ID), so the position is safe for songs. Two things do use the raw enum value:
  - JSON export writes the enum value as the chip `id` (`src/engine/fileOps/json.cpp:78`) and JSON import range-checks it against `DIV_SYSTEM_MAX` (`json.cpp:1536`). JSON files that contain a fork chip therefore break when an upstream merge adds a chip above it. (Decision 2026-10-17: the pilot makes JSON export write the file ID and import prefer it.)
  - The current enum number of any chip: `awk '/^enum DivSystem \{/{f=1;next} f&&/^\};/{exit} f&&/^[ ]*DIV_SYSTEM_[A-Z0-9_]+/{n=$1; sub(/,.*/,"",n); print c++, n}' src/engine/sysDef.h | grep ASTROCADE` (at HEAD KLATTSCH is 114, MAX is 115).
- Touching `sysDef.h` (included from `src/engine/song.h` and `src/engine/engine.h`) causes a near-full rebuild. Do the enum edit once, early.

### 1.5 Instrument type: reuse `DIV_INS_STD` (decision)
A new chip does NOT need a new `DIV_INS_*` type. Use `DIV_INS_STD` (the standard macro instrument) unless the chip has per-instrument parameters that macros cannot express.
- Precedent: the SN76489 channels use `DIV_INS_STD` (`src/engine/sysDef.cpp:923-926`) and so does the Dummy system (`sysDef.cpp:2827`). Pong and PC Speaker use `DIV_INS_BEEPER` (`sysDef.cpp:1496,1505`), Pokemon Mini `DIV_INS_POKEMINI` (`sysDef.cpp:1565`), TIA `DIV_INS_TIA` (`sysDef.cpp:1115`): those have their own types because they have their own instrument editors, not because the engine requires it.
- `DIV_INS_STD` gives the instrument editor macros for Volume (0-15), Arpeggio, "Noise Mode" (0-3), Panning, Pitch and Phase Reset (`src/gui/insEdit/std.cpp:22-36`, dispatched from `src/gui/insEdit.cpp:244-246`). The labels are SN76489-flavoured; that is cosmetic.
- DIV_INS_* values ARE persisted in files. See 5.1. A new type is as risky as a new chip ID, and cannot use the `0x1000` trick. Avoid it. If a new type is unavoidable, see step 17 and ask Josh first.

## 2. Touchpoints in build order

"Mandatory" means the build breaks, the chip does not work, or a license is violated without it. "Optional" lists what you lose. Examples are real lines at HEAD.

| # | File (path:line at HEAD) | What goes there | Example from Supervision / uPD1771C | Mandatory? |
|---|---|---|---|---|
| 1 | `src/engine/platform/sound/<chip>.h/.cpp` (new) | The ported emulation core (step 1.2). Skip the file if the chip is so small it fits in the driver. | `sound/upd1771.h`, `sound/upd1771.cpp` (MAME HLE); Supervision's `sound/supervision.c/.h` | Mandatory if you port a core; no such file for an invented chip |
| 2 | `src/engine/platform/<chip>.h/.cpp` (new) | The `DivDispatch` driver (section 3). | `src/engine/platform/pv1000.cpp`, `supervision.cpp` | Mandatory |
| 3 | `CMakeLists.txt:760-764` (cores) and `:902-904` (drivers); both are inside the explicit `ENGINE_SOURCES` list | One line per new `.c/.cpp`. | `src/engine/platform/sound/supervision.c` (`:760`), `src/engine/platform/supervision.cpp` (`:902`) | Mandatory. If missed: link error (undefined `DivPlatform<Chip>`). Sources are listed explicitly, not globbed. |
| 4 | `src/engine/sysDef.h:269-271` | New `DIV_SYSTEM_*` in the `// fork-only chips` block (step 1.4). | `DIV_SYSTEM_SUPERVISION,` (`sysDef.h:264`) | Mandatory. Compile error without it. |
| 5 | `src/engine/sysDef.cpp:2797-2821` (put the new block after klattsch and before `DIV_SYSTEM_DUMMY` at `:2823`; the file-ID map is built by the loop at `:2830-2839`) | `sysDefs[DIV_SYSTEM_X]=new DivSysDef(...)`. Fields in step 2.1. | `sysDefs[DIV_SYSTEM_SUPERVISION]=new DivSysDef(_("Watara Supervision"), NULL, 0xe3, 0, 4, 4, 4, false, true, 0, false, 1U<<DIV_SAMPLE_DEPTH_8BIT, 0, 0, ...` (`sysDef.cpp:2469-2482`) | Mandatory. Without it `sysDefs[x]==NULL`: the chip has no name, no channels, and the file ID is unknown (load fails with "unrecognized system ID"). |
| 6 | `src/engine/dispatchContainer.cpp:79-80` (include) and `:700-705` (case; default branch at `:802-805`) | `#include "platform/<chip>.h"` and `case DIV_SYSTEM_X: dispatch=new DivPlatformX; break;` | `#include "platform/supervision.h"` (`:79`); `case DIV_SYSTEM_SUPERVISION: dispatch=new DivPlatformSupervision;` (`:700-702`) | Mandatory. SILENT failure if missed: the default branch logs a warning "this system is not supported yet! using dummy platform." and plays the Dummy chip instead (`:802-805`). |
| 7 | `src/gui/guiConst.cpp:1284-1390` (`availableSystems[]`; Supervision at `:1384`, klattsch at `:1388`) | Add `DIV_SYSTEM_X,` before the final `0 // don't remove this last one!`. | `DIV_SYSTEM_SUPERVISION,` (`guiConst.cpp:1384`) | Mandatory for the UI. SILENT if missed: the chip is absent from the "add chip" picker and the command palette (`sysPicker.cpp:31`, `commandPalette.cpp:224`); songs that already use it still load and play. |
| 8 | `src/gui/guiConst.cpp` category list: `chipsSquare[]` at `:1432` (PV1000 at `:1441`), `chipsWave` `:1447`, `chipsSpecial` `:1465` (Supervision at `:1490`) | Add to the one category that fits (Astrocade: `chipsSquare`). | `DIV_SYSTEM_SUPERVISION,` (`guiConst.cpp:1490`) | Optional. Without it the chip only shows under "All chips". |
| 9 | `src/gui/presets/square.cpp:121-125` (PV1000 entry), `specialized.cpp:149-153` (Supervision), `gameConsoles.cpp:296-300` (Supervision with tick rate). Presets moved out of `presets.cpp` in the refactor. | An `ENTRY(` with `CH(DIV_SYSTEM_X, 1.0f, 0, "")`; flags go in the last string. | `ENTRY(_("Watara Supervision"), { CH(DIV_SYSTEM_SUPERVISION, 1.0f, 0, "") });` (`specialized.cpp:149-153`) | Optional. Without it there is no entry in the "New song" system list; the chip is still reachable through "add chip" (#7). |
| 10 | `src/gui/sysConf.cpp:3008-3017` (the "nothing to configure" list; Supervision's own panel at `:2616-2638`; the default branch is `:3044-3055`) | Add `case DIV_SYSTEM_X:` to the no-options list, or write an options panel (checkboxes that `flags.set(...)` inside `e->lockSave`). | Supervision's panel: `bool sqStereo=flags.getInt("sqStereo",false); if (ImGui::Checkbox(_("Stereo pulse waves"),&sqStereo)) {altered=true;}` (`sysConf.cpp:2616-2637`); no-options list entry `case DIV_SYSTEM_PV1000:` (`:3011`) | Optional but do it. Without it the chip falls into the default branch (`:3044`) and shows a meaningless "PAL" checkbox that writes `clockSel`. The custom-clock widget (`:3156-3177`) is generic and appears for every chip with no code from you. |
| 11 | `src/gui/sysMiscInfo.cpp:26-293` (`getSystemPartNumber`; Supervision at `:284`; was `sysPartNumber.cpp` before the refactor) | `case DIV_SYSTEM_X: return "part number";` | `case DIV_SYSTEM_SUPERVISION: return "Watara Supervision";` (`sysMiscInfo.cpp:284-286`) | Optional. The default returns the system name (`:290-292`). |
| 12 | `src/gui/gui.h:85-86` (`CHECK_HIDDEN_SYSTEM`) | Only to hide a chip from the pickers. | `x==DIV_SYSTEM_UPD1771C` (`gui.h:86`) | Optional. Do not add for a normal chip. |
| 13 | `src/gui/debug.cpp:54` (include), `:237` (`putDispatchChip` switch, PV1000 at `:514`), `:553` (`putDispatchChan` switch, PV1000 at `:1043`) | Include, plus a `case` that prints driver state in the Debug window. | `#include "../engine/platform/supervision.h"` (`debug.cpp:54`). Supervision has no case in either switch at HEAD. The driver header declares `friend void putDispatchChip(void*,int);` (`supervision.h:72`). | Optional. SILENT if missed: the Debug window prints "Unimplemented chip! Help!" (`:545-548`, `:1097-1100`). The `friend` lines are only needed if debug.cpp reads private members. |
| 14 | `src/gui/about.cpp:165` and `src/main.cpp:363` (the `-V` text) | One credit line each for a ported third-party core. | `_N("MAME µPD1771C-017 HLE core by David Viens")` (`about.cpp:165`); `printf("- MAME µPD1771C-017 HLE core by David Viens (BSD 3-clause)\n");` (`main.cpp:363`) | Mandatory when the core is BSD/MIT (the notice must travel with binaries). Not applicable to an invented chip. |
| 15 | `papers/format.md:272-282` (chip ID list; Supervision at `:272`, klattsch `:275`, "reserved for development" `:281-282`) | One line per fork ID, plus a one-time note below `:282` that IDs `0x1000` and up are reserved for this fork. | `- 0xe3: Watara Supervision - 4 channels` (`format.md:272`) | Mandatory (it is the only ID registry; the ID check in 1.3 reads sysDef.cpp, but humans read this). Documentation only: no build effect. |
| 16 | `doc/7-systems/README.md:120` (+ new `doc/7-systems/<chip>.md`), `README.md:102` (chip list) | A list line and a short page. | `- [Watara Supervision](watarasv.md)` (`doc/7-systems/README.md:120`); `  - Watara Supervision` (`README.md:102`) | Optional. |
| 17 | New instrument type only (see 1.5; not needed with `DIV_INS_STD`) | Chain in 4.4 below. | `DIV_INS_SUPERVISION=64` (`src/engine/instrument.h:101`) | Optional; avoid. |
| 18 | New effect command only (not needed if the chip reuses an existing `DIV_CMD_*`) | Chain in 4.5 below. | `{0x12, {DIV_CMD_STD_NOISE_MODE, _("12xx: Set duty cycle/noise mode ...")}}` reuses an existing command (`sysDef.cpp` Supervision entry) | Optional; prefer reuse. |

The 16 files of the Supervision commit map as follows: CMakeLists.txt -> #3; dispatchContainer.cpp -> #6; instrument.h -> #17; sound/supervision.c/.h -> #1; supervision.cpp/.h -> #2; song.h -> #4 (now `sysDef.h`); sysDef.cpp -> #5; debug.cpp -> #13; guiConst.cpp -> #7, #8 (and the `insTypes` row in #17); insEdit.cpp -> #17; presets.cpp -> #9; sysConf.cpp -> #10; sysPartNumber.cpp -> #11 (now `sysMiscInfo.cpp`); furIcons.h -> #17. The extra file in the uPD1771C commit, `instrument.cpp`, -> #17. Files in the klattsch commit that you do not need: `engine.cpp`, `playback.cpp`, `gui.cpp`, `pattern.cpp`, `insEdit.cpp`, `klattschInput.*`, `cmdStream*.cpp`, `dispatch.h` (those serve its custom text-entry UI and new effect commands).

### 2.1 `DivSysDef` constructor fields
Real signature: `src/engine/sysDef.h:123-142`. The comment at `src/engine/sysDef.cpp:375-380` is stale (it omits `compound` and `formatMask`); trust the header.

Order: `name, nameJ, fileID, fileID_DMF, chans, minCh, maxCh, isFM, isSTD, vgmVer, compound, formatMask, waveWid, waveHei, desc, channelDefs, [effects], [postEffects], [preEffects]`.

| Field | Meaning | Astrocade value |
|---|---|---|
| `name` | `_("...")` display name | `_("Bally Astrocade")` |
| `nameJ` | Japanese name | `NULL` |
| `fileID` | 16-bit ID stored in `.fur` (`sysDef.h:108`) | `0x1000` |
| `fileID_DMF` | DefleMask ID; `0` = not a DMF system | `0` |
| `chans, minCh, maxCh` | default / min / max channel count | `4, 4, 4` (3 tone + noise) |
| `isFM` | FM chip flag (Supervision: `false`) | `false` |
| `isSTD` | "standard" chip flag; read only at `engine.h:1742` (`isSTDSystem`) and `dmf.cpp:1472` (DMF export instrument check) | `true` |
| `vgmVer` | minimum VGM version; `0` = chip cannot be exported to VGM | `0` |
| `compound` | compound system (e.g. Genesis) | `false` |
| `formatMask` | bitmask of sample formats the chip takes, e.g. `1U<<DIV_SAMPLE_DEPTH_8BIT` (Supervision `sysDef.cpp:2471`); `0` = no samples | `0` |
| `waveWid, waveHei` | wavetable size; `0, 0` = no wavetable support | `0, 0` |
| `desc` | one-line description | `_("...")` |
| `channelDefs` | `DivChanDefFunc({ DivChanDef(name, shortName, DIV_CH_*, insType[, insType2]), ... })` or a template helper like `simpleChanDef<DIV_CH_PULSE,DIV_INS_STD>` (`sysDef.cpp:435-465`) | `DivChanDef(_("Square 1"),"S1",DIV_CH_PULSE,DIV_INS_STD)` x3, then `DivChanDef(_("Noise"),"NO",DIV_CH_NOISE,DIV_INS_STD)` |
| `effects` | chip-specific effect map, `{0x1x, {DIV_CMD_*, _("1xxx: ...")}}` | reuse existing commands, e.g. `DIV_CMD_STD_NOISE_MODE` |

The resulting block looks like the SN76489 entry's channel list (`sysDef.cpp:923-926`) plus an `_("...")` description. A NEW `insType` (a value you add to `instrument.h`) forces the steps in 4.4; reusing an existing one such as `DIV_INS_BEEPER` does not.

## 3. Driver skeleton

Files: `src/engine/platform/<chip>.h` and `.cpp`. Copy `pv1000.h` / `pv1000.cpp` and edit; the shape is below. Abstract defaults are in `src/engine/platform/abstract.cpp`.

### 3.1 Class shape (`pv1000.h:26-64`, `supervision.h:27-106`)
- `struct Channel: public SharedChannel { ... Channel(bool linear=true): SharedChannel(maxVol,linear) {} };` `SharedChannel` (`dispatch.h:469`) provides `freq, baseFreq, pitch, pitch2, ins, note, vol, outVol, active, keyOn, keyOff, freqChanged, inPorta, rawFreq`, the macro runner `std`, `handleArp()`, `macroInit()`, `calcBaseFreq()` and `calcFreq()`.
- `Channel chan[N]; DivDispatchOscBuffer* oscBuf[N]; bool isMuted[N]; DivPitchTable pitchTable; unsigned char regPool[R];`
- Optional for deferred writes: `struct QueuedWrite {unsigned char addr, val;}; FixedQueue<QueuedWrite,512> writes;` (Supervision, `supervision.h:46-52`).
- `friend void putDispatchChip(void*,int); friend void putDispatchChan(void*,int,int);` (only for the Debug window, #13).

### 3.2 Methods
Pure virtual: none. Everything has a default in `abstract.cpp`, but the defaults below are wrong for a working chip. A minimal macro-driven chip implements these (line numbers in `pv1000.cpp`):

| Method | What it does | Notes |
|---|---|---|
| `int init(DivEngine* p, int channels, int sugRate, const DivConfig& flags)` (`:304`) | `parent=p; dumpWrites=false; skipRegisterWrites=false;` `new DivDispatchOscBuffer` per channel, `isMuted[i]=false`, `setFlags(flags); reset(); return N;` | Must set `parent`. The return value is ignored by the container (`dispatchContainer.cpp:807`). |
| `void quit()` (`:317`) | `delete oscBuf[i]` | |
| `void setFlags(const DivConfig& flags)` (`:281`) | Set `chipClock`, then `CHECK_CUSTOM_CLOCK;` (`dispatch.h:1683-1688`, honours the "custom clock" setting), then `rate=chipClock/divider;`, `oscBuf[i]->setRate(rate)`, tell the core its clock, `notifyPitchTable();` | `rate` is the chip's NATIVE output rate; the container resamples (`dispatchContainer.cpp:807-825`). Supervision: `chipClock=4000000; CHECK_CUSTOM_CLOCK; rate=chipClock/64;` (`supervision.cpp:522-524`). Read your own flags with `flags.getInt("name",default)`, written by #10. |
| `void reset()` (`:248`) | `memset(regPool,0,..)`; for each channel `chan[i]=Channel(); chan[i].pitchTable=&pitchTable; chan[i].std.setEngine(parent);` reset the core; mute all voices with register writes | Without `std.setEngine(parent)` the macro runner has no engine pointer; macros do not work. |
| `void acquire(short** buf, size_t len)` (`:40`) | `oscBuf[i]->begin(len)` for each voice; loop `h` over `len` samples: apply queued register writes, tick the core once, `buf[0][h]=mixedSample;`, `oscBuf[i]->putSample(h, voiceSample)`; then `oscBuf[i]->end(len)` | Generate exactly `len` samples at `rate`. `buf[0]` is mono/left, `buf[1]` right when `getOutputCount()==2` (`supervision.cpp:96-97`). Osc samples are signed 16-bit; scale each voice to about `+-32767` (`pv1000.cpp:49`: `d65010g031.out[i]<<2`). |
| `void tick(bool sysTick)` (`:58`) | Per channel: `chan[i].std.next();` apply `std.vol/arp/duty/pan/pitch` `.had` values; `handleArp()` (when `NEW_ARP_STRAT`); on `freqChanged\|\|keyOn\|\|keyOff` compute `freq=calcFreq()` and write registers | Called once per engine tick (not per sample). |
| `int dispatch(DivCommand c)` (`:105`) | `switch (c.cmd)`: `NOTE_ON` (`getIns(ins,DIV_INS_STD)`, `macroInit(ins)`), `NOTE_OFF`, `NOTE_OFF_ENV`/`ENV_RELEASE`, `INSTRUMENT`, `VOLUME`, `GET_VOLUME`, `PITCH`, `NOTE_PORTA`, `LEGATO`, `PRE_PORTA`, `GET_VOLMAX`, `MACRO_OFF/ON/RESTART`; chip effects use the commands you named in sysDef (#5) | Copy the whole switch from `pv1000.cpp:106-208` and change the register writes. `GET_VOLMAX` returns the max volume. |
| `SharedChannel* getChanState(int ch)` (`:228`) | `return &chan[ch];` | Default returns `NULL`. |
| `DivMacroInt* getChanMacroInt(int ch)` (`:232`) | `return &chan[ch].std;` | Default returns `NULL` (macros then do nothing in the GUI). |
| `DivDispatchOscBuffer* getOscBuffer(int ch)` (`:236`) | `return oscBuf[ch];` | Default returns `NULL` (no oscilloscope). |
| `unsigned char* getRegisterPool()` / `int getRegisterPoolSize()` (`:240`, `:244`) | Return the shadow register array and its size in bytes | Feeds the Register View window. Keep `regPool[addr]=value` updated on every write (`pv1000.cpp:24`: `#define rWrite(a,v) {regPool[(a)]=(v)&0xff; ...}`). `getRegisterPoolDepth()` defaults to 8 (bits per register, `abstract.cpp:73-75`); override it for 16-bit registers. |
| `void muteChannel(int ch, bool mute)` (`:211`) | `isMuted[ch]=mute;` and silence or restore the voice | |
| `void forceIns()` (`:221`) | `chan[i].insChanged=true; chan[i].freqChanged=true;` | Called after instrument edits. |
| `int getOutputCount()` (`:263`) | `1` (mono) or `2` (stereo) | Default is 1. |
| `void notifyInsDeletion(void* ins)` (`:267`) | `chan[i].std.notifyInsDeletion((DivInstrument*)ins);` | MUST be overridden: the default logs "notifyInsDeletion NOT implemented!" and calls `abort()` (`abstract.cpp:187-190`). Deleting an instrument would crash the program. |
| `void notifyPitchTable(int sample)` (`:273`) | `pitchTable.init(parent->song.tuning, chipClock, CHIP_DIVIDER, maxFreq, true, parent->song.compatFlags.linearPitch);` | Signature `init(float tuning, double clock, double divider, int maximum, bool period, bool linear)` (`dispatch.h:372-440`, body `src/engine/pitchTable.cpp:177-217`). `maximum`: largest legal register value; the table picks the octave so the lowest (period mode) or highest (frequency mode) note still fits. `period`: `true` for a chip whose register is a period/divisor (output frequency falls as the register rises: PV1000 `pv1000.cpp:274`, Supervision `supervision.cpp:503`, SN76489 `sms.cpp:595`), `false` for a phase-accumulator chip whose register is proportional to frequency (Dummy `dummy.cpp:172`). `linear`: pass `parent->song.compatFlags.linearPitch` unchanged. `divider`: period mode computes `reg = round(chipClock / (f * divider))`, frequency mode `reg = round(f * divider / chipClock)` (`pitchTable.cpp:208-210`). Start with divider = N/2 for a chip whose square output is `clock/(N*reg)`: the Astrocade outputs `clock/(2*(master+1)*period)` and needs `master+1` (`astrocade.cpp:30`; `2*(master+1)` played exactly one octave high, and `4*(master+1)` two). A larger divider gives a smaller register value and a higher pitch. The SN76489's 64 (`sms.cpp:639`) depends on how its driver counts the register, so don't copy it. Only a render measurement settles it (the pilot's `tools/chip-verify/astrocade/wiring.py` prints the error per note). |
| `unsigned int getMaxFreq(int ch)` (`:277`) | Largest legal `freq` value | Default `0xffff`. Clamp to the register width. |
| `void poke(unsigned addr, unsigned short val)` and `poke(std::vector<DivRegWrite>&)` (`:292`, `:296`) | Write registers from outside (Register View, "poke" tools) | Optional but cheap. |
| `const char** getRegisterSheet()` (`:36`) | NULL-terminated `{"name","hexaddr",...}` list for Register View | Optional (`pv1000.cpp:28-34`). |
| `bool getDCOffRequired()` (`:300`) | `true` if the core output is unipolar (never goes negative) | Container then applies a high-pass (`dispatchContainer.cpp:227`). Default `false`. |
| `bool keyOffAffectsArp(int ch)` | `true` if note-off should stop the arpeggio macro | Optional (`supervision.h:87`). |
| `int getClockRangeMin()` / `getClockRangeMax()` | Limits for the custom clock | Defaults `MIN_CUSTOM_CLOCK`/`MAX_CUSTOM_CLOCK` = 100000/40000000 (`dispatch.h:35-36`). |

Register writes: Furnace drivers either write straight into the core (`pv1000.cpp:24`) or queue writes and apply them inside `acquire()` so they land on a sample boundary. Queue form (`supervision.cpp:27`):
```
#define rWrite(a,v) if (!skipRegisterWrites) {writes.push(QueuedWrite(a,v)); if (dumpWrites) {addWrite(a,v);} }
```
`skipRegisterWrites` is set while the engine seeks (do not touch the chip). `dumpWrites` is set during VGM-style export; `addWrite` records the write (`dispatch.h:1226-1230`). A chip with `vgmVer==0` never gets a dump, but keeping the macro as above costs nothing.

`acquire()` drain loop (`supervision.cpp:71-76`): `while (!writes.empty()) { QueuedWrite w=writes.front(); core_write(w.addr,w.val); regPool[w.addr]=w.val; writes.pop(); }`.

Do not add: samples (`getSampleMem`, `renderSamples`, ...), `acquireDirect`, `postProcess`. They are for sample chips and blip-direct cores.

## 4. Build and smoke test

### 4.1 Build (Windows, VS2019, existing `build-gui/`)
- CMake is not on PATH. Use the one bundled with VS2019 Build Tools (from Claude's memory file `C:\Users\joshu\.claude\projects\C--dev-furnace-furnace\memory\windows-build.md`):
  ```
  "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" --build build-gui --config Release --target furnace --parallel 6
  ```
- Target name: `furnace` (`CMakeLists.txt:1436-1437` sets `FURNACE` to `furnace`; `:1445` is the `add_executable` for the console-subsystem build; `:1443` is the Windows GUI-subsystem form).
- `build-gui/` was configured with `-S . -B build-gui -G "Visual Studio 16 2019" -A x64 -DCONSOLE_SUBSYSTEM=ON`. Editing `CMakeLists.txt` re-runs configure automatically on the next `--build`.
- Binary: `build-gui/Release/furnace.exe` (console subsystem, prints logs to stdout). Do not use `-j 12` (out of memory once); a full build takes about 20 minutes, and an enum edit in `sysDef.h` or `instrument.h` rebuilds nearly everything.
- `build-cli/` is an older headless attempt; `-DBUILD_GUI=OFF` fails on MSVC. Ignore it.
- Always pass `-noreport`, otherwise an error opens a blocking message box.

### 4.2 CLI flags that matter (`src/main.cpp:703-745`)
`-o/--output <file>` render audio (WAV by extension; implies headless output mode, `main.cpp:1029`); `-O/--vgmout`; `-C/--cmdout`; `-t/--txtout`; `-furout <file>` save as `.fur`; `-jsonout <file>`; `-i/--info`; `-c/--console`; `-q/--noreport`; `-l/--loops <n>`; `-s/--subsong <n>`; `-L/--loglevel` (did not reduce log output in my test; filter with `grep` instead). Single-dash long names (`-output`, `-jsonout`, `-info`, `-noreport`) are the forms verified in this recipe..

### 4.3 Smoke test, headless
There is no UI step. Build a tiny song as JSON (the loader needs only `chips` and one subsong; `ideas/001-json-song-import.md:72`), render it, check the audio is not silent, and check the log shows no Dummy fallback.

1. Get the chip's enum number (1.4): call it `ID`; at HEAD the first fork chip is `115`. JSON `id` is the enum value until the pilot switches it to the file ID.
2. Save as `mk.py` in the scratchpad (tested at HEAD with SMS, id 4, 4 channels):
   ```python
   import json, sys
   chip_id, chans, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
   rows = [{} for _ in range(32)]
   for i, n in enumerate([108, 112, 115, 120]):   # C-4 E-4 G-4 C-5 (108 = C-4)
       rows[i * 8] = {"note": n, "ins": 0}
   rows[31] = {"note": 253}                        # 253 = note off
   song = {
     "chips": [{"id": chip_id, "channels": chans, "volume": 1.0, "panning": 0.0, "frontRear": 0.0, "flags": {}}],
     "subsongs": [{
       "patternLength": 32, "orderLength": 1,
       "channelData": [{} for _ in range(chans)],
       "orders": [[0] for _ in range(chans)],
       "patterns": [[{"rows": rows}] if c == 0 else [{"rows": [{} for _ in range(32)]}] for c in range(chans)],
     }],
   }
   json.dump(song, open(out, "w"))
   ```
   Note values: `0-179` are notes (`108` = C-4), `253` off, `254` release, `255` macro release (`src/engine/defines.h:51-54`, `json.cpp:1467-1469`).
3. Run:
   ```
   python mk.py <ID> 4 chip.json
   build-gui/Release/furnace.exe -noreport -output chip.wav chip.json > run.log 2>&1
   ```
4. Check: `grep -c "using dummy platform" run.log` must print `0` (if not, #6 is missing); `chip.wav` must exist, and its peak must be above 0:
   ```
   python -c "import wave,array; w=wave.open('chip.wav'); a=array.array('h',w.readframes(w.getnframes())); print('peak',max(abs(x) for x in a))"
   ```
   (HEAD baseline for SMS in my test: 16-bit stereo 44100 Hz, peak 12324.)
5. Also check `furnace.exe -noreport -info chip.json` prints the song info, and `furnace.exe -noreport -furout chip.fur chip.json` then `-info chip.fur` loads it back (this proves the 16-bit `0x1000` ID survives a write and a read).
6. Pitch check: render one held note, find its frequency (zero-crossings or FFT) and compare with the expected C-4 (about 261.6 Hz at A=440). A wrong `CHIP_DIVIDER` shows up here.
7. The reference-core comparison harness belongs to the pilot (`ideas/006-chip-emulators-with-claude.md`, spike step 5), not to this recipe.

### 4.4 Chain for a new `DIV_INS_*` (only if 1.5 forces it)
All of these, or the build breaks or colors misalign:
1. `src/engine/instrument.h:104-105`: append before `DIV_INS_MAX` with an explicit number (`DIV_INS_KLATTSCH=67`). Read 5.1 first.
2. `src/gui/guiConst.cpp:146-215`: add a row at the same position in `insTypes[DIV_INS_MAX+1][3]` (name, icon, letter icon). The table is positional (index = enum value), with no compile-time check.
3. `src/gui/gui.h:392-396`: add `GUI_COLOR_INSTR_X` in the same order as the enum (the GUI computes `uiColors[GUI_COLOR_INSTR_STD+ins->type]`, `insEdit.cpp:128`, `dataList.cpp:131`, `piano.cpp:46`); `src/gui/guiConst.cpp:1118-1121`: `D(GUI_COLOR_INSTR_X,...)`; `src/gui/settings/allSettings.cpp:2728-2731`: `SETTING_COLOR(GUI_COLOR_INSTR_X)`.
4. `src/icon/furIcons.h:78-82`: `#define ICON_FUR_INS_X u8"\ue168"` (next unused glyph; klattsch is `\ue167`, `furIcons.h:82`).
5. `src/gui/insEdit.cpp:433-451`: `case DIV_INS_X: insEditX(ins); break;` (default branch shows "invalid instrument type! change it first."); new `src/gui/insEdit/<x>.cpp`, a declaration in `src/gui/gui.h` (Supervision: `gui.h:3294`), and a `CMakeLists.txt` line (`:1038` for Supervision).
6. `src/engine/instrument.cpp:2047-2058`: `case DIV_INS_X:` in the `putInsData2` `.fui` feature switch (a type with no extra data just `break;`s; `DIV_INS_UPD1771C` at `:2054`). Missing it is a switch warning, not an error (`WARNINGS_ARE_ERRORS` is OFF).
7. `src/engine/fileOps/json.cpp:335-472` (the `switch (ins->type)` has no `default:`; STD-like types are listed at `:456-471`): add the case.
8. `papers/newIns.md:133`: add `- 68: X`. Do this also for fork types, and mark them "fork".
9. `src/gui/sysMiscInfo.cpp:350-375`: only if the type should count as "other" instead of the channel's DIV_CH type.
10. `src/engine/song.cpp:976-1018` needs nothing, but `isInsTypePossible[DIV_INS_MAX]` is indexed by the channel's `insType` without a bounds check: an `insType` >= `DIV_INS_MAX` writes out of bounds.

### 4.5 Chain for a new `DIV_CMD_*` (only if no existing command fits)
1. `src/engine/dispatch.h:353-355`: append AFTER `DIV_CMD_TEST_REG` (`:353`) and before `DIV_CMD_MAX` (`:355`). The header comment (`dispatch.h:47-56`) says to append; klattsch inserted before `TEST_REG`, which is why `TEST_REG` is no longer fixed. Two `static_assert`s pin the legacy IDs (`dispatch.h:359-360`).
2. `src/engine/playback.cpp:330-344`: add the name to `cmdName[]` in the same position. Missed: compile error from the `static_assert` at `:348`.
3. `src/engine/cmdStream.cpp:497-570` (argument-reading switch: one-byte commands `:360-515`, two-byte commands `:516-568`, e.g. `TEST_REG` at `:565`) and `src/engine/cmdStreamOps.cpp:169-229` (argument size) and `:604-665` (writer): add the command. SILENT if missed: command-stream export (`-C`) drops the arguments and logs "unimplemented command" (`cmdStreamOps.cpp:707-709`).

## 5. Known traps (things that fail silently)

### 5.1 Are `DIV_INS_*` values persisted? Yes.
- The instrument writer stores the type as ONE byte: `w->writeC(type);` then `w->writeC(0);` (`src/engine/instrument.cpp:1769-1770`). This is the data block for `.fui` files and for the instruments embedded in `.fur` songs.
- The new-format reader reads it as a 16-bit short (`instrument.cpp:3419`), the old reader as one byte (`:3542`).
- JSON instruments store it as an integer and reject `type >= DIV_INS_MAX` (`json.cpp:1169-1170`).
- Consequences for the fork:
  - A fork-only instrument type is as risky as a chip ID: upstream numbers its types sequentially (the enum carries the warning "before adding new instrument types to this struct, please ask me first. absolutely zero support granted to conflicting formats", `instrument.h:33-35`). If the fork takes 68 and upstream later uses 68 for something else, every saved fork instrument is misread by upstream and, after a merge, by the fork.
  - The `0x1000` trick does NOT work for instruments: the type is one byte on write, so it must be below 256. The `insTypes[]` table and the `GUI_COLOR_INSTR_*` enum are also dense arrays indexed by type, so a sparse high value (for example 200) needs 130 padding rows and 130 color entries.
  - So: use `DIV_INS_STD`. This also means no `papers/newIns.md` change, no `furIcons.h`, no `insEdit.cpp`, no `guiConst.cpp:146` row, no color entry.

### 5.2 Other traps
- Missing `case` in `dispatchContainer.cpp` -> the song plays on the Dummy chip with a log warning only (`:802-805`). Always grep the render log for "dummy platform".
- Missing `notifyInsDeletion` override -> `abort()` when the user deletes an instrument (`abstract.cpp:187-190`).
- Missing `std.setEngine(parent)` in `reset()`, `getChanMacroInt()`, or `std.next()` in `tick()` -> macros silently do nothing.
- `getOscBuffer()` not overridden or `oscBuf[i]->setRate(rate)` not called -> empty or wrongly timed oscilloscope; no error.
- `rate` must be the native rate your `acquire()` produces. A wrong `rate` gives the right notes at the wrong pitch.
- `DIV_SYSTEM_MAX` / `DIV_INS_MAX` size these arrays automatically (`sysDef.cpp:28`, `engine.h:872`, `exportDef.cpp:35-56`, `song.cpp:976`, `guiConst.cpp:146`). `sysDefs` has `MAX+1` slots; no manual change needed for the system array. For instruments, only `insTypes[]` and the color enum are manual (4.4).
- ROM export filters (`src/engine/exportDef.cpp:80-141`) list specific systems (Amiga, TIA, POKEY, PC Speaker, ...); a new chip is simply not offered a ROM export. `src/engine/export/grub.cpp:35` and `ipod.cpp:35` check for PC Speaker only. No change needed.
- VGM export (`src/engine/vgmOps.cpp:514,1261`) is a per-chip `case` list. A chip with no case is skipped, and a song with only that chip fails with "no chip in this song can be exported to VGM" (`main.cpp:1206-1209`). Audio/WAV export is unaffected.
- `src/engine/engine.cpp:2274-2290` (`getEffectiveSampleRate`) and `src/engine/fileOps/fur.cpp:34-103`, `src/engine/sysDef.cpp:78-186` (old-format conversion) switch over specific chips; none needs the new chip.
- JSON songs contain the enum value as chip `id` (1.4). Since the Astrocade pilot, JSON export also writes `fileID` and import prefers it (`json.cpp:80`, `:1538-1545`), so fork chips in JSON survive upstream enum changes. JSON written before that, or by upstream, still uses `id` only.
- `po/*.po` files are regenerated translation catalogs; do not edit them by hand.
- Do not commit `build-gui/`, `build-cli/` (not gitignored); stage files by name.

## 6. Verification (from the Astrocade pilot)

Two checks, kept in `tools/chip-verify/<chip>/`. Copy the Astrocade ones.

1. **Core fidelity** (`fidelity.cpp`, `build.cmd`): the original core, pinned to an upstream commit in `reference/`, is compiled unmodified against a small stand-in for MAME's device framework (`shim/emu.h`). It and the port get the same random register writes, and their outputs must match sample for sample at the chip clock. This proves the port changed no emulation. It is fast (5 x 20 s of chip time in seconds). Plant a one-line bug in the port once to confirm it fails. `vcvars64.bat` prints a harmless "'vswhere.exe' is not recognized" line on every run.
2. **Driver wiring** (`wiring.py`, run with `tools/furnace-mcp/.venv/Scripts/python.exe`): renders a JSON test song through `furnace.exe` and checks:
   - each note sits on an integer period's exact frequency;
   - that period is the nearest one, or one step off (the pitch table's truncation);
   - volume steps match the chip's mixing law;
   - each effect behaves as expected: `10xx` retunes, `11xx` vibrato alternates between two periods in the right ratio, and `12xx` noise modulation scatters the pitch;
   - noise is noisy;
   - the chip ID survives a `.fur` save and reload.

   This is the check that caught the octave error. Plant a wiring bug, such as swapped volume registers or an ignored effect, to confirm it fails. Each effect needs its own segment: a check that only plays notes would pass a driver that ignores every effect.

What these do not prove: that the reference core matches real hardware. For a MAME port, the reference is MAME.

### What the pilot changed in this recipe
- The pitch-table divider (`notifyPitchTable` row): halve the chip's own divider; measure, don't reason.
- JSON chip identity: `fileID` added (5.2).
- Global chip controls (master oscillator, vibrato, modulation source) reuse existing `DIV_CMD_*` values that carry one byte (`DIV_CMD_STD_NOISE_FREQ`, `DIV_CMD_FM_LFO`, `DIV_CMD_PCE_LFO_MODE`). A new command would be appended to the enum and change the numbering `-cmdout` writes (4.5).
- Use the queue form of `rWrite` and keep `regPool` in the macro. Effects can fire between `acquire()` calls.
- Registration needed 11 files, all small. The GUI needs nothing beyond `availableSystems`, a category list and the `sysConf` no-options case when the chip uses `DIV_INS_STD`.
