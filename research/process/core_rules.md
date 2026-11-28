# Core rules: loop, protocol, UE4SS facts, crash table

Read at startup. Detail lives in the linked files. Pass-1 wording of every condensed incident: `git show 3449200:research/process/core_rules.md`.

## The loop (every change)
1. Edit `src\mods\<Mod>\Scripts\main.lua` (and `data\` files) with the Write/Edit tools (see "Editing rules" below). A patch script must assert that its anchor strings occur exactly once.
2. Install: `bash src/tools/install_mod.sh <Mod>` (copies Scripts + data into the game and the bundle, registers in `mods.txt`).
3. **UE4SS reads Lua only at game launch.** Reloading the save does NOT pick up changes. Hot-reload is deliberately OFF (crash table).
   If the game is running: start `bash src/tools/relaunch_on_exit.sh` with `run_in_background: true`, then ask the tester to quit.
   It relaunches via `launch_game.sh` (Steam `-applaunch`, see `autotest_startup.md` "Launching through Steam") after a confirmed exit. If not running: `bash src/tools/launch_game.sh`.
4. Watch the log with the Monitor tool: command `bash src/tools/watch_log.sh`, `timeout_ms: 1800000`; re-arm on expiry and after any session restart. Keep the filter quiet (per-sweep lines flood the chat).
5. The tester loads the save and presses keys; you read results from the log and ask the tester what is visible. The log proves calls ran, only the tester can confirm visuals/physics. Automated runs: `autotest.md`.

## User protocol (the tester drives the game)
- The tester presses all in-game keys; you cannot. Give exact key, place to stand/look, and what should happen.
- **No waiting at the main menu (user decision 2026-11-18).** The "wait ~60 s at the menu" rule is withdrawn (it never worked reliably): the lobby -> world GC-watchdog crash is an open **bug to fix**, not to work around. Tests click through the menu as soon as it is visible. Lobby banner in log: `not in L_Main (World /Game/Maps/L_ClientLobby...)`.
- The test save loads at about **(-331747, 420670, -2072)** (near the surface, Axum/AR area, ~21 m deep).
- **Console commands are disabled in the test save** ("commands are disabled"): `Warp`, `SpawnCreature` etc. are unavailable. Implement movement/tests in Lua (e.g. F1 teleports via `Pawn:K2_SetActorLocation`).
- Back up saves before anything that could persist: `bash src/tools/backup_saves.sh`.
- Runtime edits vanish when the world reloads (respawn, menu, relaunch): mods must re-apply on every world load (`ClientRestart` hook / sweep loop).

## Game and UE4SS facts
- UE **5.6.1** Shipping, DX12, Early Access build CL-131439 (2026-09-18). IoStore content (`Subnautica2-Windows.utoc/.ucas`) + legacy `.pak` (configs). Not encrypted, Oodle.
- UE4SS: Subnautica2Modding fork 1.0.0 = UE4SS v3.0.1-953 experimental (zip in `tools\downloads\`). Files: `Win64\dwmapi.dll` + `Win64\ue4ss\`. Fallback: upstream UE4SS v4.0.0 (2026-11-12, supports 5.5-5.8). Disable UE4SS by renaming `dwmapi.dll`.
- `UE4SS-settings.ini` changes from default: `GuiConsoleEnabled = 1`, `GuiConsoleVisible = 1`, `EnableHotReloadSystem = 0`.
- Default UE4SS mods enabled: CheatManagerEnablerMod, ConsoleCommandsMod, ConsoleEnablerMod (UE console on `~`/F10), BPML_GenericFunctions, BPModLoaderMod (INS), Keybinds.
- Mod enable: `ue4ss\Mods\<Mod>\enabled.txt` and/or `<Mod> : 1` in `ue4ss\Mods\mods.txt` (`enabled.txt` in a mod folder overrides `mods.txt : 0`).
- Lua `print` lands in `UE4SS.log` as `[Lua] ...`; our mods prefix `[<ModName>]`.
- `tasklist` truncates image names to 25 chars: match `Subnautica2-Win64`.

## Editing rules (each learned from a failure)
- **No raw control characters in Lua source (2026-11-19).** Run `20261119_201024_lmain_baseline` = FAIL_LOBBY: `Error loading script: ...SN2AutoTest/Scripts/main.lua:215: unfinished string near '"['`; a pattern held a real CR, LF and TAB (LOGGED cause: an inline Python/bash edit had its backslash escapes expanded, and Python text mode turned LF into CRLF). Rules: write Lua with Write/Edit; if a patch script is needed, build escapes with `chr(92)` and use binary mode; repo Lua is LF only. Guards (2026-11-19, UNTESTED in game): `install_mod.sh` runs `src/tools/check_lua_ctl.py` on `Scripts/*.lua` and refuses (exit 5, file:line) on any CR or control byte except TAB/LF; the autotest driver ends with `RESULT FAIL_LUA_LOAD <error line>` (+ `shots/stall_lua_load.png`, `windows_lua_load.txt`) on an `Error loading script ... SN2...` line in UE4SS.log (assumes UE4SS truncates the log per launch); `autotest_retry.sh` never retries it.
- **Backslashes in Bash-tool heredocs get mangled (VERIFIED 2026-11-23, twice in `research/process/README.md`):** a quoted `python - <<'PY'` heredoc turned `\a`, `\r`, `\t`, `\202` in Windows paths into BEL, CR, TAB, U+0082, and the damage landed in research files. Never put backslashes in heredoc text that ends up in a file; write the script with Write, use `chr(92)`, or use Edit. After a scripted edit check: `python -I -c "import re;s=open(p,encoding='utf-8').read();print([ascii(s[m.start()-20:m.start()+20]) for m in re.finditer('[\x00-\x08\x0b-\x1f\x7f-\x9f]',s)])"`.

## UE4SS Lua rules (each learned from a failure)
More Lua facts from tests (water A/B, builder probe, VERIFIED 2026-11-27 / 2026-11-28): `process/ue4ss_lua_facts.md`. Full pass-2 crash rows: `crashes/crash_table_full.md`.
- **`FindFirstOf` / `FindAllOf` / `:GetWorld()` never return nil for "not found": they return an INVALID UObject wrapper, and a method call on it can be a native null dereference that `pcall` cannot catch** (VERIFIED 2026-11-26, three minidumps: AV READ 0x0 at `UE4SS.dll+0x350206` in the `UObject::GetWorld` wrapper, from `FindFirstOf("PlayerController"):GetWorld()` in a LoadMap pre-hook at the first Browse). Test `pcall(function() return o:IsValid() end)` first (a bare `o.IsValid ~= nil and o:IsValid()` threw `System: Global for __index doesn't exist.` on an actor that died mid-sweep, 2026-11-16). Do not touch world/controller objects from a LoadMap hook without it. `require("UEHelpers").GetWorld()` is the safe way to get the world (diag.lua).
- **Property accessors are unchecked casts (FAILED 2026-11-28, run `20261128_120333_buildprobe_dump`: game crash after `SN2BuilderTool.LogMissingRequirementAnalytics`).** `prop:GetPropertyClass()`, `GetStruct()`, `GetEnum()`, `GetInner()` crash on the wrong `FProperty` type. Read `prop:GetClass():GetFName():ToString()` first: `ObjectProperty`/`ClassProperty`/`Soft*` -> `GetPropertyClass`, `StructProperty` -> `GetStruct`, `EnumProperty` -> `GetEnum`, `ArrayProperty` -> `GetInner`; read plain value types only. Reusable: `propType()` in `src/mods/SN2AutoTest/data/buildprobe.lua`. `ForEachProperty` over the class chain + reading only number/boolean values is a safe generic dump (`uwa8`, VERIFIED 2026-11-27, 224 + 68 props).
- **`MaterialInstanceDynamic:K2_GetScalarParameterValue("Name")` kills the game thread (FAILED 2026-11-27, run `20261127_173849_uwab_lmain`, dump `crash_2026_11_27_17_39_51.7525699.dmp`).** Read the `ScalarParameterValues` / `VectorParameterValues` arrays (own overrides) and walk `.Parent` for inherited ones (`SN2AutoTest/data/uwa.lua`, VERIFIED 2026-11-27). `CreateDynamicMaterialInstance(0, parentMaterial, FName("x"))`, `SetScalarParameterValue(FName("x"), v)` and `SetVectorParameterValue(FName("x"), {R=,G=,B=,A=})` worked (VERIFIED 2026-11-27, run `20261127_175122_uwab_sn2`).
- **Don't pass/return complex structs through UFunctions** (FText, TSoftObjectPtr, FGameplayTagContainer, arrays of such): `SN2AdaptationsPlayerStateComponent:GetAdaptations()` crashed UE4SS.dll (AV READ 0x10) twice on 2026-11-16. Plain structs (FVector, FGameplayTag as `{ TagName = FName("...") }`) are fine.
- **Never call UFunctions on class-default objects** (`Default__...`, returned by `FindAllOf`): crashed the game (2026-11-14). Filter with a name check.
- **`ExecuteWithDelay` / `LoopAsync` callbacks run off the game thread.** Wrap engine calls in `ExecuteInGameThread(function() ... end)`; `LoadAsset` refuses otherwise ("can only be called from within the game thread"). `RegisterKeyBind` and `RegisterHook` callbacks are already on the game thread.
- Out-params: pass a table variable and read it after (`local O, E = {}, {}; a:GetActorBounds(false, O, E, false)`). Exception: `AppendBuffersToMesh` rejects this ("no table was on the stack"), unresolved.
- Structs are plain tables (`{X=,Y=,Z=}`; transform `{Rotation={X,Y,Z,W}, Translation={...}, Scale3D={...}}`); enums are integers; `nil` for optional object params.
- UE 5.6 line traces: `HitResult.HitObjectHandle.ReferenceObject:Get()` may return the hit **component**; use `:GetOwner()` for the actor.
- Reading arbitrary property values can fail; names/types via `Class:ForEachProperty` are safe. `StaticFindObject(path)` only finds loaded objects; load with `LoadAsset(path)` on the game thread.
- Spawning: `GameplayStatics:BeginDeferredActorSpawnFromClass(World, Class, T, 1, Owner, 0)` -> configure -> `FinishSpawningActor(Actor, T, 0)` (both have older signatures without the trailing arg; code tries both).
- A spawned mesh whose bounding sphere contains the camera is invisible (back-face culling): place beyond `mesh:GetBounds().SphereRadius`.
- Destroy + free: `actor:K2_DestroyActor()` then `KismetSystemLibrary:CollectGarbage()`; confirm with object counts before/after.
- Do not keep UObject lists across seconds of streaming (stale objects crash UE4SS): re-find before use. Do nothing periodic in `L_ClientLobby` / during map loads (precaution; not the cause of the GC watchdog).

## Test-running gotchas (2026-11-28, investigator)
- `TaskStop` on a Bash chain `acquire && install && autotest.sh` that already launched the game kills only the shell: game, hidden holder and driver keep running as orphans (no `result.txt`, no slot cleanup; check `slots_pre.txt` against the save folder). Never stop such a chain; wait for it.
- Heavy-lock takeover happens after ~10-60 s without a heavy process (`idle 16 s > 10 s` in history.log): `install_mod.sh` + the launch must follow `acquire` immediately in one command; another session's run can start between two of yours.
- A second chain started while the first one's game is up fails `game is running - abort` or FAIL_LOBBY: check `tasklist` first.
- `autotest_retry.sh` is the right entry point here: 2 of 5 runs on 2026-11-28 ended in the lobby GC-watchdog CRASH and the retry completed.

## Crashes (dumps in `<Workspace>\crashes\`, parse with `python -I tools/mdmp.py <dmp>`)
Symptom: game process gone, new `ue4ss\crash_*.dmp`, game log ends without `LogExit: Exiting`. Move dumps to `crashes\` after reading. One row per distinct cause; detail in the linked file.
| When | Cause | Rule |
|---|---|---|
| 2026-11-14, first F5 probe | Lua called `GetRuntimeState`/`IsLevelLoaded` on CDOs: AV in the exe | Skip `Default__` objects |
| 2026-11-16 21:08:55 and 21:14:24 | AV `UE4SS.dll+0x2428D7` after the menu / lobby ClientRestart; `GetAdaptations()` struct conversion (LOGGED) | No FText/TSoftObjectPtr/FGameplayTagContainer struct UFunctions from Lua; hot reload stays 0 |
| 2026-11-16 21:19:17 | AV `UE4SS.dll+0x242897`; probable stale UObjects after landscape streamed out | Re-find objects before use; no UObject lists across streaming |
| 2026-11-18, 2026-11-27, default (Deep) start in L_Main | AV READ 0x20 at exe+0x162AD90 after `Applying start conditions of Deep`; **UNEXPLAINED, open** | `SN2_START=Shallows bash src/tools/autotest.sh <plan> ...` for L_Main diagnostics. `research/crashes/deep_start_crash.md` |
| 2026-11-22, 2026-11-26 (SN2AutoTest PODDUMP) | AV READ in `UE4SS.dll+0x9347F0` while iterating every SceneComponent from `FindAllOf` (LOGGED 2026-11-26) | PODDUMP removed 2026-11-26 (`git show a3fa5e5:src/mods/SN2AutoTest/Scripts/main.lua`). Never sweep all objects from Lua while the world streams |
| **GC watchdog, lobby -> world LoadMap** (`LogGarbage: Spent more than 20.00s on routing FinishDestroy...`), 11 instances 2026-11-14 to 2026-11-24 | **Open bug.** Explanation H8, fix 1 `--vt-prio 3` UNTESTED. **FAILED (2026-11-18): "Lua polling in the lobby causes it"** (crash with all Lua mods off) | Harness treats dump-less exit, AV and hang as this bug; `autotest_retry.sh` retries a CRASH once. `research/crashes/gc_watchdog.md` |
| "Wait ~60 s at the menu" workaround (withdrawn 2026-11-18) | Never prevented the crash reliably | Do not reintroduce; fix the bug |
