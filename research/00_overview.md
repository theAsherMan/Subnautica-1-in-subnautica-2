# START HERE — Subnautica 2 world modding: implementer notes

Audience: the implementer (Claude) picking this project up in a fresh session. Read this file, then `01_runbook.md`, before touching anything.
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
| Per-machine paths | `../local.config` (git-ignored; template `../local.config.example`): `SN2_GAME_DIR` = `<GameDir>`, `SN2_WORKSPACE` = `<Workspace>`, `SN2_MODKIT_DIR` = `<ModkitDir>` |
| **Mod source (edit here)** | `src\mods\<Mod>\Scripts\main.lua` (+ `data\`) |
| Drop-in install bundle | `<Workspace>\install\Win64\` (contents → game `Binaries\Win64\`) |
| Helper scripts / tools | `src\tools\` (`sn2_env.sh` config loader, `install_mod.sh`, `backup_saves.sh`, `relaunch_on_exit.sh`, `watch_log.sh`, `mdmp.py`, `make_test_heightfield.py`, `heightfield_to_unreal.py`; gitignored: `bin\repak.exe`, `bin\retoc.exe`, `sn2_packaged_files.txt`) |
| Modkit side (editor scripts, runner, cook/install, editor add-on source) | `src\modkit\` — see `08_modkit_setup.md` |
| Raw dumps (probe output) | `<Workspace>\reports\` (`probe_report.txt`, `probe_values.txt`, `probe_deep.txt` 10k lines, `exec_functions.txt`, `memory_log.csv`) |
| Crash dumps / save backups | `<Workspace>\crashes\`, `<Workspace>\save_backups\<timestamp>\` |
| Game log | `%LOCALAPPDATA%\Subnautica2\Saved\Logs\Subnautica2.log`; saves in `...\Saved\SaveGames\` |
| Human-facing setup guide (accounts, installs, step order, cache redirects) | `../README.md` — keep it in sync when setup steps change |

## Files in this folder
| File | Read when |
|---|---|
| `01_runbook.md` | Always — edit/install/launch/test loop, user protocol, UE4SS Lua rules, crashes |
| `02_world_systems_reference.md` | Need a class/property name for anything in the world (zones, water, temperature, sky, audio, edge) |
| `03_creating_terrain.md` | Removing, adding or generating terrain — working recipes with code |
| `04_placing_features.md` | Spawns, heat zones, water look, music, lights, resources (mostly UNTESTED recipes) |
| `05_console_commands.md` | Dev console commands — **disabled in the test save**, keep for reference |
| `06_asset_index.md` | Where content lives (`/Game/...` paths for meshes, BPs, data assets, banks, configs) |
| `07_mods_reference.md` | Code map of the Lua mods (SN2WorldProbe; SN2TerrainEdit — deleted 2026-11-16, kept as history): sections, keys, config tables, how to extend |
| `09_intro_and_world_replacement.md` | Skipping the intro, starting in the lifepod, not loading the SN2 world at all (current phase) |
| `08_modkit_setup.md` | Modkit (cooked editor) install on `<ModkitDir>`: layout, step status, prerequisites |

## State of play (updated 2026-11-17)
| Capability | Status |
|---|---|
| UE4SS 3.0.1-953 injected, Lua mods load, game stable | VERIFIED |
| Inspect the live world (classes, properties, values, console commands) | VERIFIED (SN2WorldProbe) |
| Spawn any game static mesh at coordinates, with collision | VERIFIED |
| Remove rocks/meshes at runtime (hide or destroy) | VERIFIED |
| Remove heightmap landscape at runtime | VERIFIED (Ctrl+F2, then automatic regions) |
| Auto-clear a region on load: landscape tiles + StaticMesh/Prefab/environment BPs, destroyed + GC (memory freed) | VERIFIED (≈10.6k actors + 18–21 tiles in 300 m) |
| Custom geometry via Geometry Script `DynamicMeshActor` | VERIFIED (star prism) |
| Terrain from a data file: 160 m, 19.6k tris, 0.27 s, rendered + collidable | VERIFIED |
| One-call arbitrary mesh (`AppendBuffersToMesh`) for non-grid meshes (caves, overhangs) | FAILED from Lua (out-param error); **works from editor Python** 2026-11-16 → saved Nanite static mesh asset, see `03` |
| Modkit editor installed, game content mounted, scripted from the shell (`ue_run.py`) | VERIFIED 2026-11-16, see `08` |
| Cooked terrain mod (`SN2Terrain`: ModActor + SM_SeafloorTest, built by editor Python, packaged as pak chunk 1 in `LogicMods`) appearing in game | **VERIFIED 2026-11-16** — visible at the Lua test spot + collision (the tester); region still cleared by Lua |
| Terrain deletion done by the cooked mod instead of Lua (ModActor graph built by `src/modkit/scripts/sn2terrain_removal_graph.py`) | **VERIFIED 2026-11-16** — tester: "its all there" (ground + dressing gone, custom seafloor present); log: proxies 22 → 4 within 4 s of load with the Lua sweep disabled; ModActor self-destroys in the lobby. Lua counter logger hit `A function requiring userdata as param #1 was called without userdata` once and logged nothing (cause not found yet) |
| Never loading SN2 terrain at all (RAM requirement) | UNTESTED — design notes in `03` |
| Temperature / water-look / music / spawn-zone actors spawned from Lua | UNTESTED (properties known) |
| Asset (pak/IoStore) mods, modkit | UNTESTED |
| New **Survival** game skips the intro, empty hotbar, only the breathing adaptation, via launch argument `-OverridePlayerStart=Shallows` (`bash src/tools/launch_game.sh`; no mod) | **VERIFIED 2026-11-18** (tester: "worked perfectly. Intro skipped. hotbar empty. only pressure tolerance adaptation") — see `09`. The Lua mod SN2IntroSkip (v1–v5) was deleted |
| Never loading the SN2 world (only our crater) | NOT STARTED — options in `09`. `SN2Terrain` currently parked in `<Workspace>\disabled_mods` (not installed) |
| Lobby→`L_Main` load crash (GC watchdog, 22.8k objects) | NOT fixed: crashed again 2026-11-18 with all our Lua mods disabled, so our polling is not the cause; A/B without UE4SS pending, see runbook |
| Reading Subnautica 1 terrain files | NOT STARTED |

## Next steps (agreed direction, in order)
0. ~~Move region clearing from Lua into the ModActor graph~~ — done and verified 2026-11-16 (SN2GraphTools editor add-on builds the graph from Python); Lua terrain mod deleted.
0b. **Current phase (started 2026-11-16): replace the SN2 world.** Intro skip = DONE (`09`). Remaining: lifepod position vs our crater, then stop `L_Main` terrain loading
   entirely (options in `09`), so only the crater exists.
1. ~~Fix the arbitrary-mesh path~~ — solved via editor Python (`03`); Lua path still FAILED but no longer needed for production.
2. Extend the clearing allow-list: `/Game/Blueprints/Environment/**`, `/Game/Prototyping/Resources/CoralPads/**`, `/Game/Blueprints/Resources/BP_AcidAnemone`, `DecalActor`, `PointLight` in region.
3. Subnautica 1 terrain extraction: locate/parse SN1 batch files, convert one 160 m batch to a mesh file, load it with the existing loader.
4. Streaming design for many chunks + the "never load SN2 terrain" RAM requirement (project requirement: the finished mod must not keep hidden SN2 map in RAM).

## Distribution target (decided 2026-11-15): the finished mod will be shared with other players
Implications for the architecture (analysis, not yet tested):
- **Loader:** keep UE4SS — it is the de-facto SN2 mod loader (CurseForge/Nexus mods depend on it; CurseForge installs it). Ship as a mod folder / zip.
- **Terrain delivery:** the runtime Lua mesh generation proven here is for prototyping. For a whole map it will hitch (0.27 s per 160 m chunk on the game thread),
  has no Nanite/HLOD/proper streaming, and costs RAM. Target: SN1 terrain converted into **cooked static meshes / landscape in our own level**, built with the
  Subnautica2-Project modkit and packaged as IoStore (`LogicMods\<Mod>\` or `~mods\`), with a thin Lua/Blueprint layer that loads our level and skips/clears SN2's.
  This also satisfies the "never load SN2 terrain" RAM requirement.
- **Legal:** do not distribute data extracted from Subnautica 1. Ship a **converter** each user runs against their own SN1 install to produce the terrain
  (or the cooked assets, if the build step can run locally — open question; cooking needs the editor). Check Unknown Worlds' modding policy before public release.
- **Co-op:** runtime-spawned/destroyed actors are local, not replicated. All players need the same mod version; host authority over movement/creatures with
  divergent terrain is UNTESTED (game log already shows server-side move rejection: "Player moved too much ... Disregarding move").
- **Fragility:** Early Access patches can break UE4SS signatures, BP class names, and World Partition cell names; prefer data-driven, name-tolerant code and
  avoid overriding `_Generated_` cells. Watch for official mod support (`UWEUserGeneratedContent` plugin and `DefaultUWEUserGeneratedContent.ini` ship in the game).

## Standing project requirements
- Finished mod must not fill RAM with hidden Subnautica 2 terrain → prefer destroy/never-load over hide.
- Keep testing non-destructive: in-memory changes only; back up saves before risky tests; game files are only touched inside `ue4ss\Mods\`.
- Keep these research notes up to date as work happens (see project `CLAUDE.md`).
