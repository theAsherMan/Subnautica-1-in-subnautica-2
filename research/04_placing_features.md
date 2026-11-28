# Placing features

Status: only "Rocks, props, structures" is VERIFIED. Every other recipe here is **UNTESTED** — class and property names are verified (see `02`), but nobody has
spawned these actors from Lua yet. When you test one, update its status line with the date and result.
"Spawn" means the deferred-spawn recipe in `03_creating_terrain.md` §2 (helper `spawnActorOfClass` in SN2TerrainEdit) with a different class; set properties
between `BeginDeferredActorSpawnFromClass` and `FinishSpawningActor` where possible. Blueprint classes must be loaded first (`LoadAsset` on the game thread,
or `StaticFindObject` if an instance exists nearby). Console commands mentioned below are disabled in the test save.

## Rocks, props, structures — VERIFIED 2026-11-14
`SN2TerrainEdit` → `PLACEMENTS` table: `{ name, mesh = "/Game/…/SM_X.SM_X", loc = {X,Y,Z}, yaw, scale }`. Auto-placed 4 s after the player appears in `L_Main`, F4 to re-place.
First placed rock: scree pile at (-200350, 433900, -26450). Use `BP_*` prefab/rock Blueprint classes for clusters (e.g. `BP_Tufa_RockPile_01d_C`, `BP_CG_CoralDomeMedium_02a_C` — these were in the loaded-actor list).

## Creature spawns
- Quick tests from the console: `SpawnCreature <Name> [Qty]` (names follow the archetype/agent names: Geordie, ElectricGeordie, Hammerhead, NeedlerShark, NibblerShark, TwinEels,
  JetoCaris, Marrowbreach, Cerathecan, Epicurean, CoralCrab, SurgeJelly, JellyFisher, Sandspear, JellyRing, Waxmoon, TarCrab, Quadrate, Houndgar, SeaOlive, Halfmoon, Bullethead,
  FlashFish, AnemoneCrab, FourEye, Pneumo, SpineyTail, HillRay, WaterSlug, VoidLeviathan, CollectorLeviathan, DeepWingLeviathan…), `DestroyCreatures <Name> <Amount>`, `WorldPopRemove <ResourceName>`.
- Persistent, systemic spawns: a `UWEBoxWorldZone` (box 100 × 200 × 120 m) whose `RegionAsset` points at a `UWEWorldRegionDataAsset`. The region DA + its `_Config`
  list `DA_WPResource_*` entries (species, densities, surfaces). Copy `DA_L_Template_World`/`_Config` for a new region (needs an asset mod → IoStore pak, or runtime
  property edits on an existing region DA from Lua). Per-species caps: `PopSettings/DA_<Creature>PopulationSettings`.
- Home areas: `UWEHabitationVolume` with a `HabitationAreaTag` and a sphere/box shape. Set-piece encounters: `Data/DynamicEvents/*`, console `StartDynamicEvent <Name>`.
- Navigation: creatures use Mercuna 3D nav (`MercunaNavGridVolume`, octrees). New terrain far from existing nav volumes will have no pathing until nav is rebuilt (modkit).

## Hot / cold area
Spawn `BP_AreaTemperature_Proto_C` (class path `/Game/Blueprints/Prototypes/ExtremeTemperatures/…` — exact asset path TBD; the instance's component is
`BPC_AreaTemperatureRegionVolume_Proto_C`) and set on the component: `Temperature` (the shipped one is 100), `Radius` (cm), `ContributionType`, `BoxExtent`.
The player already carries the heat/cold accumulation effects, so damage and the heat-resistance items work automatically.
Decorate with `BP_BO_HeatVent_{Small,Medium,Large}_C` (also power sources) and a fog sphere with warm `Emissive`.

## Water colour / fog per area ("biome look")
Spawn `BP_UWEWaterBiomeRegionActor_C`; set `WaterBoxVolumeComponent.BoxExtent` to the area size and fill `BiomeVolumeComponent.WaterLightSettings`:
`BiomeExtinction`/`BiomeExtinctionSkylight` (how fast light dies, per channel — green/red-heavy = murky), `BiomeAlbedo` + `BiomeNeutralColor` (water tint),
`WaterFogDistance/Thickness/BaseThickness` (visibility), `BiomeBlendDistance` (soft edge). Sliders on the BP add sediment/bubbles/marine snow.
Alternative cheap mood: `BP_Fog_Sphere_C` (Albedo/Extinction/Emissive/Scale) and a local `PostProcessVolume`.
Global: `BP_UWESky_C` — `SetTimeOfDay "HH:MM"`, `SetCurrentWeather <DA name>` from the console, or set `TimeOfDay`/weather refs in Lua.

