# 002 — Bring the CLI up to GUI export parity

> Executor instructions: follow the steps in order and verify each one before starting the next.
> If a STOP condition triggers, stop and report. Do not improvise.
> Drift check first: `git diff --stat 5b9c00314..HEAD -- src/main.cpp src/engine/engine.cpp src/engine/engine.h doc/8-advanced/command-line.md`.
> If any in-scope file changed since planning, STOP and report the drift.

- **Status**: SELECTED
- **Verdict / Score**: Advance, 8/10
- **Lenses**: inside-out (Signal 3, surface asymmetry) / outside-in (live-research: upstream #540; repo-internal: `test/furnace-test.sh`)
- **Effort**: M
- **Planned at**: 5b9c00314 on 2026-10-15
- **Depends on**: none. Ideas 001 (JSON import) and 003 (MCP server) build on this.

## Why this matters

Furnace's command line can render audio, VGM, a command stream, ROMs and text. It cannot:
- write JSON, .fur or S98, all of which the GUI can;
- set VGM options (it hard-codes them);
- report a song's duration or loop region.

Anything that drives Furnace from outside the GUI hits these gaps: batch export scripts, and the Claude/MCP tooling planned in 003. "Good" means a script can convert any loadable file to .fur or JSON, export S98 and VGM with real options, and read a song's length, all without opening the GUI. Existing flags must keep working exactly as before.

## Current state

**Flag table**: `src/main.cpp:634-667`. Each flag is a `TAParam(shortName, name, takesValue, handler, valueName, description)` (`src/ta-utils.h:69-83`). Excerpt:

```cpp
// src/main.cpp:637
  params.push_back(TAParam("o","output",true,pOutput,"<filename>","output audio to file"));
// src/main.cpp:644-649
  params.push_back(TAParam("O","vgmout",true,pVGMOut,"<filename>","output .vgm data"));
  params.push_back(TAParam("D","direct",false,pDirect,"","set VGM export direct stream mode"));
  params.push_back(TAParam("C","cmdout",true,pCmdOut,"<filename>","output command stream"));
  params.push_back(TAParam("r","romout",true,pROMOut,"<filename|path>","export ROM file, or path for multi-file export"));
  params.push_back(TAParam("R","romconf",true,pROMConf,"<key>=<value>","set configuration parameter for ROM export"));
  params.push_back(TAParam("t","txtout",true,pTxtOut,"<filename>","export as text file"));
// src/main.cpp:660
  params.push_back(TAParam("o","outmode",true,pOutMode,"one|persys|perchan","set file output mode"));
```

**Short-flag collision.** `output` and `outmode` both use `o`. The parser takes the first match and breaks (`src/main.cpp:874-886`), so `-o` always means `output`, and `outmode` is reachable only as `-outmode`.

**Handler pattern** (`src/main.cpp:588-592`):

```cpp
TAParamResult pVGMOut(String val) {
  vgmOutName=val;
  e.setAudio(DIV_AUDIO_DUMMY);
  return TA_PARAM_SUCCESS;
}
```

**Globals**: `src/main.cpp:89-93` (`outName`, `vgmOutName`, `cmdOutName`, `romOutName`, `txtOutName`), reset at `main.cpp:744-748`. Output mode is detected at `main.cpp:916`:

```cpp
  const bool outputMode = outName!="" || vgmOutName!="" || cmdOutName!="" || romOutName!="" || txtOutName!="";
```

**Output block** (`src/main.cpp:1053-1170`). The VGM writer, which is the template for the new writers:

```cpp
    if (vgmOutName!="") {
      SafeWriter* w=e.saveVGM(NULL,true,0x171,false,vgmOutDirect);
      if (w!=NULL) {
        FILE* f=ps_fopen(vgmOutName.c_str(),"wb");
        if (f!=NULL) {
          fwrite(w->getFinalBuf(),1,w->size(),f);
          fclose(f);
        } else {
          reportError(fmt::sprintf(_("could not open file! (%s)"),strerror(errno)));
        }
        w->finish();
        delete w;
      } else {
        reportError(_("could not write VGM!"));
      }
    }
```

**Engine save calls** (`src/engine/engine.h`):

```cpp
SafeWriter* saveFur(bool notPrimary=false);                                   // :1461
SafeWriter* saveVGM(bool* sysToExport=NULL, bool loop=true, int version=0x171, bool patternHints=false, bool directStream=false, int trailingTicks=-1, bool dpcm07=false, int correctedRate=44100); // :1487
SafeWriter* saveS98(float tickRate=0.0f, bool* sysToExport=NULL, bool loop=true, int trailingTicks=-1); // :1500
SafeWriter* saveJSON(DivJSONExportOptions* options);                          // :1520, only #ifdef WITH_JSON
```

`DivJSONExportOptions` (`engine.h:219-240`) has the fields `format` (EXPORT_JSON/BSON/CBOR), `jsonPretty`, `exportMetadata`, `exportChips`, `exportOrders`, `exportPatterns`, `exportInstruments`, `exportWaves`, `exportSamples`, `exportCompatFlags` (default **false**), and `optimizePatterns`. `WITH_JSON` is ON by default (`CMakeLists.txt:129`).

**How the GUI saves .fur** (`src/gui/gui.cpp:2791-2840`): it calls `e->saveFur(false)` and writes the buffer, compressing it with zlib only when `settings.compress` is set. The loader accepts both compressed and uncompressed .fur, so an uncompressed CLI write is valid.

**`-info`** returns at `main.cpp:1019-1023`, before `e.init()`. It calls `DivEngine::dumpSongInfo()` (`engine.cpp:2669-2725`), which prints name, author, system and counts, but no timing. Timing data is in `DivSongTimestamps` (`song.h:75-104`: `totalTime` as `TimeMicros{seconds,micros}`, `totalTicks`, `totalRows`, `loopStart`/`loopEnd` {order,row}, `isLoopDefined`, `isLoopable`). It is filled by `DivEngine::calcSongTimestamps()` (`engine.cpp:206-210`) into `curSubSong->ts`.

**Conventions** (CONTRIBUTING.md):
- Two-space indent, never tabs.
- No spaces in calls or around operators except `||` and `&&`.
- `String` instead of `std::string`; `NULL` instead of `nullptr`.
- Use `snprintf`/`strncpy` with C strings.
- `default` goes last in a `switch`.
- Exemplar file: `src/main.cpp` itself.

## Commands

| Purpose | Command | Expected |
|---|---|---|
| fetch deps (once) | `git submodule update --init --recursive` | exits 0; `extern/SDL` etc. populated |
| configure (headless) | `cmake -S . -B build-cli -DBUILD_GUI=OFF -DCMAKE_BUILD_TYPE=Release` | "Generating done" |
| build | `cmake --build build-cli -j 8 --config Release` | produces `build-cli/furnace` (or `build-cli/Release/furnace.exe` with MSVC) |
| smoke | `<furnace> -help` | prints the flag list, exit 0 |
| fixture | `demos/genesis/ChocolateFactory.fur` | any multi-chip demo also works |

Call the built binary `$F` below.

## Scope

- **In**: `src/main.cpp`; `src/engine/engine.cpp` (only `dumpSongInfo`); `doc/8-advanced/command-line.md`.
- **Out**:
  - The GUI (`src/gui/*`).
  - File-format code (`fileOps/fur.cpp`, `loadFur`/`saveFur` internals).
  - `json.cpp`.
  - Adding new engine save functions.
  - Bumping any version number. CONTRIBUTING forbids it.

## Steps

0. **Baseline build.** Run the submodule, configure and build commands. **Verify**: `$F -help` prints the flags and `$F -output base.wav demos/genesis/ChocolateFactory.fur` writes a non-empty WAV. Keep `base.wav` for step 8.

1. **Fix the `-o` collision.** In the `outmode` TAParam (`main.cpp:660`), change the short name from `"o"` to `""`. The long form `-outmode` keeps working. **Verify**: rebuild; `$F -outmode persys -output x.wav <fixture>` succeeds; `$F -help` no longer lists `-o` twice.

2. **Add `-furout <filename>`.** Add a global `String furOutName;` beside the others and reset it at `main.cpp:744-748`. Add a `pFurOut` handler following `pVGMOut`, a TAParam `("","furout",true,pFurOut,"<filename>","save as .fur (uncompressed); use to convert imported modules")`, include `furOutName!=""` in `outputMode` (`main.cpp:916`), and add a writer block in the output section copying the VGM block with `e.saveFur(false)` and the error `_("could not write .fur!")`. **Verify**: `$F -furout out.fur demos/genesis/ChocolateFactory.fur` exits 0, `out.fur` is non-empty, and `$F -info out.fur` prints the same name and system as `$F -info` on the original.

3. **Add `-jsonout <filename>` and `-jsonpretty`.** Wrap everything in `#ifdef WITH_JSON`. Add a `DivJSONExportOptions jsonOpts;` global, set `exportCompatFlags=true` (round-tripping needs them), and have `-jsonpretty` set `jsonPretty=true`. The writer uses `e.saveJSON(&jsonOpts)` with the VGM block pattern. **Verify**: `$F -jsonout out.json -jsonpretty <fixture>` exits 0, and `python -c "import json;d=json.load(open('out.json'));print(sorted(d.keys()))"` prints a key list that includes `songInfo`.

4. **Add `-s98out <filename>`.** Writer: `e.saveS98(0.0f,NULL,vgmLoop,-1)`, using the loop toggle from step 5. **Verify**: exits 0, and the output starts with bytes `S98` (`head -c 3 out.s98`).

5. **VGM/S98 options.**
   - `-vgmver <hex>`: parse with `std::stoi(val,NULL,16)` in a `try` like `pLoops`. Accept only the versions the GUI offers (`src/gui/guiConst.cpp:131-139`: `0x150, 0x151, 0x160, 0x161, 0x170, 0x171, 0x172`). Copy that list into `main.cpp`; don't link GUI code into the CLI. Otherwise logE and return TA_PARAM_ERROR.
   - `-noloop`: sets `bool vgmLoop=false`, applies to VGM and S98.
   - `-vgmhints`: pattern hints.
   - Pass them into `e.saveVGM(NULL,vgmLoop,vgmVersion,vgmHints,vgmOutDirect)`. Defaults must reproduce today's call exactly: `true,0x171,false`.

   **Verify**:
   - `$F -vgmout a.vgm <fixture>` is byte-identical to a pre-change build's output. Keep a copy from step 0, or check out 5b9c00314 into another build dir.
   - `$F -vgmver 0x161 -vgmout b.vgm <fixture>` has version bytes `61 01 00 00` at offset 8 (`xxd -s 8 -l 4 b.vgm`).

6. **Duration and loop in `-info`.** In `dumpSongInfo()`, after the header printf, call `calcSongTimestamps()` and print `- duration: %d.%06ds`, `- ticks: %llu`, `- rows: %d`, `- loop: order %d row %d → order %d row %d` (or `- loop: none` when `!isLoopable`), reading `curSubSong->ts`. **Verify**: `$F -info <fixture>` prints a non-zero duration close to the length of the WAV from step 0. Compare with `ffprobe -i base.wav`: it should be within a loop's length, because `-output` renders loops.

7. **Update docs.** In `doc/8-advanced/command-line.md`:
   - Add every new flag.
   - Log level: the code default is `trace` (`src/log.cpp:30`), so the doc is right and the `-help` text is wrong. Fix the help text in `main.cpp` (corrected during execution; this plan originally had it backwards).
   - Add `-benchmark walk`, `-outformat`, `-bitrate`, `-ratemode`, `-compression`, `-audio pipe`.
   - Note that `-outmode` has no short form.

   **Verify**: every name in the TAParam table appears in the doc (`grep -o '"[a-z]*",' src/main.cpp`, then check each).

8. **Regression check.** **Verify**: `$F -output after.wav <fixture>` is byte-identical to `base.wav` (`cmp base.wav after.wav`).

## Test plan

There is no unit test framework for the CLI. The verifies above are the tests, and each must check content, not only exit status:
- The .fur round trip matches `-info`.
- The JSON parses and has `songInfo`.
- The S98 has its magic bytes.
- The VGM default output is byte-identical and the `-vgmver` header bytes are correct.
- The audio output is byte-identical (no playback regression).

## Done criteria

- [ ] `$F -help` lists `furout`, `jsonout`, `jsonpretty`, `s98out`, `vgmver`, `noloop`, `vgmhints`, and `o` appears once
- [ ] Each verify in steps 2–6 passes when re-run
- [ ] `cmp base.wav after.wav` reports no difference
- [ ] Default VGM output is byte-identical to the 5b9c00314 build
- [ ] `command-line.md` documents every flag in the TAParam table
- [ ] `git diff --stat` touches only the three in-scope files

## STOP conditions

- The step 0 baseline build fails (missing toolchain or dependencies). Report the error; do not patch CMake.
- `calcSongTimestamps()` crashes or returns zero in `-info` because the engine isn't initialised. Report it; do not move the `-info` early-return without asking.
- Any verify fails twice.
- A change seems to need edits to `fur.cpp`, `json.cpp` or GUI files.
- Drift detected at the start.

## Maintenance notes

- **Executed 2026-10-15** on branch `cli-export-parity`. All Done criteria passed. Two corrections were found during execution:
  - **Log level.** See step 7.
  - **Windows builds.** `-DBUILD_GUI=OFF` fails on Windows/MSVC (upstream bug: `main.cpp` calls `SDL_SetHint`/`SDL_Quit` without including `SDL.h` in headless builds). The default GUI build is a windowed app that prints nothing to the terminal. Build instead with the Visual Studio 2019 bundled CMake: `cmake -S . -B build-gui -G "Visual Studio 16 2019" -A x64 -DCONSOLE_SUBSYSTEM=ON`, then `cmake --build build-gui --config Release`. The binary is `build-gui/Release/furnace.exe`.
  - **Not verified**: module → .fur conversion, because the repo has no .mod/.xm/.dmf fixtures. .fur → .fur round trip renders byte-identical audio.

- Merge risk on upstream sync is limited to `main.cpp` flag-table hunks and one function in `engine.cpp`.
- Left out on purpose: DMF output, audio sample-rate and fade options, per-chip selection for VGM/S98, and compressed .fur output. Each is a small follow-up using the same pattern.
- Idea 003 (MCP server) will call `-furout`, `-jsonout`, `-info` and `-output`.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\002-cli-export-parity.md in full before doing anything. It is a self-contained implementation plan: follow the executor instructions at the top, run the drift check first, execute the steps in order verifying each, and stop at any STOP condition. Scope: add -furout/-jsonout/-s98out and VGM options to Furnace's CLI, add duration/loop to -info, fix the -o collision, update command-line.md. Work on a branch; when done, report against the Done criteria checklist.
```
