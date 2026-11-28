# Biome water look and the SN1 biome map

Sources: 04_placing_features.md "Water colour / fog per area ("biome look")", 10_sn1_world_data.md "6. Biome map", 10_sn1_world_data.md "6c. Underwater calibration: SOLVED for natures_table (2026-1", 00_overview.md "State of play", 00_overview.md "Next steps" (split 2026-11-28; old text: git show 7221ba9:research/<old file>). Full pass-1 notes: `git show 3449200:research/features/biome_look.md`.

## Water colour / fog per area ("biome look")
Spawn `BP_UWEWaterBiomeRegionActor_C`; set `WaterBoxVolumeComponent.BoxExtent` to the area size and fill `BiomeVolumeComponent.WaterLightSettings`: `BiomeExtinction`/`BiomeExtinctionSkylight` (how fast light dies, per channel; green/red-heavy = murky), `BiomeAlbedo` + `BiomeNeutralColor` (water tint), `WaterFogDistance/Thickness/BaseThickness` (visibility), `BiomeBlendDistance` (soft edge). Sliders on the BP add sediment/bubbles/marine snow. Alternative cheap mood: `BP_Fog_Sphere_C` (Albedo/Extinction/Emissive/Scale) and a local `PostProcessVolume`. Global: `BP_UWESky_C` — `SetTimeOfDay "HH:MM"`, `SetCurrentWeather <DA name>` from the console, or set `TimeOfDay`/weather refs in Lua.

### Enums, related classes and the SN1 transfer tools (2026-11-24, from `<ModkitDir>/Subnautica2-Project/Automation/Headers.hpp` ~line 140320)
- `EBiomeRegionType` {BRT_Water=0, BRT_MaskedWater=1, BRT_Air=2}; `EBiomeRegionVolumeType` {BRVT_Brush=0, BRVT_Shape=1}; `EBiomeBlendType` {XYZ=0, XYSeperateZ=1}. **VERIFIED (2026-11-24, header)**
- `AUWEWaterBiomeRegionActor` functions: `RecreateMaterials`, `SetAirLightSettings`, `SetWaterFogOpacityWeight`, `SetupAirVolume`. Components also `WaterStaticMeshComponent`, `InternalVolumeModel/Mesh`, `InternalWaterPlaneMesh`. `UUWEBiomeTrackerSubsystem{SkyActor, Volumes, BiomeMaterialParameterCollection, BiomeNiagaraParameterCollection}`; `UUWEBiomeMapComponent{CaptureRadius, RenderTarget, DefaultVolumeSettings, WorldToBiomeMapScaleAndOffset}` (on BP_Ocean); `UUWEWaterBiomeRegionSettings{MaterialBiome, MaterialBiomeMasked, MaterialAir}`; `FUWEWaterLightSettingsAdvanced{BiomeAlbedoPower, BiomeAlbedoTint, BiomeEmissive, BiomeAlbedoDesaturation, BiomeAlbedoBrightness}`. **VERIFIED (2026-11-24, header)**
- The modkit's `Plugins/UWEWater` holds only `UWEWater.uplugin` (no C++, no `.usf/.ush` shaders) **VERIFIED (2026-11-24, file search)**: the meaning of the WaterLightSettings numbers cannot be read from source, the SN1 -> SN2 conversion is calibrated empirically from screenshot pairs.
- `WaterLightSettings` is not exposed to Python; set it through T3D text (EDIT COPY, add `WaterLightSettings=(...)` to the `Begin Object Name="BiomeVolumeComponent"` property block, destroy, EDIT PASTE). Proven on the ocean region in `sn2world_map.py` `paste_region_with_water_light` (2026-11-19).
- Transfer pipeline: `src/tools/sn1_biome_transfer.py` (SN1 biome map -> boxes + converted settings, `research/features/biome_shallows_boxes.md`) -> `src/modkit/scripts/sn1biome_regions.py` (editor; one `/Game/Blueprints/World/Water/BP_UWEWaterBiomeRegionActor.BP_UWEWaterBiomeRegionActor_C` per box in L_SN2World, scale 1, tags `SN1Biome` + `SN1Biome_<biome>`, folder `SN1Biome/<biome>`; BoxExtent, volume type and WaterLightSettings go in through one T3D copy/paste of all regions; save + reload check) -> `tools/cook_install.sh SN2EmptyWorld 2`. Editor side **VERIFIED (2026-11-26)**: 42 Safe Shallows regions saved, each re-copied T3D has its own `BoxExtent` and the converted WaterLightSettings, before and after a reload. The regions ARE loaded at runtime with the converted settings **VERIFIED (2026-11-26, envprobe, run `20261126_180611_sn1cmp_shallows_env`)**. Region priority and seams: UNTESTED.
- Fresh `BP_UWEWaterBiomeRegionActor_C` as spawned in the editor **VERIFIED (2026-11-26, T3D dump `<Workspace>/reports/lmain_biome_regions/fresh_water_region.t3d`)**:
  - Components: `BiomeVolumeComponent` (UWEWater.UWEBiomeVolumeComponent), `PostProcessComponent` (UWEBiomePostProcessComponent), `RootComponent`, `WaterBoxVolumeComponent` (**UWEVolumeTracker.BoxVolumeComponent**: a ShapeComponent, *not* an engine `BoxComponent`, so `get_components_by_class(unreal.BoxComponent)` misses it; find it by name), `WaterStaticMeshComponent`, `WaterVolumeComponent` (UWEVolumeTracker.BrushVolumeComponent).
  - BoxExtent = 0 and bounds = 0. The modkit C++ is a stub: `call_method("SetBoxExtent", (vec, True))` runs but changes nothing, `GetUnscaledBoxExtent` always returns 0. Set `BoxExtent=(X=..,Y=..,Z=..)` as a line in the `Begin Object Name="WaterBoxVolumeComponent"` property block of the T3D; it exports back after a paste and a reload.
  - Not exposed to Python (`get_editor_property` -> "Failed to find property"): `biome_region_volume_type`, `biome_region_type`, `is_ocean`, `priority`; there is no `unreal.BiomeRegionVolumeType` enum.
  - The actor-level line reads `BiomeRegionVolumeType=BRVT_Brush` after a spawn and a reload; after a T3D paste with `BRVT_Shape` the line is not exported at all (equals the class default). The saved .umap name table has `BRVT_Brush` but no `BRVT_Shape`, so the editor class default is Shape and Brush comes from the editor's construction pass. This is the reason the runtime graph must set Shape (see below).
  - Actor-level `WaterLightingSettings=(...)` with every field 0 is left alone; runtime values come from `BiomeVolumeComponent.WaterLightSettings`.
