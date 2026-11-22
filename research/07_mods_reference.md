# Mods: code map and how to extend

**SN2TerrainEdit was deleted on 2026-11-16** (terrain removal + custom terrain now come from the cooked modkit mod `SN2Terrain`, see `08`).
Its sections below are kept as a record of working Lua recipes; the code is in git: `git show e30f3d0:src/mods/SN2TerrainEdit/Scripts/main.lua`
(test heightfield moved to `src/modkit/data/seafloor_test.txt`). Current Lua mods: SN2WorldProbe, SN2IntroProbe (see `09`).

Source of truth: `src/mods/<Mod>/Scripts/main.lua` in this project (tools in `src/tools`, paths from `local.config`). Install with `src/tools/install_mod.sh <Mod>`. Both load in `L_ClientLobby` too — gate world work with `worldName():find("L_Main")`.

## Key map (avoid collisions when adding keys)
| Key | Mod | Action |
|---|---|---|
| F1 | SN2TerrainEdit | Teleport player 10 m above the generated seafloor patch |
| F1 / F2 / F3 | SN2Census | Teleport pawn to (-204942,432071,-2000) / (-146623,228913,-1000) World Tree base / (-336997,433246,322); sample + report 5 s later |
| F5 | SN2Census | Sample + `census_<YYYYMMDD_HHMMSS>.txt` report now (clashes with SN2WorldProbe F5 only if both enabled; WorldProbe is off) |
| F2 / Shift+F2 / Ctrl+F2 | SN2TerrainEdit | Identify crosshair target / remove target (repeat at empty water = restore last) / toggle ALL loaded landscape |
| F3 | SN2TerrainEdit | Custom shape 15 m ahead (Geometry Script star → PMC pyramid → cube stack fallbacks) |
| F4 | SN2TerrainEdit | Re-place `PLACEMENTS` rocks |
| F5 | SN2WorldProbe | World report → `probe_report.txt` (streaming, landscape, actor histogram, world-system schemas) |
| F6 | SN2WorldProbe | Toggle nearest landscape tile + static meshes within 20 m (hide) |
| F7 | SN2WorldProbe | Spawn a resident rock mesh along the camera beyond its radius |
| F8 | SN2WorldProbe | Fog density ×6 toggle (UNTESTED — never pressed) |
| F9 | SN2WorldProbe | Console commands with parameters → `exec_functions.txt` |
| F10 / ~ | UE4SS ConsoleEnabler | UE console (game commands disabled in the test save) |
| F11 | SN2WorldProbe | Simple property values of world-system actors → `probe_values.txt` |
| F12 | SN2WorldProbe | Deep schema: struct fields, components, values → `probe_deep.txt` |
| INS | UE4SS BPModLoaderMod | (default) |
Reports are written next to the mod in the game folder; copy to `<Workspace>\reports\` to keep them.

## SN2Census (new 2026-11-18, ~215 lines, read-only) — measurement for the SN2EmptyWorld test
Never destroys/hides anything; only F1-F3 teleport (`pawn:K2_SetActorLocation({X,Y,Z}, false, {}, true)`). Log prefix `[SN2Census]`. Status: UNTESTED in game.
Sections: guarded helpers (`isValid` pcall, `findAll` skips `Default__`) -> `cvar(name)` (`Default__KismetSystemLibrary:GetConsoleVariableIntValue`) -> `findModActor` (FindAllOf `ModActor_C`
whose class full name contains `/Game/Mods/SN2EmptyWorld/`; reads its int vars) -> `sample()` -> `writeReport` -> scheduling (`scheduleAt`: chained `ExecuteWithDelay`, no LoopAsync, nothing runs in the lobby)
-> `ClientRestart` hook (arms only if the controller's world full name contains `L_Main`; any other world disarms; samples at 1,5,15,30,60,120 s then every 120 s) -> keys.
Sample line (one per sample):
`[SN2Census] t=<s> cvarSrc= cvarHLOD= genLevels= actors= uaid= sma= lsp= landscape= hlod= aiPawn= aiChar= placeable= wpResource= smc= ismc= skm= niagara= pawn=(x,y,z) | mod: found= purges= map= creatures= storage= lastActors= srcBefore= src= hlodBefore= hlod=`
(-999 = read failed; mod fields -1 = ModActor not found). Report `census_<stamp>.txt` in the mod folder (written at t=15 s and on every F5): sample line, actor class histogram,
remaining `_UAID_` actors as `<full name> | <class> | loc=(x,y,z) | rot=(pitch,yaw,roll) | scale=(x,y,z)`, a PlayerStart section (same fields + `tag=` PlayerStartTag), `_Generated_` Level names, ModActor `DestroyedClassNames` (TArray `:ForEach`, pcall-wrapped).

SN2WorldLevel (2026-11-18, ~55 lines, DISABLED after the tests): F8 = `UWELobbyStatics:SetWorldLevel` to the SupplyCrates dev map, F9 = restore; `GetWorldLevelName` returns `/Game/Maps/Main/L_Main` style. SN2Census arms in any world except `L_ClientLobby` and prefixes samples with `world=<name> worldLevel=<GetWorldLevelName>`; report also lists lifepod/water/sky/manager actors with transform + attach parent.

## SN2IntroSkip (DELETED 2026-11-18, replaced by the launch argument `-OverridePlayerStart=Shallows`, see `09`; v4 code: `git show f2b4354:src/mods/SN2IntroSkip/Scripts/main.lua`) and SN2IntroProbe (≈200 lines, recorder, disabled)
Keys (Ctrl + top-row number, `bind(key,label,fn)`): Ctrl+1 dump state, Ctrl+4 `unstick`. Design and results: `09`.
SN2IntroSkip sections: constants (`LIFEPOD_END`, `DONE_GOAL`, `DEEPSTART_GOALS` ×18) → guarded helpers (`isValid/nameOf/fullOf/notCDO/firstOf/cdoOf/getPC`, `step/try`)
→ `unlockGoals` (subsystem → statics fallbacks) → `unstick` → `skipStoryState` (phase A) → `skipMove` (phase B) → `parentClass`, `dump` → keybinds
→ `ClientRestart` hook (arms only in `L_Main`) → `LoopAsync(500)` state machine (waits for non-spectator pawn ≥3 ticks, bed-attached, then `waitingGetUp`, 45 s timeout).
SN2IntroProbe: story-goal / data-layer / pawn polling + hooks (sequence, media, lifepod manager); polls only in `L_Main` every 5 s. Enable only for new recordings.
SN2WorldProbe keys are in the table below (F5–F12). Table rows for SN2TerrainEdit refer to the deleted mod.

## SN2TerrainEdit (DELETED; ≈860 lines) — sections in file order
1. **config**: `PLACEMENTS` (`{name, mesh, loc={X,Y,Z}, yaw, scale}`; current: `first_rock` boulder at (-200350, 433900, -26450)), `WORLD_MATCH="L_Main"`, `DELAY_MS=4000`.
2. **helpers**: `isValid`, `getPC`, `getWorld`, `worldName`, `FALLBACK_MESHES`, `tryLoad`/`loadMesh` (StaticFindObject → LoadAsset → fallbacks → any loaded rock), `quatFromYaw`.
3. **placement**: `placeOne`, `placeAll` (auto via ClientRestart hook + `ExecuteWithDelay(DELAY_MS)` → `ExecuteInGameThread`).
4. **custom shapes (F3)**: `cameraRay`, `spawnActorOfClass(classPath, T)` (deferred spawn helper — reuse it), `rockMaterial()` (material from a resident rock),
   `shape_GeometryScript`, `shape_ProceduralMesh` (UNTESTED), `shape_CubeStack` (UNTESTED), `spawnCustomShape`.
5. **terrain removal (F2)**: `notCDO`, `crosshairHit` (KismetSystemLibrary:LineTraceSingle, component→owner fix), `describe` (LANDSCAPE / STATIC MESH / PREFAB / HLOD / BLUEPRINT),
   `setRemoved`, `identify`, `removeTarget`, `toggleAllLandscape`, `bindMod(key, modifiers, label, fn)` (keybind helper with game-thread wrapper).
6. **removal regions**: `REMOVE_REGIONS = {{name, center={X,Y}, radius, mode="destroy"|"hide", clearDressing, fillWithTestPatch}}` — current: `spawn_hole`
   at (-331747, 420670), r = 300 m, destroy, clearDressing, fillWithTestPatch. `SWEEP_MS=1500`. `boundsXY`, `regionFor` (circle vs XY box), `countOf`, `landscapeCounts`,
   `hideProxyComponents`, `diagnoseProxies` (logs tiles IN a region when the loaded set changes), `sweepRegions` (destroys tiles, records landscape Z, requests GC,
   heartbeat every 20 sweeps with player position).
7. **full clear (dressing)**: `dressingChecked` cache, `ourActors` (never remove our own spawns), `isDressing` (allow-list), `inRegionPoint`, `sweepDressing`
   (also logs surviving classes once per world).
8. **generated seafloor**: `modDir`, `readHeightfield`, `buildPatch(region)` (tries AppendBuffersToMesh, falls back to rectangle + SetVertexPosition; logs timings, bounds),
   `maybeBuildPatch` (once per world, after ≥4 sweeps and once landscape Z is known), F1 teleport, ClientRestart reset of per-world state.
9. **LoopAsync driver**: every `SWEEP_MS` → `ExecuteInGameThread` → `sweepRegions` → `sweepDressing` → `maybeBuildPatch`.
10. **wiring**: ClientRestart → placements, F4.
Per-world state must be reset in a `ClientRestart` hook (actors and addresses are invalid after a world change).

## SN2WorldProbe (≈750 lines)
Read-only inspection plus the original F6/F7/F8 tests. Reusable pieces: `findAll` (CDO-filtered FindAllOf), `forEachProp`/`dumpSchema`/`dumpValues`
(reflection walkers with a `STOP_AT` class list), `DETAIL` (class-name patterns treated as world systems), `DEEP_TARGETS` (F12 list), `paramsOf(UFunction)`
(parameter list incl. out/return flags), `openReport` (incremental, flushed writer — use it for any long dump so a crash leaves partial output).
To inspect a new class: add its name to `DEEP_TARGETS`, reinstall, relaunch, F12.

## Extending — patterns that work
- New feature = new section above the `-- ---- wiring` marker; keep functions `local`; define before use (Lua locals are lexically ordered).
- Anything triggered by a timer → `ExecuteInGameThread`. Anything per world → reset in `ClientRestart`.
- Log one summary line per action with counts/timings; never log per-actor in a sweep (log volume floods the Monitor).
- Add `pcall` around every engine call that may not exist in this build; log the error text — it usually names the problem precisely.


## SN2AutoTest + automated test tools (2026-11-18)
- `src/mods/SN2AutoTest/Scripts/main.lua` (~180 lines, **observe-only**): arming (`run/active_plan.lua` -> dofile -> rename `.consumed`); `ClientRestart` hook logs `[SN2AutoTest] WORLD <short name>`; in non-lobby worlds polls (1 s `ExecuteWithDelay`) for `PAWN possessed spawn=(..)` and logs `SETTLED spawn` 12 s later (the "spawn" waypoint uses the settled position); `SetWorldLevel` 2 s after `WORLD L_ClientLobby` when the plan has `worldLevel` (the only non-observing call); hotkeys `Ctrl+Shift+Z/X/C/V/B` = teleport to plan waypoint 1..5 (`K2_SetActorLocation` sweep false, teleport true; lifepod + offset, or the settled spawn); `Ctrl+F11` = `STATE world= pawn=(..) cam=(..) yaw= pitch= lifepod=(..)`. Never calls StartNewLocalGame*, LoadLocalGame, SetControlRotation, QuitGame or console commands.
- `src/tools/autotest_driver.py`: ctypes SendInput driver. Subcommands `focus | click X Y | key NAME [ms] | combo MOD+KEY | mouse DX DY | shot FILE | state | dialogs | arm PLAN.json RUN_DIR | run PLAN.json`. `dialogs` (read-only) prints the game process's `#32770` dialogs (title, texts, child classes, buttons); `run` dismisses a start-up dialog through an `OK`/`Continue`/`Close` button. Result lines: `DONE FAIL_LOBBY FAIL_NOPAWN FAIL_FOCUS` (exit 3) `FAIL_DIALOG` (exit 4: a dialog with no such button; buttons listed) `FAIL_EXCEPTION`; failed runs close the game cleanly (`clean_exit`, see `01` "Start-up hang"). `run` = whole plan (menu steps from `plans/menus.json`, calibration, waypoints, manifest, quit). Needs Pillow + numpy; env `SN2_UE4SS_DIR` (set by sn2_env.sh), `SN2_AUTOTEST_OUT`.
- `src/tools/autotest_screens.py` + `src/mods/SN2AutoTest/plans/screens.json` / `screen_labels.json` (2026-11-19): menu-screen fingerprints (numbers only) used by the driver for screen-identity navigation; driver subcommands `windows REASON OUT`, `identify [FILE]`, `screens-build`, `screens-check [--loo]`. Details and thresholds: `01` "Screen-identity menu navigation".
- `src/tools/heavy_lock.sh` (2026-11-19): a cross-session lock for the game, editor and cook. Launch, install, autotest, cook, `launch_editor.sh` and `ue_run.py` all check it. Details are in `01_runbook.md` "Parallel sessions".
- `src/tools/autotest.sh <plan>` (one attempt, collection + summary), `src/tools/autotest_retry.sh <plan>` (<= 3 attempts, only after `CRASH`), `src/tools/autotest_sheets.py <run> <plan>` (contact sheets + `shot_stats.txt`).
- `SN2Census` additionally writes its report automatically 20 s after it arms (used by autotest; F5 still works).

