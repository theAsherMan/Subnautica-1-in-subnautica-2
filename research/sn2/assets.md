# SN2 asset index

Sources: 06_asset_index.md "Asset index — where things live in the game content" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## Asset index — where things live in the game content

Status: VERIFIED from the 43,525-entry packaged-file manifest (`<GameDir>\Manifest_UFSFiles_Win64.txt`; one path per line,
copy at `src\tools\sn2_packaged_files.txt` — grep it). Paths are `Subnautica2/Content/…` on disk = `/Game/…` at runtime;
object path = `/Game/<dir>/<Name>.<Name>` (Blueprint class: `.<Name>_C`). Plugin content: `Subnautica2/Plugins/<P>/Content/…` = `/<P>/…`.
Top-level counts: Art 13,389 · Data 7,158 · Maps 5,864 · Blueprints 3,016 · FMOD 2,457 · Materials 974 · UI 796 · VFX 723 · Audio 507.

### Maps
- `Maps/Main/L_Main.umap` + `Maps/Main/L_Main/_Generated_/<hash>.umap` ×5,055 (World Partition cells), `Maps/Main/RVT/RVT_Landscape_*`.
- Data layers: `Maps/StartZone/DL_*`, `Maps/StartZone/ScorpiusDataLayers/DL_Scorpius_*`, `Maps/Main/DL_Lifepod_*`.
- Others: `L_ClientLobby` (menu), `L_Default_DevMap`, `L_BlightTest_Hardened`, `GameplayZoos/*`, `AssetZoos/CoralGarden/L_AssetZoo_CoralGarden`.

### Terrain / environment art (`Art/Environment/Biome/<Biome>/…`)
| Biome folder | Contents |
|---|---|
| `CoralGarden` | `Rocks` (230: `SM_CG_Rock*`, `SM_CG_Plateau*`, `SM_CG_Graveyard_Spire*`), `Corals` (148 + materials), `Foliage`, `Blockout`, `Prefabs/Plateaus` |
| `OvergrownRuins` | `Rocks` (178: `SM_OR_*`), `Organic` (180), `Inorganic/Terrain` (`SM_Crater_*`, `SM_SandFill_*`, `SM_BioticPatch_*`) |
| `SparsePlains` | `Rocks` (168), `Tar` (32), `Organic` |
| `JellyPlateaus` | `Rocks` (86), `Organic` |
| `WorldTree` | `Roots` (40), `Blockout` |
| `Generic` | `Caves` (126), `Corals` (157), `Foliage` (137), `Blight` (75), `MicrobialMats` (42), `Organic/AngelComb`, `Prefabs` |
Also `Art/Environment/Set/*` (1,833: Axum/Alterra/Cicada structures), `Art/Environment/Placeholders`, `TechAssets/PCG_*`, `BakedSplines`, `Art/Surfaces/Tiling` (653 textures).
Landscape materials: `Materials/Environment/Landscape/MasterMaterials/M_Landscape_Biome|SparsePlains|01|DevMap`, `LandscapeLayers/LL_*`, `FoliageTypes/LGT_*`.
Engine primitives available: `/Engine/BasicShapes/{Cube,Sphere,Sphere_Nanite,Cylinder,Cone,Plane}` + `BasicShapeMaterial`.

### Creatures
`Art/Creatures/<Name>_01` (≈55 species folders), `Blueprints/AI/Agents/<Name>` (≈45, `BP_<Name>.uasset` + behaviour trees), `Data/AI/Archetypes/DA_*Archetype` (57),
`Data/AI/Movement` (419), `Blueprints/AI/Agents/*/EQS`. Audio banks `FMOD/Desktop/creature_*.bank`.

### Gameplay data (`Data/…`, all Data Assets — scanned at load, moddable by override)
`WorldPopulation2` (634) · `Narrative` (2,296) · `BaseBuilding` (704) · `DatabankEntry` (543) · `StoryGoal` (524) · `ScanData` (433) · `ItemType` (341) ·
`CraftingRecipes/{Fabricator,Builder}` (315) · `GotoLocations` (228) · `Biomods` (83) · `SurfaceSpawnData` (54) · `AudioData/MusicData` (28) · `Blight/BlightNodes` · `DynamicEvents` · `Pings` · `Resonatable` · `AbilitySets`.