### Enums, related classes and the SN1 transfer tools (2026-11-24, from `<ModkitDir>/Subnautica2-Project/Automation/Headers.hpp` ~line 140320)
- `EBiomeRegionType` {BRT_Water=0, BRT_MaskedWater=1, BRT_Air=2}; `EBiomeRegionVolumeType` {BRVT_Brush=0, BRVT_Shape=1}; `EBiomeBlendType` {XYZ=0, XYSeperateZ=1}. **VERIFIED (2026-11-24, header)**
- `AUWEWaterBiomeRegionActor` functions: `RecreateMaterials`, `SetAirLightSettings`, `SetWaterFogOpacityWeight`, `SetupAirVolume`. Components also
  `WaterStaticMeshComponent`, `InternalVolumeModel/Mesh`, `InternalWaterPlaneMesh`. `UUWEBiomeTrackerSubsystem{SkyActor, Volumes, BiomeMaterialParameterCollection,
  BiomeNiagaraParameterCollection}`; `UUWEBiomeMapComponent{CaptureRadius, RenderTarget, DefaultVolumeSettings, WorldToBiomeMapScaleAndOffset}` (on BP_Ocean);
  `UUWEWaterBiomeRegionSettings{MaterialBiome, MaterialBiomeMasked, MaterialAir}`; `FUWEWaterLightSettingsAdvanced{BiomeAlbedoPower, BiomeAlbedoTint, BiomeEmissive,
  BiomeAlbedoDesaturation, BiomeAlbedoBrightness}`. **VERIFIED (2026-11-24, header)**
- The modkit's `Plugins/UWEWater` holds only `UWEWater.uplugin` (no C++, no `.usf/.ush` shaders) **VERIFIED (2026-11-24, file search)**, so the meaning of the
  WaterLightSettings numbers cannot be read from source: the SN1 -> SN2 conversion is calibrated empirically from SN1/SN2 screenshot pairs.
- `WaterLightSettings` is not exposed to Python; set it through T3D text (EDIT COPY, add `WaterLightSettings=(...)` to the `Begin Object Name="BiomeVolumeComponent"`
  property block, destroy, EDIT PASTE). Proven on the ocean region in `sn2world_map.py` `paste_region_with_water_light` (2026-11-19).
- Transfer pipeline: `src/tools/sn1_biome_transfer.py` (SN1 biome map -> boxes + converted settings, see `10` §6) ->
  `src/modkit/scripts/sn1biome_regions.py` (editor; one `/Game/Blueprints/World/Water/BP_UWEWaterBiomeRegionActor.BP_UWEWaterBiomeRegionActor_C` per box in
  L_SN2World, scale 1, tags `SN1Biome` + `SN1Biome_<biome>`, folder `SN1Biome/<biome>`; BoxExtent, volume type and WaterLightSettings all go in through one
  T3D copy/paste of all regions; save + reload check) -> `tools/cook_install.sh SN2EmptyWorld 2`. Editor side **VERIFIED (2026-11-26)**: 42 Safe Shallows
  regions saved, each re-copied T3D has its own `BoxExtent` and the converted WaterLightSettings, before and after a reload. Effect in game: **FAILED
  (2026-11-26, autotest screenshots, run `20261126_175137_sn1cmp_shallows`)**: no visible change, water still orange/brown inside the Safe Shallows
  boxes (details `10` §6). The regions ARE loaded at runtime with the converted WaterLightSettings **VERIFIED (2026-11-26, envprobe, run `20261126_180611_sn1cmp_shallows_env`)**,
  and the SN2 ocean region is blue too, so the cause is the render path, not the values (`10` §6). Region priority and seams: UNTESTED.
