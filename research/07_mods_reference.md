# Mods: code map and how to extend

**SN2TerrainEdit was deleted on 2026-11-16** (terrain removal + custom terrain now come from the cooked modkit mod `SN2Terrain`, see `08`).
Its sections below are kept as a record of working Lua recipes; the code is in git: `git show e30f3d0:src/mods/SN2TerrainEdit/Scripts/main.lua`
(test heightfield moved to `src/modkit/data/seafloor_test.txt`). Current Lua mods: SN2WorldProbe, SN2IntroProbe, SN2IntroSkip (see `09`).

Source of truth: `src/mods/<Mod>/Scripts/main.lua` in this project (tools in `src/tools`, paths from `local.config`). Install with `src/tools/install_mod.sh <Mod>`. Both load in `L_ClientLobby` too — gate world work with `worldName():find("L_Main")`.

## Key map (avoid collisions when adding keys)
| Key | Mod | Action |
|---|---|---|
| F1 | SN2TerrainEdit | Teleport player 10 m above the generated seafloor patch |
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

## SN2IntroSkip (≈250 lines, v4, VERIFIED 2026-11-17) and SN2IntroProbe (≈200 lines, recorder, disabled)
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
