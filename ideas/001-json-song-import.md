# 001 — Load songs from JSON

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat 5b9c00314..HEAD -- src/engine/fileOps/json.cpp src/engine/fileOps/fileOpsCommon.cpp src/engine/engine.h`. If the evidence files changed materially, re-check the evidence before starting.

- **Status**: SELECTED
- **Verdict**: Advance (spike chosen first)
- **Score**: 8/10 (see ideas/README.md)
- **Lenses**: inside-out (Signal 3, export without import) / outside-in (interview)
- **Effort (coarse)**: M
- **Planned at**: 5b9c00314 on 2026-10-15

## The idea

Furnace can save a whole song as JSON but can't open one. Add a loader so a JSON file in the export's schema opens like any other song. Then a script, or Claude, can read a song as JSON, change it, and hand it back.

## Who wants this and why now

- **Josh, the fork's maintainer**, wants to "drive music creation and chip creation/tuning through Claude with API/MCP" (interview, 2026-10-15). Claude needs a text format it can write; today nothing outside the GUI can write a song.
- **Batch exporters and tool authors**: upstream #2782 asks for import/export extensibility for formats "not likely to be used by the majority".

## Why this project, why cheap

- `src/engine/fileOps/json.cpp:32` `saveJSON` already serialises song info, chips, orders, patterns, instruments, macros, waves, samples and compat flags (serializers declared at `json.cpp:24-29`). A loader mirrors a schema that already exists.
- nlohmann/json is bundled (`json.cpp:21`). Export landed in July–August 2026 (commits `dd76ff194`, `cb856f38d`, `6edfe14c5`), so the schema is fresh.
- No loader exists: `fileOpsCommon.cpp` never sniffs for JSON, and there is no `loadJSON`.

## Trade-offs and risks

- **The export may be lossy.** `exportCompatFlags` defaults to false (`engine.h:239`). Unknown whether samples, chip flags, grooves, subsongs and song-level settings are all written. A loader can't restore what the export leaves out.
- **Schema stability.** The upstream export is young and may change. A fork loader tied to it adds merge work.
- **Validation.** A hand-written or Claude-written JSON can be malformed in ways .fur never is (pattern length mismatches, out-of-range instrument indices). The loader must reject these safely, because a crash would lose user work.
- **Sibling**: having Claude emit binary .fur directly. Rejected because .fur is complex and CONTRIBUTING.md treats it as compatibility-critical.

## Open questions

1. Is a full-export JSON lossless? That is: .fur → JSON → (new loader) → .fur, then do both play byte-identically?
2. Which fields does `saveJSON` omit (compat flags off by default, grooves, subsong settings, chip flags, sample loop data)?
3. How are samples stored: base64, arrays, or omitted when large?
4. Can the loader reuse `DivSong` setup from an existing importer (e.g. `fileOps/dmf.cpp` or `fur.cpp`) for chip initialisation?
5. Should partial JSON (patterns only) be supported as a patch onto an open song, or only whole songs?
6. Where does the loader hook in: extension sniffing in `fileOpsCommon.cpp`, or an explicit CLI flag?

## Spike plan

1. **Export three demo songs** with every JSON option on, including compat flags. Use the GUI or idea 002's `-jsonout`. Cover an FM song (`demos/genesis`), a sample-heavy song (`demos/amiga`) and a multi-chip song. *You'll know when* you have three JSON files and their sizes.
2. **Inventory the schema.** Diff the JSON key tree against `DivSong` / `DivSubSong` fields in `song.h` and list every field the export omits. *You'll know when* you have a table of song fields with exported yes/no.
3. **Prototype `loadJSON` behind `#ifdef WITH_JSON`** for metadata, chips, orders and patterns only. Load one song and compare its pattern data with the original in memory or via `-txtout`. *You'll know when* text exports of the original and the JSON round trip match for orders and patterns.
4. **Extend to instruments and waves**, then render both versions with `-output` and `cmp` the WAVs. *You'll know when* the audio is byte-identical or you can name the first differing field.
5. **Malformed-input pass**: truncate one file and corrupt one index. *You'll know when* the loader returns an error instead of crashing.

## Decision criteria

- **Build it**: the round trip is byte-identical for at least two of the three songs, and the gaps are fields the export can add cheaply.
- **Reshape it**: the export is badly lossy. Build a fork-owned "complete" JSON export first, or limit import to patches applied onto a loaded .fur (patterns and instruments only), which is enough for Claude-driven editing.
- **Drop it**: the export misses core data (samples, chips) and fixing that means touching `fur.cpp` semantics.

## Spike results (2026-10-15, branch `json-import-spike`)