- Fresh `BP_UWEWaterBiomeRegionActor_C` as spawned in the editor **VERIFIED (2026-11-26, T3D dump `<Workspace>/reports/lmain_biome_regions/fresh_water_region.t3d`)**:
  - Components: `BiomeVolumeComponent` (UWEWater.UWEBiomeVolumeComponent), `PostProcessComponent` (UWEBiomePostProcessComponent), `RootComponent`,
    `WaterBoxVolumeComponent` (**UWEVolumeTracker.BoxVolumeComponent**: a ShapeComponent, *not* an engine `BoxComponent`, so `get_components_by_class(unreal.BoxComponent)`
    misses it; find it by name), `WaterStaticMeshComponent`, `WaterVolumeComponent` (UWEVolumeTracker.BrushVolumeComponent).
  - BoxExtent = 0 and bounds = 0. The modkit C++ is a stub: `call_method("SetBoxExtent", (vec, True))` runs but changes nothing, and `GetUnscaledBoxExtent` always
    returns 0. Set `BoxExtent=(X=..,Y=..,Z=..)` as a line in the `Begin Object Name="WaterBoxVolumeComponent"` property block of the T3D; it exports back after a paste and a reload.
  - Not exposed to Python (`get_editor_property` -> "Failed to find property"): `biome_region_volume_type`, `biome_region_type`, `is_ocean`, `priority`; there is
    no `unreal.BiomeRegionVolumeType` enum.
  - The actor-level line reads `BiomeRegionVolumeType=BRVT_Brush` after a spawn and after a level reload. After a T3D paste with `BRVT_Shape`, the line is not
    exported at all, meaning it equals the class default. The saved .umap name table has `BRVT_Brush` but no `BRVT_Shape`, so the class default is Shape and the
    Brush value comes from the editor's construction pass. Which one the cooked game uses: **UNTESTED** (check if the regions show no effect).
  - There is also an actor-level `WaterLightingSettings=(...)` with every field 0 (fog distance, opacity weight, caustics...). It is left alone; the runtime
    values read so far come from `BiomeVolumeComponent.WaterLightSettings` (`03` envprobe).
- L_Main region probe (`src/modkit/scripts/lmain_biome_regions_probe.py`, 2026-11-26): in the editor only the ocean region is loaded:
  `BP_UWEOceanBiomeRegionActor_C`, loc (0, 0, -5000000), scale (1e6, 1e6, 1e5), a child actor of BP_Ocean_C, so it cannot be copied. The per-area water regions
  live in World Partition cells that are not loaded, and `unreal.WorldPartitionEditorSubsystem` does not exist in Python, so SN2's own hand-tuned per-area
  values were not obtained. **FAILED (2026-11-26)** as a calibration source; summary in `<Workspace>/reports/lmain_biome_regions/summary.txt`.
- Known blocker for any comparison: L_SN2World water looks dark brown/orange without blue fog (see `00` step 3.1(a)); a region's effect may be hidden by it.
- **Region water volume (SOLVED 2026-11-27, `10` 'Region water volume in L_SN2World: SOLVED'):** the underwater look needs the Volume-domain `M_OceanVolume` on a region cube, the placed ocean region owning tracker slot 15 (remove `BP_Ocean`'s child region `CAT_0`) and `BiomeRegionVolumeType` = Shape at runtime (set from the cooked ModActor graph; a saved Shape is never serialized because the editor stub default is Shape, the game default Brush). Baking the MID alone (earlier root-cause guess) was not enough. Earlier diagnostic (2026-11-26): at the ravine pose the 42 SN1Biome region PostProcessComponents all read BlendWeight 0.0 (the ocean region's PP reads 1.0) although the camera is inside one box. Whether boxes need an overlap/collision setup that the T3D-pasted `WaterBoxVolumeComponent` lacks: UNTESTED.

## Music and ambience
Spawn `UWEMusicVolume` and set `MusicVolumeComponent.Config` to a `UUWEMusicVolumeData` (`/Game/Data/AudioData/MusicData/DA_Music_*_Playlist`), `Priority` higher than neighbours.
Ambience: `FMODAmbientSound` with an FMOD event (`/Game/FMOD/Events/sfx/environment/ambience/underwater/...`), or the `DA_Ambience_*` data. New audio = new FMOD Studio 2.03 bank
dropped next to the others (loading mechanism TBD) — re-pointing to existing events needs no new banks.