## SN2GraphTools additions + changed editor scripts (2026-11-18, evening)
New editor-only `unreal.SN2GraphLibrary` functions (source `src/modkit/plugins/SN2GraphTools`, copy kept in sync in `<ModkitDir>\Subnautica2-Project\Plugins\SN2GraphTools`; reflection only, no Water module dependency; build OK 289 s, Python exposes them - **VERIFIED 2026-11-18** and used in the editor):
- `describe_object_array(obj, "PropName") -> [str]`: one line per element `"<idx> <element path> outer=<outer path>"`; `["MISSING <name>"]` if absent or not an array of object pointers.
- `clear_object_array(obj, "PropName") -> int`: `Modify()`, empties the array, returns the removed count, -1 if missing / wrong type.
- `notify_property_changed(obj, "PropName")`: `PreEditChange(prop)` + `PostEditChangeProperty(FPropertyChangedEvent(prop, ValueSet))`.
`src/modkit/scripts/sn2world_map.py`: ocean now copied with the level (`RUNTIME_SPAWNED = ()`, `NOT_COPIED = (BP_UWEOceanBiomeRegionActor_C,)`); step 4b sets lighting/locker root mobility MOVABLE and attaches them to the pod (KEEP_RELATIVE); step 4c clears the ocean's `CollisionBoxes`/`CollisionHullSets` and calls `notify_property_changed(comp, "CollisionExtents")`; the check requires pod attach parents + expected world transforms and 1 biome region parented to the ocean. `src/modkit/scripts/sn2emptyworld_graph.py`: the L_SN2World branch only destroys the ModActor (106 nodes). Details and results in `09`.
`sn2world_map.py` update 2026-11-19: step 4b sets the pod `RootComponent` STATIC (modkit class default is MOVABLE, game is STATIC); step 4d attaches the nine pod components (KEEP_RELATIVE, stay STATIC, no MOVABLE fallback); `check_pod()` runs in memory and again after save + reload from disk (step 7, `die()` on failure). `pod_components_probe.py` also logs the class CDO root. `src/modkit/tools/cook_install.sh` has a cook guard: `AttachTo: ... Aborting` lines for `/Game/Mods/<MOD>/` in the cook log -> exit 3, no install, unless `SN2_ALLOW_ATTACH_ABORTS=1` (see `08`).
`sn2world_map.py` update 2026-11-19 (water): `KEEP` gained `BP_BoxVolume_C` (only the origin air volume, `keep_source()`); `NOT_COPIED = (REGION_CLS,)` again (EDIT COPY cannot copy a child actor) but the region is now SPAWNED as a standalone actor in step 4e (class from L_Main's child, transform = our ocean actor + L_Main offset (0,0,-5e6), scale (1e6,1e6,1e5)); helpers `comp_rows`, `snapshot`/`apply_snapshot` (copy Python-readable differing properties from L_Main's child), `paste_region_with_water_light` (T3D round trip that injects `WATER_LIGHT_SETTINGS` into the `BiomeVolumeComponent`, not exposed to Python); `check_region(tag)` (standalone transform + per-component world scale/location vs L_Main, air volume transform and Z relative to the ocean) runs in `[memory]` and `[reload]`. `MAIN` dict = L_Main reference values captured before `new_level`. Details and cooked-file results in `09` "Standalone water region + origin air volume implemented in the map". Offline tooling used (not in the repo): `<ModkitDir>\scratch_bp\uaa\uaa\bin\Debug\net8.0\uaa.exe <usmap> <outdir> <umap>` (JSON dump of a legacy map), `scratch_bp\sn2w_all2` / `sn2w_leg2` / `sn2w_json2` (our cook), `scratch_bp\lmain_json` (shipped L_Main, 425 MB JSON).
- SN2AutoTest observe-only additions (2026-11-18): after every `STATE` and at `SETTLED` a line `BASE comp=<full name> owner=<actor> loc=(x,y,z) rot=(p,y,r)` (pawn movement base; `BASE none` + a `BASEFLOOR ...` line from a downward `LineTraceSingle` when there is no base, which is the usual case); at `SETTLED` a pod component dump `<mod>un\poddump_<world>_<ts>.txt` (tab-separated, one row per SceneComponent of every actor within 1500 uu of `BP_StaticLifepod_Surface_C` or attached to it + `BP_LifepodManager_C`, then a `## MANAGER_PROPERTIES` section) logged as `PODDUMP written <path> rows=<n>`; `autotest.sh` copies it into the run folder. `src/tools/pod_diff.py <A> <B> <out.md>` compares two dumps in the pod's local frame (1 cm / 0.5 deg tolerance; only-A / only-B / differences / manager-property tables). Findings: `09` "Pod component diff".


