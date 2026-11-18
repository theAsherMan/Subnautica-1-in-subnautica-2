# Intro skip + replacing the world (phase started 2026-11-16)

Goal: a new game starts the player directly in the lifepod (no intro), and the SN2 world (`L_Main` terrain) never loads — only our terrain.

**Requirements (user, 2026-11-16):**
- the new-game character selection/customisation must still appear before spawning — skip only what comes after it;
- the player must spawn with the breathing adaptation (normally granted during the intro's adaptation tutorial: goal
  `DA_Adaptation_BreathingAdaptation_StoryGoal`, unlocked together with `DA_Storygoal_Player_Ch1_AdaptationTutorial_Adapt`). Verify the effect in game,
  not just the goal unlock — the adaptation may also live in `USN2AdaptationsPlayerStateComponent` / `FUWEPlayerAdaptation` (Headers.hpp 115403, 121419).

## Recording 1 (new game, 2026-11-16, terrain mods off) — timeline, t = seconds since spawn
- Lobby `L_ClientLobby`: pawn `BP_MainMenuPawn_C`, view target `CineCameraActor`. 1,403 `UWEStoryGoal` objects loaded, 0 unlocked.
- New game → `L_Main`, first a `UWESpectatorPawn` (loading), then ClientRestart:
- t=0: pawn `BP_Character_01_C` **attached to `BP_BioBed_C_UAID_C87F54AE2B7268F101_1674741001`** at (-346279, 446978, -57953) — the start set is ~580 m below sea level.
- t=5: `DA_Tools_PDA_StoryGoal`, `DA_StoryGoal_Player_Ch1_FirstPrint`
- t=25: `DA_Storygoal_Player_Ch1_FirstPrint3_StoryGoal`; t=27 detached from the biobed (free movement at (-346136, 447120, -57953))
- t=45: `DA_StoryGoal_NarrativeSignal_Investigation_CoralGardens_1_Unknown`
- t=51: `DA_Deepstart_OpenFirstDoor_StoryGoal`
- t=63: `DA_Storygoal_Player_Ch1_NoA_Uploaded_StoryGoal`
- t=76/80: `DA_Storygoal_Player_Ch1_AdaptationTutorial1`, `...2`
- t=84: attached to `StaticMeshActor_UAID_3C7C3FF4FD32026202_1304058360` (class `BP_AngelCombCore_DeepStart_C`) at (-344734, 447868, -57949); `AdaptationTutorial_Interact`
- t=91: `AdaptationTutorial_Insert`; t=92: `DA_Adaptation_BreathingAdaptation_StoryGoal`, `AdaptationTutorial_Adapt`; t=101 detached
- t=125 `DA_Storygoal_Player_Ch1_BiolockScanning`; t=131 `..._BiolockApproved`; t=146 `DA_Tools_MedKit_StoryGoal`; t=152 `..._Ch1_UnexpectedDepth`;
  t=159 `DA_StoryGoal_Player_Ch1_SeriousAccident_StoryGoal`; t=167 `DA_BlackBox_Investigation_DeepStart_Unknown_StoryGoal`
- t=169 **entered lifepod**: `DA_Storygoal_Player_Ch2_EnteredLifepod_StoryGoal`, `DA_StoryGoal_Player_Ch1_LifepodsFound`; t=173 `DA_StoryGoal_World_Ch1_LifepodNoABooted`;
  t=183 `DA_StoryGoal_World_Ch1_LifepodInvestigatorAssigned`; t=212 `DA_Storygoal_Player_Ch1_BiocapitalTip`
- t=226 ride: actor `BP_LifepodManager_C_UAID_047C166D6A3238B502_1890634767` (persistent level) logs via `LogLifepod`:
  "Loading Bink URL" → "Bink URL opened successfully" → "Playing Lifepod Video" → `HideHud` → "Lifepod Video Length - 57.85" → "Starting fade in" →
  "Server Lifepod Ride Starting" → "Server starting SG sequence" → "Lifepod Launch Logic Server"; goals `DA_Player_Ch1_LifepodRide1_StoryGoal`,
  `DA_StoryGoal_World_Ch1_LifepodsReleased`. (LifepodRide2..8 never unlocked.) The ride is an FMV (Bink), not a level sequence.