## Lights
Standard `PointLight`/`SpotLight` actors spawn fine (53/11 loaded in the area); game light fixtures are `BP_Lighting_*`, `BP_LightStick_Static_C`, `BP_Cicada_SpotLight_01_C`.

## Resources / flora
World-pop resources: `BP_WorldPopSpawnedTitanium_C`, `…Quartz_C` etc. are placed by the zone system; hand placement via `BP_ResourceDeposit_<Mineral>_C` and `BP_ResourceNode_<Mineral>_C`
(Titanium, Copper, Quartz, Lead, Sulfur, Gold, Celestine, Lithium, Salt, Silver, Atacamite, Fulgurite, TarGraphene, AxumRebar). Flora Blueprints live under
`Art/Environment/Biome/<Biome>/{Organic,Foliage,Corals}` (e.g. `BP_AcidAnemone_C`, `BP_PomePlant_01a_C`, `BP_Freesia_*`, `BP_CG_CoralDome*_C`) and surface rules in `Data/SurfaceSpawnData`.

## Scale reference
Player stood at z = −240 m; Coral Gardens landscape tiles 252 m; spawn zone boxes 100 × 200 × 120 m; temperature radius 15 m; fog sphere blend 5 m; ocean body 10 km square.

## Vehicles: spawning a Tadpole (2026-11-23, mod `SN2Tadpole`, run `autotest/20261123_164556_tadpole`, plan `tadpole.json`, DONE 156 s)
- `FindFirstOf("SN2CheatManager"):Spawn("Tadpole")` spawns a real vehicle: **VERIFIED (2026-11-23)** UE4SS.log `cheat produced 1 new Tadpole actor(s)`, class `BP_Tadpole_C` (native `SN2Tadpole`, found with `FindAllOf("SN2Tadpole")`). The cheat places it near the player; `K2_SetActorLocation` + `K2_SetActorRotation` then moved it: final loc read back (-731,-951,-143), as requested.
- Screenshot `autotest/20261123_164556_tadpole/shots/01_uw_pod_k5.png` (pawn 1 m under water at the pod, looking toward yaw -136): a white Tadpole hull with cockpit and cyan glow, partly overexposed, just under the horizon about 12 m away. **VERIFIED (2026-11-23, autotest screenshot)** that it exists and is visible. Not seen in the other yaws (k6 also shows it at the left edge).
- Power: the actor has `BPC_PowerCell` (component), `PowerInventoryComponent`, `PowerInventoryInteraction`, `PowerCellItemType` (soft ptr on `SN2Tadpole`). Charge value NOT read (UNTESTED); enterability and driving UNTESTED (cannot be automated).
- **Enter and drive: VERIFIED (2026-11-23, user F1 report `<Workspace>/bugshots/20261123_181716_004` `screen.png`).** The user was piloting an F4 Tadpole about 250 m from the pod at UE (-2882,24957,-6669), HUD 66 m depth. The screenshot shows:
  - the cockpit view, with both hands on the control sticks;
  - prompts "Exit (E)" and "Turn Lights On (mouse)";
  - a gauge panel at the bottom right with 100 (wrench, hull) and 100 (lightning, power).

  So the spawned Tadpole has full power and can be entered and driven. Persistence in a save is still UNTESTED.
- Direct spawn fallback (`BeginDeferredActorSpawnFromClass` of `/Game/Blueprints/Vehicle/BP_Tadpole.BP_Tadpole_C`) is coded but UNTESTED (cheat worked, so it never ran).
- L_SN2World geometry measured 2026-11-23: `BP_StaticLifepod_Surface_C` actor location (0,0,100), yaw 52.4; `BP_Ocean_C` at Z=0 (water surface); player standing inside the pod is at about Z=235.
- Cheat state: cheat commands change only the world actor list; the Tadpole is a normal world actor (whether it persists in a save is UNTESTED).