- `src/modkit/scripts/ocean_compare_probe.py` (2026-11-19): read-only editor probe, `[OCEANPROBE]` lines: components/scales/mobility/CollisionBoxes/properties of every water-like actor in L_Main and L_SN2World plus the `BP_Ocean_C` CDO. Output is large (L_Main has ~60 EdgeOfWorld volumes); filter with grep. `sn2world_map.py` now sets ocean `BodySize` (step 4c0) and has `check_ocean()` (memory + reload); `SN2AutoTest` logs `WATER ...` per STATE and always dumps ocean/biome-region/WaterZone rows (see `09` "Water physics").

- `SN2WaterFix` (runtime ocean repair) was REJECTED 2026-11-19 and deleted (the map must be fixed at source; see `09`). `SN2AutoTest` gained `WATER` (3 physics-volume reads + IsSwimming/IsInWater), `OCEAN` (runtime BodySize) and one-time `WATERCENSUS` lines.
- `src/tools/check_lua_ctl.py` (2026-11-19): exits 1 and prints file:line for raw control characters (CR etc., TAB/LF allowed) in Lua; called by `install_mod.sh`. `autotest_driver.py` result `FAIL_LUA_LOAD` (UE4SS.log `Error loading script` for an SN2* mod during the lobby wait). `SN2AutoTest` and `SN2Census` converted to LF-only 2026-11-19. See `01` Lua rules.
- `autotest_screens.py` / `screen_labels.json` / `screens.json` (2026-11-19): fingerprints support per-screen `mask` rects (save rows of `save_list`), `extra` and `not_o` label entries; offline check 0 misidentified on 448 shots; see `01`.

