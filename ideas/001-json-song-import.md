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

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\001-json-song-import.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: find out whether Furnace's JSON export can be loaded back losslessly, with a prototype loader. Do not build beyond the spike; prototype work happens behind a flag or on a branch.
```