## Base building (Habitat Builder) in L_SN2World: why placement is refused, and the fix (investigation 2026-11-28)
**Answer (root cause VERIFIED in game 2026-11-28):** the builder's support search finds the SN1 terrain but rejects it, because `SN2BuilderBlueprintFunctionLibrary.IsGroundSurface(component)` is false for every SN1 terrain StaticMeshComponent. The game marks "ground" through asset data on the StaticMesh, not through collision, physical material or tags. The HUD shows `Cannot find valid support surface` (`Reason.Builder.CannotFindValidSupportSurface`) on a red ghost.

**Evidence**
- Run `20261128_123211_buildprobe_check` (L_SN2World, pawn at (1500,0,-200), builder given in memory, `DA_Corridor_ItemBrushData` activated, `shots/00_uw_ghost.png`): red corridor ghost with the text above; the seabed is 17 m below (down trace hit `(1500,0,-1929)`); `IsGroundSurface` = false for the hit component (profile `BlockAll`, object type 0 WorldStatic, collision enabled 3, tags `SN1Terrain`) and `groundSurface=0` for all 32 `SN1Terrain` components. **VERIFIED (2026-11-28).** The hit component responds Block to Visibility (1), BuilderSculpt (26) and BuilderBlocker (27) (`COMPRESP`, run `20261128_133118_buildprobe_udata`), so the trace reaches it; only the ground test fails.
- Run `20261128_133118_buildprobe_udata` (after one GC-watchdog CRASH, retried by `autotest_retry.sh`): in memory, every SN1 terrain StaticMesh got `AddAssetUserDataOfClass(/Script/UWEAssetRegistry.UWEAssetUserData)` and `DataAssets[1] = /Game/Data/SurfaceSpawnData/DA_SandSurfaceData`. Log: `UDATA comps=32 groundBefore=0`, `UDATA meshes patched=32 groundAfter=32 (of 32)`, the same traced component now `IsGroundSurface=true`. Screenshots: `shots/00_uw_before.png` red ghost + "Cannot find valid support surface"; `shots/00_uw_after_sand.png` the same ghost, same spot, **green** with the cost line "0 / 2 Titanium" (a legal placement; the cost line only shows the in-memory test inventory is not counted). **VERIFIED (2026-11-28, in game).**
- Tags read live: `DA_SandSurfaceData.TagsToApplyToSpawnPoints` = `WorldPopulation.SpawnPoint.Sand`, `DA_RockSurfaceData` = `...SpawnPoint.Rock`, `DA_RockScreeSurfaceData` = `...SpawnPoint.RockScree` (class `/Script/UWEWorldPopulation2.UWESurfaceSpawnData`). **VERIFIED (2026-11-28).**
- Stock terrain meshes carry exactly this data. Cooked `SM_CG_RockFlatLarge_05a` and `SM_RockPorousSmooth_01a` (read with retoc + UAssetAPI): `StaticMesh.AssetUserData` = [`AutoBlendUserData_0` (`AutoBlendOption`), `UWEAssetUserData_0` with `DataAssets` = [`/Game/Data/SurfaceSpawnData/DA_RockSurfaceData`]]. The UWEAssetUserData class is `/Script/UWEAssetRegistry.UWEAssetUserData`. **VERIFIED (2026-11-28, cooked assets).** Stock landscape tiles pass by the other rule (the owner is a `LandscapeProxy`); the landscape layer infos (`LL_*`) hold no physical material.

**Static analysis of `IsGroundSurface` (exe rva 0x6fbfe30, CL-131439, another agent; raw output `<Workspace>/reports/static_groundsurface_*.txt`; the in-game test above confirms rule 3):** true only if (1) the owner is a `LandscapeProxy`; (2) the actor's asset data (a `UWEAssetDataComponent`, else the root component's `AssetUserData`, else the root StaticMesh's) holds a `UWESurfaceSpawnData` whose `TagsToApplyToSpawnPoints` shares a tag with `UWESculpturalBaseModuleSettings.GroundSurfaceTags`; or (3) the component is a StaticMeshComponent whose StaticMesh asset has that `UWEAssetUserData`. `GroundSurfaceTags` (`DefaultUWESculputuralBase.ini` in the pak): `WorldPopulation.SpawnPoint.{Axum.Building, BlueCoral, CoralDome, CoralDonut, PlateauFloor, PlateauWalls, PlateauFold, PlateauPetal, RockDonut, Rock, RockScree, SandScree, TreeRoot, ThermalSpire, YellowCoral, Sand}` plus `BuildableSurface.Planter`. Collision, physical material and tags are never read. Support search: a trace on `BuilderSculpt` (ECC_GameTraceChannel13); the first static blocking hit that is not ground ends the search with `Illegal_InvalidSupports` = the reason above.

