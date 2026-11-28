# Lua mods code map

Sources: 07_mods_reference.md "Mods: code map and how to extend", 07_mods_reference.md "Key map (rewritten 2026-11-23: all old player-facing hotkeys", 07_mods_reference.md "SN2IntroSkip (DELETED 2026-11-18, replaced by the launch arg", 07_mods_reference.md "SN2TerrainEdit (DELETED; â‰ˆ860 lines) â€” sections in file", 07_mods_reference.md "SN2WorldProbe (â‰ˆ750 lines)", 07_mods_reference.md "Extending â€” patterns that work", 00_overview.md "State of play" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## Mods: code map and how to extend

**SN2TerrainEdit was deleted on 2026-11-16** (terrain removal + custom terrain now come from the cooked modkit mod `SN2Terrain`, see `research/code/modkit_setup.md`).
Its sections below are kept as a record of working Lua recipes; the code is in git: `git show e30f3d0:src/mods/SN2TerrainEdit/Scripts/main.lua`
(test heightfield moved to `src/modkit/data/seafloor_test.txt`). Current Lua mods: SN2BugShot, SN2Tadpole, SN2Census, SN2AutoTest (SN2WorldProbe, SN2IntroProbe, SN2WorldLevel deleted 2026-11-23).

Source of truth: `src/mods/<Mod>/Scripts/main.lua` in this project (tools in `src/tools`, paths from `local.config`). Install with `src/tools/install_mod.sh <Mod>`. Both load in `L_ClientLobby` too â€” gate world work with `worldName():find("L_Main")`.

## Key map (rewritten 2026-11-23: all old player-facing hotkeys removed)
Player-facing keys in normal play: **F1 = SN2BugShot** (bug report) and **F4 = SN2Tadpole** only.
| Key | Mod | Action |
|---|---|---|
| F1 | SN2BugShot | Save one bug report json (+ engine HighResShot) to the mod's `reports/`; `bugshot_watch.sh` collects it. 1 s debounce. |
| F4 | SN2Tadpole | Spawn one Tadpole ~12 m from the lifepod, 3 m under the water |
| Ctrl+Shift+Z/X/C/V/B, Ctrl+F11 | SN2AutoTest | TEST-ONLY: bound only while a harness plan is armed (file returns "idle (no plan)" otherwise) |
| INS | UE4SS BPModLoaderMod | stock (reload-mods style default, never used) |
| F10 / ~ | UE4SS ConsoleEnabler | UE console (game commands disabled in the test save) |
| (F3 LineTraceMod, Ctrl+Y/U/I SplitScreenMod) | stock | both mods DISABLED in mods.txt (stock `Keybinds` mod only registers keys from its own table, none set) |
Removed 2026-11-23, VERIFIED by grep of `RegisterKeyBind` over `src/mods` and the installed Mods dir: SN2Census F1/F2/F3 teleports + F5 sample (Census is kept, timer-driven, autotest.sh uses its census_*.txt and `[SN2Census] world=` lines); mods SN2WorldProbe (F5-F12), SN2IntroProbe, SN2WorldLevel (F8/F9) deleted from repo and game Mods dir and mods.txt. Recover: `git show 40820f3:src/mods/<Mod>/Scripts/main.lua` (Census binds: same commit, `SN2Census`).
Reports of the removed WorldProbe etc. are history; the sections below describe their old code.

## SN2IntroSkip (DELETED 2026-11-18, replaced by the launch argument `-OverridePlayerStart=Shallows`, see `09`; v4 code: `git show f2b4354:src/mods/SN2IntroSkip/Scripts/main.lua`) and SN2IntroProbe (â‰ˆ200 lines, recorder, disabled)
Keys (Ctrl + top-row number, `bind(key,label,fn)`): Ctrl+1 dump state, Ctrl+4 `unstick`. Design and results: `research/sn2/README.md`.
SN2IntroSkip sections: constants (`LIFEPOD_END`, `DONE_GOAL`, `DEEPSTART_GOALS` Ã—18) â†’ guarded helpers (`isValid/nameOf/fullOf/notCDO/firstOf/cdoOf/getPC`, `step/try`)
â†’ `unlockGoals` (subsystem â†’ statics fallbacks) â†’ `unstick` â†’ `skipStoryState` (phase A) â†’ `skipMove` (phase B) â†’ `parentClass`, `dump` â†’ keybinds
â†’ `ClientRestart` hook (arms only in `L_Main`) â†’ `LoopAsync(500)` state machine (waits for non-spectator pawn â‰¥3 ticks, bed-attached, then `waitingGetUp`, 45 s timeout).
SN2IntroProbe: story-goal / data-layer / pawn polling + hooks (sequence, media, lifepod manager); polls only in `L_Main` every 5 s. Enable only for new recordings.
SN2WorldProbe keys are in the table below (F5â€“F12). Table rows for SN2TerrainEdit refer to the deleted mod.

