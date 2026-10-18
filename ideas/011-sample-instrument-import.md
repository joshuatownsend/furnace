# 011 — Sample and instrument import (.fti, .bti, more formats)

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/engine/fileOpsIns.cpp src/engine/fileOps/ftm.cpp src/engine/fileOpsSample.cpp src/gui/gui.cpp doc/2-interface/formats.md`.

- **Status**: Brief written
- **Verdict**: Validate
- **Score**: 5/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in (upstream requests); Josh does not need it himself
- **Effort (coarse)**: M for the whole list; S for `.fti` alone
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Load more instrument and sample file types, one format at a time. Start with FamiTracker instruments (`.fti`), then BambooTracker instruments (`.bti`). Each loader is a new reader that turns the file into a normal Furnace instrument. No change to the `.fur` format.

## Who wants this and why now

- **Upstream #859** ("More instrument formats support", 2022, Suggestions). freq-mod's checklist is mostly done. Still open: `.bti`, `.fti`, GEMS `.pat` and `.bnk`, TriloTracker `.wa`, BambooTracker banks `.btb`, and `.gin`. The one named user is **mrparn**: "FTI would be interesting to me, particularly VRC7 instruments. I have a big bank of VRC7 FTI instruments which I'd like to use."
- **Upstream #1921** ("Support for 4 bit wav file import/export", 7 upvotes, the most of the three). A commenter adds: let the user pick low or high nibble first.
- **Upstream #2174** (4 upvotes): SFZ, SF2, SF3, SFOGG, ITI and DLS. Soundfonts belong to idea 16, which pairs with this one.
- **Why now**: idea 005 just merged (`7447298d4`, #12). Its `detect_sample_pitch` and `tune_sample` MCP tools can tune 8- and 16-bit samples that a new loader brings in, such as SFZ and SF2 samples (idea 16). They do **not** cover `.fti` DPCM samples: those load as 1-bit DPCM (`ftm.cpp:2008`), which the tools cannot read.

## What Furnace already has

### The `.fti` and `.bti` gap is real (the card is right)

- The loader knows both extensions (`fileOpsIns.cpp:2019-2022`), but the cases are empty: `case DIV_INSFORMAT_FTI: // TODO` and `case DIV_INSFORMAT_BTI: // TODO` (`fileOpsIns.cpp:2066-2069`).
- The Load Instrument dialog does not list `*.fti` or `*.bti` (`gui.cpp:2488-2505`). You only reach them through "all files". `doc/2-interface/formats.md:109-125` does not list them either.
- **A small bug on the way:** `instrumentFromFile` clears `warnings` (`fileOpsIns.cpp:1876`) but never clears `lastError`, and the empty TODO cases set no error. So opening an `.fti` today shows "cannot load instrument!" with an empty message or the text of an older, unrelated failure (`gui.cpp:6829`, `:6848`).

### Instrument formats that already load

`.fui` and `.dmp` (load and save); `.tfi`, `.vgi`, `.eif`, `.s3i`, `.sbi`, `.opli`, `.opni`, `.y12`, `.bnk` (AdLib), `.ff`, `.gyb`, `.opm`, `.wopl`, `.wopn` (load only). Loaders are in `fileOpsIns.cpp:93-1709`; the dispatch is at `:2000-2103`. `.s3i` with PCM samples is refused (`:597`).

### FamiTracker conversion code already exists

- The `.ftm` module importer (`src/engine/fileOps/ftm.cpp`) already turns every FamiTracker instrument type into a Furnace one: 2A03 → NES, VRC6, VRC7 → OPLL, FDS, N163, 5B → AY, and 6581 → C64 (`ftm.cpp:945-967`). It also maps FamiTracker sequences to Furnace macros (`copyMacro`, `ftm.cpp:278`) and reads DPCM note assignments (`:984-1010`).
- Its header says the borrowed parts come from FamiTracker under GPLv2+, so they are safe to reuse.
- **What differs in `.fti`**: a module keeps sequences in a separate `SEQUENCES` block and the instrument points to them by index. An `.fti` stores its sequences inline, right after the type and name. 2A03 `.fti` files also embed their DPCM samples. So this is a new reader that feeds the existing conversion code. It is not a copy and paste.

