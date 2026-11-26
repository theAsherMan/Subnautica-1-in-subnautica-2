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
