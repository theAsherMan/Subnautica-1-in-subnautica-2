# Modkit scripting: editor tasks, cook, GraphTools

Sources: 07_mods_reference.md "SN2GraphTools additions + changed editor scripts (2026-11-18", 08_modkit_setup.md "First editor task (planned 2026-11-15): redo the Lua terrain" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## SN2GraphTools additions + changed editor scripts (2026-11-18, evening)
New editor-only `unreal.SN2GraphLibrary` functions (source `src/modkit/plugins/SN2GraphTools`, copy kept in sync in `<ModkitDir>\Subnautica2-Project\Plugins\SN2GraphTools`; reflection only, no Water module dependency; build OK 289 s, Python exposes them - **VERIFIED 2026-11-18** and used in the editor):
- `describe_object_array(obj, "PropName") -> [str]`: one line per element `"<idx> <element path> outer=<outer path>"`; `["MISSING <name>"]` if absent or not an array of object pointers.
- `clear_object_array(obj, "PropName") -> int`: `Modify()`, empties the array, returns the removed count, -1 if missing / wrong type.
- `notify_property_changed(obj, "PropName")`: `PreEditChange(prop)` + `PostEditChangeProperty(FPropertyChangedEvent(prop, ValueSet))`.
`src/modkit/scripts/sn2world_map.py`: ocean now copied with the level (`RUNTIME_SPAWNED = ()`, `NOT_COPIED = (BP_UWEOceanBiomeRegionActor_C,)`); step 4b sets lighting/locker root mobility MOVABLE and attaches them to the pod (KEEP_RELATIVE); step 4c clears the ocean's `CollisionBoxes`/`CollisionHullSets` and calls `notify_property_changed(comp, "CollisionExtents")`; the check requires pod attach parents + expected world transforms and 1 biome region parented to the ocean. `src/modkit/scripts/sn2emptyworld_graph.py`: the L_SN2World branch only destroys the ModActor (106 nodes). Details and results in `research/sn2/README.md`.
`sn2world_map.py` update 2026-11-19: step 4b sets the pod `RootComponent` STATIC (modkit class default is MOVABLE, game is STATIC); step 4d attaches the nine pod components (KEEP_RELATIVE, stay STATIC, no MOVABLE fallback); `check_pod()` runs in memory and again after save + reload from disk (step 7, `die()` on failure). `pod_components_probe.py` also logs the class CDO root. `src/modkit/tools/cook_install.sh` has a cook guard: `AttachTo: ... Aborting` lines for `/Game/Mods/<MOD>/` in the cook log -> exit 3, no install, unless `SN2_ALLOW_ATTACH_ABORTS=1` (see `research/code/modkit_setup.md`).
`sn2world_map.py` update 2026-11-19 (water): `KEEP` gained `BP_BoxVolume_C` (only the origin air volume, `keep_source()`); `NOT_COPIED = (REGION_CLS,)` again (EDIT COPY cannot copy a child actor) but the region is now SPAWNED as a standalone actor in step 4e (class from L_Main's child, transform = our ocean actor + L_Main offset (0,0,-5e6), scale (1e6,1e6,1e5)); helpers `comp_rows`, `snapshot`/`apply_snapshot` (copy Python-readable differing properties from L_Main's child), `paste_region_with_water_light` (T3D round trip that injects `WATER_LIGHT_SETTINGS` into the `BiomeVolumeComponent`, not exposed to Python); `check_region(tag)` (standalone transform + per-component world scale/location vs L_Main, air volume transform and Z relative to the ocean) runs in `[memory]` and `[reload]`. `MAIN` dict = L_Main reference values captured before `new_level`. Details and cooked-file results in `research/sn2/l_sn2world_water.md` "Standalone water region + origin air volume implemented in the map". Offline tooling used (not in the repo): `<ModkitDir>\scratch_bp\uaa\uaa\bin\Debug\net8.0\uaa.exe <usmap> <outdir> <umap>` (JSON dump of a legacy map), `scratch_bp\sn2w_all2` / `sn2w_leg2` / `sn2w_json2` (our cook), `scratch_bp\lmain_json` (shipped L_Main, 425 MB JSON).
- SN2AutoTest observe-only additions (2026-11-18): after every `STATE` and at `SETTLED` a line `BASE comp=<full name> owner=<actor> loc=(x,y,z) rot=(p,y,r)` (pawn movement base; `BASE none` + a `BASEFLOOR ...` line from a downward `LineTraceSingle` when there is no base, which is the usual case). The SETTLED pod component dump (PODDUMP) and `src/tools/pod_diff.py` were removed 2026-11-26 after they crashed UE4SS (`research/process/core_rules.md` "Crashes"); recover with `git show a3fa5e5:src/mods/SN2AutoTest/Scripts/main.lua` and `git show a3fa5e5:src/tools/pod_diff.py`. Findings they produced: `research/sn2/l_sn2world_pod.md` "Pod component diff".