### Sample formats

- **libsndfile** loads WAV, AIFF, AU, CAF, IFF/8SVX, VOC, W64, RF64, SD2, SDS, XI (sample only) and more (`fileOpsSample.cpp:27`, list in `formats.md:136-178`). Loop points and root note come from the file's instrument chunk when present (`fileOpsSample.cpp:402-424`).
- **Custom loaders**: `.dmc`, `.brr` (`fileOpsSample.cpp:168-240`), and the PMD/FMP banks `.ppc .pps .pvi .pdx .pzi .p86 .p` (`:64-150`).
- **Raw import** has many depths, including 4-bit with a nibble-swap option (`sampleFromFileRaw`, `fileOpsSample.cpp:435`, 4-bit at `:528` and `:640`; dialog at `gui.cpp:8129-8169`). So most of #1921 already works through raw import. What is missing is 4-bit audio **inside a WAV file**, and 4-bit export. libsndfile has no 4-bit linear PCM mode, so that needs its own small reader.
- **Docs promise more than this build gives.** `formats.md` lists FLAC, OGG/Opus and MP3. The fork's own build has them switched off (`ENABLE_EXTERNAL_LIBS=OFF`, `ENABLE_MPEG=OFF` in `build-gui/CMakeCache.txt`; wired at `CMakeLists.txt:347-348`). Worth checking before telling anyone those load.

### Per-file warnings mostly exist

The card calls per-file warnings a separate parked item. That gap is smaller than it says. When you open several files at once, the GUI already collects one line per failed file, for instruments (`gui.cpp:6818-6850`) and for samples (`gui.cpp:6702-6730`). Sample loads report errors but not warnings. A bank with several instruments already gets the "which ones to load?" picker (`gui.cpp:6852`).

## Why this project, and why it is cheap

- `fileOpsIns.cpp` is almost untouched upstream: 0 commits in 90 days, 1 in a year. A new reader there costs nearly nothing on upstream syncs.
- The other edits are one line each: the dialog filter (`gui.cpp:2488`, a busy file with 186 commits in a year, but a one-line change is easy to re-apply) and `formats.md`.
- The `.fti` dispatch stub is already there. The conversion to Furnace instruments already exists in `ftm.cpp`.
- Upstream would likely take it. It closes two ticks on #859. A clean upstream PR would remove the fork's merge cost entirely.

## Format notes

### `.fti` (FamiTracker instrument)

- Header: ASCII `FTI` then a 3-character version (writers save `2.4`; Dn-FamiTracker reads up to 2.5). Then 1 byte type (1 = 2A03, 2 = VRC6, 3 = VRC7, 4 = FDS, 5 = N163, 6 = 5B; 0 means 2A03), a 4-byte name length, and the name.
- Then the per-type data. For sequence types: a count, and per sequence an enabled flag, then length, loop point, release point, setting and values. 2A03 adds DPCM note assignments and then the DPCM samples themselves (index, name, size, data). VRC7 holds a patch number and 8 custom registers. FDS holds a 64-step wave, a 32-step modulation table, and three sequences. N163 adds wave size, position and wave data.
- **Licensing**: Dn-FamiTracker is **GPLv3+** (`LICENSE.md`). Furnace is GPL-2.0-or-later, so we must not copy Dn code. Use it only to learn the layout. Write our reader from scratch on top of `ftm.cpp`'s converters. The same goes for 0CC-FamiTracker: reading is fine, but check its license before copying anything.

### `.bti` (BambooTracker instrument)

- Header `BambooTrackerIst`, then an `INSTRMNT` block (name and kind: 0 FM, 1 SSG, 2 ADPCM, 3 drumkit), then `INSTPROP` with the FM parameters, envelopes and sequences. ADPCM instruments carry sample data.
- BambooTracker's own reader (`BambooTracker/io/bti_io.cpp`) is 2680 lines. Its file header is MIT-style, which is fine for GPL-2+.
- Harder than `.fti`: no converter for BambooTracker sequences exists in Furnace yet (there is no `.btm` module importer). FM maps onto Furnace's OPNA instrument; SSG maps onto AY macros.

### The rest of #859

GEMS `.pat`/`.bnk`, TriloTracker `.wa`, `.btb` and `.gin` have no named user. Ask before building any of them.

