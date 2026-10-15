# Ideate run — Furnace (personal fork) — 2026-10-15

- **Repo**: C:\dev\furnace\furnace (fork joshuatownsend/furnace, zero divergence from tildearrow/furnace)
- **Run SHA**: 5b9c00314
- **Mode**: quick (plus upstream issue/discussion recon)
- **Fork goal (maintainer)**: personal fork — upstream acceptance doesn't matter

## Evidence sources

| Source | Type | Status |
|---|---|---|
| Inside-out signal mining (5 signals, 15 findings) | repo-internal | delivered (subagent), strongest citations re-verified by hand |
| Upstream Discussions (344 Suggestions) + Issues | live-research | delivered (subagent) |
| Session transcripts | transcript | delivered, zero result: only this session exists under ~/.claude/projects/C--dev-furnace-furnace — no prior sessions to mine |
| Maintainer interview | interview | 1 of 3 answered. Q3: "drive music creation and chip creation/tuning through Claude with API/MCP". Q1, Q2 skipped |

Key verified facts:
- `src/engine/fileOps/json.cpp:32` `saveJSON` exists (added 2026-07/08, `WITH_JSON` on by default); no `loadJSON` anywhere; no CLI flag for JSON.
- `src/main.cpp:634-667` CLI flags: audio render (-output, formats), VGM, cmdstream, ROM, text, -info, console mode. `main.cpp:1071` hard-codes VGM options. `-o` collides between output/outmode (`main.cpp:637`,`660`).
- `src/engine/engine.h:2172` `synchronized()`, `engine.h:1948` `noteOn()`, `engine.h:1528` `saveAudio()` — engine APIs a controller could use.
- `src/gui/tuner.cpp:37-59` FFTW pitch detector (live output only). nlohmann/json and fftw are bundled in extern/.
- `extern/asio` = Steinberg ASIO audio SDK (not networking). No socket/HTTP library in tree. Submodules not checked out locally.
- Upstream CONTRIBUTING.md discourages AI-written code; maintainer called a "sound chip creator" out of scope (#1746).

## Personas

**P1 — Josh, composing through Claude** (LOW-CONFIDENCE, interview-only). Grounded line: wants to "drive music creation and chip creation/tuning through Claude with API/MCP". Today / weekly ritual / frustration: *not evidenced* — interview Q1/Q2 skipped, no transcripts, no fork commits. Reading of "chip creation/tuning" assumed to be instrument/patch design and sample tuning, not writing new chip emulators.

**P2 — The DAW refugee.** Today: works in a DAW, trying Furnace, blocked by tracker workflow. Ritual: composes in DAW, wants to move. Frustration: "As a DAW user for 20+ years, I'm looking to jump ship ... but ... being held back" (#2480); "I really struggle with tracker" (#2311); DAW plugin request (#1804, 13u, top suggestion).

**P3 — The homebrew / batch exporter.** Today: renders and exports many songs via scripts (`test/furnace-test.sh:26` loops `-output`), reads `papers/export-tech.md`. Ritual: export → test on target. Frustration: CLI can't do what GUI export can (`main.cpp:1071`), "a big waste of time having to export every single channel" (#1888), CLI error feedback (#540).

**P4 — Module importer / cover arranger** (LOW-CONFIDENCE). Imports MOD/XM/IT/FTM and fixes them up. Frustration: import accuracy knowingly limited (won't-fix #2644, #2646), only a first-time generic popup (`gui.cpp:2998-3010`); copying between OpenMPT and Furnace (#1029).

## Portfolio

| # | Idea | Verdict | Score | Lenses | Persona | Evidence | Effort | Build |
|---|------|---------|-------|--------|---------|----------|--------|-------|
| 1 | Load songs from JSON (round-trip the existing JSON export) | Advance | 8/10 | both | P1, P3 | `json.cpp:32` saveJSON exists, no loader; interview Q3 needs a write path | M | natural-fit |
| 2 | Bring CLI to parity with GUI export (JSON/.fur/S98 out, audio+VGM options, richer `-info`) | Advance | 8/10 | both | P3, P1 | `main.cpp:1071` hard-coded VGM; `test/furnace-test.sh:26`; #540 | M | natural-fit |
| 3 | Claude-driven composing & instrument tuning via an MCP server wrapping the CLI | Validate | 7/10 | both | P1 | interview Q3; CLI render `main.cpp:637`; JSON in/out (#1,#2) | M (after 1+2) | new-ground (natural-fit once 1+2 exist) |
| 4 | Headless "listen" report: render a snippet and return pitch/spectrum/loudness as text | Validate | 7/10 | both | P1 | `tuner.cpp:37-59` FFT only on live output; fftw bundled; interview "tuning" | M | natural-fit |
| 5 | Auto-detect a sample's pitch and set its center rate | Validate | 6/10 | inside-out | P1 (if "tuning" = samples), P4 | `doc/9-guides/tuning-samples.md:10-12` manual math; `tuner.cpp` | S–M | natural-fit |
| 6 | Write new chip emulators with Claude: a repeatable chip-addition recipe, proven on one pilot chip | Validate | 8/10 | both | P1 | Mid-run maintainer request; Supervision add = 16 files/916 lines (9d279cead); Dummy System template `sysDef.cpp:2824`; Klattsch invented chip (390137b35); chips are the largest upstream request theme (#873) | M–L | natural-fit (pattern exists) |

Chain: #1 + #2 are standalone wins AND the write/render substrate for #3; #4 is the feedback loop #3 needs for tuning. #3 is the maintainer's stated goal, but its recurring trigger is unevidenced (see kill answers).

### Scoring detail (Pain / Fit / Feas / Backing / Diff)
1. 2/2/1/2/1 = 8 — backing: repo-internal + interview. Feas 1: unknown whether export is lossless enough to rebuild a song (systems, compat flags, sample data).
2. 2/2/2/2/0 = 8 — backing: repo-internal + live-research.
3. 2/2/0/2/1 = 7 — Feas 0 on its own (new-ground until #1+#2 exist). Validate: no recurring job evidenced; whether Claude can produce good results without hearing is open.
4. 2/2/1/2/0 = 7 — differentiation 0 on its own; value is as #3's feedback loop.
5. 1/2/2/1/0 = 6 — repo-internal doc friction only.
6. 2/2/1/2/1 = 8 band, verdict Validate (disagreement recorded): which pilot chip, what reference to verify accuracy against, and how to allocate fork-only system IDs without colliding with upstream are all open.

### Kill-question answers for survivors

**#1 JSON import.** (1) P1's every Claude edit session; P3 when scripting song generation. (2) Newly possible: edit a song outside the GUI and load it back. (3) Leverage: reuses in-tree serializers + nlohmann. (4) JSON export landed 2026-07/08 — the asymmetry is fresh; it's the cheapest write path for the fork's stated goal. (5) Strengthens JSON export; no duplicate (text export isn't importable either). (6) Smallest: load what saveJSON emits with exportMetadata on; refuse partial files. Risk: export may omit fields. (7) Beats sibling "teach the MCP to write .fur binary" — .fur is complex, compatibility-sensitive (CONTRIBUTING). (8) Displaces CLI parity time; they're complementary.

**#2 CLI parity.** (1) P3 every batch render; P1 every MCP render/inspect call. (2) Scriptable export with real options; duration/loop/memory without GUI. (3) Wires existing engine calls. (4) `main.cpp` evidence + test script + #540. (5) Extends CLI; folds in richer `-info` (merged candidate). (6) New flags only; additive, low merge burden. (7) Beats "MCP calls GUI" — GUI isn't scriptable. (8) Low cost.

**#3 MCP server.** (1) **Gap: no recurring trigger evidenced** — maintainer stated it as the killer feature but skipped workflow/frustration questions. (2) Newly possible: describe music/patches in words, get a .fur back. (3) Leverage: Claude + Furnace's 100+ chip engines + CLI render. (4) The fork's stated purpose. (5) No existing equivalent. (6) Smallest: external process (Python/Node) exposing tools read_song / write_song / render / export, shelling to the CLI. In-process live control needs a new networking dependency (parked as sibling). (7) Beats in-process live server on buildability and merge burden. (8) Cost: depends on #1+#2 first.

**#4 Listen report.** (1) Every tuning iteration in #3. (2) Lets Claude check what it made sounds as intended (pitch, brightness, envelope). (3) Reuses tuner FFT + CLI render. (4) "tuning" in Q3. (5) Extends tuner/spectrum to headless. (6) CLI flag or MCP-side analysis of rendered WAV. Open: are text metrics enough to tune FM patches? (7) Beats "Claude listens to audio" — not available. (8) Only useful with #3.

**#5 Sample pitch detect.** (1) Whenever a recorded sample is loaded. (2) Removes manual semitone math. (3) Reuses tuner FFT. (4) Doc documents the workaround. (5) Extends sample editor. (6) One button. (7) Beats external calculator. (8) Small. Open: does Josh load samples at all?

**#6 Chip emulators (added mid-run at maintainer request; previously killed as 'new chips cluster').** (1) Josh, each time he wants a chip Furnace lacks; frequency unevidenced. (2) Newly possible: chips Furnace doesn't have, including invented ones (Klattsch precedent). (3) Leverage: a fixed ~16-file touchpoint pattern + Dummy System template + existing MAME/other cores to port — Claude follows a recipe rather than inventing architecture. (4) Personal fork lifts upstream's 'chip creator out of scope' (#1746) objection; upstream chip demand is the largest theme by count. (5) Extends the chip catalog; distinct from #3 (patch design on existing chips). (6) Smallest: one pilot chip ported from an existing open-source core, plus a checklist and a render-compare test. Risks: system ID byte is saved in .fur (Supervision = 0xe3, upstream allocations reach 0xe7) — fork chips need a reserved ID range and will make files upstream can't open; accuracy without hardware. (7) Beats 'write emulator from datasheet' (higher accuracy risk) and 'generic chip creator UI' (rejected upstream, L). (8) Competes with #1–#4 for time; independent of them.

## Parked ledger
| Idea | Reason | Closest survivor |
|---|---|---|
| In-process live control server (MCP inside running GUI) | needs new networking dep (`extern/asio` is audio-only), touches hot `gui.cpp`; spike #3 decides if live is needed | #3 |
| Load FamiTracker .fti / BambooTracker .bti instruments (`fileOpsIns.cpp:2066`) | strong gap (#859, #2174) but value is to NES/OPNA users; no evidence Josh composes for those; upstream won't take AI code | #1 |
| Per-file import warnings for MOD/S3M/XM/IT/FC | real gap (0 addWarning calls vs 16 in dmf.cpp) but benefits importers, not evidenced for Josh | #2 |
| Audio effects/DSP layer (`engine.h:864`) | L effort, changes .fur format in a fork (incompatible files), upstream already building it | — |
| Wavetable reorder doesn't update references (`engine.cpp:3326`) | it's a bug, best reported upstream; not a fork feature | — |
| Instrument compile for GB etc. (`instrument.cpp:536`) | niche driver-author need; no link to Josh | #2 |
| Bundled instrument browser (1,246 files hidden) | polish for casual users; better exposed to Claude as a catalog tool inside #3 | #3 |
| DAW plugin (VST/CLAP) (#1804, 13u) | top upstream demand but L, new-ground, no link to Josh | #3 |
| Piano roll (#2311) | L GUI work; #3 partly substitutes (compose without the grid) | #3 |

## Killed ledger
| Idea | Reason | Closest survivor |
|---|---|---|
| Richer `-info` standalone | merged into #2 | #2 |
| Finish auto-clone (TODO.md) | upstream's own 0.7 item; fork version would collide on next sync | — |
| CSM macros (TODO.md) | upstream's own 0.7 item; same collision | — |
| Preview samples/wavetables in file picker | polish/convenience only | — |
| VGM/NSF/SID import | maintainer rejected NSF/SID (#1689); register-log→patterns is huge | — |
| Shared register-dump export helper | internal refactor, no user value to the fork | #2 |
| Repo hygiene (stale `vgmOps_after_surgery.cpp`, "TODO: elaborate" errors) | chores, not features — observation only | — |
| Document S98/JSON exports | docs belong upstream | #2 |

## Disclosures
- Idea #6 was added mid-run on the maintainer's request after the portfolio was presented; it reverses the earlier kill of the new-chips cluster.
- No prior Claude Code transcripts exist for this repo; transcript source returned zero.
- Interview: 1 of 3 answered; P1 is thin and LOW-CONFIDENCE; "chip creation/tuning" reading is an assumption.
- Live research limited to upstream GitHub Suggestions/Issues (quick mode; no web search). Upstream demand is shallow (top suggestion 13 upvotes).
- Personal-fork trade-off: every change adds merge burden on upstream sync — additive changes (new files, new CLI flags) are cheaper than edits to hot files (gui.cpp, insEdit.cpp).
- Build note: submodules (e.g. extern/asio) not checked out locally; building the fork needs `git submodule update --init` first.
- Policy observation: `fileOps/midi.cpp:20-30` contains an AI-use disclosure; no prompt injection found anywhere.
