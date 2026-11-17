# Runbook — how to change the game and test it

## The loop (every change)
1. Edit `src\mods\<Mod>\Scripts\main.lua` (and `data\` files). For large edits, write a small Python patch
   script that asserts its anchor strings occur exactly once, then replaces — this caught several mismatches.
2. Install: `bash src/tools/install_mod.sh <Mod>` (copies Scripts + data into the game and the bundle, registers in `mods.txt`).
3. **UE4SS reads Lua only at game launch.** Reloading the save does NOT pick up changes. Hot-reload is deliberately OFF (see Crashes).
   If the game is running: start `bash src/tools/relaunch_on_exit.sh` with `run_in_background: true`, then ask the tester to quit.
   It relaunches via `steam://rungameid/1962700` after a confirmed exit. If not running: `powershell -NoProfile -c "Start-Process 'steam://rungameid/1962700'"`.
4. Watch the log with the Monitor tool: command `bash src/tools/watch_log.sh`, `timeout_ms: 1800000`; re-arm on expiry.
   Monitors die when the Claude session restarts — re-arm after any restart. Keep the filter quiet (per-sweep lines flood the chat).
5. The tester loads the save and presses keys; you read results from the log and ask the tester what is visible. The log proves calls ran, only the tester can confirm visuals/physics.

## User protocol (the tester drives the game)
- The tester presses all in-game keys; you cannot. Give exact key, place to stand/look, and what should happen.
- **Tell the tester to wait ~60 s at the main menu before loading the save** (crash otherwise, see below). Lobby banner in log: `not in L_Main (World /Game/Maps/L_ClientLobby...)`.
- the test save loads at about **(-331747, 420670, -2072)** (near the surface, Axum/AR area, ~21 m deep). Earlier tests used the Coral Gardens area around (-204942, 432071, -24066).
- **Console commands are disabled in the test save** ("commands are disabled"), so `Warp`, `SpawnCreature`, etc. are unavailable — implement movement/tests in Lua
  (e.g. F1 teleports via `Pawn:K2_SetActorLocation`).
- Back up saves before anything that could persist: `bash src/tools/backup_saves.sh`.
- Runtime edits vanish when the world reloads (respawn, menu, relaunch) — mods must re-apply on every world load (`ClientRestart` hook / sweep loop).

## Game and UE4SS facts
- UE **5.6.1** Shipping, DX12, Early Access build CL-131439 (2026-09-18). IoStore content (`Subnautica2-Windows.utoc/.ucas`) + legacy `.pak` (configs). Not encrypted, Oodle.
- UE4SS: Subnautica2Modding fork 1.0.0 = UE4SS v3.0.1-953 experimental (zip in `tools\downloads\`). Files: `Win64\dwmapi.dll` + `Win64\ue4ss\`.
  Fallback: upstream UE4SS v4.0.0 (2026-11-12, supports 5.5–5.8). Disable UE4SS by renaming `dwmapi.dll`.
- `UE4SS-settings.ini` changes from default: `GuiConsoleEnabled = 1`, `GuiConsoleVisible = 1`, `EnableHotReloadSystem = 0`.
- Default UE4SS mods enabled: CheatManagerEnablerMod, ConsoleCommandsMod, ConsoleEnablerMod (UE console on `~`/F10), BPML_GenericFunctions, BPModLoaderMod (INS), Keybinds.
- Mod enable: `ue4ss\Mods\<Mod>\enabled.txt` and/or `<Mod> : 1` in `ue4ss\Mods\mods.txt`.
- Lua `print` lands in `UE4SS.log` as `[Lua] ...`; our mods prefix `[<ModName>]`.
- `tasklist` truncates image names to 25 chars → match `Subnautica2-Win64`.

## UE4SS Lua rules (each learned from a failure)
- **Validity checks must be pcall-wrapped.** `o.IsValid ~= nil and o:IsValid()` threw `System: Global for __index doesn't exist.` on an actor that died mid-sweep
  (2026-11-16, caught by the sweep's pcall → one skipped sweep). `isValid` in SN2TerrainEdit now does `pcall(function() return o:IsValid() end)`.
- **Don't pass/return complex structs through UFunctions from Lua** (structs containing FText, TSoftObjectPtr, FGameplayTagContainer, arrays of
  such): `SN2AdaptationsPlayerStateComponent:GetAdaptations()` crashed UE4SS.dll (AV READ 0x10) twice on 2026-11-16. Plain structs (FVector,
  FGameplayTag as `{ TagName = FName("...") }`) are fine.
- **Never call UFunctions on class-default objects** (`Default__…`, returned by `FindAllOf`) — crashed the game (12:55, access violation in the exe). Filter with a name check.
- **`ExecuteWithDelay` / `LoopAsync` callbacks run off the game thread.** Wrap engine calls in `ExecuteInGameThread(function() … end)`; `LoadAsset` refuses otherwise
  ("can only be called from within the game thread"). `RegisterKeyBind` and `RegisterHook` callbacks are already on the game thread.
- Out-params: pass a table variable and read it after (`local O, E = {}, {}; a:GetActorBounds(false, O, E, false)`).
  Exception found: `AppendBuffersToMesh` rejects this ("no table was on the stack") — unresolved.
- Structs are plain tables (`{X=,Y=,Z=}`; transform `{Rotation={X,Y,Z,W}, Translation={...}, Scale3D={...}}`); enums are integers; `nil` for optional object params.
- UE 5.6 line traces: `HitResult.HitObjectHandle.ReferenceObject:Get()` may return the hit **component**; use `:GetOwner()` to reach the actor.
- Reading arbitrary property values can fail; reading names/types via `Class:ForEachProperty` is safe. Simple value types read fine.
- `StaticFindObject(path)` only finds loaded objects; load with `LoadAsset(path)` on the game thread.
- Spawning: `GameplayStatics:BeginDeferredActorSpawnFromClass(World, Class, T, 1, Owner, 0)` → configure → `FinishSpawningActor(Actor, T, 0)`
  (both have older signatures without the trailing arg; code tries both).
- A spawned mesh whose bounding sphere contains the camera is invisible (back-face culling) — place beyond `mesh:GetBounds().SphereRadius`.
- Destroy + free: `actor:K2_DestroyActor()` then `KismetSystemLibrary:CollectGarbage()`; confirm with object counts before/after.

## Crashes (dumps in `<Workspace>\crashes\`, parse with `python -I tools/mdmp.py <dmp>`)
| When | Cause | Rule |
|---|---|---|
| 2026-11-14 12:55, first F5 probe | Lua called `GetRuntimeState`/`IsLevelLoaded` on CDOs → AV in exe | Skip `Default__` objects |
| 2026-11-16 21:08:55, ~1 s after the main menu appeared (no input yet) | AV in **UE4SS.dll+0x2428D7** (READ 0x10), stack all UE4SS; dump `crashes\crash_2026_11_16_21_08_55.6236665.dmp`. New that launch: `EnableHotReloadSystem = 1`, SN2IntroProbe polling 1,403 `IsStoryGoalUnlocked` + data layers every 1 s in the lobby, 4 new Ctrl+number keybinds; a GameInput device connected 0.2 s before | Repeated identically at 21:14:24 with hot reload off and lighter probe, again ~1.2 s after the lobby ClientRestart = exactly when SN2IntroSkip v2's spawn dump ran (even in the lobby). The dump called `SN2AdaptationsPlayerStateComponent:GetAdaptations()` (returns `TArray<FUWEPlayerAdaptation>` with FText / TSoftObjectPtr / FGameplayTagContainer) → **probable cause: UE4SS converting that struct array**. Rule: don't call UFunctions that take/return such structs from Lua; dump only in L_Main. Hot reload back to 0 anyway |
| 2026-11-16 21:19:17, new game on the biobed, right after SN2TerrainEdit **Ctrl+F2 "ALL landscape RESTORED"** (pressed by mistake twice, 9 s apart) | AV in UE4SS.dll+0x242897 (READ 0x18) — same function as the two lobby crashes (+0x2428D7) | Probable: the toggle re-touched landscape objects that streamed out/died in between (stale UObject). Rule: don't keep UObject lists across seconds of streaming; re-find objects before use. SN2TerrainEdit disabled for the intro work (its `enabled.txt` removed — note `enabled.txt` in a mod folder overrides `mods.txt : 0`) |
| 2026-11-17 17:27:51, new save loading screen (~59 s after the menu appeared), SN2IntroSkip v4 + SN2IntroProbe loaded, no keys pressed | Same engine GC watchdog as 11-14 (`LogGarbage: Spent too much time waiting for FinishDestroy for 22790 object(s) (last object: SphereComponent)` → `AbortInsideMemberFunction` → AV WRITE 0x0 in Subnautica2-Win64-Shipping.exe+0x1626F24). Not UE4SS. Intermittent (many loads succeeded, incl. at ~22–36 s after the menu); waiting ~60 s did not prevent it this time | Just relaunch and retry; record each occurrence. Not yet understood — ideas: lobby→L_Main with `FinishDestroy` backlog from the lobby's 22k SphereComponents; try loading later / earlier, or without the probe mods to A/B |
| 2026-11-17 17:30:21, second identical crash (menu 17:29:36, `LoadMap /Game/Maps/Main/L_Main??game=Survival` 17:30:00, crash exactly 20 s later; 22,791 objects) | Same GC watchdog. RAM/CPU normal (7.8 GB free, nothing heavy running) | **Hypothesis (UNTESTED):** FinishDestroy is time-sliced inside a 20 s wall-clock budget; our Lua `LoopAsync` + `FindAllOf` (every 0.5–1 s, whole-GUObjectArray scans, game thread) in the lobby during `LoadMap` eats frame time. Mitigation applied: SN2IntroSkip arms only from the ClientRestart hook's own controller when the world is L_Main (no FindAllOf in the lobby); SN2IntroProbe disabled. **Rule: Lua mods must do nothing periodic in L_ClientLobby / during map loads.** Check whether the crash stops; if it does, that's the confirmation |
| 2026-11-14 13:24 and 18:33, loading a save ~10 s after the menu appeared | Engine GC watchdog during lobby→`L_Main` (`LogGarbage: Spent more than 20.00s on routing FinishDestroy … 22,78x SphereComponent` → `AbortInsideMemberFunction`) | Wait ~60 s at the menu; every load that waited succeeded. Not A/B-tested without UE4SS. Hot-reload on/off made no difference |
Symptom of a crash: game process gone, new `ue4ss\crash_*.dmp`, game log ends without `LogExit: Exiting`. Move dumps to `crashes\` after reading.

## Offline tools (in `tools\bin\`, SHA-256 verified at download; never run yet)
- `repak.exe` v0.2.3 — unpack legacy pak: `repak unpack <pak> -o <dir>` (the `.ini` configs live in `Subnautica2-Windows.pak`).
- `retoc.exe` v0.1.5 — IoStore ↔ legacy; needed to build asset mods (`to-zen`). SN2 loads only IoStore triples (`.pak/.utoc/.ucas`), not plain `.pak`.
- Earlier attempts to run them were blocked by the Claude Code auto-mode classifier; ask the tester to allow if needed.
- FModel (not installed) + `.usmap` from UE4SS GUI → Dumpers tab, for browsing asset contents (Data Asset fields).
- Subnautica2-Project modkit (github.com/Subnautica2Modding/Subnautica2-Project): custom UE 5.6 cooked editor; ~60 GB, Epic↔GitHub link, VS 2022 MSVC 14.38,
  FMOD for Unreal 2.03.x. Packages pak chunks (id 1–300) → `Content\Paks\LogicMods\<Mod>\<Mod>.pak/.utoc/.ucas`; content-only plugins in `<game>\Mods\` auto-register items/recipes/etc.
- Packaged file list (43,525 paths, from `Manifest_UFSFiles_Win64.txt`): `tools\sn2_packaged_files.txt` — grep it to find asset paths.