- t=284 "Server ending lifepod ride" → "Video Ended" → "Showing UW Presents"; t=285 `DA_StoryGoal_World_Ch2_LifepodArrived_StoryGoal`, `DA_BreachedSurface_StoryGoal`
- t=288.7 "Door Open Begin" + level sequence `/Game/Art/Cinematics/LifepodDoorOpen/LS_LifepodDoorOpen` (actor `LevelSequenceActor_UAID_047C166D6A3268B702_2131794261`);
  t=289 pawn **at (-336997, 433246, 242)** (surface), view target `CineCameraActor`
- t=291 `DA_Investigation_BioBed_Trigger_CoralGardens_StoryGoal`, `DA_Storygoal_Player_Ch2_FirstTimeAtSurface_StoryGoal`; t=295/302/310 `DA_Player_Ch2_FirstTimeAtSurface2_2/3/4_Storygoal`
- t=312 "Door Sequence End" + `ShowHUD`; t=313 view target back to the character, free at (-336997, 433246, 242) = **lifepod end position**
  — Δ = (−5250, +12576) cm from the SN2Terrain region centre (-331747, 420670) → **136 m away, inside the 300 m clearing radius**.
  The old test save loaded at (-331747, 420670, -2072), i.e. the region was centred on a different spot than the lifepod's final position.
- Data layer state reads failed (`GetRuntimeState`/`GetEffectiveRuntimeState` not callable this way → printed "?"); fix in the probe.

## Sources
- **Header dump of every game class:** `<ModkitDir>\Subnautica2-Project\Automation\Headers.hpp` (4.9 MB, UHT-style, UFunction signatures, no bodies).
  Also there: `Subnautica2-131439.usmap`, `DataIndex.json`, `GameplayTags.txt`, `AssetSnapshot.txt`. Grep these before probing in game.
- Packaged file list: `src/tools/sn2_packaged_files.txt` (gitignored, regenerate with retoc).

## What the intro is made of (from asset names, UNTESTED order)
- FMOD banks `intro/arrival_sequence`, `cinematics/adaptation_intro_sequence`, `cinematics/lifepod_sequence` (events: `lifepod_sequence_start_to_firstTakeoff`,
  `..._firsTakeoff_to_thrusterExplosion`, `..._waterImpact_to_end`, `..._Ending_for_use_with_FMV`, `arrival_*`, `intro_adaptation_sequence_sfx`).
- Level sequences: `/Game/Art/Cinematics/LifePodDeploy/LS_DeployLifepod_vFallOff`, `/Game/Art/Cinematics/LifepodDoorOpen/LS_LifepodDoorOpen`;
  biobed intro animations `AS_Biobed-IntroCinematic_Player`, `AS_Biobed_Player_IntroCinematic_02`.
- Story goals: `DA_Player_Ch1_LifepodRide1..8_StoryGoal`, `DA_StoryGoal_World_Noa_Ch1_Intro_EverTriggeredOnServer`, adaptation/biosample tutorial goals.
- Data layers in L_Main: `/Game/Maps/Main/DL_Lifepod_Static`, plus `USN2LifepodSettings` (DeveloperSettings) → `SequenceLifepodDataLayer`, `StaticLifepodDataLayer`,
  `LifepodVideo*` (FileMediaSource FMV, 4 quality variants). Start-zone data layers `Maps/StartZone/DL_*`, `ScorpiusDataLayers/DL_Scorpius_*`.

## Relevant classes (Headers.hpp line numbers, build CL-131439)
- `ASN2LifepodManager : AActor` (117980): `HideHud()`, `ShowHUD()`, `LogLifepod(FString, bool IsError)`.
- `ASN2WorldGameMode : AUWEGameModeBase` (121168): `BioBedManager (AUWEBioBedManager*)`, `SaveHandle`, `GameSettingsOverrides (FUWEGameConfigSettings)`,
  `OnPlayerGameStartedDelegateBP`, `OnPlayerJoinedReady`. `FUWEGameConfigSettings` has **no** skip-intro flag (Story: only `bUnlockAllDatabankEntries`).
