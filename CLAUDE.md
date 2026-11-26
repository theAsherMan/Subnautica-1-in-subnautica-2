# Subnautica 1 → Subnautica 2 project

Long-term goal: render the entire Subnautica 1 map inside Subnautica 2, as a UE4SS mod. `build_idea.md` holds the project owner's notes for later — background only;
do not start work from it unless asked.

## Before doing anything
Read `research/00_overview.md` (state of play, paths, status legend, next steps), then `research/01_runbook.md` (edit → install → relaunch → test loop,
UE4SS Lua rules, crash rules). Consult the other `research/` files as the task needs. Do not rediscover what they already record — re-verify only when
something contradicts them or the game has been updated (check the build in `<GameDir>\version.txt` against CL-131439).

## Machine paths come from `local.config`
This repo is shared; never write a personal name or machine-specific path into tracked files. Paths are placeholders, resolved from the git-ignored
`local.config` (template `local.config.example`): `<GameDir>` = `SN2_GAME_DIR`, `<Workspace>` = `SN2_WORKSPACE` (reports, crashes, save_backups, install
bundle — outside git), `<ModkitDir>` = `SN2_MODKIT_DIR`, `<RepoDir>` = this repo. Read `local.config` to get the real values on the current machine.
If it is missing, ask the user for the paths and create it.

## Where the code lives
- Lua mods: `src/mods/<Mod>/Scripts/main.lua` (SN2BugShot = F1 bug report, SN2Tadpole = F4, SN2AutoTest + SN2Census = test-only; old SN2WorldProbe/SN2IntroProbe/SN2WorldLevel deleted 2026-11-23, recover with `git show 40820f3:src/mods/<Mod>/Scripts/main.lua`). Terrain is done by the modkit mod `SN2Terrain` (`src/modkit`); the old Lua terrain mod SN2TerrainEdit was deleted 2026-11-16 (recover with `git show e30f3d0:src/mods/SN2TerrainEdit/Scripts/main.lua`). Shell/Python tools: `src/tools/` (all source `src/tools/sn2_env.sh` for paths).
  `src/tools/bin`, `downloads`, `sn2_packaged_files.txt` are gitignored. Code map: `research/07_mods_reference.md`.
- Launch: `bash src/tools/launch_game.sh` (adds `-OverridePlayerStart=Shallows` = intro skipped, empty hotbar; no mod involved).
- Install: `bash src/tools/install_mod.sh <Mod>`. UE4SS reads Lua only at game launch — a full quit + relaunch is required
  (`src/tools/relaunch_on_exit.sh` in the background, then ask the tester to quit). Save backup: `bash src/tools/backup_saves.sh`.
- Watch results with the Monitor tool on `bash src/tools/watch_log.sh`; re-arm it after expiry and after any session restart.
- SN1 vs SN2 comparison samples: `samples/<biome>/<shot>/{SN1,SN2}/` (picture + info.json each). When the user says **"use the samples"**, follow
  `samples/README.md` step by step (take the prescribed SN2 photos with one autotest run, `src/tools/samples.py` import + analyze, write each
  `analysis.md`, record the result in `research/`). New SN1 references come only from `src/tools/sn1_live.py capture` in the user's own SN1 session.
- Modkit (Unreal editor) work: `src/modkit/` — editor Python scripts in `scripts/`, runner `tools/ue_run.py` (runs them inside the open editor),
  `tools/cook_install.sh <Mod> <ChunkId>`, `tools/launch_editor.sh` (opens the editor; use it instead of double-clicking `Launch-Editor.cmd`), editor add-on source `plugins/SN2GraphTools` (copied into the modkit project). See `research/08_modkit_setup.md`.

## Parallel sessions: one heavy job at a time
RAM allows only one of these at a time: the game, the modkit editor, a cook, Subnautica 1 (any SN1 launch, incl. `sn1_run.sh`), or the SN1 builder / terrain extractor. Several sessions may run at once, so they share the lock `bash src/tools/heavy_lock.sh`.
- This list is the single source of truth: `research/01_runbook.md` and the agent files in `.claude/agents/` point here instead of copying it. When you change it, also update `SN2_HEAVY_PROCS` in `src/tools/heavy_lock.sh` (the process-name prefixes the lock counts as heavy work), and make sure the new job's launcher script takes the lock.
- Check `heavy_lock.sh status` before planning heavy work.
- launch_game / install_mod / launch_editor / ue_run / cook_install / autotest take or require the lock themselves, and refuse with exit 4, 5 or 2 when another session holds it.
- To wait for the lock, run `heavy_lock.sh acquire <what> --wait <s>` in the background. Do not poll.
- When done: close what you started (game or editor), then run `heavy_lock.sh release`. Never `release --force` another session's lock unless the user says so.
- Install your mods right before you launch: the game folder is shared between sessions. Details: `research/01_runbook.md` "Parallel sessions".

## Working with the tester
- The tester (the person at the PC) plays and presses the in-game keys; you cannot. Give the exact key, where to be, and what should happen. Ask what is visible — the log only proves calls ran.
- Game console commands are disabled in the test save — build test actions (teleport, spawn) into the Lua mods.
- Keep tests non-destructive: in-memory changes only; run `bash src/tools/backup_saves.sh` (copies `%LOCALAPPDATA%\Subnautica2\Saved\SaveGames\` to
  `<Workspace>\save_backups\<timestamp>\`) before anything that could reach a save.
- The finished mod must not keep hidden Subnautica 2 terrain in RAM — prefer destroy / never-load over hide.

## Keep the research log current (required)
The `research/` folder is the project's memory between sessions. Update it **as you go, in the same turn as the finding**, not at the end:
- New fact, recipe, class/property name, path, signature or gotcha → add it to the matching file (`02` world systems, `03` terrain, `04` features,
  `05` console, `06` assets, `07` mod code, `01` process/tooling). Create a new numbered file only for a genuinely new area (e.g. SN1 file formats),
  and list it in the `00_overview.md` file table.
- Every claim carries a status: **VERIFIED (date)** = seen in game, **LOGGED (date)** = log says it ran but effect unconfirmed, **UNTESTED**, **FAILED (date)** with the reason.
  Only upgrade a status with new evidence; never mark something VERIFIED on log output alone.
- Failures and dead ends are worth recording (what was tried, the exact error text, why it failed) so they are not retried blindly.
- **Condense once solved.** While a problem is open, keep the full working notes. When it is solved, or an approach is replaced:
  - Rewrite its section as the current recipe or state, with statuses.
  - Shorten each failed attempt to one line in a "Dead ends" list: date, what was tried, exact error or symptom, why it failed (keep **FAILED (date)**).
  - Delete run-by-run narratives, superseded plans and "Update:" / "superseded by" chains. Keep a run ID only where it is the evidence for a current claim.
  - Keep section headings that other files link to, or update those links.
  - Removed text stays in git history; when it may still help, add a pointer such as `git show <commit>:research/<file>`.
- When a test changes what works, update the "State of play" table and "Next steps" in `00_overview.md`.
- Write for the implementer: exact paths, class/function names, signatures, code snippets, numbers. No narrative for the tester.
- Raw dumps go to `<Workspace>\reports\`; crash dumps to `<Workspace>\crashes\` (record cause + rule in `01_runbook.md`).
