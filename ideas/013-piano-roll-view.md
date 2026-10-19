# 013 — Piano roll or DAW-style pattern view

> Brief for a design spike. Investigate and prototype; do not ship.
> Drift check: `git diff --stat f491976c9..HEAD -- src/gui/pattern.cpp src/gui/piano.cpp src/gui/gui.h src/gui/gui.cpp src/gui/doAction.cpp src/gui/guiConst.cpp src/engine/pattern.h src/engine/defines.h tools/furnace-mcp/furnace_mcp/song.py`.

- **Status**: SPIKE IN PROGRESS (steps 1 and 3 done, step 2 waiting on Josh and Michael)
- **Verdict**: Validate
- **Score**: 4/10 (my estimate; /ideate has not scored this)
- **Lenses**: outside-in (people who arrive from DAWs)
- **Effort (coarse)**: L for an editable piano roll. S for a view outside the app, S–M for a read-only window in the app.
- **Planned at**: f491976c9 on 2026-10-18

## The idea

Show a pattern as a piano roll: time across, pitch up and down, each note a bar. Start read-only, for one channel or one pattern, so people who think in DAW terms can see a melody's shape and spot wrong notes. Editing comes later, if ever.

This brief is a design spike. It ends in a go, reshape or drop decision, and the first steps cost no C++.

## Who wants this and why now

- **Upstream #2311** ("Request To Add Piano Roll Window For Selected Channel", 2024-12-27): 6 upvotes, 33 comments (9 top-level plus 24 replies; the card is right). The author struggles to spot wrong notes in a column of letters, and wants to see every tick. Most replies say a tracker should stay a tracker. One says a DAW plugin (idea 012) is the better answer.
- **Upstream #1024** ("DAW-Like Pattern Editor", 2023-03-13): 4 upvotes, no comments, one concept image. Weaker evidence than the card suggests.
- **The upstream FAQ says no**: "there are no plans for this. Furnace is a tracker, and changing the interface would involve a long and painful rewrite" (`doc/1-intro/faq.md:41–43`). So this lives in the fork only.
- **Someone already built one.** The last comment on #2311 links `rednoobmusic/furnace-piano-roll` (6 stars, pushed 2026-09-19). Its description: "a somewhat useable piano roll". More below.
- **In the family:** unknown. Michael uses Furnace already, and the Lumatone briefs (018, 019) suggest he thinks in keys. Ask whether a piano roll would help him (question 1).

## What Furnace already has

- **How notes are stored.** Each pattern is `short newData[256][32]` (`src/engine/pattern.h:40`). Column 0 is the note, 1 the instrument, 2 the volume, then effect and value pairs (`src/engine/defines.h:34–38`). Note 60 is C-0; 253 is note off, 254 note release, 255 macro release; -1 is empty (`pattern.h:26–39`, `defines.h:50–53`).
- **How the pattern view finds a pattern.** `e->curPat[i].getPattern(e->curOrders->ord[i][curOrder],true)` (`src/gui/pattern.cpp:749`). The view is `drawPattern()` (`pattern.cpp:84`), 2375 lines in all. The play cursor is `oldRow` and `playOrder` (`pattern.cpp:1138`).
- **The Piano window is a keyboard, not a roll.** `drawPiano()` (`src/gui/piano.cpp:97`, 660 lines) draws keys with an ImGui draw list (`piano.cpp:380`, `:427`). Its key-drawing code is a useful reference for the pitch axis.
- **Outside the app, the fork can already read patterns.** furnace-mcp loads a song as JSON (`tools/furnace-mcp/furnace_mcp/song.py:97`) and reads pattern rows (`song.py:314`). A script can draw a piano roll from that with no change to Furnace.

## The existing piano-roll fork

`rednoobmusic/furnace-piano-roll` is 9 commits ahead of upstream and 82 behind (checked 2026-10-18). Against upstream it changes:

| File | Change |
|---|---|
| `src/gui/pianoRoll.cpp` | new, 3700 lines |
| `src/gui/pianoRoll.h` | new, 33 lines |
| `src/gui/gui.h` | +132 |
| `src/engine/engine.cpp` / `engine.h` | +39 / +15: `seekTo(order,row)`, `previewEffect`, `effectValIsValid` |
| `src/gui/gui.cpp`, `guiConst.cpp`, `CMakeLists.txt` | small |
| `src/engine/fileOps/fur.cpp` | +5: a stack fix (`DivSong` on the heap), not piano-roll specific |

It is an editor, not just a view, and it does not change the file format. It is GPL-2-or-later like Furnace, so we could borrow from it. Trying it costs nothing but a build.

## Four ways to do it

- **A. Try the existing fork.** Build `rednoobmusic/furnace-piano-roll` and have Michael and Josh use it on a real song. No code.
- **B. A view outside the app.** A furnace-mcp script (or MCP tool) draws one order as an HTML or PNG piano roll from `song.load`. Zero merge cost. Also useful for Claude and for idea 014's videos.
- **C. A read-only window in the app.** New `src/gui/pianoRoll.cpp`: for the cursor's channel, walk the rows of the current order, draw a bar from each note to the next note, off or release, and draw the playhead. Effects show as small markers. Guess: 300–500 lines.
- **D. An editable piano roll.** Port or rewrite the fork's editor. L, and the fork's 3700 lines show why.

Recommended order: A, then B to test the look cheaply, then C if people want it inside Furnace. D only if C gets real use.