## SN2TerrainEdit (DELETED; â‰ˆ860 lines) â€” sections in file order
1. **config**: `PLACEMENTS` (`{name, mesh, loc={X,Y,Z}, yaw, scale}`; current: `first_rock` boulder at (-200350, 433900, -26450)), `WORLD_MATCH="L_Main"`, `DELAY_MS=4000`.
2. **helpers**: `isValid`, `getPC`, `getWorld`, `worldName`, `FALLBACK_MESHES`, `tryLoad`/`loadMesh` (StaticFindObject â†’ LoadAsset â†’ fallbacks â†’ any loaded rock), `quatFromYaw`.
3. **placement**: `placeOne`, `placeAll` (auto via ClientRestart hook + `ExecuteWithDelay(DELAY_MS)` â†’ `ExecuteInGameThread`).
4. **custom shapes (F3)**: `cameraRay`, `spawnActorOfClass(classPath, T)` (deferred spawn helper â€” reuse it), `rockMaterial()` (material from a resident rock),
   `shape_GeometryScript`, `shape_ProceduralMesh` (UNTESTED), `shape_CubeStack` (UNTESTED), `spawnCustomShape`.
5. **terrain removal (F2)**: `notCDO`, `crosshairHit` (KismetSystemLibrary:LineTraceSingle, componentâ†’owner fix), `describe` (LANDSCAPE / STATIC MESH / PREFAB / HLOD / BLUEPRINT),
   `setRemoved`, `identify`, `removeTarget`, `toggleAllLandscape`, `bindMod(key, modifiers, label, fn)` (keybind helper with game-thread wrapper).
6. **removal regions**: `REMOVE_REGIONS = {{name, center={X,Y}, radius, mode="destroy"|"hide", clearDressing, fillWithTestPatch}}` â€” current: `spawn_hole`
   at (-331747, 420670), r = 300 m, destroy, clearDressing, fillWithTestPatch. `SWEEP_MS=1500`. `boundsXY`, `regionFor` (circle vs XY box), `countOf`, `landscapeCounts`,
   `hideProxyComponents`, `diagnoseProxies` (logs tiles IN a region when the loaded set changes), `sweepRegions` (destroys tiles, records landscape Z, requests GC,
   heartbeat every 20 sweeps with player position).
7. **full clear (dressing)**: `dressingChecked` cache, `ourActors` (never remove our own spawns), `isDressing` (allow-list), `inRegionPoint`, `sweepDressing`
   (also logs surviving classes once per world).
8. **generated seafloor**: `modDir`, `readHeightfield`, `buildPatch(region)` (tries AppendBuffersToMesh, falls back to rectangle + SetVertexPosition; logs timings, bounds),
   `maybeBuildPatch` (once per world, after â‰¥4 sweeps and once landscape Z is known), F1 teleport, ClientRestart reset of per-world state.
9. **LoopAsync driver**: every `SWEEP_MS` â†’ `ExecuteInGameThread` â†’ `sweepRegions` â†’ `sweepDressing` â†’ `maybeBuildPatch`.
10. **wiring**: ClientRestart â†’ placements, F4.
Per-world state must be reset in a `ClientRestart` hook (actors and addresses are invalid after a world change).

## SN2WorldProbe (â‰ˆ750 lines)
Read-only inspection plus the original F6/F7/F8 tests. Reusable pieces: `findAll` (CDO-filtered FindAllOf), `forEachProp`/`dumpSchema`/`dumpValues`
(reflection walkers with a `STOP_AT` class list), `DETAIL` (class-name patterns treated as world systems), `DEEP_TARGETS` (F12 list), `paramsOf(UFunction)`
(parameter list incl. out/return flags), `openReport` (incremental, flushed writer â€” use it for any long dump so a crash leaves partial output).
To inspect a new class: add its name to `DEEP_TARGETS`, reinstall, relaunch, F12.

## Extending â€” patterns that work
- New feature = new section above the `-- ---- wiring` marker; keep functions `local`; define before use (Lua locals are lexically ordered).
- Anything triggered by a timer â†’ `ExecuteInGameThread`. Anything per world â†’ reset in `ClientRestart`.
- Log one summary line per action with counts/timings; never log per-actor in a sweep (log volume floods the Monitor).
- Add `pcall` around every engine call that may not exist in this build; log the error text â€” it usually names the problem precisely.

## State of play detail (moved from 00_overview.md, 2026-11-28)

| Capability | Status |
|---|---|
| UE4SS 3.0.1-953 injected, Lua mods load, game stable | VERIFIED |
| Inspect the live world (classes, properties, values, console commands) | VERIFIED (SN2WorldProbe, deleted 2026-11-23) |
