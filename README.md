# Subnautica 1 → Subnautica 2 world mod — setup guide

How to set up a Windows PC to work on this project from scratch: which accounts to create, what to install, and the steps in order.
Technical research notes are in [`research/`](research/00_overview.md). Instructions for Claude are in [`CLAUDE.md`](CLAUDE.md).

There are two toolchains:

| Toolchain | Used for | Needs |
|---|---|---|
| **A. Lua mods (UE4SS)** | Runtime experiments in the game: removing terrain, spawning test geometry, probing the world | Subnautica 2, UE4SS, Python, Git Bash |
| **B. Modkit (Unreal Editor)** | Building real assets (terrain meshes, levels) and packaging them as mod files | Everything in A, plus Visual Studio, the custom Unreal Engine, FMOD and the modkit project |

Toolchain A is enough to play-test the existing mods. Toolchain B is needed to build the finished terrain.

## 0. Per-machine settings (do this first)

Everything machine-specific lives in one git-ignored file. Copy `local.config.example` to `local.config` in the repo root and set:

| Key | Meaning | Written as in the docs |
|---|---|---|
| `SN2_GAME_DIR` | Steam folder of Subnautica 2 (contains `version.txt` and the inner `Subnautica2\` folder) | `<GameDir>` |
| `SN2_WORKSPACE` | A folder outside the repo for reports, crash dumps, save backups and the install bundle | `<Workspace>` |
| `SN2_MODKIT_DIR` | Modkit root, about 60 GB (toolchain B only) | `<ModkitDir>` |

`<RepoDir>` means the folder you cloned this repo into. The shell tools (`src/tools/*.sh`), the editor launcher (`src/modkit/Launch-Editor.cmd`) and the
editor runner (`src/modkit/tools/ue_run.py`) all read this file.

---

## 1. Accounts to create

| Account | Why | Notes |
|---|---|---|
| **Steam** | Owns Subnautica 2 (appid 1962700) | Subnautica 1 will also be needed later, for its terrain data |
| **GitHub** (github.com) | Download the custom Unreal Engine and the modkit | Free account |
| **Epic Games** (epicgames.com) | Unreal Engine source access goes through Epic | Free account |
| **Epic ↔ GitHub link** | Without it the custom engine page shows **404 Not Found** | See step 2 |
| **FMOD** (fmod.com) | Download the FMOD plugin; the modkit cannot open without it | Free account; on the "register" form, pick a non-commercial / personal option |

## 2. Link Epic Games to GitHub (needed for toolchain B)

1. Sign in at **epicgames.com** in a browser (not the launcher), open **Account** (top right) → **Connections** (older UI: "Apps and Accounts") → **Accounts** tab → **GitHub** → Connect, and authorise.
   Epic's guide: https://www.unrealengine.com/ue-on-github
2. Within a few minutes GitHub emails an invitation to join the **@EpicGames** organisation. **Accept it.** The email link expires after 7 days.
   It can also be accepted at https://github.com/EpicGames.
3. Check: https://github.com/Buckminsterfullerene02/UnrealEngine should now open instead of showing 404.

## 3. Software to install

| # | Software | Where it goes | Toolchain |
|---|---|---|---|
| 1 | **Subnautica 2** (Steam) | Any Steam library → `SN2_GAME_DIR` | A, B |
| 2 | **UE4SS for Subnautica 2** — the Subnautica2Modding fork 1.0.0 (UE4SS v3.0.1-953): https://github.com/Subnautica2Modding/Subnautica2-UE4SS/releases (copy kept in `src/tools/downloads/UE4SS_SN2_fork_1.0.0.zip`) | Unzip into the game's `Subnautica2\Binaries\Win64\` (next to `Subnautica2-Win64-Shipping.exe`) | A, B |
| 3 | **Python 3** (python.org, tick "Add to PATH") | Default | A, B |
| 4 | **Git for Windows** (includes Git Bash; used by the helper scripts) | Default | A, B |
| 5 | **VS Code** — the code editor used for this project | Default | A, B |
| 6 | **Visual Studio 2022 Community** — needed only as the C++ compiler for Unreal, not as an editor | `C:\Program Files\...` (cannot be moved) | B |
| 7 | **Custom Unreal Engine 5.6 "SN2-Engine-V4"** (about 7 GB download, 17.3 GB unpacked) | `<ModkitDir>\UE_5.6_SN2\` | B |
| 8 | **FMOD for Unreal 2.03.x for UE 5.6, Windows** (e.g. `fmodstudio20315ue5.6win64.zip`, about 93 MB) | `<ModkitDir>\downloads\` (not extracted by hand) | B |
| 9 | **Subnautica2-Project modkit** (git clone) | `<ModkitDir>\Subnautica2-Project\` | B |

### Visual Studio 2022 details
- In the Visual Studio Installer, select the workloads **Desktop development with C++** and **Game development with C++**.
- In **Individual components**, also tick **MSVC v143 – VS 2022 C++ x64/x86 build tools (v14.38-17.8)**. Unreal 5.6 for this modkit needs toolset **14.38**; newer ones such as 14.40 are not enough on their own.
- If installing it from the command line, the installer must run **as administrator**. Otherwise it fails with exit code 5007.

## 4. Disk space

| Item | Size | Location |
|---|---|---|
| Engine archives (can be deleted after unpacking) | 7.1 GB | `<ModkitDir>\downloads` |
| Unpacked engine | 17.3 GB | `<ModkitDir>\UE_5.6_SN2` |
| Modkit project + game sound banks | about 1.1 GB | `<ModkitDir>\Subnautica2-Project` |
| Editor caches (shaders, derived data), growing with use | 10–30 GB | `<ModkitDir>\DDC` (see section 7) |
| Visual Studio + C++ workloads | about 10 GB | system drive (cannot be moved) |

If the system drive is small, put `<ModkitDir>` on another drive; section 7 keeps Unreal's caches and temp files there too.

## 5. Setting up toolchain A (Lua mods)

1. Install Subnautica 2 and run it once.
2. Unzip UE4SS into `<game>\Subnautica2\Binaries\Win64\`. Launch the game once; `Binaries\Win64\ue4ss\UE4SS.log` should appear.
3. Install a mod from this repo by running this in Git Bash:
   ```bash
   bash src/tools/install_mod.sh SN2WorldProbe
   ```
   This copies `src/mods/SN2WorldProbe` into the game's `ue4ss\Mods\` folder (found via `SN2_GAME_DIR`) and enables it.
3b. To skip the intro (new games start at the surface with an empty hotbar), launch the game with `-OverridePlayerStart=Shallows`: `bash src/tools/launch_game.sh`
   (or add that text to the game's Steam launch options). No mod is needed for this.
4. **Fully quit and restart the game** after every mod change. UE4SS only reads Lua files at launch.
5. Before testing anything risky, back up your saves: `bash src/tools/backup_saves.sh` (copies `%LOCALAPPDATA%\Subnautica2\Saved\SaveGames\`
   to `<Workspace>\save_backups\<timestamp>\`).
6. Watch the mods' log output: `bash src/tools/watch_log.sh`.

## 6. Setting up toolchain B (modkit / Unreal Editor) — in order

| Step | What to do |
|---|---|
| 1 | Do toolchain A first, plus sections 1–3 (accounts, Epic↔GitHub link, Visual Studio with 14.38). |
| 2 | Clone the modkit:<br>`git clone https://github.com/Subnautica2Modding/Subnautica2-Project <ModkitDir>\Subnautica2-Project` |
| 3 | Edit `GameInstallDirectory.txt` in the project so it holds the **inner** game folder, e.g. `<GameDir>\Subnautica2` (the folder that contains `Binaries` and `Content`). |
| 4 | Copy the game's sound banks into the project. In PowerShell, from the project folder: `.\copy-fmod-banks.ps1`. **Re-run after every game update.** |
| 5 | Download the custom engine from the **Releases** page of https://github.com/Buckminsterfullerene02/UnrealEngine. Use the release that matches the modkit's README ("custom engine V4" at the time of writing). It comes as a **split zip** (`SN2-Engine-V4.zip.001` … `.004`) and **every part** is needed. Set the browser to save to `<ModkitDir>\downloads\`. |
| 6 | Unpack it. Windows can't open split zips; either use 7-Zip on `.001`, or use this repo's helper, which needs no extra software and checks every file:<br>`python -I src\modkit\tools\splitzip.py extract <ModkitDir>\downloads\SN2-Engine-V4.zip.001 <ModkitDir>\UE_5.6_SN2`<br>(about 13 minutes on a hard drive). |
| 7 | Download FMOD (section 3, item 8), then from the project folder in PowerShell:<br>`$env:TEMP='<ModkitDir>\Temp'; powershell -ExecutionPolicy Bypass -File setup-fmod.ps1 -FMODPluginZip "<ModkitDir>\downloads\fmodstudio20315ue5.6win64.zip"`<br>Don't copy the plugin folder from the zip into the project yourself. |
| 8 | Link the project to the engine. The modkit README says to right-click `Subnautica2.uproject` → **Switch Unreal Engine version**, but this engine build has no version selector, so register it manually instead: add a string value to `HKCU\Software\Epic Games\Unreal Engine\Builds` named `{<new GUID>}` with data `<ModkitDir>/UE_5.6_SN2`, and put the same `{GUID}` into `"EngineAssociation"` in `Subnautica2.uproject` (any new GUID works; details in `research/08_modkit_setup.md`). |
| 9 | Optional: the cache redirects in section 7. |
| 10 | Copy this repo's editor add-on into the modkit: `src\modkit\plugins\SN2GraphTools` → `<ModkitDir>\Subnautica2-Project\Plugins\SN2GraphTools`, then build the editor once (editor closed):<br>`<ModkitDir>\UE_5.6_SN2\Engine\Build\BatchFiles\Build.bat Subnautica2Editor Win64 Development -Project=<ModkitDir>\Subnautica2-Project\Subnautica2.uproject -WaitMutex` (about 10 minutes the first time). It lets the scripts in `src/modkit/scripts` build Blueprint logic. |
| 11 | Start the editor with **`src\modkit\Launch-Editor.cmd`**. The first launch compiles shaders and can take 20–40 minutes on a hard drive. If asked to rebuild modules, click **Yes**. If asked to **convert** the project, cancel: the engine link is wrong. |
| 12 | Check: the Content Browser shows the game's folders (`Art`, `Blueprints`, `Maps`, …). Game content is **read-only**. When viewing levels, hide `BP_Ocean` so you can see. |
| 13 | Let scripts drive the editor: **Edit → Project Settings → Plugins → Python → Enable Remote Execution?** = on. Test: `python -I src/modkit/tools/ue_run.py -c "1+1"`. |
| 14 | Build and install the test terrain mod: `python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2terrain_build.py`, then `... sn2terrain_removal_graph.py`, then `bash src/modkit/tools/cook_install.sh SN2Terrain <ChunkId>` (the chunk id is printed by the build script). |

## 7. Keeping Unreal's caches off the system drive (optional)

By default Unreal writes tens of GB to `%LOCALAPPDATA%` and `%TEMP%`. To keep them in `<ModkitDir>` instead:

| What | Default location | Change |
|---|---|---|
| Unreal derived data cache **and** Zen cache server data | `%LOCALAPPDATA%\UnrealEngine\Common\DerivedDataCache`, `...\Zen\Data` | `Launch-Editor.cmd` sets `UE-LocalDataCachePath=<ModkitDir>\DDC`, which moves both (Zen uses `<ModkitDir>\DDC\Zen`). To cover tools started some other way, also set it as a user environment variable. |
| Compiler / shader temp files | `%TEMP%` | Always start the editor through `src\modkit\Launch-Editor.cmd` (sets `TEMP`/`TMP=<ModkitDir>\Temp`); `cook_install.sh` does the same for cooking. |
| Visual Studio download cache | `C:\ProgramData\Microsoft\VisualStudio\Packages` | Registry `HKLM\SOFTWARE\Microsoft\VisualStudio\Setup`: `CachePath=<new folder>`, `KeepDownloadedPayloads=0` (as admin). **Also copy the `_Instances` subfolder** from the old cache to the new one, or Unreal stops finding Visual Studio ("No valid Visual C++ toolchain was found"). |

The modkit is a git clone, and the setup steps edit tracked files (`GameInstallDirectory.txt`, `Subnautica2.uproject`). Before updating it, run `git stash`, then `git pull`, then `git stash pop`.

## 8. After every Subnautica 2 update
- Compare `<game>\version.txt` with the build the notes were made on (CL-131439). A newer build can break UE4SS and the modkit.
- Re-run `copy-fmod-banks.ps1` in the modkit.
- Check the modkit and UE4SS fork for matching updates; the engine release may change too.

## 9. Sharing the finished mod (for friends)
Players won't need any of toolchain B. They need Subnautica 2, UE4SS (CurseForge can install it), and the packaged mod folder. Later, they'll also need their own copy of Subnautica 1 for the terrain converter, because Subnautica 1's data can't be redistributed.