- `src/modkit/scripts/ocean_compare_probe.py` (2026-11-19): read-only editor probe, `[OCEANPROBE]` lines: components/scales/mobility/CollisionBoxes/properties of every water-like actor in L_Main and L_SN2World plus the `BP_Ocean_C` CDO. Output is large (L_Main has ~60 EdgeOfWorld volumes); filter with grep. `sn2world_map.py` now sets ocean `BodySize` (step 4c0) and has `check_ocean()` (memory + reload); `SN2AutoTest` logs `WATER ...` per STATE and always dumps ocean/biome-region/WaterZone rows (see `research/sn2/l_sn2world_water.md` "Water physics").

- `SN2WaterFix` (runtime ocean repair) was REJECTED 2026-11-19 and deleted (the map must be fixed at source; see `research/sn2/README.md`). `SN2AutoTest` gained `WATER` (3 physics-volume reads + IsSwimming/IsInWater), `OCEAN` (runtime BodySize) and one-time `WATERCENSUS` lines.
- `src/tools/check_lua_ctl.py` (2026-11-19): exits 1 and prints file:line for raw control characters (CR etc., TAB/LF allowed) in Lua; called by `install_mod.sh`. `autotest_driver.py` result `FAIL_LUA_LOAD` (UE4SS.log `Error loading script` for an SN2* mod during the lobby wait). `SN2AutoTest` and `SN2Census` converted to LF-only 2026-11-19. See `research/process/README.md` Lua rules.
- `autotest_screens.py` / `screen_labels.json` / `screens.json` (2026-11-19): fingerprints support per-screen `mask` rects (save rows of `save_list`), `extra` and `not_o` label entries; offline check 0 misidentified on 448 shots; see `research/process/README.md`.