## SN2AutoTest engine input mode (2026-11-22)
- `main.lua` command channel: `run/cmd.txt` lines `<seq> <verb> <args>`, polled every 250 ms, run in `ExecuteInGameThread`, result log `CMD <seq> <verb> ok|fail <detail>`. Verbs: `look` (IA_Look injection, gain 6.25 deg/unit), `inject`, `buttons`, `widgets`, `click` (labels `text`, `name:Widget`, `name:Widget@Screen`; calls `HandleButtonClicked`; denylist RemoveButton, ConfirmRed, RenameButton, UploadButton, ConvertButton, UpgradeButton, ImportSaveButton and labels containing remove/delete -> `DENIED`), `exec`, `screen`, `funcs`. Visibility check `chainVisible` walks ancestors and requires the active WidgetSwitcher child. **VERIFIED 2026-11-22 (run 5)**.
- `src/tools/autotest_driver.py` engine mode: screen-driven menu navigation (`do_steps_engine`), pure logic in `src/tools/autotest_menu_pick.py` (offline check: `python -I src/tools/autotest_menu_pick.py <BTN-line file>`); guards raise on `press`/`combo`/`click`/`mouse_move`/`focus`/`ImageGrab.grab` in engine mode. `src/tools/winshot.py` (PrintWindow shots), `src/tools/autotest_occluder.py` (topmost occluder; REMOVED 2026-11-22, engine mode is now the default and runs without any covering window, UNTESTED 2026-11-22; OS mode is opt-in via `--input os` / `SN2_INPUT=os`), `launch_game.sh` Steam-running preflight. Mode flag `--input engine|os` / `SN2_INPUT`, written to `active_plan.lua` and `summary.txt`. Widget names: ContinueBtn (HealthWarning/PressStart), PlaySinglePlayerButton (WBP_MainLobbyScreen), WBP_NewGameButton (WBP_LoadGamePanel), StartButton (WBP_CreateGameScreen), HandlePause, WBP_RoundedButton_ExitGame, ExitWithoutSavingButton, QuitButton.