**Recommendation: Build it.** The decision criteria are met: every demo song now round-trips through JSON, and every gap was a field the export could add in one or two lines.

Commits (local, not pushed): `314ce8cd1` loader, `ee6ff36b2`, `02b1ef350`, `cb253af94`, `8ea9541ea` export/import field additions.

### What was built
- `DivEngine::loadJSON()` at the end of `src/engine/fileOps/json.cpp`, declared in `engine.h` under `WITH_JSON`.
- `DivEngine::load()` (`fileOpsCommon.cpp`) opens any file whose first non-blank byte is `{` as JSON. That means the CLI, drag-and-drop and command-line opening all work; no new flag is needed.
- The loader builds a separate song and only replaces the open song once everything has loaded, copying `loadFur()`'s install sequence. On any error the open song is untouched.

### Results
- **All 481 demo songs** (`demos/*/*.fur`): rendered to WAV directly and via `-jsonout` → load JSON. 478 are byte-identical.
- The other 3 are OPZ songs, and the cause is the OPZ emulator, not JSON. Their re-saved .fur files are byte-identical to the originals. Rendering the *original* "The bongos and teh base OPZx2" four times gave one odd result. Re-run one at a time, the other two match: four renders of `only_dream_opz` loaded from JSON all equal the original's audio. OPZ renders occasionally differ between runs of the same file. This is an upstream issue worth reporting separately.
- **Hand-written JSON** (what Claude would produce): a file with only `chips: [{id: 4}]` and one subsong (`patternLength`, `orderLength`, four empty `channelData` entries, `orders`, a few note rows) loads and renders with sound. No instruments, songInfo or compat flags are needed. **Gotcha for 003:** notes use Furnace's numbering, not MIDI. Note 60 is C-0 and middle C (C-4) is 108.
- **Malformed input**: 14 broken or hand-edited files (truncated, not JSON, unknown chip, wrong channel count, order out of range, huge pattern length, bad instrument type, over-long macro, short sample data, too many effect columns, wrong value types, empty object). Each is rejected with a readable error (e.g. `invalid JSON song: sub-song 0 has 6 channels but the chips have 7`), and nothing crashed. A pattern pointing at a missing instrument loads and plays, as .fur allows.
- Load + render time is the same as .fur (under a second to load).

### Answers to the open questions
1. **Lossless?** Not originally; yes after the fixes below (see results).
2. **Fields the export omitted, now added** (all affect playback): master volume; per-chip channel count; per-subsong effect divider and arp speed; FM `tremLFO`; SNES `gain`; the `arpSpeedGlobal` compat flag; the unused slots of speed and groove patterns (playback reads them); and any instrument data block that differs from default but doesn't match the instrument's type (the .fur writer keeps these; the JSON export dropped them).
   **Still not exported, not affecting playback**: legacy VGM tag strings (composer, copyright, Japanese names, etc.), wavetable `min`, sample `legacyRate`, pattern rows past the pattern length, and DSP effect storage (unused in practice). Demo songs didn't carry these, so they're untested.
3. **Samples** are stored as JSON arrays of raw bytes at the sample's current depth. This works, but the file grows about 4× per sample byte. Demo songs are 77–171 KB of JSON.
4. **Reuse**: `DivSong` defaults plus `initDefaultSystemChans()`/`recalcChans()`, and `loadFur()`'s install sequence. No importer code needed copying.
5. **Partial JSON** (patches onto an open song) was not prototyped. Whole-song import is enough for Claude-driven editing, and 003 can decide whether patches are needed.
6. **Hook**: content sniffing in `load()`. Exports with `exportCompatFlags` off still load, with a warning that playback may differ.

### Follow-ups if built
- The GUI "Open" dialog filters for song formats only; add `*.json` (untested in the GUI).
- BSON/CBOR input isn't handled (only text JSON).
- For 003: a full song is 77–171 KB, mostly 256 pattern slots per channel and sample bytes. Claude will want a compact view (or patches) rather than whole-file edits.
- The export changes add new keys (`masterVolume`, `channels`, `speedsFull`, …); older Furnace builds ignore them.
- The fixes edit lines inside upstream's `saveJSON()`, not just new code, so they may conflict when syncing with upstream.
- Content sniffing sends any file starting with `{` to the JSON loader, so a .mod whose title starts with `{` would fail instead of falling through to the MOD loader. Fix in the build phase: on a parse error, continue to the other loaders.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\001-json-song-import.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: find out whether Furnace's JSON export can be loaded back losslessly, with a prototype loader. Do not build beyond the spike; prototype work happens behind a flag or on a branch.
```
