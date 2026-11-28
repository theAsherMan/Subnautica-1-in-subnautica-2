# Modkit setup

Pass 2 (2026-11-28): setup is solved; tables kept as the install recipe, status tail merged (full notes: `git show 3449200:research/code/modkit_setup.md`). Editor scripting and cooks: `research/code/modkit_scripting.md`.

## Modkit setup (Subnautica2-Project cooked editor)

Why: distribution target is cooked terrain assets (see `research/status.md` → Distribution target). The modkit is a UE 5.6 editor that mounts the game's cooked content
read-only and packages mods as IoStore pak chunks / content-only plugins.

## Requirements and reference timings
- ~60 GB free for `<ModkitDir>` (any drive; an HDD works but is slow). 16 GB RAM is the practical minimum: editor + game together are tight, and a
  parallel C++ build can be killed by memory pressure (see SN2GraphTools build notes).
- Visual Studio 2022 Community with C++ desktop + game workloads and MSVC toolset **14.38** (newer toolsets alone are rejected).
- Timings in these notes were measured on a mid-range 6-core desktop with the modkit on an HDD; expect faster on an SSD.

## Layout
| Path | Content |
|---|---|
| `<ModkitDir>\Subnautica2-Project\` | git clone of github.com/Subnautica2Modding/Subnautica2-Project, commit `827162c` (2026-10-07, "update for v0.1.2.2 (131439)" - matches game build CL-131439), latest tag `sn2-v0.1.2.0` |
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
| 5/6 | Engine release "SN2-Engine-V4" = byte-split zip `SN2-Engine-V4.zip.001`–`.004` (3 × 1,992,294,400 B + 1,121,483,344 B = 7.10 GB) in `<ModkitDir>\downloads\`. Index: **243,797 members, 17.32 GiB unpacked**, single root `Engine/` (Plugins 8.0, Binaries 5.6, Source 1.5, Content 1.1, Intermediate 0.95 GiB). (A stray `Unconfirmed 524443.crdownload`, 1.68 GB, is an abandoned browser duplicate - safe to delete.) | VERIFIED 2026-11-15 |
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

## Status (2026-11-28)
Modkit editor installed, game content mounted, scripted from the shell (`ue_run.py`): **VERIFIED 2026-11-16**. Asset (pak/IoStore) mods from the modkit: the SN2Terrain pak loaded in game (**VERIFIED 2026-11-16**, `research/code/modkit_scripting.md` "Cook + install"); later cooks of SN2EmptyWorld/L_SN2World are in the same file and `research/sn2/README.md`.
