# Status: what works and what is open

Pass-1 text (full rows, items and tails): `git show 3449200:research/status.md`; older: `git show 7221ba9:research/00_overview.md`.

## State of play (condensed 2026-11-28)
| Capability | Status |
|---|---|
| UE4SS 3.0.1-953 injected, Lua mods load, game stable | VERIFIED; [mods](code/mods.md) |
| Lua terrain tools: spawn meshes, remove landscape, auto-clear a region (about 10.6k actors), Geometry Script terrain (160 m, 19.6k tris, 0.27 s) | VERIFIED (prototype; mod deleted 2026-11-16); [legacy](terrain/legacy_lua.md) |
| One-call arbitrary mesh (`AppendBuffersToMesh`) from Lua | FAILED; works from editor Python 2026-11-16; [import](terrain/import.md) |
| Modkit editor, game content mounted, scripted by `ue_run.py`; cooked mod `SN2Terrain` shows terrain and clears SN2 terrain without Lua | VERIFIED 2026-11-16; [modkit](code/modkit_setup.md) |
| Never loading SN2 terrain at all (RAM requirement) | UNTESTED, design only; [import](terrain/import.md) |
| Temperature / water-look / music / spawn-zone actors spawned from Lua | UNTESTED; [placement](features/placement.md) |
| New Survival game starts in the lifepod, intro skipped, empty hotbar, no launch option (single `BP_ShallowsPlayerStart_C`; Steam `-applaunch`, display args only) | VERIFIED 2026-11-22; [intro](sn2/intro_skip.md), [map](sn2/l_sn2world_map.md) |
| Empty world via cooked mod `SN2EmptyWorld`; own map `/Game/Mods/SN2EmptyWorld/L_SN2World` chosen by `UWELobbyStatics.SetWorldLevel` | VERIFIED 2026-11-18 (empty world, other map runs); default Deep start crashes (cause open); [map](sn2/l_sn2world_map.md) |
| L_SN2World pod, ocean and swim physics (pod components re-attached, ocean region at (0,0,-5e6) + air volume) | VERIFIED 2026-11-19 (pod interior, swims like L_Main); [pod](sn2/l_sn2world_pod.md), [water](sn2/l_sn2world_water.md) |
| Underwater water look in L_SN2World: blue like L_Main, then calibrated (Safe Shallows) | VERIFIED 2026-11-27 / 2026-11-28; [look](features/biome_look.md) |
| Habitat Builder placement on SN1 terrain | VERIFIED 2026-11-28 (IsGroundSurface fix); [base](features/base_building.md) |
| Automated tests: `autotest.sh`, engine input mode and hidden desktop by default, death/respawn, load_game chain, test-world cleanup | VERIFIED 2026-11-22; no-occluder default run and cleanup on a real run UNTESTED then; [autotest](process/autotest.md), [input](process/autotest_input.md), [hidden desktop](process/autotest_hidden_desktop.md) |
| Lobby to world load crash (GC watchdog, about 22.8k objects), also the 2026-11-22 spot-1 crash kinds | OPEN, not fixed, undiagnosed; [crash](crashes/gc_watchdog.md) |
| SN1 files read offline (layouts); `SN1Inspector` (BepInEx 5.4.23.6) via `sn1_run.sh`; 10 reference shots; placed objects decoded (12,362 in the origin cube) | VERIFIED 2026-11-19 / 2026-11-22 / 2026-11-26; [files](sn1/world_files.md), [modding](sn1/modding.md), [objects](sn1/objects.md) |
| SN1 terrain: extract (spot 1, 1.1M tris, 0.029 m error), import into L_SN2World (`src/modkit/scripts/sn1terrain_import.py`, 16 Nanite StaticMeshActors tagged `SN1Terrain`), visible in game; origin cube run 12/12; holes fixed (manifold) | VERIFIED 2026-11-22 / 2026-11-23; [extract](terrain/extract.md), [import](terrain/import.md), [spot1](terrain/checks_spot1.md), [origin](terrain/checks_origin.md) |