- Story goals (module path to confirm in game, probably `/Script/UWEStoryGoals`):
  `UUWEStoryGoalsStatics` — `IsStoryGoalUnlocked(WorldContext, Goal, PlayerState)`, `UnlockPlayerStoryGoal(WorldContext, Goal, PlayerState)`,
  `UnlockPlayerStoryGoalForPawn`, `UnlockWorldStoryGoal(WorldContext, Goal)`;
  `UUWEStoryGoalsWorldSubsystem` — `UnlockStoryGoal(Goal, InitTarget, bIgnorePrerequisites)`, `Start/StopTimedStoryGoalSequence`, delegates `OnStoryGoalUnlocked`;
  `UUWEStoryGoalCommandComponent` (on `ASN2PlayerController.StoryGoalCommandComponent`) — `UnlockPlayerStoryGoal`, `UnlockWorldStoryGoal`;
  `UUWEStoryGoal : UUWEPrimaryDataAssetBase` — `StoryGoalType`, `StoryGoalUnlocks`, `UnlockingRequirements`, `UnlockOnRequirementsMet`, dialogue/notification/tag events.
- `SN2CheatManager:UnlockStoryGoal(Str TagName)` / `StoryGoalDebugger` exist (console disabled in normal saves).

## Recorder mod: `src/mods/SN2IntroProbe` (VERIFIED 2026-11-16: produced the timeline above; disabled since 2026-11-17)
Polls every 1 s: story goals (all loaded `UWEStoryGoal`, `IsStoryGoalUnlocked` diff), `DataLayerInstance` runtime states, pawn/view target/attach parent/location.
Hooks: `MovieSceneSequencePlayer:Play`, `MediaPlayer:OpenSource`, `SN2LifepodManager:{HideHud,ShowHUD,LogLifepod}`, `PlayerController:ClientRestart`.
For the recording run the terrain mods were disabled: `LogicMods\SN2Terrain` moved to `<Workspace>\disabled_mods\`, `SN2TerrainEdit : 0` in `ue4ss\Mods\mods.txt`
(re-enable both afterwards). Note: the old test save loaded at (-331747, 420670, -2072) — probably the lifepod landing area, i.e. where SN2Terrain clears.

## Character selection (user, 2026-11-16)
New game: short text → character selection → spawn on the biobed. In the log this is the `UWESpectatorPawn` phase in L_Main (~34 s) before the
ClientRestart that possesses `BP_Character_01_C`. So "spawned as BP_Character_01_C attached to BP_BioBed" is after selection — safe trigger point.

## Skip mod v1: `src/mods/SN2IntroSkip` (FAILED 2026-11-16, superseded by v4 below; history kept)
Trigger: ClientRestart in L_Main → pawn is not `UWESpectatorPawn` for ≥3 checks (1.5 s) → attached to `*BioBed*` and
`DA_Storygoal_Player_Ch2_EnteredLifepod_StoryGoal` not unlocked. Steps: `UWEBioBedStatics:UnassignPawnFromBioBed` + `K2_DetachFromActor(1,1,1)`;
`K2_SetActorLocation(-336997, 433246, 322)`; unlock the recorded goal list via `UWEStoryGoalsWorldSubsystem:UnlockStoryGoal(goal, pawn, true)`
(fallback statics); `DataLayerManager:SetDataLayerInstanceRuntimeState` `DL_Lifepod_Sequence`→0, `DL_Lifepod_Static`→2; `BP_LifepodManager_C:ShowHUD()`;
dumps `BP_LifepodManager_C` functions (`UClass:ForEachFunction`). Other APIs found: `UDataLayerManager` Get/SetDataLayerInstanceRuntimeState,
GetDataLayerInstanceFromName/FromAsset, GetDataLayerInstances; `UUWEBioBedStatics` AssignPawnToBioBed / SpawnPawnAtBioBed / UnassignPawnFromBioBed /
IsPlayerAssignedToAnyBioBed; `AUWEBioBedManager::GetBioBedManager`.

### Skip v1 run (2026-11-16 21:01) — LOGGED
- All steps OK: release + move (pawn settled at (-336997, 433246, 257)), 32/32 goals unlocked via `UWEStoryGoalsWorldSubsystem:UnlockStoryGoal`,
  data layers already correct at new-game start (`DL_Lifepod_Static` = 2 Activated from the beginning, `DL_Lifepod_Sequence` = 0), `ShowHUD` called.
- **Side effect:** unlocking the goals made `BP_LifepodManager_C` start the ride FMV ("Loading Bink URL" … "Server starting SG sequence",
  "Lifepod Launch Logic Server") ~0.1 s into the unlock loop — i.e. one of the early goals in the list (before the lifepod ones? the log order shows it fired
  between "move" and "unlocked 32/32") triggers `LaunchLifepod`. Next version must avoid this.
- `BP_LifepodManager_C` functions (30): `ApplyCreativeModeStart, AreAllPlayersInLifepod, AssignLatePlayer, AssignToBiobed, ExecuteUbergraph_BP_LifepodManager,
  FallbackVideoFailed, GetNumClampsReleased, GetRelevantLifepod, HasLifepodBeenLaunched, HideAllPlayers, JustBeforeVideoEnd, LaunchLifepod!, LifepodEndLogic,
  LifepodLaunchLogic, OnLifepodArrived, OnLifepodLaunched, OnMediaOpened_Event, OnPlayerJoinedReady_Event, OnSequenceEnd, OnSkip, OnVideoEnd, PlayVideo,
  ReceiveBeginPlay, ReceiveEndPlay, RemoveDeepStartTags, ServerLifepodRide, SetLifepodRideCompleted, ShowAllPlayers, UpdatePlayerStartAndTransforms,
  VideoNeverFinishedPlaying`. Candidates for a clean skip: **`ApplyCreativeModeStart`** (creative mode has no intro), `SetLifepodRideCompleted`,
  `RemoveDeepStartTags`, `UpdatePlayerStartAndTransforms`, `OnSkip` (video skip). Parameters still unknown — dump with `UFunction:ForEachProperty`.

### Skip v1 result (tester, 2026-11-16) — FAILED
Everything from the escape-launch video onward played as normal; afterwards the player sat in the lifepod and **could not move, turn or open the
inventory** (HUD visible), dialogue/notifications piled up, and the **breathing adaptation was not given** (goal unlock alone does not grant it).

### Adaptations API (Headers.hpp 115403, 121419; GameplayTags.txt)
`USN2AdaptationsPlayerStateComponent` (on the PlayerState): `GetAdaptations() -> TArray<FUWEPlayerAdaptation>`, `HasAdaptation(FUWEPlayerAdaptation)`,
`SetAdaptationEnabled(FUWEPlayerAdaptation, bool)`, `AdaptationUnlockChanged(FGameplayTag, int32 NewCount)`; delegates OnAdaptationInstalled/Removed/Initialized.
`FUWEPlayerAdaptation { FGameplayTag AdaptationTag; FText Name, Description, AdaptationMissingDescription; TSoftObjectPtr<UTexture2D> Icon;
TArray<TSoftObjectPtr<UUWEStoryGoal>> StoryGoalsToUnlock; bool bIsDescriptionVisibleByDefault; FGameplayTagContainer GameplayEffectsToRemoveOnAdapt; }`.
Tags: `Adaptations.Breathing`, `Adaptations.Missing.Breathing`, `Adaptations.Breathing.Missing`, `GameplayCue.Adaptations.BreathingAdaptationMissing`,
`Adaptations.HeatResistance`, `Adaptations.Stomach`, `Adaptations.AxumGlyphs`. Deep-start assets: `/Game/Blueprints/Blight/BP_AngelCombCore_DeepStart`,
`/Game/Blueprints/NarrativeBPs/DeepStart/BP_DeepStartLifepodClamps`, NoA CYOA data `Data/Narrative/NoA/CYOA/DeepStart/DA_NoA_CYOA_SC*`.

### Skip v2 = test build with keys (2026-11-16, UNTESTED)
Nothing automatic except logging + dump on spawn. Ctrl+1 dump (manager fn params via `UFunction:ForEachProperty`, input flags, movement mode, adaptations),
Ctrl+2 `ApplyCreativeModeStart()`, Ctrl+3 deep-start goals only + teleport + unstick, Ctrl+4 unstick (`RemoveDeepStartTags`, unassign biobed, detach,
`ResetIgnoreInputFlags`, `EnableInput`, walking mode, view target, `ShowAllPlayers`/`ShowHUD`, breathing via `SetAdaptationEnabled`).
Hot reload was enabled for this, then the game crashed in UE4SS.dll ~1 s after the menu (see `01_runbook.md` crashes) → set back to 0; probe polling reduced.

### BP_LifepodManager_C parameters (dump 2026-11-16 21:17; `UFunction:ForEachProperty` lists params AND BP locals — real params first)
- `ApplyCreativeModeStart(Character)` (local: HasLifepodBeenLaunched result)
- `OnSkip()`; `LifepodEndLogic()`
- `SetLifepodRideCompleted(Player)`; `RemoveDeepStartTags(Player)` (uses GetUWEAbilitySystemComponentFromActor + two MakeLiteralGameplayTag → removes 2 tags from the player's ASC)
- `UpdatePlayerStartAndTransforms()` (switch on GetGameModeType; casts to `BP_Static_Lifepod_Surface`; uses GetRelevantLifepod)
- `OnLifepodArrived()`; `HasLifepodBeenLaunched() -> Launched` (checks a story goal OR a global tag); `AreAllPlayersInLifepod() -> PlayersAllIn`
  (casts to `BP_Lifepod` / `BP_Static_Lifepod`, calls "Are All Active Players in Lifepod")
- Lifepod classes: `BP_Lifepod` (ride), `BP_Static_Lifepod`, `BP_Static_Lifepod_Surface`.
- v2's first build called these without the player argument; fixed (Ctrl+2 → `ApplyCreativeModeStart(pawn)`, unstick → `RemoveDeepStartTags(pawn)`,
  `SetLifepodRideCompleted(pawn)`).

### v2 run 2026-11-16 21:22 — **Ctrl+2 then Ctrl+3 WORKS** (VERIFIED by tester)
- Ctrl+2 `ApplyCreativeModeStart(pawn)`: no visible change, player stays on the biobed and the deep-start intro keeps running, but it **unlocks the
  arrival goals** over the next ~30 s (`Investigation_BioBed_Trigger_CoralGardens`, `Ch2_FirstTimeAtSurface`, `FirstTimeAtSurface2_2/3/4`).
- Ctrl+3 (≈40 s later): move to (-336997, 433246, 322) OK; `RemoveDeepStartTags(pawn)` OK; `SetLifepodRideCompleted(pawn)` OK; unassign biobed + detach OK;
  ResetIgnoreInputFlags OK; view target OK; ShowAllPlayers/ShowHUD OK. Failed (harmless): deep-start goal unlock 0/18 (subsystem call failed — cause TBD),
  `CharacterMovement:SetMovementMode` ("attempt to call a UObject value"), `AdaptationUnlockChanged` (same error — `adaptationsComp` lookup returns a bad object).
- Game then unlocked `Ch2_EnteredLifepod` by itself (t=49 s, lifepod trigger) and later `DA_Player_Ch2_FirstDive_StoryGoal` (t=129 s).
- Tester: **breathing adaptation works** (→ granted by `RemoveDeepStartTags`, which removes the missing-breathing tag; no adaptation call needed),
  **no ride FMV / door sequence**, player was frozen only until the "open PDA" tutorial step was done, then free.

### Skip v3 (automatic, 2026-11-16) — FAILED (see v4 "why v3 failed")
1.5 s after a fresh-intro spawn: `ApplyCreativeModeStart(pawn)` → deep-start goals (subsystem → `UnlockPlayerStoryGoal` → `UnlockWorldStoryGoal`
fallbacks, logs which worked) → move into lifepod → `RemoveDeepStartTags(pawn)` → `SetLifepodRideCompleted(pawn)` → unassign/detach → reset input →
view target → `ShowAllPlayers`/`ShowHUD`. Dropped: lifepod/ride goals, adaptation calls, SetMovementMode. Keys: Ctrl+1 dump, Ctrl+4 unstick.
Open question: does unlocking `DA_Tools_PDA_StoryGoal` clear the "open PDA" tutorial gate, or must the player still open the PDA once?

### Skip v4 — VERIFIED 2026-11-17 (tester: "It worked perfectly")
Final design (`src/mods/SN2IntroSkip/Scripts/main.lua`):
- **Arming:** `PlayerController:ClientRestart` hook arms the mod only if the hook's own controller (`ctx:get():GetWorld():GetFullName()`) is `L_Main`.
  In the lobby the mod runs nothing (see the GC-watchdog rule in `01_runbook.md` — scanning with `FindAllOf` every 0.5–1 s in the lobby is the suspected cause
  of the 20 s `FinishDestroy` crash; with the recorder off and this change the load succeeded, 1 of 1 so far — not yet statistically solid).
- **Phase A** (≥1.5 s after the character spawns, pawn attached to a `*BioBed*`, `Ch2_EnteredLifepod` not unlocked): `BP_LifepodManager_C:ApplyCreativeModeStart(pawn)`,
  unlock 18 deep-start goals (`UWEStoryGoalsWorldSubsystem:UnlockStoryGoal(goal, pawn, true)`, 18/18 OK). Player stays in the bed.
- **Phase B** (pawn no longer attached to the bed — 26.0 s in this run, i.e. after the normal wake-up animation; 45 s timeout): move to (-336997, 433246, 322),
  `RemoveDeepStartTags(pawn)` (also removes the missing-breathing state → breathing adaptation works, panting stops), `SetLifepodRideCompleted(pawn)`, unassign biobed + detach,
  `ResetIgnoreInputFlags`, `SetViewTargetWithBlend(pawn)`, `ShowAllPlayers`, `ShowHUD`.
- **Why v3 failed:** moving/unlocking at 1.5 s interrupted the bed wake-up animation → input stayed locked, pawn ended inside the lifepod back wall
  (the 26 s delay also let the pawn spawn at the right place relative to the lifepod).
- **Crash rules found on the way:** (1) never call methods on empty-result objects (`pawn:GetAttachParentActor():GetClass()` when not attached → UE4SS.dll AV;
  helpers `nameOf/fullOf` now check `isValid` first); (2) never read `GetAdaptations()` etc. (complex structs); (3) no periodic `FindAllOf` in the lobby.
- SN2IntroProbe (recorder) is disabled (`SN2IntroProbe : 0`, `enabled.txt` removed); enable it again only for new recordings, and re-check (3) first.

## Current state of the world replacement (2026-11-17)
- `LogicMods\SN2Terrain` is **not installed** (parked in `<Workspace>\disabled_mods\SN2Terrain` for the recordings); reinstall by moving it back to `<GameDir>\Subnautica2\Content\Paks\LogicMods\`.
- Lifepod end position (-336997, 433246, 322) is ~136 m from the crater centre (-331747, 420670) used by SN2Terrain → crater must be moved/rebuilt around the lifepod.
- ModActor is also spawned in the lobby (self-destroys there); gate it to `L_Main` when integrating.
- Nothing of the "never load SN2 world" step has been run yet. Planned first experiment: option 1 (UNTESTED), compare RAM/object counts before vs after.

## World replacement — options (to evaluate after the recording)
1. **Keep L_Main, stop World Partition streaming of terrain cells** (e.g. CVar `wp.Runtime.OverrideRuntimeSpatialHashLoadingRange` / disabling streaming
   sources) so only always-loaded actors (game mode, ocean, sky, lifepod, managers) exist; ModActor supplies terrain. Needs a way to run CVars from Lua
   (`KismetSystemLibrary:ExecuteConsoleCommand` — UNTESTED whether the SN2 console gate blocks it).
2. **Own level** built in the modkit with our terrain + required systems (ocean, sky, lifepod, player start, game mode) and travel to it instead of L_Main.
   Cleanest for RAM but must recreate everything the game expects from L_Main.
3. Current approach (destroy streamed cells' actors + GC) — works, but cells are still read from disk and briefly loaded.

## Blueprint disassembly: how the intro really works (2026-11-18, VERIFIED from cooked assets; behaviour of the override UNTESTED)
Tooling (reproducible, all on `<ModkitDir>` D:, nothing on C:): `retoc to-legacy --no-shaders --version UE5_6 -f <NamePart> <GameDir>\Subnautica2\Content\Paks <out>` (pass the **Paks directory**, not the .utoc;
`-f` is a name filter) → legacy `.uasset/.uexp`. Parse with **UAssetAPI 1.1.0** (dotnet 8, NuGet; `new UAsset(path, EngineVersion.VER_UE5_6, new Usmap("<Automation>\Subnautica2-131439.usmap"))`,
`SerializeJson()`; bytecode in `FunctionExport.ScriptBytecode`). Jump targets in the Kismet bytecode = (sum of `expr.Write()` sizes) + statement index. CookedExport (`--dump-blueprints`) fails: Oodle "not initialized"
(`-od <Engine>\Binaries\DotNET\AutomationTool\oo2core_9_win64.dll` did not help). Scratch work lives in `<ModkitDir>\scratch_bp\` (disassembler `tools\kdis.py`).
- **Start system.** Every spawn applies the conditions of one `ASN2PlayerStart` actor (class `BP_*PlayerStart`, C++ `AUWEPlayerStart::ApplyStartConditions`, log line `Applying start conditions of <PlayerStartTag> to player`).
  Data on each start's CDO: `PlayerStoryGoals`, `UnlockStoryGroups`, `InventoryItems` (inventory), `EquippedItems`, `GrantTags`, `RemoveTags`, `AppliedEffects`, `bSetTimeOfDay/TimeOfDay`, `DefaultForGameModeClass`, `PlayerStartTag`.
  Survival's start = `BP_DeepPlayerStart` (tag `Deep`, `DefaultForGameModeClass = BP_SN2WorldGameMode_C`); Creative's = `BP_CreativeModePlayerStart` (tag `Creative`, `DefaultForGameModeClass = ..._CreativeMode_C`).
- **`BP_DeepPlayerStart` = the intro.** `GrantTags = [Character.State.HideUI, Adaptations.Missing.Breathing]`, `AppliedEffects = [GE_BreathingAdaptationMissing_C, GE_DeepstartHealthLoss_C]`; `OnStartConditionsApplied`:
  `WorldEventTracker.Notify(EventTracker.DeepStart.PlayersStarted)`; if lifepod already launched → `Manager.AssignLatePlayer(pawn, true)`; else hide pawn, `AssignToBiobed`, add global tag `Gamestate.DeepStartIntro`,
  `DeepStartIntroTrigger.Trigger`, `BioBed.PlayDeepStartBiobedAnim(pawn)`, spawn `BP_DeepStartPreparePlayerHandler`; removes the tag again when `FirstTimeAtSurface` goal unlocks.
- **`BP_CreativeModePlayerStart`:** `OnPreSpawnReady` → `ClientPushScreenToLayer(WBP_CharacterIntroScreen_C, 6)` (character select); `OnStartConditionsApplied` → `BP_LifepodManager_C:ApplyCreativeModeStart(pawn)`.
  Data: goals `Ch2_FirstTimeAtSurface`, `Ch1_LifepodsFound`, `Ch1_FirstPrint`, `Ch1_AdaptationTutorial1`; group `StoryGroup.Deepstart`; **InventoryItems** Flashlight, Scanner, Builder, Wakemaker, SonicResonator, Flares, SurvivalMultiTool;
  **EquippedItems** OxygenTank_Medium, ImprovedFins; RemoveTags `Character.State.HideUI`, `Adaptations.Missing.Breathing`; time 0.25.
- **Cheats come from the game mode, not the start:** `BP_SN2WorldGameMode_CreativeMode` CDO `GameSettingsOverrides` (`FUWEGameConfigSettings`): `bInvisibleToHostiles, bEnableNoCost, bUnlockAllBioAbilities, bUnlockAdaptations, bUnlockAllBiomodSlots, bUnlockAllRecipes, CraftingSpeedMultiplier 3, QuickProccessing, bEnableUnlimitedPower, bUnlockAllScanningFilters, bInvulnerable, bBlockOxygen/Food/WaterConsumption …`.
  That is where the `Cheat.*` / `DamageImmunity.*` / `Adaptations.*` global tags in the 2026-11-18 Creative log come from. (Hence v5's strip-after-the-fact approach was the wrong layer.)
- **`BP_ShallowsPlayerStart` (tag `Shallows`) is exactly "intro skipped, nothing else":** goal `Ch2_FirstTimeAtSurface`, group `StoryGroup.Deepstart`, RemoveTags `[Character.State.HideUI, Adaptations.Missing.Breathing]` (= breathing works), time 0.25,
  **no InventoryItems, no EquippedItems, no GrantTags**. Other starts: `Farmlands/Pinnacles/Karakorum` (Deepstart group + small tank + fins only), `FreeBuild` (Builder + ImprovedFins + Cheat.GodMode…), GoldenPath `BP_01..10_*` (story checkpoints with full kits), `Phototour`, `BlightEncounter`, `Graveyard*`, `SparsePlains_LeviathanZone_A/B`.
- **`BP_LifepodManager_C`** (`ReceiveBeginPlay`, ubergraph entry 4408): `GetGameModeType`; **Creative → binds nothing** (no intro listeners); Survival/None → binds `OnLifepodLaunched` (story-goal `DA_Player_Ch1_LifepodRide1_StoryGoal` starts the Bink ride video) and `OnPlayerJoinedReady_Event`
  (→ `AssignLatePlayer(pawn,false)`, a no-op until the pod has launched). `HasLifepodBeenLaunched()` = story goal `LifepodArriveSG` unlocked OR global tag `Gamestate.LifepodAscending`.
  `ApplyCreativeModeStart(Character)`: if not launched → `LifepodEndLogic()` (ubergraph 7800 `OnLifepodArrived` chain); then `AssignLatePlayer(Character,false)`.
  `AssignLatePlayer`: only when launched; `Character.SetLifepodRideCompleted()`, `AssignPawnToBioBed(static surface lifepod bed)`, `RemoveGlobalTag(Gamestate.DeepStartIntro)`, ASC persistent tags: `Character.State.HideUI` off, `Adaptations.Missing.Breathing` off, `UI.PDA` off, `Adaptations.Breathing` **on**, remove effect `GE_BreathingAdaptationMissing_C`.
- **Command line:** the shipping exe contains `OverridePlayerStart=` (and `ChoosePlayerStart/FindPlayerStart/PlayerStartTag` strings). Test: `Subnautica2-Win64-Shipping.exe -OverridePlayerStart=Shallows` (the `steam://run/1962700//<args>/` URL did NOT start the game; start the exe directly with `SteamAppId=SteamGameId=1962700` while Steam runs). Result: **VERIFIED 2026-11-18** (tester): new Survival game skips the whole intro, hotbar empty, only the breathing adaptation, movement free. No Lua mod involved (UE4SS + SN2WorldProbe were loaded, load succeeded, no crash). Spawn point relative to the lifepod/crater NOT yet recorded.
- Consequences: SN2IntroSkip (v1–v5) deleted; launcher `src/tools/launch_game.sh` (`SN2_START=none` disables the override). The Creative-save route and v5 strip approach are obsolete. Survival rules stay intact (no cheats, normal game mode).
- Open: the `Shallows` start actor's location (where the player appears) and whether it is inside the area we replace; alternatives if it is wrong: other starts by tag (`Farmlands`, `Pinnacles`, `Karakorum`), or move the pawn from a mod. Inventory later: edit the start's `InventoryItems/EquippedItems` lists (cooked override of `BP_ShallowsPlayerStart`) or `ASN2PlayerStart` data at runtime.