- L_Main region probe (`src/modkit/scripts/lmain_biome_regions_probe.py`, 2026-11-26): in the editor only the ocean region is loaded (`BP_UWEOceanBiomeRegionActor_C`, loc (0, 0, -5000000), scale (1e6, 1e6, 1e5), a child actor of BP_Ocean_C, not copyable). The per-area regions live in unloaded World Partition cells and `unreal.WorldPartitionEditorSubsystem` does not exist in Python. **FAILED (2026-11-26)** as a calibration source for SN2's own per-area values; summary `<Workspace>/reports/lmain_biome_regions/summary.txt`.
- **Region water volume (SOLVED 2026-11-27, `research/sn2/l_sn2world_water.md` "Region water volume in L_SN2World: SOLVED"):** the look needs the Volume-domain `M_OceanVolume` on a region cube, the placed ocean region owning tracker slot 15 (remove `BP_Ocean`'s child region `CAT_0`, `sn2world_ocean_slot.py`) and `BiomeRegionVolumeType` = Shape at runtime (set from the cooked ModActor graph via `SetBytePropertyByName`). Baking the MID alone was not enough. The 42 SN1 boxes stay volType 0 (no local look yet). Whether boxes need an overlap/collision setup that the T3D-pasted `WaterBoxVolumeComponent` lacks: UNTESTED.

## 6. Biome map
- `biomeMap.bin` = 2-byte header + 1024 x 1024 `uint8` cells, 4 m per pixel across 4096 m. Values 0-18 index `biomes.csv`. **VERIFIED (2026-11-19, file)**
- `biomes.csv` has a header line `name`; skip it, then the order is 0-based (index mapping confirmed by the signals.csv check below):

  | Index | Biome | Index | Biome |
  |---|---|---|---|
  | 0 | safeShallows | 10 | crashZone |
  | 1 | kelpForest | 11 | void |
  | 2 | grassyPlateaus | 12 | sparseReef |
  | 3 | underwaterIslands | 13 | dunes |
  | 4 | mushroomForest | 14 | bloodKelp |
  | 5 | kooshZone | 15 | mountains |
  | 6 | grandReef | 16 | seaTreaderPath |
  | 7 | arctic | 17 | bloodKelpTwo |
  | 8 | inactiveLavaZone | 18 | CragField |
  | 9 | unassigned | | |

  - The most common value is 11 (359,220 px), "void" around the edges. 7, 8 and 9 never occur.
- Deep biomes (Lost River, Lava Zones) are not in this 2D map; they come from the atmosphere volumes (§5).
- **Axis orientation: `row = floor((unity.z + 2048) / 4)`, `col = floor((unity.x + 2048) / 4)`** (pixel centre: `x = col*4 - 2046`, `z = row*4 - 2046`). All 8 flips/transposes were tested against `signals.csv`; this one matches every row whose biome is in the 2D map (10/14). The 4 misses are floatingIsland, JellyshroomCaves, lavazone and one underwaterIslands entry at the lavazone position, all volume biomes. Pixel (512, 512) = origin/lifepod = safeShallows. **VERIFIED (2026-11-24, file + signals.csv)**
  ```python
  m = np.frombuffer(open(B + "biomeMap.bin", "rb").read()[2:], dtype=np.uint8).reshape(1024, 1024)  # m[row=z, col=x]
  names = [l.strip() for l in open(B + "biomes.csv").read().splitlines()[1:] if l.strip()]
  ```
- How SN1 picks the biome at a point (decompiled `WaterBiomeManager.GetBiome`): if an `AtmosphereVolume` encloses the point, its `overrideBiome` wins; otherwise `LargeWorld.GetBiome(pos)` reads this 2D map (the open-water fallback). **VERIFIED (2026-11-24, decompiled code)**
- **Safe Shallows (value 0), 4-connected components** (Unity metres; computed from the file 2026-11-24):

  | Component | Pixels | Area | x range | z range | Centroid (x, z) |
  |---|---|---|---|---|---|
  | Main (contains origin) | 18,827 | 0.301 km² | -248 ... 536 | -508 ... 388 | (51, -83) |
  | West lobe | 4,394 | 0.070 km² | -924 ... -388 | 60 ... 260 | (-665, 157) |
  | Stray pixel | 1 | - | 508 | 104 | - |

  Main-area border pixels by neighbour: kelpForest 637, grassyPlateaus 270, crashZone 86, mushroomForest 12. The shape is irregular, so the SN2 transfer uses a box decomposition (`research/features/biome_shallows_boxes.md`).

## 6c. Underwater calibration: SOLVED for natures_table (2026-11-28)
**Recipe (VERIFIED 2026-11-28, run `20261128_162423_samples`, compare.png of all 3 shots viewed):**
1. **Luminance = auto-exposure bias.** The view is histogram auto-exposed, so water MIC values (albedo brightness 1..30, extinction distance x1..x10) are normalised away and only move hue. `DS_Main_Day` rewrites the sky PostProcessComponent (priority -1000, bias 0.5) every frame, so it cannot be edited at runtime. Fix at source: an unbound `PostProcessVolume` labelled `SN2_ExposurePPV` in L_SN2World, `priority` 10, only `override_auto_exposure_bias` set, `auto_exposure_bias` = **2.4** (script `src/modkit/scripts/sn2world_exposure.py`, idempotent, run in the editor via `ue_run.py`, then cook). In-memory sweep at the old water: bias 0.5 -> lum 41, 1.5 -> 95, 2.0 -> 126, 2.5 -> 157, 3.0 -> 183 (about 31 lum per 0.5 EV). Stock L_Main underwater is also about 40.
2. **Hue = ocean MIC + 42 SS box MICs** (`src/modkit/scripts/sn2world_water_mats.py`, TUNE_V block applied to all MICs): `BiomeAlbedo` (0.02, 0.45, 1.0, 1.0), `BiomeExtinctionColorDirectionalLight` and `BiomeExtinctionColorSkylight` (0.40, 0.92, 0.97, 1.0); all other values stay at original L_Main ocean values / converted SN1 box values (`safeShallows.json`). Bake in editor, then `SN2_ALLOW_ATTACH_ABORTS=1 bash src/modkit/tools/cook_install.sh SN2EmptyWorld 2` (editor closed first).
3. `BiomeRegionVolumeType`=1 (Shape) is set at runtime for the ocean and the boxes by the ModActor graph (`sn2emptyworld_graph.py`); boxes only show a look with Shape.

**Result (SN1 target in brackets; B/R / luminance / colour distance):** natures_table 1.97 / 139 / 19.1 [2.30 / 144] (acceptance MET); small_hill 1.20 / 142 / 30.4 [1.64 / 136] (luminance and distance met, B/R under 1.5: foreground sand is orange terrain albedo); shallow_ravine 0.80 / 113 / 109.3 [1.50 / 46] (WORSE than before: 0.23 / 36 / 45.5, because exposure is global; orange walls = terrain albedo, out of scope).
**Still differs (OPEN):** short sight distance (milky midground), no caustics / god rays, orange terrain albedo, ravine too bright (a dark ravine would need a local exposure volume).

**Iterations (natures_table / shallow_ravine / small_hill):** baseline `20261127_211729_samples`: 1.91/44/171, 0.42/34/37, 0.88/42/159. it1-it3 (water MIC only: brightness up to 30, ext dist x10, albedo/ext colour changes): lum stayed 44-48, B/R 0.2-3.2 (`20261128_132123`, `134347`, `135442`). it4 exposure 2.3, MICs reset (`20261128_154215_samples`): 1.34/133/53.0, 0.59/97/109.7, 0.92/133/57.5 (hue lavender-grey). it5 exposure 2.4 + hue above (`20261128_162423_samples`): final.

**Dead ends:** FAILED (2026-11-28) runtime writes to the ocean MID (runs `20261128_121534_wtune1..3`) turned the picture grey even with identical values; baking MIC values at source is the only working path. FAILED (2026-11-28) water MIC values as a luminance lever (exposure normalises them). FAILED (2026-11-28) writing the sky PP at runtime (rewritten each frame). In game every region MID has `CurrentWaterBodyBlendType`=0 whereas the MIC has 1 (LOGGED, harmless so far).
**Tools kept:** SN2AutoTest verbs `lum_read`, `lum_bias`, `lum_bias_hi`, `lum_unclamp`, `lum_nocurve`, `lum_b15..b30` with `data/lum.lua`, plans `lum_sn2.json`, `lum_sweep.json` (exposure fields of every PostProcessComponent plus bias sweeps) for regression checks. GC-watchdog lobby crashes (FAIL_MENU / CRASH) hit 2 of 6 samples runs; the retry passed.

## Status and next steps (merged 2026-11-28) — OPEN (2026-11-24)
- Underwater water look in L_SN2World SOLVED, **VERIFIED 2026-11-27** (run `20261127_211152_uwconfirm_sn2`, no in-memory patches: blue water at 2 m and 11 m like L_Main; `uwa21`: ocean region idx 15, volType 1). Samples after the fix (`20261127_211729_samples`) were blue but dark (numbers in `research/features/biome_shallows_boxes.md`); calibrated 2026-11-28 above (VERIFIED).
- Open next steps: (1) check whether the 42 SN1 boxes can give a local look (volType 0 = Brush at runtime; the same runtime-set trick on `BP_UWEWaterBiomeRegionActor_C` is the first thing to try, with `uwa1` on a box MID in the plan; UNTESTED); (2) rerun `uwconfirm_sn2` after any change to the map or the ModActor (regression test, `research/code/README.md`); (3) the per-run haze/weather difference between L_SN2World and L_Main (UNTESTED); (4) sight distance, caustics / god rays, terrain albedo, ravine exposure (above); (5) next biomes after Safe Shallows: run `sn1_biome_transfer.py <biome>` for each (boundary of Safe Shallows found 2026-11-24: 2 components, 0.37 km², 42 boxes at 32 m cells, 5.7 % missed / 6.3 % extra, VERIFIED offline).
- History in one line: 2026-11-26 the placer put 42 regions in L_SN2World and the cooked game showed no effect (FAILED, brown water); the root cause (the region water MID missing in L_SN2World) was found 2026-11-27 and fixed at source the same day (`research/sn2/l_sn2world_water.md`).