## Trade-offs and risks

- **Few users per format.** Each format is a small audience. That is why this is Validate, not Advance.
- **Lossy conversion.** Newer FamiTracker forks add features (for example 0CC's arpeggio schemes, which I did not find handled in `ftm.cpp`), and BambooTracker's sequence types may not map one to one onto Furnace macros. Say what was dropped in a warning, not silently.
- **Embedded samples.** `.fti` DPCM samples and `.bti` ADPCM samples become new song samples. The loader must use the `loadAssets` path (`instrumentFromFile(path,true,...)`) so they land correctly, and the sample count limit applies.
- **No test files in the repo.** We need real `.fti` and `.bti` files, ideally mrparn's kind of VRC7 bank, plus files saved by both old (2.4) and Dn (2.5) FamiTracker.
- **Licensing slip.** The easiest reference code (Dn-FamiTracker) is GPLv3+. Copying it by habit would be a real problem.

## Open questions

1. Is `.fti` enough for a first pass, or does Josh want `.bti` in the same PR?
2. Should we aim this at upstream as a PR (removes merge cost), or keep it in the fork?
3. Is the 4-bit WAV part of #1921 worth a reader, given raw import already handles 4-bit with nibble swap?
4. Where do we get test files? FamiTracker forums and instrument packs have many `.fti` banks; we need a license-clean set for the repo, or keep them out of git.
5. Should the stale `lastError` bug be fixed on its own first (a one-line fix that upstream would take)?

## Spike plan

1. **Collect test files** (no code). At least one `.fti` of each type (2A03 with DPCM, VRC6, VRC7, FDS, N163, 5B), saved by original FamiTracker and by 0CC or Dn-FamiTracker. Two or three `.bti` files (FM, SSG, ADPCM). *You'll know when* you have a folder of files that FamiTracker or BambooTracker opens without complaint.
2. **Dump the layout in Python** (no C++). Write a throwaway reader in the scratchpad that prints each file's header, type, name and sequences. *You'll know when* every test file parses to the last byte with nothing left over.
3. **Prototype the `.fti` reader on a branch.** Fill in the `DIV_INSFORMAT_FTI` case, reading inline sequences and reusing `ftm.cpp`'s type mapping and `copyMacro` (move them where both can call them). Add `*.fti` to the dialog filter. Set `lastError` on every failure path. *You'll know when* each test file loads, and its macros match the same instrument loaded from an `.ftm` module that uses it.
4. **Check the sound.** For each type, save a short song with the loaded instrument and render it with furnace-mcp, next to the same instrument imported from an `.ftm`. *You'll know when* the two renders match (or you can name what differs, and why).
5. **Check embedded DPCM.** Load a 2A03 `.fti` with samples. *You'll know when* the samples appear in the sample list at DPCM depth and play on their assigned notes, at the assigned pitch. (005's pitch tools don't apply here: they read 8- and 16-bit PCM only.)
6. **Size up `.bti`** (reading only). Map each `INSTPROP` field to a Furnace instrument field. *You'll know when* you have a table of what maps, what is lost, and a line count estimate.

## Decision criteria

- **Build it**: `.fti` loads all six types with matching sound, and the reader is mostly reused code. Ship `.fti` with docs and the filter line, as an upstream-friendly PR (S). Do `.bti` next only if the mapping table looks clean (M).
- **Reshape it**: `.fti` works but some types lose too much. Ship the types that convert well (VRC7 and 2A03 first, for mrparn's use case) and warn on the rest (S).
- **Drop it**: test files are hard to find, or the conversion needs its own macro engine changes. Then fix only the stale `lastError` message and stop.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\011-sample-instrument-import.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: add a FamiTracker .fti instrument reader in src/engine/fileOpsIns.cpp (the DIV_INSFORMAT_FTI case is an empty TODO), reusing the instrument conversion in src/engine/fileOps/ftm.cpp, and size up BambooTracker .bti. Do NOT copy code from Dn-FamiTracker: it is GPLv3+ and Furnace is GPL-2.0-or-later; use it only to learn the layout. Prototype on a branch; do not build beyond the spike. Ask Josh before collecting test files from the web into the repo.
```