**Fix at source (APPLIED and VERIFIED in game 2026-11-28):** every SN1 terrain StaticMesh asset carries a `UWEAssetUserData` whose `DataAssets` = [`/Game/Data/SurfaceSpawnData/DA_SandSurfaceData`]. Helper `src/modkit/scripts/sn1terrain_udata.py` (`add_ground_udata(mesh)`, idempotent), called from `sn1terrain_import.py` after `mesh.set_material` (new imports get it) and by the one-off `src/modkit/scripts/sn1terrain_ground_udata.py` (ran on the 32 existing `/Game/Mods/SN2EmptyWorld/SN1Terrain/SM_*_tile_*`: `patched=32 alreadyOK=0 failed=0`, re-run `alreadyOK=32`). Re-run the one-off after any re-import of tiles from another path. L_SN2World and the water files were not touched; the cook (`cook_install.sh SN2EmptyWorld 2`, exit 0) packaged the map state saved by the calibration session.
- Evidence: run `20261128_145306_buildprobe_udata` (read-only, no in-memory patch) log `BPROBE UDATA comps=32 groundBefore=32`; `shots/00_uw_before.png` green corridor ghost on orange-brown rock, cost line `0 / 2 Titanium`, no `Cannot find valid support surface` text. **VERIFIED (2026-11-28, in game).** Regression run `20261128_145529_uwconfirm_sn2` DONE; `shots/01_pod_10m_below_k0.png` shows the SN1 terrain visible below the pod at 9 m depth. **VERIFIED (2026-11-28).** The user placed a base by hand in the water around the pod: **VERIFIED (2026-11-28, user report)**.
- Side effects: `UWESurfaceSpawnData` tags are also read by the WorldPopulation 2 system. Run logs (`driver.log`, `UE4SS.log`) of the two runs showed no spawn lines other than the player pawn; nothing new visibly spawned in the shots. **LOGGED (2026-11-28), no visible effect.** Fallback if it ever causes spawns: a `UWESurfaceSpawnData` of our own with tag `BuildableSurface.Planter`.
- Not part of this fix: the lifepod floats 18 m above the seabed (nearest terrain 13.8 m, `03`), and the first corridor piece uses the Floating surface only in the `Place Initial Actor` mode (`DA_Corridor_ItemBrushData`: AllowedSurfaces 1, AllowedZones 5 = Water | Air), the other modes need an existing base. So the first test spot must be within the builder interact distance (1000 uu) of the seabed.

**Dead ends / ruled out**
- **FAILED (2026-11-28) hypothesis: out of bounds.** `UWEEdgeOfWorldSubsystem.IsEdgeOfWorldEnabled` = false, `IsEdgeOfWorldCollisionEnabled` false, `IsPointOutOfBounds` false at 5 offsets, `IsActorOutOfBounds(pawn)` false (run `20261128_123211_buildprobe_check`); no `UWEEdgeOfWorldSpline`, `UWEHabitationVolume` (L_SN2World and the purged L_Main run alike). The missing spline does not block building.
- **FAILED / not needed (2026-11-28): collision profile, physical material, component tags.** The static analysis shows they are never read; the planned `gsurf` mutation test was dropped (a partial run `20261128_131356_buildprobe_gsurf` hit the lobby GC crash before the probe ran).
- **Invalid reference (2026-11-28):** `buildprobe_check_lmain` (run `20261128_123430_buildprobe_check_lmain`) runs L_Main with SN2EmptyWorld installed, whose ModActor purges every `_UAID_` actor and keeps streaming off: no terrain, trace `hit=false`, 0 `BP_EdgeOfWorldVolume_C`; the ghost in open water shows the same red text. A stock L_Main reference needs SN2EmptyWorld uninstalled (not done; another session uses it).
- Placement HUD for no placement mode: the user's 2026-11-28 log has `IMC_Builder` added 03:47:54 and removed 03:48:06 and no ghost or error lines (the ghost reason is HUD-only).