## Next steps (open items only; one line per OPEN heading)
1. PAUSED by user order 2026-11-28; the real import is UNTESTED; resume when the user says so — `research/terrain/import.md` "Import an area: `sn1_import_area.sh`"
2. NOT fixed; Fix 1 (`--vt-prio 3`) is the next test; blocks the F1 popup test — `research/crashes/gc_watchdog.md` "Summary"
3. Deep (default) start crash in L_Main, UNEXPLAINED; use the Shallows start for diagnostics — `research/crashes/deep_start_crash.md` "Deep-start crash in L_Main"
4. F1 popup has not opened in game (FAILED 2026-11-24, widget class not found), PAUSED until the GC crash is fixed — `research/process/bug_reports.md` "State of play (2026-11-24)"
5. Multi-launch create-then-load test not implemented; loaded save spawns at 50000,0,-200 — `research/process/autotest_saves.md` "Open points"
6. Focus/mouse-grab probe (MOUSEPROBE) not run, load-time variability, no-occluder default needs a routine run (UNTESTED) — `research/process/autotest_input.md` "Open points"
7. Ignored first title click (cause UNKNOWN), FPS drop after the first teleport (cause UNTESTED), Steam start path (UNTESTED) — `research/process/autotest_startup.md` "Open points"
8. Dialog dismissal in a real hidden-desktop run, gamepad / XInput leakage (UNTESTED) — `research/process/autotest_hidden_desktop.md` "Open points"
9. Subagents share the parent's lock identity (FAILED 2026-11-26); full cook with the fixed lock script UNTESTED — `research/process/heavy_lock.md` "Open points"
10. Imported terrain disappears for the user, cause UNTESTED — `research/terrain/checks_origin.md` "Imported terrain disappears"
11. Never-load-SN2-terrain RAM requirement, UNTESTED — `research/terrain/import.md` "4. Memory requirement"
12. Local look from the 42 SN1 boxes, sight distance, caustics, god rays, terrain albedo, bright ravine (UNTESTED) — `research/features/biome_shallows_boxes.md` "Remaining differences and calibration direction"

13. Biome look: local look from the 42 boxes, regression rerun, haze/weather, next biomes (UNTESTED) — `research/features/biome_look.md` "Status and next steps"
14. SN1 breakable resources to SN2 resource Blueprints, investigation open (2026-11-26) — `research/features/resources.md` "SN1 breakable resources"
15. First-launch builder: open SN2 questions (UNTESTED) — `research/sn1/first_launch_builder.md` "8. Open questions for SN2"
16. First-launch builder: cheap experiments, in order (UNTESTED) — `research/sn1/first_launch_builder.md` "First experiments"
17. Lifepod versus crater alignment, character select on the L_SN2World path — `research/sn2/l_sn2world_map.md` "Open problems"
18. L_SN2World versus L_Main cooked differences (Task B), open — `research/sn2/l_sn2world_water_region.md` "Task B"
19. Whole-map extraction pipeline (UNTESTED) — `research/terrain/extract.md` "Whole-map pipeline"
20. Terrain import leftovers: material table, extractor beyond one cube, texture streaks, runtime mesh build — `research/terrain/import.md` "Open items for terrain import"

## Distribution target (decided 2026-11-15): the finished mod is shared with other players
- **Loader:** UE4SS, the de-facto SN2 mod loader; ship as a mod folder / zip.
- **Terrain delivery:** runtime Lua mesh generation hitches (0.27 s per 160 m chunk), has no Nanite/HLOD/streaming and costs RAM. Target: SN1 terrain as cooked static meshes in our own level (modkit, IoStore in `LogicMods\<Mod>\`) plus a thin Lua/Blueprint layer; this also satisfies "never load SN2 terrain".
- **Legal:** do not distribute data extracted from SN1; ship a converter each user runs on their own SN1 install. Checked 2026-11-19 (`sn1/legal.md` §9): no published permission covers shipping SN1 assets; pre-built SN1-derived assets need written permission from Unknown Worlds / KRAFTON.
- **Proposed (2026-11-19, user idea; design in `sn1/first_launch_builder.md` §10): first-launch builder, no editor on the user's PC.** We ship a cooked pak, a UE4SS C++ loader dll, native `sn1build.exe`, a ClassId mapping table and an SN1 file manifest; on first launch it converts the user's SN1 `Build18` data into a mesh/instance cache in `%LOCALAPPDATA%\Subnautica2\Saved\SN1World\`; the dll builds non-Nanite meshes from it at runtime. `BuildFromStaticMeshDescriptions` is in the shipping exe (string grep 2026-11-19), callability UNTESTED; if adopted it replaces the modkit-cooked target.
- **Local only, no multiplayer (user, 2026-11-19).** Hosting/joining disabled or warned. Lowers legal exposure (unconfirmed KRAFTON note). SN2 still runs its network code in solo ("Player moved too much ... Disregarding move"), so test movement checks solo.
- **Fragility:** Early Access patches can break UE4SS signatures, BP class names and World Partition cell names: prefer data-driven, name-tolerant code; avoid overriding `_Generated_` cells. Watch for official mod support (`UWEUserGeneratedContent` plugin).

## Standing project requirements
- (user, 2026-11-18) UE4SS Lua mods are allowed anywhere; cooked modkit mods stay the production path for content.
- (user, 2026-11-18) Replace the map rather than purge L_Main: `sn2/l_sn2world_map.md` "World replacement - options" (`UWELobbyStatics.SetWorldLevel`).
- The finished mod must not keep hidden SN2 terrain in RAM: destroy / never-load over hide.
- Tests are non-destructive: in-memory changes, back up saves first, touch game files only inside `ue4ss\Mods\`.
