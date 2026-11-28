# Status: what works and what is open

Sources: 00_overview.md "State of play", "Next steps", "Distribution target", "Standing project requirements" (split 2026-11-28; old text: git show 7221ba9:research/00_overview.md). Full old rows and items are in the topic files under "State of play detail" and "Next steps history".

## State of play (updated 2026-11-22)
| Capability | Status |
|---|---|
| UE4SS 3.0.1-953 injected, Lua mods load, game stable | VERIFIED; [detail](code/mods.md) |
| New Game in L_SN2World starts in the lifepod, no launch option, no Lua (single `BP_ShallowsPlayerStart_C` in the map; game launched via Steam `-applaunch`, display args only) | VERIFIED 2026-11-22, lifepod start without launch option; [detail](sn2/l_sn2world_map.md) |
| Inspect the live world (classes, properties, values, console commands) | VERIFIED (SN2WorldProbe, deleted 2026-11-23); [detail](code/mods.md) |
| Spawn any game static mesh at coordinates, with collision | VERIFIED; [detail](terrain/legacy_lua.md) |
| Remove rocks/meshes at runtime (hide or destroy) | VERIFIED; [detail](terrain/legacy_lua.md) |
| Remove heightmap landscape at runtime | VERIFIED (Ctrl+F2, then automatic regions); [detail](terrain/legacy_lua.md) |
| Auto-clear a region on load: landscape tiles + StaticMesh/Prefab/environment BPs, destroyed + GC (memory freed) | VERIFIED (about 10.6k actors, 18-21 tiles in 300 m); [detail](terrain/legacy_lua.md) |
| Custom geometry via Geometry Script `DynamicMeshActor` | VERIFIED (star prism); [detail](terrain/legacy_lua.md) |
| Terrain from a data file: 160 m, 19.6k tris, 0.27 s, rendered + collidable | VERIFIED (160 m, 19.6k tris, 0.27 s); [detail](terrain/legacy_lua.md) |
| One-call arbitrary mesh (`AppendBuffersToMesh`) for non-grid meshes (caves, overhangs) | FAILED from Lua; works from editor Python 2026-11-16; [detail](terrain/import.md) |
| Modkit editor installed, game content mounted, scripted from the shell (`ue_run.py`) | VERIFIED 2026-11-16; [detail](code/modkit_setup.md) |
| Cooked terrain mod (`SN2Terrain`: ModActor + SM_SeafloorTest, built by editor Python, packaged as pak chunk 1 in `LogicMods`) appearing in game | VERIFIED 2026-11-16, visible plus collision; [detail](terrain/import.md) |
| Terrain deletion done by the cooked mod instead of Lua (ModActor graph built by `src/modkit/scripts/sn2terrain_removal_graph.py`) | VERIFIED 2026-11-16, ModActor graph clears terrain without Lua; [detail](terrain/legacy_lua.md) |
| Never loading SN2 terrain at all (RAM requirement) | UNTESTED, design notes only; [detail](terrain/import.md) |
| Temperature / water-look / music / spawn-zone actors spawned from Lua | UNTESTED (properties known); [detail](features/placement.md) |
| Asset (pak/IoStore) mods, modkit | UNTESTED; [detail](code/modkit_setup.md) |
| New **Survival** game skips the intro, empty hotbar, only the breathing adaptation, via launch argument `-OverridePlayerStart=Shallows` (`bash src/tools/launch_game.sh`; no mod) | VERIFIED 2026-11-18, intro skipped, empty hotbar; [detail](sn2/intro_skip.md) |
| Empty SN2 world, catch-all (cooked mod `SN2EmptyWorld`: lobby sets `wp.Runtime.UpdateStreamingSources 0` → no WP cells ever load; L_Main ModActor purges every `_UAID_` map actor except the lifepod/ocean/sky keep-list) | VERIFIED 2026-11-18, empty world; default Deep start crashes (cause open); [detail](sn2/l_sn2world_map.md) |
| Game opening a map other than L_Main (`UWELobbyStatics.SetWorldLevel("/Game/...")` in the lobby) | VERIFIED 2026-11-18, other map ran as Survival game; [detail](sn2/l_sn2world_map.md) |
| Own replacement map (only lifepod + ocean + sky), `/Game/Mods/SN2EmptyWorld/L_SN2World`, selected by the lobby ModActor | PARTLY VERIFIED 2026-11-18; water surface and lifepod interior FAILED then; [detail](sn2/l_sn2world_map.md) |
| Automated in-game tests: **actions via simulated OS keyboard/mouse (`autotest_driver.py`); Lua `SN2AutoTest` is observe-only + test hotkeys**; 8 screenshots per waypoint, contact sheets, logs, no tester | VERIFIED 2026-11-18, autotest runs end to end; [detail](process/autotest.md) |
| Autotest engine input mode (`--input engine`): UE4SS file commands, `HandleButtonClicked`, IA_Look injection, PrintWindow shots, no real input; DEFAULT input mode since 2026-11-22, OS mode opt-in via `--input os`; the occluder window was removed 2026-11-22 at user request | VERIFIED 2026-11-22 (engine input mode; run without occluder UNTESTED); [detail](process/autotest_input.md) |
| Autotest death/respawn + engine load_game chain (2026-11-22) | VERIFIED 2026-11-22, death/respawn and load_game chain; [detail](process/autotest.md) |
| L_SN2World fixes (2026-11-18 evening): lifepod lighting + wall locker attached to the pod (static root -> MOVABLE first); `BP_Ocean_C` saved in the level (CollisionBoxes cleared + notify); ModActor only destroys itself in L_SN2World | Editor side VERIFIED 2026-11-18; in-game parts LOGGED; [detail](sn2/l_sn2world_pod.md) |
| Water volume fixed in the map itself (2026-11-19): standalone `BP_UWEOceanBiomeRegionActor_C` at (0,0,-5e6), scale (1e6,1e6,1e5) + origin air volume `BP_BoxVolume_C` (scale 1e5, Air, priority 10) in `L_SN2World`, independent of `BP_Ocean_C`'s construction script | COOKED package VERIFIED 2026-11-19; swimming result in detail; [detail](sn2/l_sn2world_water.md) |
| Lobby→`L_Main` load crash (GC watchdog, 22.8k objects) | NOT fixed; crashed 2026-11-18 with our Lua mods off; workaround withdrawn; [detail](crashes/gc_watchdog.md) |
| Reading Subnautica 1 terrain files | Started 2026-11-19, offline only; layouts VERIFIED; [detail](sn1/world_files.md) |
| SN1 modding/inspection: BepInEx 5.4.23.6 + `SN1Inspector` (pos, biome, batch, teleport, near, shot, newgame creative, quit) driven by `sn1_run.sh` on the hidden desktop | VERIFIED 2026-11-22, plugin runs and teleport works; [detail](sn1/modding.md) |
| SN1 placed objects (decorations, outcrops, creatures) for the origin cube, `src/tools/sn1_objects.py` | VERIFIED 2026-11-26 (offline), 12,362 baked objects decoded; [detail](sn1/objects.md) |
| SN1 reference shots (open-water point, 8 yaws + up + down) via `sn1_run.sh` | VERIFIED 2026-11-22, 10 reference shots; [detail](sn1/runs.md) |
| SN1 terrain extraction, test spot 1 (500 m cube centred on (-1245.47, -267.33, 210.45)) with `src/tools/sn1_extract_terrain.py` | VERIFIED 2026-11-22 (offline), 1.1M triangles, 0.029 m error; [detail](terrain/extract.md) |
| SN1 terrain import into L_SN2World (`src/modkit/scripts/sn1terrain_import.py`, 16 Nanite StaticMeshActors tagged `SN1Terrain`, winding `a,d,b`) | VERIFIED 2026-11-22 (editor), imported and cooked; [detail](terrain/import.md) |
| SN1 terrain visible in game at spot 1 | VERIFIED 2026-11-22 (close range); FAILED parts in detail; [detail](terrain/checks_spot1.md) |
| SN1 origin cube (500 m cube centred on Unity (0,-150,0), around the lifepod): extract, import by set, cook, SN1 reference shots, SN2 compare | VERIFIED 2026-11-23, origin cube visible, run 12/12; [detail](terrain/checks_origin.md) |
| SN1 biome water look ported to SN2 (Safe Shallows: 42 `BP_UWEWaterBiomeRegionActor_C` boxes in L_SN2World with converted SN1 fog/colour, `research/features/biome_look.md` §6) | VERIFIED 2026-11-27, underwater water look solved; [detail](features/biome_look.md) |
| Habitat Builder placement in L_SN2World (SN1 terrain) | VERIFIED 2026-11-28, builder fix via IsGroundSurface; [detail](features/base_building.md) |
| SN2 crashes seen on 2026-11-22 spot1 runs | Open, undiagnosed (two crash kinds, 2026-11-22 runs); [detail](crashes/gc_watchdog.md) |