## Merge cost

- **New window files are cheap; edits to `pattern.cpp` are not.** `pattern.cpp` had 19 commits this year and `gui.h` 86. Put the view in its own file.
- **A new window still touches shared files.** The Tuner window is the model. It needs about a dozen one-line edits: `gui.h:624` (window enum), `gui.h:2552` (open flag), `gui.h:3353` (draw function), `gui.cpp:1362` (default layout), `gui.cpp:5549`, `:5944` (menu), `:6180`, `:9519` and `:9704` (save open state), `:10178` (constructor), `doAction.cpp:325`, `:492`, `guiConst.cpp:669` (action name), `editControls.cpp:658`, plus `CMakeLists.txt`. These are small, but they sit in the busiest GUI files, so expect small conflicts on most upstream syncs.

## Trade-offs and risks

- **Rows are not time.** Speed, groove and tempo change how long a row lasts. Drawing one row as one unit is simple and matches the pattern view. Drawing real time needs the song's timing (`DivSongTimestamps`, `src/engine/song.h:75`). Start with rows.
- **Effects change pitch.** Arpeggio (`00xx`), slides (`01`, `02`, `03`), vibrato and detune (`E5xx`) are not in the note column. A read-only roll shows written notes, with markers where effects are. It will not show what you hear.
- **Written pitch is not heard pitch.** Some chips play a written A-4 one or two octaves up (NES, SN76489; furnace-mcp's `inspect_song` reports each chip's octave, an idea 003 follow-up). The roll should show written notes, like the pattern view.
- **Upstream won't take it.** The FAQ rules it out. Fork-only, forever.
- **Who uses it.** If Michael is happy in the tracker, this helps DAW newcomers only, and the fork has few of those.
- **Idea 003 overlap.** Claude composes through text, so it does not need a roll. B helps Claude show its work, though.

## Open questions

1. Would a piano roll help Michael? Does he struggle to spot wrong notes, or to see a melody's shape?
2. After trying the existing fork (A), what is good and what is missing?
3. Read-only or editable? Is "see it" enough, or is "draw notes with the mouse" the point?
4. One channel at a time, or all channels in colors?
5. Rows across, or real time across?
6. Inside Furnace (C), or is a view next to it (B) enough?

## Spike plan

1. **Ask question 1.** *You'll know when* you know whether anyone in the family wants this.
2. **Build and try the existing fork (A).** Build `rednoobmusic/furnace-piano-roll` with the Windows build notes, load a song of Michael's, and use its piano roll for 15 minutes. *You'll know when* you have a short list of what works and what doesn't, and whether it is stable.
3. **Make an outside-the-app view (B).** A furnace-mcp script draws one order of one channel, or all channels in colors, as an HTML page. *You'll know when* Michael or Josh says whether the look helps them read the music.
4. **If they want it in the app, prototype C** on a branch: a new `pianoRoll.cpp`, read-only, cursor channel only, with a playhead during playback. *You'll know when* it follows playback on a real song and the change outside the new file is about a dozen lines.
5. **Write up** go / reshape / drop with the effort for C and D. *You'll know when* Josh can pick one.

## Decision criteria

- **Go**: someone uses A or B and asks for it inside Furnace. Build C (S–M) as a new window file. Consider D later, borrowing from the fork.
- **Reshape**: B is enough. Ship it as a furnace-mcp tool or script, with no GUI change and no merge cost.
- **Drop**: nobody in the family wants it, or the existing fork already serves the people who do. Point them to that fork.

## Spike results so far (2026-10-19)

- **Step 1 (question 1)**: Josh says yes, for both. Wrong notes and a melody's shape are each hard to see in a column of letters. He wants all channels in colors (question 4).
- **Step 2 (try the fork)**: `rednoobmusic/furnace-piano-roll` is cloned to `C:\devurnaceurnace-piano-roll` and built there (see the build note below). Waiting for Josh and Michael's 15 minutes.
- **Step 3 (view outside the app)**: done as `furnace_mcp/roll.py`, the `piano_roll` MCP tool and `python -m furnace_mcp.roll`. One self-contained HTML page: rows across, written pitch up, a color per channel, order, bar and beat lines, effect markers, and the tracker cell on hover, with every note of the same pitch lit up. Click a channel to hide it, double-click to solo it. Checked on Evergreen (8 channels, 1739 notes) and NES Byte-Sized Bop (11 channels).
- **Seen so far**: drum channels land among the pitched parts (they have notes too), and a noise channel plots its noise setting as a pitch. Hiding them fixes both. Rows-not-time is fine for these songs.
- **Question 5 (real time)** has a cheap answer if wanted: `picture.order_starts()` already gives each order's start in seconds from the engine's own timing walk.
- **Not built, on purpose**: key detection or out-of-key highlighting for wrong notes. Ask after Josh and Michael try the page.

## Kickoff prompt

```text
Read C:\dev\furnace\furnace\ideas\013-piano-roll-view.md in full before doing anything. It is a design-spike brief: run the spike steps, answer the open questions, and report against its decision criteria. Scope: find out whether a piano-roll view helps Josh or Michael read Furnace patterns, by trying the existing rednoobmusic/furnace-piano-roll fork, then drawing a read-only piano roll outside the app with furnace-mcp. Do not build beyond the spike: no editing, and any in-app prototype goes in a new window file on a branch. Ask Josh question 1 before step 2.
```