## First editor task (planned 2026-11-15): redo the Lua terrain test as cooked content
Goal from the tester: repeat "delete terrain + add custom terrain" using the editor instead of Lua.
- **Custom terrain → editor asset.** Inputs ready in `<ModkitDir>\import\` (made by `src\tools\heightfield_to_unreal.py` from the Lua test file):
  `seafloor_test.obj` (101×101 verts, 20,000 tris, cm, Z up, centred, UV 1 = 4 m, normals) → import as Static Mesh, Nanite on, complex-as-simple collision;
  `seafloor_test_h16.png` + `_h16.json` (16-bit heightmap, ScaleXY 160, ScaleZ 4.7989, actor Z = min height + 1228.5 cm) → alternative Landscape import.
  Material: reference a cooked SN2 rock material (e.g. the one on `SM_CG_RockScatterSmall_04a` / `SM_CG_RockRubble_BoulderMed_6a`).
  Target position = the Lua test: centre (-331747, 420670), Z ≈ -6224 (old landscape mean).
- **Placement:** a mod Blueprint (`Content/Mods/<Mod>/ModActor`, loaded by UE4SS BPModLoader from `LogicMods`) that spawns the mesh actor at the target, or a
  streamed sublevel. Packaging via SN2 Mod Tools "Cook & Install" (pak chunk id 1–300).
- **Deletion stays a runtime step.** `L_Main` is cooked and opens read-only in the modkit — edits cannot be saved. Options: (a) port the Lua region sweep
  (destroy landscape proxies + dressing in radius, then GC) into the ModActor Blueprint (`GetAllActorsOfClass`, `DestroyActor`, `CollectGarbage` are all BP-callable),
  (b) keep the Lua sweep and ship it alongside, (c) override `_Generated_` cells (rejected: breaks every patch).
- **Automation:** prefer driving the editor with Python (`UnrealEditor-Cmd.exe <uproject> -run=pythonscript -script=<file>` or the Python console) for imports,
  material assignment and asset creation; Blueprint graphs are hard to author from Python — expect the tester to build the ModActor graph by hand from instructions,
  or check whether the modkit allows C++ mod code.

### Driving the open editor from the shell (2026-11-16)
- `src\modkit\tools\ue_run.py` (+ copy of the engine's `remote_execution.py` beside it): `python -I ue_run.py <file.py>` runs a file in the editor,
  `python -I ue_run.py -c "<stmt>"` evaluates one statement; prints the editor's output. Needs editor setting Project Settings → Plugins → Python →
  **Enable Remote Execution?** (UDP multicast 239.0.0.1:6766 bound to 127.0.0.1, TCP 127.0.0.1:6776). Before it is enabled: `NO EDITOR FOUND` (exit 2).
- **Heavy lock (2026-11-19):** `ue_run.py` exits 5 (`HEAVY LOCK NOT HELD`) unless this session holds `src/tools/heavy_lock.sh`. VERIFIED in a scratch-dir test.
  - Open the editor with `bash src/modkit/tools/launch_editor.sh`, which acquires `editor` and then runs `Launch-Editor.cmd`. It is UNTESTED with a real launch.
  - `cook_install.sh` acquires `cook`.
  - See `research/process/heavy_lock.md` "Parallel sessions".
- Fallback: the tester types `py "src/modkit/scripts/<file>.py"` in the editor's bottom `Cmd` box. Script output goes to `Saved\Logs\Subnautica2.log` (`LogPython`).
- SN2 Mod Tools facts (source `Plugins\SN2ModTools\Source\SN2ModTools\Private\ModActions.cpp`): "New mod" = `BlueprintFactory(ParentClass=AActor)` → `Content/Mods/<Mod>/ModActor`
  + `PrimaryAssetLabel` `PAL_<Mod>` (ChunkId = lowest unused 1–300, CookRule AlwaysCook, bLabelAssetsInMyDirectory). "Cook & Install" runs
  `RunUAT BuildCookRun -platform=Win64 -clientconfig=Shipping -build -cook -stage -pak -iostore -archive -archivedirectory=<project> -nocompileeditor -installed -iterativecooking -cookincremental`,
  then copies `pakchunk<id>-*` into `<GameDir>\Subnautica2\Content\Paks\LogicMods\<Mod>\` (renamed to `<Mod>.*`). GameDir = parent of the path in
  `GameInstallDirectory.txt` if it contains `Subnautica2.exe` → our inner-folder entry resolves correctly.

### Terrain test script: `src\modkit\scripts\sn2terrain_build.py` — asset build VERIFIED in editor 2026-11-16 (in-game UNTESTED)
Run result (9.0 s total): PAL_SN2Terrain **chunk_id=1** (DemoMod uses 14); `append_buffers_to_mesh` OK (10,201 verts / 20,000 tris; returns a tuple);
triangle winding a,b,d / a,d,c (CCW seen from +Z) gives face normal **-Z** in UE → script calls `GeometryScript_Normals.flip_normals` (so for UE buffers use
**a,d,b / a,c,d** to face up); asset creation 7.5 s; material resolved to `/Game/Art/Environment/Biome/CoralGarden/Rocks/Material/MI_CG_RockSmooth_01a`;
bounds origin (0,0,378) extent (8000,8000,1228). Gotchas:
- Python class names are the ScriptNames: `unreal.GeometryScript_MeshEdits` (append_buffers_to_mesh, set_vertex_position…), `GeometryScript_MeshQueries`,
  `GeometryScript_Normals`, `GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)` → `(StaticMesh, GeometryScriptOutcomePins.SUCCESS)`.
  `unreal.GeometryScript_MeshBasicEditFunctions` does NOT exist (AttributeError).
- `GeometryScriptCreateNewStaticMeshAssetOptions.enable_nanite=True` did **not** enable Nanite → set `mesh.nanite_settings.enabled=True` afterwards.
  With Nanite on, the fallback LOD0 dropped to 398 verts (and `lod_for_collision=0` → collision would use it) → set `fallback_target=PERCENT_TRIANGLES`,
  `fallback_percent_triangles=1.0` → 10,201 verts. (For full-map terrain, revisit: separate simplified collision vs full-res fallback.)
- `SubobjectDataBlueprintFunctionLibrary.get_object` is deprecated (use `get_associated_object`) but works.

### Cook + install (2026-11-16)
- **Cook guard (2026-11-19, `cook_install.sh`):** after the cook it greps the log for `AttachTo: .* Aborting` lines mentioning `/Game/Mods/<MOD>/`, prints them (counted, truncated) and exits 3 WITHOUT installing, unless `SN2_ALLOW_ATTACH_ABORTS=1` (known benign: the ocean `WaterBodyOceanComponent ... WaterSpline` line). Reason: the cooker silently drops attaches it cannot do (STATIC child on a MOVABLE parent) and an editor in-memory check does not show it. Caveat: an incremental cook with `Packages Cooked: 0` logs no aborts, so the guard only sees them on the run that recooked the map. Closing the editor: `python -I src/modkit/tools/ue_run.py -c "unreal.SystemLibrary.execute_console_command(unreal.EditorLevelLibrary.get_editor_world(), 'QUIT_EDITOR')"`. VERIFIED 2026-11-19 (guard fired exit 3 on the ocean lines, install with the override worked).
- Ran the Mod Tools BuildCookRun command myself (TEMP in <ModkitDir>; now scripted as `src/modkit/tools/cook_install.sh`) → `<ModkitDir>\cook_SN2Terrain.log`. First run: UAT exit 6 (VS instance invisible, see the VS cache trap in the caches table).
  Second run: **BUILD SUCCESSFUL** — build (UBT, Subnautica2 Win64 Shipping) 698 s, cook 428 s (`Packages Cooked: 615 ... Total 624`), UnrealPak ~20 s.
  Re-cooks are incremental (`-iterativecooking -cookincremental`) and should be much faster.
- Output: `Subnautica2-Project\Windows\Subnautica2\Content\Paks\pakchunk1-Windows.{pak 339 B, ucas 3.4 MB, utoc}` (2 packages: SM_SeafloorTest + bulk, ModActor);
  `pakchunk0` (≈350 MB, modkit content — never install), `pakchunk14` = DemoMod. Inspect with `retoc.exe list <utoc>` (run from a scratch cwd —
  `retoc manifest` writes `pakstore.json` into the cwd).
- Installed to `<GameDir>\Subnautica2\Content\Paks\LogicMods\SN2Terrain\SN2Terrain.{pak,ucas,utoc}`; `BPModLoaderMod : 1` in mods.txt.
  Uninstall = delete that folder. Saves backed up to `save_backups\20261116_192519`. Lua SN2TerrainEdit set to `fillWithTestPatch = false` (still clears the region).
- **In-game result VERIFIED 2026-11-16:** UE4SS log `[BPModLoaderMod] Mod: SN2Terrain ... AssetPath == /Game/Mods/SN2Terrain/ModActor`, then
  `Loading mod: SN2Terrain` on every world load (twice in the lobby `L_ClientLobby`, once on save load into L_Main). The tester: the patch "exists, and has collision"
  at the expected spot (player reached it at Z ≈ -5800). → BPModLoader spawns ModActor at the **world origin**, so a component's relative location = world location.
  Note the ModActor (and its 160 m mesh) is also spawned in the lobby map — harmless for now; gate by world name in the graph later.
  Lua clearing in the same session: 22 proxies → 4 after GC, 18 destroyed, ~8.9k dressing actors.

### SN2GraphTools editor plugin (ours, 2026-11-16) — lets Python author Blueprint graphs
- Source: `<ModkitDir>\Subnautica2-Project\Plugins\SN2GraphTools\` (Editor module, `EnabledByDefault`, PostEngineInit; deps UnrealEd, BlueprintGraph, Kismet, KismetCompiler).
  Python: `unreal.SN2GraphLibrary` — `get_event_graph, clear_graph, add_event_override(bp, g, "ReceiveBeginPlay", x, y), add_custom_event (delegate pin "OutputDelegate"),
  add_call_function(g, Class.static_class(), "FnName", x, y)` (KismetArrayLibrary fns get `UK2Node_CallArrayFunction`), `add_standard_macro("ForEachLoop")`,
  `add_branch, add_sequence(n), add_self, add_member_variable(bp, name, "real"/"int"/"bool"/"struct", sub, obj, is_array, default), add_variable_node(bp, g, name, setter)`,
  `set_pin_default, set_pin_default_object, connect(a, pin, b, pin) -> (ok, msg)` (pin by PinName or display name), `describe_pins(node)`, `compile_with_log(bp) -> (ok, [msgs])`.
  Compile variables first (`compile_with_log`) so getter/setter nodes resolve on the skeleton class.
- Build: `Engine\Build\BatchFiles\Build.bat Subnautica2Editor Win64 Development -Project=<uproject> -WaitMutex -NoHotReloadFromIDE` with TEMP in <ModkitDir>, editor closed.
  First build recompiles all project editor plugins (78–123 actions, 640 s). A run killed by RAM pressure (other apps using memory) left the log cut off mid-list with exit 4 —
  just rerun; finished actions are kept. `-MaxParallelActions=4` lowers RAM use.
- **Build 2026-11-18 (3 new reflection functions, see `research/code/README.md`):** `Build.bat Subnautica2Editor Win64 Development -Project=<uproject> -WaitMutex -NoHotReloadFromIDE -MaxParallelActions=4`, editor closed, TEMP in `<ModkitDir>\Temp`: 6 actions, **289 s, Result: Succeeded**. Started from a `.cmd` wrapper (log `<ModkitDir>/build_graphtools_ocean.log`). After the build the editor (started with `Start-Process Launch-Editor.cmd`; `cmd /c start` from Git Bash did NOT start it) took ~15 min until `ue_run.py` connected; early attempts fail with `NO EDITOR FOUND` and then `Remote party failed to attempt the command socket connection!` (editor still starting) - just retry. Cook with the editor closed: `cook_install.sh SN2EmptyWorld 2` = 116 s, BUILD SUCCESSFUL (VERIFIED 2026-11-18).
- **UE Python gotchas (2026-11-16):** (1) Kismet libraries are renamed in Python (`unreal.KismetMathLibrary` → AttributeError; it is `MathLibrary`) — load by path
  instead: `unreal.load_class(None, "/Script/Engine.KismetMathLibrary")`. (2) A UFUNCTION returning `bool` with out-params returns **only the out-params, or `None`
  when the bool is false** (`connect` → message str / None; `compile_with_log` → [msgs] / None). (3) Class pins don't connect to Object pins (GetObjectClass →
  GetPathName refused) → use `GetClassDisplayName(Class)` and `Conv_ClassToSoftClassReference` → `Conv_SoftClassReferenceToString`. (4) `GetCurrentLevelName` is
  impure (exec pins) — off the exec chain it is pruned ("was pruned because its Exec pin is not connected"). `GetActorBounds` likewise checked at build time.
- Removal graph built 2026-11-16: 87 nodes, 0 connect errors, compile clean, ModActor saved; CDO vars verified (RegionCenter (-331747,420670,0), RegionRadius 30000),
  Seafloor component intact. In-game behaviour UNTESTED.
- Graph script for the removal port: `src\modkit\scripts\sn2terrain_removal_graph.py` (rules = Lua isDressing/regionFor; counters SweepCount, ScanCount, TilesDestroyed,
  DressingDestroyed, LastStaticMeshCount, bActive as public vars; lobby → ModActor destroys itself). Lua SN2TerrainEdit: `LUA_REGION_REMOVAL = false`, logs the
  ModActor counters + landscape counts on change, F1 teleports above the cooked patch.

### Earlier plan notes for this script
Creates mod `SN2Terrain` (ModActor + PAL, same as New mod), builds `/Game/Mods/SN2Terrain/SM_SeafloorTest` from
`src\mods\SN2TerrainEdit\data\seafloor_test.txt` via `GeometryScript_MeshBasicEditFunctions.append_buffers_to_mesh`
(arbitrary triangle buffers — the call that FAILED from Lua) → `GeometryScript_CreateNewAsset.create_new_static_mesh_asset_from_mesh` (Nanite, complex-as-simple),
material from `SM_CG_RockRubble_BoulderMed_6a` slot 0, then adds StaticMeshComponent `Seafloor` to ModActor at relative (-331747, 420670, -6224) —
assumes BPModLoader spawns ModActor at the world origin (UNTESTED). Deletion of SN2 terrain stays in Lua (SN2TerrainEdit regions) for this test; porting it
to the ModActor graph is the follow-up.

### Editor Python: AssetUserData on a StaticMesh (2026-11-28, VERIFIED in editor, in game via `04`)
- `cls = unreal.load_class(None, "/Script/UWEAssetRegistry.UWEAssetUserData")`; `mesh.add_asset_user_data_of_class(cls)` returns the object; `mesh.get_asset_user_data_of_class(cls)` reads it back. The array property is PascalCase: `ud.set_editor_property("DataAssets", [...])` (`data_assets` raises `Failed to find property`). `unreal.load_asset("/Game/Data/SurfaceSpawnData/DA_SandSurfaceData")` works (reported as PrimaryDataAsset). Call `mesh.modify()` and `eal.save_asset(path, only_if_is_dirty=False)`.
- The editor keeps imported modules between `ue_run.py` runs: a shared helper next to the script needs `sys.path.insert(0, dirname(__file__))` and `importlib.reload(mod)`. `__file__` is defined in `MODE_EXEC_FILE`.
- `ue_run.py -c "unreal.SystemLibrary.quit_editor()"` closes the editor cleanly. VERIFIED (2026-11-28).
- `launch_editor.sh` fails if another session takes the idle lock between acquire and launch; use `SN2_LOCK_WAIT=<s>` to acquire and launch in one command.