## Next steps (agreed direction, in order)

Open items only, renumbered. Closed items (0a6, 0, 0h, 1) stay in their topic files. The old item id is in brackets; the full text is in the linked file.

1. [0a8] PAUSED by user order (2026-11-28): SN1 area import tooling; real import UNTESTED; resume when the user says so. [full text](terrain/import.md)
2. [0a7] Underwater look calibrated (VERIFIED 2026-11-28); open: sight distance, caustics, god rays, orange terrain albedo, bright ravine. [full text](features/biome_look.md)
3. [0a5] Water look SOLVED (VERIFIED 2026-11-27); next: local look from the 42 SN1 boxes (UNTESTED), regression run after map changes. [full text](features/biome_look.md)
4. [0a4] Biome porting, Safe Shallows first (2026-11-24): boxes converted (VERIFIED offline), placer UNTESTED then; the item has its own Next list. [full text](features/biome_look.md)
5. [0a3] Terrain holes FIXED, VERIFIED 2026-11-23 (non-manifold edges, extractor make_manifold); render-settings dump follow-ups in the item. [full text](terrain/import.md)
6. [0a2] Startup speed-up done (2026-11-22, 224 s vs 392 s); open: first-waypoint delay, ignored first title click, FPS drop (cause UNTESTED). [full text](process/autotest_startup.md)
7. [0a1] Autotest death handling and load_game chain work (VERIFIED 2026-11-22); open: focus/mouse-grab probe, loaded save spawns at 50000,0,-200. [full text](process/autotest.md)
8. [0a0a] Launcher uses Steam applaunch, Shallows start only (2026-11-22); open: re-verify after next game update, far_500m look timeouts. [full text](process/autotest_startup.md)
9. [0a0] Autotest default is engine input mode, no occluder (2026-11-22); next routine run confirms it (UNTESTED). [full text](process/autotest_input.md)
10. [0a] Testing is automated (2026-11-18, user decision): SN2AutoTest plus autotest.sh, 8 shots per waypoint; the item holds the full rules. [full text](process/autotest.md)
11. [0a++] Pod-component re-attach (2026-11-19): editor check PASSED, in-game FAILED (cook lacked the fix); cause LOGGED, steps in the item. [full text](sn2/l_sn2world_pod.md)
12. [0a+++] Water fix VERIFIED 2026-11-19 (sn2world swims like L_Main); next: find why L_SN2World looked darker, harness follow-ups. [full text](sn2/l_sn2world_water.md)
13. [0i] SN1 inspection available and VERIFIED 2026-11-22; next: check the SN1 to SN2 coordinate mapping with SN1Inspector. [full text](sn1/modding.md)
14. [0j] SN2 test saves deleted, harness deletes its own slot (2026-11-22); first real run of the cleanup UNTESTED then. [full text](process/autotest.md)
15. [0a+] Once the harness works, continue world-clearing tests (2026-11-18, user): water surface, lifepod interior, character select, 5 waypoints. [full text](process/autotest.md)
16. [0b gc] Fix the lobby to world GC-watchdog crash (2026-11-18): NOT fixed; ON-only run mode and hand checks are next. [full text](crashes/gc_watchdog.md)
17. [0b cur] Current phase (since 2026-11-16): replace the SN2 world; intro skip DONE; lifepod versus crater alignment remains. [full text](sn2/l_sn2world_map.md)
18. [2] Extend the clearing allow-list (Environment, CoralPads, BP_AcidAnemone, DecalActor, PointLight). [full text](terrain/legacy_lua.md)
19. [3] SN1 terrain: items (a) to (c) and steps 2 to 4 (open edges, material table, streaming, runtime mesh build) are open. [full text](terrain/import.md)
20. [4] Streaming design for many chunks and the never-load-SN2-terrain RAM requirement. [full text](terrain/import.md)