- **Launcher (2026-11-22):** `src/tools/launch_game.sh` = `steam.exe -applaunch 1962700 <args>`; no start override by default, `SN2_START=<Tag>` adds `-OverridePlayerStart=<Tag>`; exit 6 if Steam is not running. `src/modkit/scripts/playerstart_probe.py` (editor) prints every PlayerStart's tag/goals/tags/items in L_SN2World. `sn2world_map.py` KEEP list holds only `BP_ShallowsPlayerStart_C` (see `09`).

- **SN2AutoTest engine verbs added/used 2026-11-22:** `death` (logs `DEATHCHK screen= continueButton= pawn=`, returns `dead` when `WBP_RespawnScreen_C` is chain-visible; VERIFIED 2026-11-22 in runs `20261122_120325_sn2world`, `..._121230_sn2world_load`). Driver additions in `src/tools/autotest_driver.py`: `is_dead`, `death_info`, `handle_death`, `do_waypoint` (retry once), `RespawnFail` -> `FAIL_RESPAWN`, MenuFail writes `buttons_menu.txt`. `load_game` engine entries in `plans/menus.json` use button names `ContinueBtn`, `PlaySinglePlayerButton`, `LoadGameButton`, `PlayButton` with `fn:HandleButtonClicked` (see 01_runbook).
- **autotest harness 2026-11-22:** death screenshot removed from `handle_death`; `autotest.sh` has `kill_driver()` (python.exe + `autotest_driver.py run` only) and an EXIT trap `on_exit` writing `exit_code.txt`; driver has `FocusGuard`, `input_state`, `mouse_probe` (env `SN2_FOCUSGUARD=0`, `SN2_MOUSEPROBE=1`). Details and status in 01_runbook.md. LOGGED (2026-11-22).

### Startup speed-up changes (2026-11-22)
- `src/tools/autotest_driver.py`: `say()` timestamps; engine mode skips the frame-diff gate; `get_state` uses the Lua `state` verb; `do_steps_engine` polls the next button (0.25 s idle, re-click 1.5 s, cap 10); pawn readiness poll (min `settleMin` 2 s, max `settleSeconds`); `wait_frames(nfr, pawn_still, label)` polls the Lua `frame` verb and logs a free FPS figure when `label` is given; `turn_to` skips the initial state read in engine mode; `fps_probe` kept only at `menu_ready`.
- `src/mods/SN2AutoTest/Scripts/main.lua`: command-file poll `LoopAsync(100, ...)` (was 250). Phase table and verdicts: `01` "Startup speed-up, phase table".
