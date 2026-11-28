# Lua mods code map

Pass 2 (2026-11-28): deleted mods reduced to recovery pointers plus the reusable recipes; mojibake in the pass-1 text fixed (full notes: `git show 3449200:research/code/mods.md`).

Source of truth: `src/mods/<Mod>/Scripts/main.lua` (tools in `src/tools`, paths from `local.config`). Install with `src/tools/install_mod.sh <Mod>`. Mods also load in `L_ClientLobby`: gate world work with `worldName():find("L_Main")`.
Current Lua mods: SN2BugShot, SN2Tadpole, SN2Census, SN2AutoTest.

## Key map (rewritten 2026-11-23: all old player-facing hotkeys removed)
Player-facing keys in normal play: **F1 = SN2BugShot** and **F4 = SN2Tadpole** only.
| Key | Mod | Action |
|---|---|---|
| F1 | SN2BugShot | Save one bug report json (+ engine HighResShot) to the mod's `reports/`; `bugshot_watch.sh` collects it. 1 s debounce. |
| F4 | SN2Tadpole | Spawn one Tadpole ~12 m from the lifepod, 3 m under the water |
| Ctrl+Shift+Z/X/C/V/B, Ctrl+F11 | SN2AutoTest | TEST-ONLY: bound only while a harness plan is armed (the file returns "idle (no plan)" otherwise) |
| INS | UE4SS BPModLoaderMod | stock (never used) |
| F10 / ~ | UE4SS ConsoleEnabler | UE console (game commands disabled in the test save) |
| (F3 LineTraceMod, Ctrl+Y/U/I SplitScreenMod) | stock | both mods DISABLED in mods.txt (stock `Keybinds` mod registers only keys from its own table, none set) |

Removed 2026-11-23, **VERIFIED (2026-11-23, grep of `RegisterKeyBind` over `src/mods` and the installed Mods dir)**: SN2Census F1/F2/F3 teleports + F5 sample (Census is kept, timer-driven; `autotest.sh` uses its `census_*.txt` and `[SN2Census] world=` lines).

## Deleted mods (recover from git)
- **SN2WorldProbe** (F5-F12, about 750 lines), **SN2IntroProbe** (recorder), **SN2WorldLevel** (F8/F9): deleted 2026-11-23: `git show 40820f3:src/mods/<Mod>/Scripts/main.lua` (Census binds: same commit, `SN2Census`).
- **SN2IntroSkip**: deleted 2026-11-18, replaced by the launch argument `-OverridePlayerStart=Shallows` (`research/sn2/intro_skip.md`): `git show f2b4354:src/mods/SN2IntroSkip/Scripts/main.lua` (v4).
- **SN2TerrainEdit** (about 860 lines): deleted 2026-11-16, terrain removal + custom terrain now come from the cooked modkit mod `SN2Terrain` (`research/code/modkit_setup.md`): `git show e30f3d0:src/mods/SN2TerrainEdit/Scripts/main.lua` (test heightfield moved to `src/modkit/data/seafloor_test.txt`).
- **SN2WaterFix** (runtime ocean repair): REJECTED and deleted 2026-11-19 (fix the map at source).
- Working recipes from them, in the recovered code: `spawnActorOfClass(classPath, T)` (deferred spawn helper), `crosshairHit` (`KismetSystemLibrary:LineTraceSingle`, component to owner fix), `tryLoad`/`loadMesh` (StaticFindObject, then LoadAsset, then fallbacks), `bindMod(key, modifiers, label, fn)` (keybind helper with game-thread wrapper), `boundsXY`/`regionFor` (circle vs XY box), tile sweep + GC request (22 proxies to 4 after GC, ~8.9k dressing actors destroyed in the 2026-11-16 test), `findAll` (CDO-filtered `FindAllOf`), `forEachProp`/`dumpSchema`/`dumpValues` (reflection walkers with a `STOP_AT` class list), `paramsOf(UFunction)` (parameter list incl. out/return flags), `openReport` (incremental, flushed writer: use it for any long dump so a crash leaves partial output). `SN2IntroProbe`/`SN2IntroSkip` helper set: `isValid/nameOf/fullOf/notCDO/firstOf/cdoOf/getPC`, `step/try`. Per-world state must be reset in a `ClientRestart` hook (actors and addresses are invalid after a world change).

## Extending: patterns that work
- New feature = new section above the `-- ---- wiring` marker; keep functions `local`; define before use (Lua locals are lexically ordered).
- Anything triggered by a timer goes through `ExecuteInGameThread`. Anything per world is reset in `ClientRestart`.
- Log one summary line per action with counts/timings; never log per-actor in a sweep (log volume floods the Monitor).
- `pcall` around every engine call that may not exist in this build; log the error text, it usually names the problem precisely.

## Status
UE4SS 3.0.1-953 injected, Lua mods load, game stable: **VERIFIED**. Live-world inspection (classes, properties, values, console commands): **VERIFIED** with SN2WorldProbe (deleted 2026-11-23); current tools are SN2AutoTest/SN2Census verbs (`research/code/autotest_verbs.md`).
