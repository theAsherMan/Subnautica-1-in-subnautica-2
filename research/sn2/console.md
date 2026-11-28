# SN2 console commands

Full pass-1 notes: `git show 3449200:research/sn2/console.md`.

## Console commands

**Status: the list and signatures are VERIFIED (F9 dump, 2026-11-15), but in the test save the game answers "commands are disabled".**
Unknown whether a cheats flag (`EnableCheats`, a save/game-mode setting) unlocks them — UNTESTED. Until then, implement test actions in Lua instead.
The underlying `SN2CheatManager` UFunctions can probably be called directly from Lua (`FindFirstOf("SN2CheatManager"):Warp(x, y, z)`) — UNTESTED; this may bypass the gate.

Open the console with **~** or **F10** (UE4SS ConsoleEnabler). 287 game-specific exec functions were dumped (full list with parameters:
`<Workspace>\reports\exec_functions.txt`); 219 live on `SN2CheatManager`, enabled by UE4SS's CheatManagerEnabler.
The devs also ship an ImGui debug UI: `ToggleDebugUI`, `ToggleImGuiCursor`, `ToggleDebugInfoVisibility`.

### World / placement
| Command | Args | Notes |
|---|---|---|
| `Spawn` | `<ItemNameAndQuantity>` | spawns items/objects by name |
| `SpawnCreature` | `<CreatureNameAndQuantity>` | e.g. `SpawnCreature Geordie 3` |
| `SpawnAll` | — | |
| `Summon` | (engine) `<ClassPath>` | spawns any actor class at the camera |
| `Goto` / `GotoAll` | `<LocationName>` / `<SecondsToWait>` | 228 named locations (`DumpAllGotoNames` lists them); names follow `Data/GotoLocations/DA_Location_*` |
| `Warp` | `<X> <Y> <Z>` | absolute teleport |
| `Teleport` | — | to the aim point |
| `Coords` / `GetCoords` / `LogLoc` | `Coords "<X Y Z>"` | print/set position |
| `WorldPopRemove` | `<ResourceName>` | remove world-pop placements |
| `DestroyCreatures` | `<CreatureName> <Amount>` | |
| `KillAllOfClass` / `DestroyAllActorsOfClass` | `<ClassName>` | |
| `ListAllActors` | `<Filter>` | |
| `ViewActor` / `ViewClass` / `ViewSelf` | | camera attach |
| `StreamLevelIn` / `StreamLevelOut` / `OnlyLoadLevel` | | level streaming control |
| `SetWorldOrigin`, `GridScale <f>` | | |

### Environment
| Command | Args |
|---|---|
| `SetCurrentWeather` / `SetNextWeather` | `<WeatherName>` (`PrintAllWeatherTypes` lists; e.g. `DA_StormA`, `DA_Clear`) |
| `GoToNextWeather`, `EnableWeather <0/1>` | |
| `SetTimeOfDay` | `<"HH:MM">` |
| `SetTimeOfDaySpeed`, `SetDayNumber <N>`, `DayNight <0..1>`, `Day`, `Night`, `FreezeTime`, `UnfreezeTime` | |
| `ToggleFog` | |

### AI / events / story
`AIDirectorDebugger <Tag>`, `DynamicEventDebugger <Tag>`, `StartDynamicEvent <Name>`, `StoryGoalDebugger`, `UnlockStoryGoal`, `Trigger <Name>`,
`AddGlobalTag <Tag>` / `RemoveGlobalTag` / `ToggleGlobalTag`, `AddTag` / `RemoveTag` (on self), `UnpossessAllCreatures`, `ToggleAILogging`, `DebugDrawStimulus`.

### Player / cheats
`God`, `Ghost`, `Fly`, `NoClip`, `Walk`, `FastSwim`, `SwimSpeed`, `Speed`, `Oxygen`, `Hunger`, `Thirst`, `Heal`, `Invisible`, `Unstuck`, `Item <Name Qty>`, `Give <Name Qty>`,
`Equip <Tag>`, `EquipAll`, `Unlock <Name>`, `UnlockAll`, `UnlockAllRecipes`, `UnlockAllDatabank`, `UnlockAllBioAbilities`, `AddBiomod`, `ClearBiomods`,
`NoCost`, `FastBuild`, `FreeBuild`, `UnlimitedPower`, `UnlimitedBattery`, `Slomo`, `ToggleFreeCam`, `ToggleDebugCamera`, `ThirdPerson`, `SetFOV`, `HideHud`, `ToggleHUD`.
Macros: `RunMacro <name>` runs `Content\Macros\<name>.txt` (shipped: `Superman`, `Starting Items`, `Base Pack`, `Equipment Pack`, `SculptDebug`).

### Base building debug
`BaseToggleFreePlacement`, `BaseAllowIllegalBuilds`, `BaseShowLattice`, `BaseShowCellBorders`, `BaseToggleSupportCheck`, `BaseRegenerateMeshes`, `BasePrintAllStructures`, …

### Save / session
`SaveGame`, `LoadGame`, `AutoSaveGame`, `ToggleAutoSave`, `SetAutoSaveDuration`, `NewGame`, `NewGameOfMode`, `ContinueGame`, `ClearSaves`, `OpenSavesFolder`, `PlayerStart`.
Dangerous (do not run): `CrashClient*`, `CrashServer*`, `ForceProcessExit`, `KickPlayer`.

### ExecuteConsoleCommand HighResShot works in a normal save (2026-11-23)
`KismetSystemLibrary:ExecuteConsoleCommand(world, "HighResShot 1", pc)` from Lua (SN2BugShot) writes `%LOCALAPPDATA%/Subnautica2/Saved/Screenshots/Windows/HighresScreenshot0000N.png` (1920x1080) **VERIFIED (2026-11-23, autotest run 20261123_174947_bugshot; image shows the lifepod interior and hatch)**. The file appears asynchronously (a few hundred ms), so poll for it. Other console commands stay disabled in the test save.
