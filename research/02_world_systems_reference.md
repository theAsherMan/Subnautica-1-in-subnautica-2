# World-system reference (class and property names)

Status: names, types and values below are **VERIFIED by reflection dumps** (`SN2WorldProbe` F5/F11/F12, 2026-11-14, player at (-204942, 432071, -24066),
Coral Gardens / Axum border). What each property *does* when changed is **UNTESTED** unless stated. Full dumps: `<Workspace>\reports\`
(`probe_deep.txt` has every struct field and component — grep it before guessing a name).
Units are Unreal units (1 uu = 1 cm). Class names are exact (Blueprint classes end in `_C`); property names are exact.

## Streaming and terrain
| Thing | Count loaded | Notes |
|---|---|---|
| `LevelStreaming` / `WorldPartitionRuntimeCell` | 5,055 / 5,056 | one per generated cell |
| `DataLayerInstance` | 14 | `DL_CG_Caves`, `DL_StartZone_*`, `DL_World_BlockerVolumes`, story-progression layers… |
| `Landscape` | 5 | separate heightmaps; proxies named `LandscapeStreamingProxy_<GUID>_<X>_<Y>_<LOD>` |
| `LandscapeStreamingProxy` / `LandscapeComponent` | 17 / 67 | Coral Gardens tiles 252 m; far seafloor 1,240 m; one landscape at z ≈ −503 m |
| `WorldPartitionHLOD` | 869 | baked distant proxies (`M_HLOD_FlattenMaterial_VT`) |
| `StaticMeshActor` | 10,652 | rock/coral/cave kits — the visible world |
| `PrefabActor` | 305 | Prefabricator groups of meshes |
| `RuntimeVirtualTextureVolume` | 6 | landscape RVTs |
| `MercunaNavGridVolume` / nav octrees | 39+ | creature navigation (3D nav, baked) |
| Actors total | 14,616 (372 classes) | |

## Spawn system (`UWEWorldPopulation2`)
- `UWEBoxWorldZone` ×32 — stacked 3D boxes. `BoxComponent.BoxExtent` = {5000, 10000, 6000} (100 × 200 × 120 m).
  Props: `Region` (soft), **`RegionAsset` → `UWEWorldRegionDataAsset`** (e.g. `/Game/Data/WorldPopulation2/Regions/DA_AR-PowerPlant`),
  `SeededCreatures` (soft), `SpatialDataStorage` (soft), `ZoneGUID`.
- `UWEWorldPopGlobalResourcesDataStorage` ×1: `ResourcesOctree`.
- Proxies: `BP_WaterSlugWorldPopProxy_C` ×79, `UWEPlaceableProxy` ×25 — placeholders hydrated into real creatures/items near the player;
  carry `AssetData` (`UWEAssetDataComponent`), `bHasBeenGathered`, `bHasBeenModified`, perception stimuli.
- `UWEHabitationVolume` ×52: `HabitationAreaTag` (GameplayTag) + `UWETransformedShapeComponent.Shape` (sphere or box) — creature home areas by tag.
- `UWEVolumeActor` ×59: `UWEVolumeActorComponent.VolumeData <TrackedVolumeData>` on a brush — generic tag volumes (see below).
- Data assets: `Regions/DA_<Region>` + `_Config` (20 regions incl. `DA_L_Template_World`), `Resources/DA_WPResource_*` (112),
  `PopSettings/DA_<Creature>PopulationSettings` (8), `LandscapeMappings/*` (which landscape material spawns what),
  `SeededData/` + `SpatialData/` per zone, `DA_WorldPopMasterRules`, `DA_WorldPopStorage`. Also `Data/SurfaceSpawnData/*` (54) for flora/resource surfaces,
  `Data/AI/Archetypes/*` (57), `Data/DynamicEvents/*`, plugins `UWEAIDirector`, `UWESpawnSystems`, `UWEStimulusSystem`.

### `TrackedVolumeData` (shared by temperature, water-box and generic volumes)
`VolumeType` (enum), `Priority` (int), `TagsToAdd`, `TagsToRemove`, `VolumeTags`, `GASLooseTags` (GameplayTagContainers), `EnvironmentType` (GameplayTag).
Plugin `UWEVolumeTracker` applies these tags to actors inside the volume — this is how an area "tells" the player/creatures what environment they are in.

## Temperature (`UWETemperatureRegions`)
- `BP_AreaTemperature_Proto_C` ×1 at (-303384, 446347, -25245), component **`BPC_AreaTemperatureRegionVolume_Proto_C`**
  (parent `BoxVolumeComponent` → `ShapeVolumeComponent`): `Temperature` = 100.0, `Radius` = 1500, `ContributionType` (enum) = 1,
  `BoxExtent` = {10000, 10000, 10000}, `Material`, `VolumeData <TrackedVolumeData>`.
- Other classes: `BP_TemperatureRegionVolume_SpireHeat_{Sm,Med}_Proto`, `BPC_{Capsule,Sphere}TemperatureRegionVolume_Proto`.
- Effects already on the player: `GE_AccumulateTemperature_C`, `GE_AccumulatedHeat/ColdTemperatureDamage_{Low,Medium,High}_C`, `GE_HeatResistanceAdaptation_C`;
  cues `GC_Damage_Player_Heat/Cold`; items `BP_HeatResistanceTorsoItem_Level1`, `DA_HeatResistanceChipRecipe`, biomod `DA_HeatResistance_BioAbilityData`.
- Heat vents in world: `BP_BO_HeatVent_{Small,Medium,Large}_C` ×22 (also Thermal Plant power sources). Current vents `BP_BO_CurrentVent_*` ×21, `BP_WaterCurrent_Tier_I_C` ×6.

## Water look / biome regions (`UWEWater`)
- `BP_UWEWaterBiomeRegionActor_C` ×5 (and `BP_UWEOceanBiomeRegionActor_C` ×1, `bIsOcean = true`, the global ocean).
  Blueprint sliders (all at defaults in the five seen): `WaterDepthAlpha`, `SedimentDensity/Size`, `SedimentStyle_{Blurry,Stringy,Sharp}`,
  `SedimentColor_{DefaultLightBlue,AlgueGreen,SulfurYellow,LuminescentBlue}`, `BubbleDensity/Size`, `SedimentMarineSnow`.
  Native: `BiomeRegionType` (enum, 0), `BiomeRegionVolumeType` (enum, 1), `bHasWaterSurface`, `bMaskOceanSurface`, `bUseDistanceFieldMask`,
  components `BiomeVolumeComponent : UWEBiomeVolumeComponent` (holds **`WaterLightSettings`**), `PostProcessComponent : UWEBiomePostProcessComponent`,
  `WaterBoxVolumeComponent : BoxVolumeComponent` (`BoxExtent`, seen {100,100,100}) / `WaterBrushVolumeComponent`, `OceanMI` (MID).
- **`UWEWaterLightSettings`** (the real colour/fog knobs): `BiomeExtinction`, `BiomeExtinctionSkylight`, `BiomeNeutralColor`, `BiomeAlbedo` (LinearColor);
  `BiomeExtinctionScaleDirectionalLight`, `BiomeExtinctionScaleSkylight`, `DirectionalLightAngleBias`, `StartDepthBiasDirectionalLight`, `StartDepthBiasSkylight`,
  `BiomeNeutralStrengthNear/Far`, `WaterFogDistance`, `WaterFogThickness`, `WaterFogBaseThickness`, `WaterFogOpacityWeight`,
  `BiomeBlendType` (enum), `BiomeBlendDistance`, `BiomeBlendDistanceXYAndZ` (Vector2D), `CausticsSettings` {SurfaceFadeDistance, CausticsBlend, DepthFadeMin/Max/Power}.
- `BP_Ocean_C` ×1 (`UWEWaterBodyOcean`): `BodySize` {1,000,000, 1,000,000, 100,000} (10 km × 10 km × 1 km), `BiomeMap : UWEBiomeMapComponent`,
  `Volume Material`, `Caustics Map` = `RT_Caustics`, Gerstner wave params (`Max Amplitude` 30), `PPUnderwaterBlur`, `WaterLightingSettings`, `WaterLinePPMThreshold` 200.
- `BP_Fog_Sphere_C` ×6: `Albedo` {0.652,0.625,0.792}, `Extinction` {0.236,0.488,0.650}, `Emissive` {0,0,0}, `Blend Distance` 500, `Sphere Hardness` 0.35, `Sphere Scale` 0.2, mesh `FogCube`.
- `PostProcessVolume` ×5: local, `BlendRadius` 100–1750, `bUnbound false`.

## Sky, weather, time (`UWESky`, `UWEWeather`, `UWETimeOfDay`, UltraDynamicSky)
`BP_UWESky_C` ×1 at (0,0,800): components `SunDirectionalLight`, `Moon` (DirectionalLight), `SkyLight`, `SkyAtmosphere`, `ExponentialHeightFog`,
`VolumetricCloud`, gas giant body/rings/auroras, `PostProcessComponentSky`, `DaySequenceModifierComponent`, `WeatherSyncComponent`, `NS_UWE_LocalRain`.
Values: `TimeOfDay` 0.313, `NormalizedDaylight` 0.47, `StartingWeather` = `/UWEWeather/WeatherTypes/DA_ClearGameStart`, current `DA_CloudyB`, next `DA_Clear`,
`BlendedGlobalWeatherSettings <F_GlobalWeatherSettings>`, `SkyOverrides` (map). Weather types: `DA_Clear`, `DA_ClearGameStart`, `DA_CloudyA/B`, `DA_SparseClouds`,
`DA_Misty`, `DA_DistantStormy`, `DA_StormA/B`, `DA_Storm_Quick`, `DA_LobbyWeather`; `DA_WeatherForecast`.

Exposure (VERIFIED 2026-11-28, `10` 6c): `PostProcessComponentSky` (unbound, priority -1000) holds `AutoExposureBias` 0.5, Min -10, Max 0 (day; -5 at night), histogram method, speeds 5/5, low percent 20, `AutoExposureBiasCurve` `/Game/VFX/Camera/CF_Exposure_Compensation_Curve_OCEAN`, meter mask `T_ExpMeteringMaskExample`; `DS_Main_Day` (`/Game/Blueprints/World/Sky/`) animates `Settings.AutoExposureBias` (constant 0.5) and `Settings.AutoExposureMaxBrightness` every frame, so runtime writes to that component are overwritten. Mean luminance of the frame follows the bias: bias 0.5 -> ~41, 2.0 -> 126, 2.5 -> 157, 3.0 -> 183 (natures_table, L_SN2World). A unbound PostProcessVolume / the pawn's `BasePostProcess` (priority 0) outranks the sky and is not rewritten.

## Audio
- `UWEMusicVolume` ×18: `MusicVolumeComponent : UWEMusicVolumeComponent` → `Config` = `UUWEMusicVolumeData` (e.g. `/Game/Data/AudioData/MusicData/DA_Music_Sparse_Plains_Playlist`),
  `Priority` 1, `Layer` (enum) 0. Playlists exist for shallows, plateaus, graveyard, coral gardens, sparse plains, ruins, heat zone, thermal caves, metal farms, eastern wastes, power station, wrecks, deep start.
- `FMODAmbientSound` ×12 (`AudioComponent`); `DA_Ambience_*` per area; `BP_Ocean_C` has `UWEBoundsTopAudio` + `FMODAudio`.
- Banks: `Subnautica2\Content\FMOD\Desktop\*.bank` (162, incl. `Master.strings.bank`, `music.bank`, `default_ambiences.bank`, per-creature banks).

## World boundary and misc
- `BP_EdgeOfWorldVolume_C` ×58 — a ring at z = +100 m: `OverlapVolume`, `CollisionCube`, `VisibilityCube`, `CollisionState` (false until approached), `CullDistance` 10000. Plugin `UWEEdgeOfWorld`.
- Blight: `BP_BlightZone_C` (capsules/sphere, `Blight Data Asset`, remediation timers), `BP_BlightCore_C`, `BP_BlightNode_C`, `BP_BlightZoneManager_C`.
- Player pawn class `BP_Character_01_C`; vehicle `ASN2Tadpole`; cheat manager `SN2CheatManager`; HUD `SN2WorldHUD`.
