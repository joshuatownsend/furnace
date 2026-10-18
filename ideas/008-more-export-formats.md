# 008 — More export formats (NSF first)

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/engine/export src/engine/export.h src/engine/export.cpp src/engine/exportDef.cpp src/main.cpp src/asm src/engine/cmdStream.cpp papers/export-tech.md src/engine/platform/nes.cpp src/engine/vgmOps.cpp`. Also run `git log --oneline f491976c9..upstream/master -- src/engine/export src/asm papers/export-tech.md` after each upstream sync: upstream is building ROM export itself.

- **Status**: BRIEF WRITTEN
- **Verdict**: Validate
- **Score**: 6/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in
- **Effort (coarse)**: M per format (a guess; the NSF pilot below is M because it needs a small replayer, not a music driver)
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Export a song to the "rip" formats that standalone players, emulators and flash carts play: NSF (NES), GBS (Game Boy), HES (PC Engine), KSS (MSX), SNDH (Atari ST) and SPC (SNES). These files hold a small program for the console's own CPU plus the music data. Players run the program.

Do one pilot format first: **NSF**, built the way SAP-R already works. Record every register write the chip makes on each frame, and pack that log behind a tiny 6502 replayer. No music driver is needed.

## Who wants this and why now

- **Upstream discussion #857**, "Other export formats" (opened 2022-01-24 by freq-mod, a collaborator). 8 upvotes, 8 comments plus 4 replies. Checked with the GitHub API on 2026-10-18.
  - The list in the post is wider than the card: NSF/NSFe/NSF2, SID, HES, AY, CMS, SNDH, GBS, SAP, KSS, SPC/SNSF, WSR and SGC. S98 and SAP are ticked as done.
  - tildearrow's first reply: "This is a very long road...". On 2026-09-19 he posted "S98 export has landed."
  - A composer (husrevv, 2025-11-03) says the gap is "causing me to lose business". They want SPC most (and MOD).
  - Another commenter (bryc) argues that a `.fur` player plugin would beat these old formats. Worth keeping in mind, but it is a different idea.
- **Musicians who want to ship a song** to a player, an emulator, a flash cart or a compilation. NSF and SPC are what chiptune sites and playlists use.
- **Why now**: idea 02 puts ROM export on the command line (see below), so a new format works from the CLI and from idea 003's MCP tools without extra work.

## What the fork already has

- **A ROM export framework** in `src/engine/export/`. An exporter is a class with `go()`, `wait()` and `getResult()` (`src/engine/export.h:58-76`). It is described by a `DivROMExportDef`: name, author, file type, extension, required chips, and a rule for how strict the chip check is (`export.h:80-109`).
- **Six exporters are registered** (`export.h:29-39`, built in `src/engine/export.cpp:29-55`, described in `src/engine/exportDef.cpp:73-145`):
  - Amiga Validation (a test, "do not use!")
  - Commander X16 ZSM, a register log for the ZSMKit, Melodius and Calliope players
  - Atari 2600 TIunA, which writes `export.asm` for an outside driver (`tiuna.cpp:612`)
  - Atari 8-bit SAP-R, a POKEY register dump (`exportDef.cpp:109-121`)
  - iPod `.tone` alarm and GRUB_INIT_TUNE, both PC Speaker
- **The register-dump route works today.** SAP-R turns on `toggleRegisterDump`, plays the song tick by tick and collects `getRegisterWrites()` (`sapr.cpp:111-147`). ZSM does the same (`zsm.cpp:597-599`).
- **The NES driver writes real APU addresses.** These are `$4000-$4017`: for example `rWrite(0x4000+i*4,...)` at `src/engine/platform/nes.cpp:306` and the DPCM setup at `nes.cpp:444-457`. Every write also reaches the dump when dumping is on (`nes.cpp:31`). The VRC6, FDS, N163 and MMC5 drivers use the same pattern (`vrc6.cpp:25`, `fds.cpp:28`, `n163.cpp:26`, `mmc5.cpp:27`).
- **The NES DPCM sample memory is available.** It is 256 KB in 16 KB banks (`nes.cpp:1005`, `nes.cpp:1017`). The VGM exporter already writes it out bank by bank (`src/engine/vgmOps.cpp:37-67`).
- **The CLI and the GUI pick up new exporters by themselves.** `-romout` chooses the exporter whose extension matches the file name (`src/main.cpp:1262-1321`; the extension match is at `:1273-1283`). `-romconf key=value` passes options (`main.cpp:755`). The GUI's ROM combo lists every registered exporter (`src/gui/exportOptions.cpp:453-458`). Per-format option widgets are optional (`exportOptions.cpp:485`).

## Where upstream is

The fork matches upstream on these paths: `git log HEAD..upstream/master` shows nothing new as of upstream `5b9c00314` (2026-10-13). Upstream is building ROM export through a different route, a **command stream plus a per-chip player**:

- A 6502 command-stream player, `src/asm/6502/stream.s` (1244 lines), and an NES test ROM, `src/asm/6502/nes/test.s`. They are built with WLA-DX (`src/asm/6502/nes/Makefile`), not by CMake.
- An SPC700 port of the same player (`src/asm/spc700/stream.s`, "early work on porting the stream player", 2026-03-20). Also "SNES: sample memory compilation" (`70b4f837b`, 2026-04-06).
- A macro compiler and instrument compilation (2026-02 to 2026-03), documented in `papers/export-tech.md`.

So when the card says "upstream expects ROM export to cover this in 0.7", the thread does not back it up: the #857 post says "planned for 0.7" only about SPC/SNSF. The evidence for wider ROM export work is the commit history above.

## Choosing the pilot

How many demo songs each format could carry, out of 481 in `demos/` (checked with `furnace -jsonout` on 2026-10-18):

| Format | Songs that fit | Notes |
|---|---|---|
| SPC | 30 (one SNES chip) | Needs a real SPC700 driver. The 64 KB of audio RAM must hold the driver, the samples and the music, so a raw log of a long song will not fit. Upstream is building this. |
| NSF | 23 (2A03, optionally with VRC6, VRC7, FDS, MMC5 or N163); 10 are 2A03 only | NSF banking gives up to 1 MB, and one header flag per expansion chip. |
| GBS | 13 (one Game Boy) | An MIT-licensed register-log engine exists: Pegmode's Deflemask GB Engine, which turns Deflemask VGMs into `.gbs`. It says it "only works with Deflemask generated .vgms". |
| HES | 11 (one PC Engine) | |
| SNDH | 11 at most (one AY-3-8910); unverified how many are clocked like an Atari ST | |

**Pick NSF.** Reasons:

1. **The player is small and ours.** Replaying a register log is a short loop: read a count, write address/value pairs, wait for the next frame. We write it, so it is GPL-2+ with no license question. I have not written or measured it; "small" is a guess until spike step 2.
2. **Most chip coverage that we can actually do.** SPC has more songs, but a log won't fit and upstream is on it. NSF has the next-largest group, and the same replayer covers all five expansion chips. They are just more addresses (spec: nesdev.org/wiki/NSF, header byte `$07B`).
3. **Size is not capped like FamiStudio's.** FamiStudio's NSF export says "approximately 28KB minus the size of the DPCM samples". NSF bank switching (`$5FF8-$5FFF`, 4 KB banks, 256 banks) lets a log grow far past that. The log size is roughly (bytes written per frame × frames). I have not measured it; spike step 3 does.
4. **DPCM comes almost free.** The sample memory is already exposed and banked in 16 KB pieces (see above). Each piece maps onto the NSF's `$C000-$FFFF` window.
5. **It is the thread's "obvious" format.** Every NSF player and most flash carts play it.

**Runner-up: GBS.** It works the same way, and Pegmode's MIT engine shows the register-log idea works on a Game Boy.

## Trade-offs and risks

- **A log is not a driver.** The game cannot change tempo, add sound effects or start at a pattern. That is fine for "ship it to a player". It is wrong for homebrew games, which is why idea 015 exists.
- **The chip-rule system can't say "NES required, expansions optional".** `DivROMExportReqPolicy` has only EXACT, ANY and LAX (`export.h:80-87`). Use ANY with `{DIV_SYSTEM_NES}`, then reject unsupported extra chips at run time, as SAP-R does with its "ignoring" warning (`sapr.cpp:43-70`).
- **One of each chip only.** NSF cannot hold two 2A03s or three VRC6s. One demo song uses 4×2A03 + 3×VRC6 + 4×OPLL + OPNA.
- **PCM mode will not survive.** Without DPCM mode, the NES driver streams samples by writing `$4011` at the audio rate with `doWrite`, which the dump never sees (`nes.cpp:79-95`). Warn, or refuse.
- **VRC7 and 5B are unverified.** In Furnace, VRC7 is an OPLL variant (`DIV_SYSTEM_VRC7`, `sysDef.h:203`) and 5B is an AY flavor. I have not checked that their dumped addresses match the NSF addresses (`$9010/$9030`, `$C000/$E000`). Leave them out of the pilot.
- **Frame rate.** The replayer runs at the NSF play rate. Songs with a custom tick rate need that rate written into the header's play-speed field (`$06E`). Odd rates may play wrong in some players.
- **No assembler at build time.** Check the replayer in as pre-assembled bytes, with its `.s` source next to it under `src/asm/6502/`. TIunA shows that the project already accepts outside drivers.
- **Upstream may ship a driver-based NSF later.** Then ours is retired. The cost stays low: one new file in `src/engine/export/` plus one line each in `export.h`, `export.cpp` and `exportDef.cpp`.
- **Docs.** `doc/2-interface/export.md:104-106` lists only TIunA, iPod and GRUB, and leaves out ZSM and SAP-R. Add NSF there when it ships.

## Open questions

1. Does Josh, or anyone he knows, want NSF specifically, or was SPC (the composer's ask) the real pull? If SPC, the answer is "wait for upstream", and this brief should say so to whoever asked.
2. How big is a register log for a typical NES demo song, raw and after simple compression?
3. Do DPCM bank switches in the dump line up with NSF banks without moving samples around?
4. Which players must work: NSFPlay, Game Music Emu (foobar2000), Mesen, a flash cart (Everdrive N8 or PowerPak)?
5. NSF, NSFe or NSF2? NSFe adds track names and lengths; NSF2 adds metadata and is backward compatible.
6. Should each subsong be its own NSF track? NSF supports many songs per file.

## Spike plan

1. **Dump one song.** Copy SAP-R's loop for the 2A03 (record writes per tick until the song loops) into a scratch exporter. Print the log size. *You'll know when* `furnace -romout out.nsf -romconf ...` writes a log file for `demos/nes/Byte-Sized Bop.fur`.
2. **Write the replayer.** It needs INIT (clear the APU, set up banks) and PLAY (write one frame of pairs, step the pointer, wrap at the loop point). Assemble it once and check in the bytes. *You'll know when* it fits in the fixed `$8000` bank, with a measured byte count.
3. **Pack the NSF.** Write the header (load, init and play addresses, play speed, bank init values, expansion bits), the replayer and the banked log. *You'll know when* NSFPlay and Mesen play the song from start to loop.
4. **Compare by ear and by file.** Render the same song with `-output` and with an NSF player's WAV export. Compare them with the idea 004 listen report. *You'll know when* the two match apart from mixing level.
5. **Add DPCM**, then VRC6, FDS, MMC5 and N163, one at a time. *You'll know when* each demo song that uses them plays right in Mesen.
6. **Measure the batch.** Export all 23 eligible demo songs. *You'll know when* you can tell Josh how many pass, the largest file size, and which chips failed.

## Decision criteria

- **Build it**: steps 3-4 pass on 2A03 songs, and most of the 23 pass by step 6. Ship as `DIV_ROM_NSF`, then try GBS the same way.
- **Reshape it**: logs are too large for long songs. Add simple compression, or keep NSF for short songs and send longer ones to idea 015's driver route.
- **Drop it**: NSF players reject the files, or upstream announces a driver-based NSF in the next release. Then wait for upstream and spend the time on something else.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\008-more-export-formats.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Run its drift check first and tell me if upstream has touched src/engine/export or src/asm since f491976c9. Scope: an NSF exporter for 2A03 songs built as a register-write log plus a small 6502 replayer, modelled on src/engine/export/sapr.cpp, picked by -romout out.nsf. Do not build beyond the spike; work on a branch. Test with demos/nes first and use load-only checks plus a listen comparison, not the full 481-song run. Ask Josh question 1 (NSF vs SPC) before step 5.
```
