# START HERE — Subnautica 2 world modding: implementer notes

Audience: the implementer (Claude) picking this project up in a fresh session. Read this file, then `research/process/README.md`, before touching anything.
Everything here was established by running code in the real game on 2026-11-14/15 unless marked otherwise.

## Project goal
Render the entire Subnautica 1 map inside Subnautica 2 (long-term; see `../build_idea.md`, which holds the project owner's notes for later — do not act on
items in it unless asked). Current phase: **proving and building the terrain toolchain** inside Subnautica 2.

## Status legend used in all notes
- **VERIFIED (date)** — seen working in game (visually by the tester and/or in the log).
- **LOGGED (date)** — the log says it succeeded, but nobody confirmed the visible/physical effect.
- **UNTESTED** — derived from class/property dumps or reasoning; never executed.
- **FAILED (date)** — tried, did not work; reason recorded.
Never upgrade a claim's status without new evidence. (A claim was once marked VERIFIED that was only LOGGED — landscape removal — and had to be corrected.)

## Where things are
| What | Path |
|---|---|
| Game install | `<GameDir>\` (Steam appid 1962700) |
| UE4SS + live mods | `<GameDir>\Subnautica2\Binaries\Win64\ue4ss\` (`Mods\`, `UE4SS.log`, `UE4SS-settings.ini`) |
| Per-machine paths | `../local.config` (git-ignored; template `../local.config.example`): `SN2_GAME_DIR` = `<GameDir>`, `SN2_WORKSPACE` = `<Workspace>`, `SN2_MODKIT_DIR` = `<ModkitDir>`, `SN1_GAME_DIR` = `<SN1Dir>` (Subnautica 1 install, read-only source data) |
| **Mod source (edit here)** | `src\mods\<Mod>\Scripts\main.lua` (+ `data\`) |
| Drop-in install bundle | `<Workspace>\install\Win64\` (contents → game `Binaries\Win64\`) |
| Helper scripts / tools | `src\tools\` (`sn2_env.sh` config loader, `install_mod.sh`, `backup_saves.sh`, `relaunch_on_exit.sh`, `watch_log.sh`, `mdmp.py`, `make_test_heightfield.py`, `heightfield_to_unreal.py`; gitignored: `bin\repak.exe`, `bin\retoc.exe`, `sn2_packaged_files.txt`) |
| Modkit side (editor scripts, runner, cook/install, editor add-on source) | `src\modkit\` — see `research/code/modkit_setup.md` |
| Raw dumps (probe output) | `<Workspace>\reports\` (`probe_report.txt`, `probe_values.txt`, `probe_deep.txt` 10k lines, `exec_functions.txt`, `memory_log.csv`) |
| Crash dumps / save backups | `<Workspace>\crashes\`, `<Workspace>\save_backups\<timestamp>\` |
| Game log | `%LOCALAPPDATA%\Subnautica2\Saved\Logs\Subnautica2.log`; saves in `...\Saved\SaveGames\` |
| Human-facing setup guide (accounts, installs, step order, cache redirects) | `../README.md` — keep it in sync when setup steps change |

## Read first

1. This file. 2. `research/status.md` (what works, what is open). 3. `research/process/core_rules.md` (the loop, the rules). Then only the folder README and topic file the task touches. The old numbered files are now short pointer stubs.

## Folder map

- [process/](process/README.md): Process and tooling. How to run things: the loop, the heavy lock, autotest, tools.
- [crashes/](crashes/README.md): Crashes. Crash investigations; the GC-watchdog crash has the most history.
- [sn2/](sn2/README.md): Subnautica 2 reference. Facts about the SN2 game, its assets and our replacement map.
- [terrain/](terrain/README.md): Terrain. SN1 terrain extraction, import and in-game checks, plus legacy Lua recipes.
- [features/](features/README.md): Features. Placing features: biome look, props, resources, vehicles, base building.
- [sn1/](sn1/README.md): Subnautica 1 reference. SN1 world files, objects, modding, runs and assets.
- [code/](code/README.md): Code maps. Where the Lua mods, the modkit and the SN1 tools live in src/.
- [status.md](status.md): current capabilities table and open next steps.

## Rules for notes

- One topic per file; soft limit 15 KB, hard limit 25 KB. A new topic is a new file plus one line in its folder README.
- Link format: `research/<folder>/<file>.md` with an optional section number or quoted heading; markdown links inside a folder README.
- Images are allowed: put them in an `img/` folder next to the note (`research/<folder>/img/<name>.png`), link them with a relative markdown link, and still say in text what the image shows (status word + date), because agents search the notes as text.
- Every claim carries a status word and a date (see the legend above).
- Run `python -I src/tools/research_lint.py` after editing notes. A Claude Code hook (`.claude/settings.json`, `src/tools/research_lint_hook.py`)
  also runs it after every Write/Edit under `research/` and reports errors in the edited file back to the agent.

## Open topics

- A topic with work left ends its heading with ` — OPEN (YYYY-MM-DD)`: em dash, then the date the topic was opened (the earliest date in its notes).
  Example: `## Pod re-attach in game — OPEN (2026-11-19)`. Work left = an unfixed bug, an UNTESTED plan still intended, PAUSED work
  (the text says PAUSED), or an open question someone means to answer.
- Tag the smallest heading that covers the open work, not the whole file.
- Every OPEN heading has exactly one line in `research/status.md` "Next steps":
  `N. <status word + date + what is left> — `research/<folder>/<file>.md` "<heading text without the tag>"`.
  Every Next steps line points at an OPEN heading. The lint checks both directions.
- Closing a topic: remove the tag, condense the section ("Condense once solved" in CLAUDE.md), delete its status.md line.
- `grep -rn "OPEN (" research/` lists everything open.- Open investigations big enough for their own files use a summary `<problem>.md` (current state, links) plus phase notes
  `<problem>_<phase>_<date>.md`, as `research/crashes/gc_watchdog.md` does.

## Splitting a file

When a note passes 15 KB:
1. Condense first: apply "Condense once solved" to anything solved.
2. Still over? Split by topic along existing `##` sections: each new file is one topic a task would open on its own.
   Never split by size or date, and never create `_part2` files.
3. Name the new file after its subject: `<area>_<topic>.md`, lowercase snake_case (e.g. `l_sn2world_water.md`).
4. Exception: open-investigation notes may be split by phase (`<problem>_<phase>_<date>.md`), with the `<problem>.md` summary listing them.
5. The original file keeps its name and its main topic, and gets a one-line "See also" pointing at the new files, so existing links still resolve.
6. Move sections intact with unchanged headings. Grep the repo for links to each moved heading and re-point them. Add the new file to the
   folder README with a one-line hook.
7. Finish with the lint at 0 errors. Nothing goes over 25 KB unless it is in the lint's `EXEMPT` list with a reason (open-investigation notes only).
