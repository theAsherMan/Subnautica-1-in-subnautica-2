# Placing features: props, spawns, climate, music, lights, scale

Sources: 04_placing_features.md "Placing features", 04_placing_features.md "Rocks, props, structures — VERIFIED 2026-11-14", 04_placing_features.md "Creature spawns", 04_placing_features.md "Hot / cold area", 04_placing_features.md "Music and ambience", 04_placing_features.md "Lights", 04_placing_features.md "Scale reference", 00_overview.md "State of play" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## Placing features

Status: only "Rocks, props, structures" is VERIFIED. Every other recipe here is **UNTESTED** — class and property names are verified (see `research/sn2/world_systems.md`), but nobody has
spawned these actors from Lua yet. When you test one, update its status line with the date and result.
"Spawn" means the deferred-spawn recipe in `research/terrain/legacy_lua.md` §2 (helper `spawnActorOfClass` in SN2TerrainEdit) with a different class; set properties
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

## Music and ambience
Spawn `UWEMusicVolume` and set `MusicVolumeComponent.Config` to a `UUWEMusicVolumeData` (`/Game/Data/AudioData/MusicData/DA_Music_*_Playlist`), `Priority` higher than neighbours.
Ambience: `FMODAmbientSound` with an FMOD event (`/Game/FMOD/Events/sfx/environment/ambience/underwater/...`), or the `DA_Ambience_*` data. New audio = new FMOD Studio 2.03 bank
dropped next to the others (loading mechanism TBD) — re-pointing to existing events needs no new banks.

## Lights
Standard `PointLight`/`SpotLight` actors spawn fine (53/11 loaded in the area); game light fixtures are `BP_Lighting_*`, `BP_LightStick_Static_C`, `BP_Cicada_SpotLight_01_C`.

## Scale reference
Player stood at z = −240 m; Coral Gardens landscape tiles 252 m; spawn zone boxes 100 × 200 × 120 m; temperature radius 15 m; fog sphere blend 5 m; ocean body 10 km square.

## State of play detail (moved from 00_overview.md, 2026-11-28)

| Capability | Status |
|---|---|
| Temperature / water-look / music / spawn-zone actors spawned from Lua | UNTESTED (properties known) |
