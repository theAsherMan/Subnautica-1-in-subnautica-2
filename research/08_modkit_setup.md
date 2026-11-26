# Modkit setup (Subnautica2-Project cooked editor)

Why: distribution target is cooked terrain assets (see `00_overview.md` → Distribution target). The modkit is a UE 5.6 editor that mounts the game's cooked content
read-only and packages mods as IoStore pak chunks / content-only plugins.

## Requirements and reference timings
- ~60 GB free for `<ModkitDir>` (any drive; an HDD works but is slow). 16 GB RAM is the practical minimum: editor + game together are tight, and a
  parallel C++ build can be killed by memory pressure (see SN2GraphTools build notes).
- Visual Studio 2022 Community with C++ desktop + game workloads and MSVC toolset **14.38** (newer toolsets alone are rejected).
- Timings in these notes were measured on a mid-range 6-core desktop with the modkit on an HDD; expect faster on an SSD.

## Layout
| Path | Content |
|---|---|
| `<ModkitDir>\Subnautica2-Project\` | git clone of github.com/Subnautica2Modding/Subnautica2-Project, commit `827162c` (2026-10-07, "update for v0.1.2.2 (131439)" — matches game build CL-131439), latest tag `sn2-v0.1.2.0` |
| `<ModkitDir>\downloads\` | engine + FMOD archives |
| `<ModkitDir>\UE_5.6_SN2\` | the custom engine (short path, no spaces) |
| `<RepoDir>\src\modkit\` | our side: `Launch-Editor.cmd`, `tools\` (ue_run.py, cook_install.sh, splitzip.py), `scripts\` (editor Python), `plugins\SN2GraphTools` (source, copied into the project's `Plugins\`) |

## Steps and status
| # | Step | Status |
|---|---|---|
| 1 | Clone project (654 MB incl. later banks) | VERIFIED 2026-11-15 |
| 2 | `GameInstallDirectory.txt` → `<GameDir>\Subnautica2` (the **inner** folder: scripts append `Content\FMOD\Desktop`; Alpakit installs plugins to `<dir>\Mods\`) | VERIFIED 2026-11-15 |
| 3 | `copy-fmod-banks.ps1` → 162 banks, 440 MB into `Content\FMOD\Desktop` (gitignored). **Re-run after every game update.** | VERIFIED 2026-11-15 |
| 4 | VS Installer: add component `Microsoft.VisualStudio.Component.VC.14.38.17.8.x86.x64` → toolset **14.38.33130** installed beside 14.40.33807. Must be launched elevated (`Start-Process ... -Verb RunAs`); non-elevated `--passive` fails with exit 5007 | VERIFIED 2026-11-15 |
| 4b | Optional: keep Unreal/VS caches and temp files inside `<ModkitDir>` instead of the system drive. See "Keeping caches off the system drive" below | done on the reference machine |
| 5 | User: link Epic account ↔ GitHub, accept the EpicGames org invite; without it github.com/Buckminsterfullerene02/UnrealEngine returns 404 (confirmed) | manual step |
| 5/6 | Engine release "SN2-Engine-V4" = byte-split zip `SN2-Engine-V4.zip.001`–`.004` (3 × 1,992,294,400 B + 1,121,483,344 B = 7.10 GB) in `<ModkitDir>\downloads\`. Index: **243,797 members, 17.32 GiB unpacked**, single root `Engine/` (Plugins 8.0, Binaries 5.6, Source 1.5, Content 1.1, Intermediate 0.95 GiB). (A stray `Unconfirmed 524443.crdownload`, 1.68 GB, is an abandoned browser duplicate — safe to delete.) | VERIFIED 2026-11-15 |
| 7 | User: fmod.com account → FMOD for Unreal 2.03.x for UE 5.6 Win64 (e.g. `fmodstudio20309ue5.6win64.zip`) into `<ModkitDir>\downloads\`. **Hard prerequisite**: repo ships `UnrealEditor-FMODStudio*.dll` but not FMOD's native `fmod.dll`/`fmodstudio.dll`/`*_vc.lib`/`resonanceaudio.dll` (license) → FMODStudio plugin cannot load without them | manual step |
| 8 | `powershell -ExecutionPolicy Bypass -File setup-fmod.ps1 -FMODPluginZip <zip>` (copies the 9 native files from `FMODStudio\Binaries\Win64\` in the zip into `Plugins\FMODStudio\Binaries\Win64\`; it unzips to `%TEMP%\fmod_ue56_setup` → run with `$env:TEMP='<ModkitDir>\Temp'`). Used `fmodstudio20315ue5.6win64.zip` (2.03.15). Zip also has `fmod_haptics.dll`, which the script does not copy — if the editor log complains about it, copy it manually | VERIFIED 2026-11-15 (9 files present) |
| 9 | Extract engine with `src\modkit\tools\splitzip.py` (reads the `.001…` parts as one virtual stream — no 7 GB concatenation, no 7-Zip needed; `list`/`test`/`extract`, CRC checked on extract, rejects `..` paths): `python -I tools/splitzip.py extract <ModkitDir>/downloads/SN2-Engine-V4.zip.001 <ModkitDir>/UE_5.6_SN2` → `<ModkitDir>\UE_5.6_SN2\Engine\...`; log `<ModkitDir>\extract_engine.log`. Took 764 s on an HDD; uses ~18 GB. Result: UE **5.6.1** (`Build.version` CompatibleChangelist 43139311), **installed build** (`Engine\Build\InstalledBuild.txt`), no `UnrealVersionSelector.exe` → "Switch Unreal Engine version" is unavailable; registered by hand instead: HKCU `Software\Epic Games\Unreal Engine\Builds` value `{<new GUID>}` = `<ModkitDir>/UE_5.6_SN2`, and the same GUID written to `"EngineAssociation"` in `Subnautica2.uproject` | VERIFIED 2026-11-15 |
| 9a | Enabled `PythonScriptPlugin` (Editor-only `TargetAllowList`) in `Subnautica2.uproject` — engine ships it prebuilt (`Plugins\Experimental\PythonScriptPlugin\Binaries\Win64`), `EnabledByDefault: false`. `EditorScriptingUtilities`, `GeometryScripting`, `ModelingToolsEditorMode` were already enabled. Local uncommitted edits in the project now: `Config/DefaultEngine.ini`, `GameInstallDirectory.txt`, `Subnautica2.uproject` | VERIFIED 2026-11-16: `LogPython: Using Python 3.11.8` on first editor launch |
| 10a | First launch log notes (2026-11-16): harmless — `LogWindows: Failed to load 'aqProf.dll'/'VtuneApi*.dll'/'WinPixGpuCapturer.dll'/'amfrt64.dll'` (optional profilers/AMD encoder), `LogTargetPlatformManager: Failed to load module 'IOS/Mac/TVOSTargetPlatform'` (stripped platforms), `LogAudio: Failed to load Default SoundClassObject from path ''`. Watch: `LogFMOD: Error: Failed to load bank lookup` / `asset lookup` right after FMOD DLL load (fmodL.dll/fmodstudioL.dll loaded OK) — probably the lookup asset is read before game content mounts; affects audio preview only (UNTESTED whether it resolves) | noted |
| 9b | Project ships prebuilt editor binaries (`Binaries\Win64\UnrealEditor-Subnautica2.dll`, SN2ModTools, Alpakit) → first open should need little/no compile | noted |
| 9c | `src\modkit\Launch-Editor.cmd` — sets `TEMP`/`TMP=<ModkitDir>\Temp`, `UE-LocalDataCachePath=<ModkitDir>\DDC`, then starts `UE_5.6_SN2\Engine\Binaries\Win64\UnrealEditor.exe <uproject>`. Always launch the editor through it | written 2026-11-15 |
| 10 | Open via `Launch-Editor.cmd`. First launch 2026-11-16: no compile prompt; `Engine is initialized` after ~14 min, `Total Editor Startup Time, took 965.101` s (HDD). Content mount (log): `[ModKit] Game install path ... (from GameInstallDirectory.txt)` → mounted `global.utoc` + `Subnautica2-Windows.utoc` (EntryCount 44002, unsigned) → `[Modkit] Populated cooked package dependencies ...: 19107 packages, 151583 hard edges`. Only `Error:` lines in the whole log: the two LogFMOD lookup errors. Hide `BP_Ocean` when viewing levels | VERIFIED 2026-11-16 (the tester screenshot: Content shows `_EditorScripts, Art, Audio, Blueprints, Data, Debug, DynamicClasses, External, FMOD, Fonts, ForceFeedback, Gameplay, GameplayCueNotifies, GameTests, Maps`, … 30 items; no shader backlog; toolbar has **Mod Tools** menu + **Modding** main menu; startup map is an `Untitled` open-world template with a Landscape, not SN2). UE5 layout: Content Browser = "Content Drawer" (bottom-left, Ctrl+Space); bottom bar has `Cmd` console box (switchable to Python) |

## Keeping caches off the system drive (optional; done on the reference machine)
| Writer | Default location | Redirect | Status |
|---|---|---|---|
| VS installer package cache | `C:\ProgramData\Microsoft\VisualStudio\Packages` (~5.5 GB) | HKLM `SOFTWARE\Microsoft\VisualStudio\Setup`: `CachePath=<ModkitDir>\VSPackageCache`, `KeepDownloadedPayloads=0` (elevated PowerShell `New-ItemProperty`); purging old payloads needs an elevated `setup.exe modify --installPath ... --nocache --passive`. Keep the `_Instances` folder — never delete the cache dir by hand | registry VERIFIED 2026-11-15 (future payloads go to the new path, not kept). Purge FAILED: a no-change `modify --nocache` exits 1 after 2 s with no reason in `%TEMP%\dd_installer_*.log`; old payloads stay until a real modify/update runs or they are removed via the Installer UI. **TRAP (found 2026-11-16):** the Setup Configuration API / `vswhere` reads instance records from `<CachePath>\_Instances`; after the redirect `vswhere -all` returned **nothing**, so UBT failed with `No valid Visual C++ toolchain was found (minimum version 14.38.33130...)` / `Visual Studio 2022 x64 must be installed` (UAT exit 6) although `VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64\cl.exe` exists. Fix: copied `C:\ProgramData\Microsoft\VisualStudio\Packages\_Instances` (27 MB, instance `<instance id>`) to `<ModkitDir>\VSPackageCache\_Instances` (original kept) → vswhere shows the instance (17.10.35122.118, isComplete 1). If CachePath is ever changed again, move `_Instances` with it |
| UE local DDC (classic) | `%LOCALAPPDATA%\UnrealEngine\Common\DerivedDataCache` | user env `UE-LocalDataCachePath=<ModkitDir>\DDC` | set 2026-11-15 |
| UE Zen storage server (UE 5.4+ default local DDC backend) | engine `BaseEngine.ini` `[Zen.AutoLaunch] DataPath=%ENGINEVERSIONAGNOSTICINSTALLEDUSERDIR%Zen/Data` (= `%LOCALAPPDATA%\UnrealEngine\Common\Zen\Data`); same section has `LocalDataCachePathEnvOverride=UE-LocalDataCachePath` (so the env var already steers it) | appended `[Zen.AutoLaunch] DataPath=<ModkitDir>/Zen/Data` to the project's `Config/DefaultEngine.ini` (**local uncommitted edit** — `git stash` before pulling modkit updates, re-apply after) | VERIFIED 2026-11-16 (first editor log): the env var wins over `DataPath` — `LogZenServiceInstance: Found local data cache path=<ModkitDir>\DDC` → zenserver launched with `--data-dir "<ModkitDir>\DDC\Zen"` (port 8558). The `DataPath` ini edit is therefore redundant (harmless). Only `zenserver.exe` is installed to `%LOCALAPPDATA%\UnrealEngine\Common\Zen\Install` (12 MB on the system drive, accepted). Classic DDC: `Using data cache path <ModkitDir>/DDC: DeleteOnly`; shared DDC disabled |
| Compiler / UBT / shader-worker temp | `%TEMP%` | launch the editor only via `src\modkit\Launch-Editor.cmd` and cook via `src/modkit/tools/cook_install.sh`; both set `TEMP`/`TMP=<ModkitDir>\Temp` for their process tree | VERIFIED 2026-11-16 (UBT log: `Setting temp directory to '<ModkitDir>\Temp\UnrealBuildTool\...'`) |
| Build outputs (obj, pdb, binaries), shaders, `Saved\`, `Intermediate\` | inside project/engine folders | already in `<ModkitDir>` | OK |
| Small per-user files (`%LOCALAPPDATA%\UnrealBuildTool`, `%APPDATA%\Unreal Engine`, CrashReportClient) | system drive | leave (KB–MB) | accepted |
| Visual Studio itself | `C:\Program Files\Microsoft Visual Studio\2022\Community` | not moved (needs reinstall; shared components stay on the system drive) | accepted |
After the first editor session, measure `%LOCALAPPDATA%\UnrealEngine` and `%TEMP%` to confirm nothing large landed on the system drive.

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
  - See `01_runbook.md` "Parallel sessions".
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
- **Build 2026-11-18 (3 new reflection functions, see `07`):** `Build.bat Subnautica2Editor Win64 Development -Project=<uproject> -WaitMutex -NoHotReloadFromIDE -MaxParallelActions=4`, editor closed, TEMP in `<ModkitDir>\Temp`: 6 actions, **289 s, Result: Succeeded**. Started from a `.cmd` wrapper (log `<ModkitDir>/build_graphtools_ocean.log`). After the build the editor (started with `Start-Process Launch-Editor.cmd`; `cmd /c start` from Git Bash did NOT start it) took ~15 min until `ue_run.py` connected; early attempts fail with `NO EDITOR FOUND` and then `Remote party failed to attempt the command socket connection!` (editor still starting) - just retry. Cook with the editor closed: `cook_install.sh SN2EmptyWorld 2` = 116 s, BUILD SUCCESSFUL (VERIFIED 2026-11-18).
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

## Modkit facts from its README (UNTESTED here until the editor opens)
- Game content in the editor is read-only (cooked). Right-click → "Make Uncooked Blueprint Copy" / widget / anim BP copies; cooked data assets can be copy-pasted into a mod.
- Blueprint mods: `Content/Mods/<Mod>/ModActor` + Primary Asset Label (`PAL_<Mod>`, Always Cook, chunk id 1–300, never 0) → package → `pakchunk<id>-Windows.pak/.utoc/.ucas`
  renamed `<Mod>.*` into `Content\Paks\LogicMods\<Mod>\` (loaded by UE4SS BPModLoader). "SN2 Mod Tools" toolbar automates New mod / Cook & Install / Launch.
- Content-only plugin mods (items, recipes, biomods, scannables, buildables, databank, story goals): Alpakit "Cook & Install" → `<game>\Mods\` — loaded by the engine
  **without UE4SS**. Example: `TestPluginMod`.
- Custom materials work only thanks to the custom engine's shader patches.
- Shipped `Automation\` folder contains a `.usmap` for FModel.
- SN2EmptyWorld cook with the 16 SN1 terrain tile meshes (1.12 M triangles, Nanite, complex-as-simple), VERIFIED 2026-11-22 (cook log + `retoc.exe list --path --size <utoc>`): incremental cook about 4 min (16:28 to 16:32), `Packages Cooked: 17` (16 SM + map), installed `SN2EmptyWorld.ucas` 123.5 MB, `.utoc` lists `SN1Terrain/SM_spot1_tile_<i>_<k>.uasset` + `.ubulk` for all 16 tiles (about 11 MB uasset + 2-3 MB ubulk each), `L_SN2World.umap` 76.9 KB + `.ubulk` 209 KB, `ModActor.uasset`. `retoc list --path --size` is needed to see asset names (plain `list` shows only chunk ids). Still needs `SN2_ALLOW_ATTACH_ABORTS=1` for the 2 benign BP_Ocean WaterSpline lines. In-game load UNTESTED.
- Timings 2026-11-23 (origin_fix1 rebuild, LOGGED): `launch_editor.sh` to first `ue_run` answer about 7 min; origin re-import (16 tiles, 1.9 M triangles) a few minutes; incremental cook 5 min 12 s (`Packages Cooked: 17`, installed `.ucas` 348,352,096 B).

## SN2GraphTools widget functions + WBP_BugReport script (2026-11-24)
- Plugin deps now include UMG, UMGEditor, Slate, SlateCore (Build.cs). Rebuild with the editor closed: **VERIFIED (2026-11-24)** build Succeeded in 352 s (`-MaxParallelActions=4`, 7 actions, wrapper `<ModkitDir>/build_bugshot.cmd`, log `build_bugshot.log`).
- New UFUNCTIONs (category SN2|Widget, python `unreal.SN2GraphLibrary.*`): `add_widget(wbp, widget_class, name, parent)` (parent None = root), `find_widget(wbp, name)`, `set_widget_is_variable(w, bool)`, `set_canvas_slot(w, anchor_min, anchor_max, pos, size, alignment, z)`, `set_box_slot(w, padding, fill_value, halign, valign)` (align 0 fill, 1 left/top, 2 centre, 3 right/bottom; fill_value>0 = Fill rule, 0 = Auto; works for Vertical/Horizontal/Overlay/Border slots), `describe_widget_tree(wbp)` (lines "depth name : class var=0/1 parent=.. slot=.."), `add_widget_bound_event(wbp, widget_name, delegate_name)`.
- **unreal.py return convention (VERIFIED 2026-11-24):** a bool-returning UFUNCTION with an out param returns the out value on success and None on failure. `connect()` returns the message string on success (can be EMPTY string, which is falsy: test `is None`), `compile_with_log()` returns the message list (maybe empty) or None on compile error, `add_widget_bound_event()` returns a tuple (node, message).
- Script `src/modkit/scripts/sn2bugshot_widget.py`: scaffolds SN2BugShot (ModActor + PAL_SN2BugShot, chunk 3; chunk ids in use before: 1, 2, 14), recreates WBP_BugReport. First run right after the delete can fail with "could not create widget blueprint" (asset still in memory): just run it again. **VERIFIED (2026-11-24)** second run: compile ok, 0 errors, 12 widgets read back, saved, generated class loadable.
- Cook: `cook_install.sh SN2BugShot 3` -> "Packages Cooked: 2" (ModActor, WBP_BugReport; PAL is not packed), `retoc list` shows 2 ExportBundleData + header, installed to LogicMods/SN2BugShot. **VERIFIED (2026-11-24)**.