### World blueprints (`Blueprints/World/…`)
`Water/BP_Ocean`, `Water/BP_UWEWaterBiomeRegionActor`, `Water/BP_UWEOceanBiomeRegionActor`, `Sky/BP_UWESky` (+ `DS_Main_Day`, `DSCA_*` day sequences), `Volumetrics/BP_Fog_Sphere`,
`EdgeOfWorld/BP_EdgeOfWorld(Volume)`, `ResourceDeposits/BP_ResourceDeposit_*`, `ResourceNode/BP_ResourceNode_*`, `OxygenReplenishArea/*`, `Interactive/*`, `PowerPlant/*`, `Observatory/*`,
`WorldPopulation2/BP_WorldPopRulePlacementSurface`. Temperature prototypes: `Blueprints/Prototypes/ExtremeTemperatures/BP_TemperatureRegionVolume_SpireHeat_{Sm,Med}_Proto`.
Resources (VERIFIED 2026-11-26, details `research/features/resources.md` "SN1 breakable resources -> SN2 resource Blueprints"): nodes `Blueprints/World/ResourceNode/BP_ResourceNode_{Titanium,Copper,Lead,Gold,Silver,Salt,Quartz,Sulfur,Celestine,Shell}` (+ `_Parent`, `_Quartz_CoralFragmentBase`), deposits `Blueprints/World/ResourceDeposits/BP_ResourceDeposit_{Titanium,Copper,Lead,Gold,Silver,Salt,Quartz,Lithium,Sulfur,Celestine,Atacamite,Fulgurite,TarGraphene,AxumRebar,...}`, loose items `Blueprints/Items/Resources/BP_<Mineral>` (parent `Blueprints/Items/BP_BasePickupItem`) and `BP_WorldPopSpawned<Mineral>`, yield data `Data/BreakableData/DA_<Mineral>Node_BreakableData` (nodes), `Data/Resonatable/DA_<Mineral>Deposit_ResonatableData` (deposits), scan/ping data `Data/ScanData/Resource/DA_<Mineral>_ScanData`, `Data/Pings/DA_MineralPing`; destructible variants under `GameplayCueNotifies/ResourceNodes/<Mineral>/`. Deprecated items (no live source): `Items/Resources/Deprecated/BP_{Diamond,Nickel,Tungsten}`. A cooked BP is not a loadable Blueprint asset in the modkit editor: use `unreal.load_class(None, "<pkg>.<Name>_C")`.
Power sources incl. heat vents: `Blueprints/PowerSources/BP_BO_HeatVent_{Small,Medium,Large}`. Lighting: `Blueprints/Lighting/{Generic,Alterra}`.

### Game plugins of interest (`Subnautica2/Plugins/*.uplugin`)
UWEWorldPopulation2, UWESpawnSystems, UWEAIDirector, UWEAIWorld, UWETemperatureRegions, UWEVolumeTracker, UWEWater, UWEWaterCurrents, UWEWeather, UWESky, UWETimeOfDay,
UWEMusicVolumeManager, UWEAmbienceSound, UWEEdgeOfWorld, UWEWorldForces, UWEPCG, UWESculpturalBase, UWESaveSystem, UWEUserGeneratedContent (!), Mercuna (3D nav), MeshBlend, Prefabricator,
FMODStudio, KOS, plus engine plugins GeometryScripting, ProceduralMeshComponent, Landmass, LandscapePatch, Water, PCG.

### Configs (inside the legacy pak; extract with `repak`)
`Subnautica2/Config/DefaultEngine.ini`, `DefaultGame.ini`, `DefaultUWEWorldPop.ini`, `DefaultUWESpawnSystems.ini`, `DefaultUWEBiomods.ini`, `DefaultUWEConsole.ini`,
`DefaultUWEUserGeneratedContent.ini`, `DefaultWEAmbienceSound.ini`, `DefaultUWELeviathan.ini`, `DefaultUWESaveGame.ini`, `DefaultGameplayTags.ini`.

### Audio
`Subnautica2/Content/FMOD/Desktop/*.bank` (162 loose): `Master.bank`, `Master.strings.bank`, `music.bank` (78 MB), `default_ambiences.bank`, `void_ambiences.bank`, `amb_*`, `env_*`, `creature_*`,
`player*`, `tadpole`, `blight_*`. UE wrappers: `Content/FMOD/Events/**` (1,790), `Buses`, `Snapshots`, `Reverbs`. Biome music events: `FMOD/Events/music/biome/music_playlist_*`.