## Distribution target (decided 2026-11-15): the finished mod will be shared with other players
Implications for the architecture (analysis, not yet tested):
- **Loader:** keep UE4SS — it is the de-facto SN2 mod loader (CurseForge/Nexus mods depend on it; CurseForge installs it). Ship as a mod folder / zip.
- **Terrain delivery:** the runtime Lua mesh generation proven here is for prototyping. For a whole map it will hitch (0.27 s per 160 m chunk on the game thread),
  has no Nanite/HLOD/proper streaming, and costs RAM. Target: SN1 terrain converted into **cooked static meshes / landscape in our own level**, built with the
  Subnautica2-Project modkit and packaged as IoStore (`LogicMods\<Mod>\` or `~mods\`), with a thin Lua/Blueprint layer that loads our level and skips/clears SN2's.
  This also satisfies the "never load SN2 terrain" RAM requirement.
- **Legal:** do not distribute data extracted from Subnautica 1. Ship a **converter** each user runs against their own SN1 install to produce the terrain
  (or the cooked assets, if the build step can run locally — open question; cooking needs the editor). Policy checked 2026-11-19 (`research/sn1/legal.md` §9): no published permission covers
  shipping SN1 assets. Option 3 (ship pre-built SN1-derived assets) needs written permission from Unknown Worlds / KRAFTON.
- **Proposed direction (2026-11-19, user idea, design in `research/sn1/first_launch_builder.md` §10): first-launch builder, no editor on the user's PC.**
  - We ship: a cooked pak (level, materials, progress widget, streaming Blueprint), a UE4SS C++ loader dll, a native `sn1build.exe`, a ClassId→SN2 mapping table and an SN1 file manifest.
  - On first launch the builder converts the user's SN1 `Build18` data into a mesh/instance cache in `%LOCALAPPDATA%\Subnautica2\Saved\SN1World\`.
  - The dll builds non-Nanite meshes from that cache at runtime. `BuildFromStaticMeshDescriptions` is present in the shipping exe (string grep 2026-11-19); callability UNTESTED.
  - If adopted, this replaces the "cooked static meshes built with the modkit" target above for SN1 terrain. The modkit stays for everything SN1-independent.
- **Local only, no multiplayer (decided 2026-11-19, user).** The mod supports single player only. While the SN1 world is active, the mod disables or hides
  hosting and joining, or warns if either is attempted. No cache-matching between players and no co-op sync work.
  - Rationale: this lowers legal exposure. The unconfirmed KRAFTON clarification says "no multiplayer tampering" (`research/sn1/legal.md` §9).
  - SN2 probably still runs its own network/server code in solo play. The game log shows server-side move rejection in solo: "Player moved too much ... Disregarding move".
  - So "local only" means no co-op support, not that the network code is absent. Movement checks against our terrain still need testing in solo.
- **Fragility:** Early Access patches can break UE4SS signatures, BP class names, and World Partition cell names; prefer data-driven, name-tolerant code and
  avoid overriding `_Generated_` cells. Watch for official mod support (`UWEUserGeneratedContent` plugin and `DefaultUWEUserGeneratedContent.ini` ship in the game).

## Standing project requirements
- (user, 2026-11-18) UE4SS Lua mods ARE allowed for any part of the work (an earlier "not Lua" was a misunderstanding); cooked modkit mods remain the production path for content.
- (user, 2026-11-18) Preferred world-removal direction: **replace the map** rather than purge L_Main — see `research/sn2/l_sn2world_map.md` "World replacement — options" (built-in `UWELobbyStatics.SetWorldLevel`).
- Finished mod must not fill RAM with hidden Subnautica 2 terrain → prefer destroy/never-load over hide.
- Keep testing non-destructive: in-memory changes only; back up saves before risky tests; game files are only touched inside `ue4ss\Mods\`.
- Keep these research notes up to date as work happens (see project `CLAUDE.md`).
