# 10 — Subnautica 1 world data: files, formats, extraction plan

What the Subnautica 1 (SN1) install contains for the world map, which parts have been decoded, and the planned pipeline into SN2.
Investigation 2026-11-19: files were read and parsed offline only. The game was not run, and nothing was implemented in `src/`.

`<SN1Dir>` is the SN1 Steam install folder, the one that contains `Subnautica_Data\`. It is resolved from `SN1_GAME_DIR` in `local.config`.
Legal: SN1 data must never be committed or distributed. The finished mod ships a converter that each user runs against their own SN1 install (see `00` → Distribution).

## 1. Install and build
- Steam appid 264710. Build checked: Steam buildid 20241558. `StreamingAssets\__buildnumber.txt` = `10`, `__buildtime.txt` = `10/03/2025 17:26:27`. **VERIFIED (2026-11-19, files)**
- World data folder: `<SN1Dir>\Subnautica_Data\StreamingAssets\SNUnmanagedData\Build18\`. **VERIFIED (2026-11-19, files)**
- Code: `<SN1Dir>\Subnautica_Data\Managed\Assembly-CSharp.dll` (3.7 MB, Mono .NET, so it can be decompiled). It contains the type names `VoxelandData`, `OctNode`,
  `LargeWorldStreamer`, `BatchOctreesStreamer`, `CompiledOctreesCache`, `ClipmapLevel`, `VoxelandBlockType`, `VoxelandTypeBase`, `VoxelandChunk`, `MeshBuilder`,
  `CellManager`, `EntityCell`, `ProtobufSerializer`, `PrefabDatabase`, `EntitySlot`, `LootDistributionData`, `WorldEntityDatabase`, `WorldEntityInfo`, `biomeMap`, `blockTypes`.
  `Unity.Addressables.dll` is also present. **VERIFIED (2026-11-19, strings)**
- Assets: Addressables bundles in `StreamingAssets\aa\StandaloneWindows64\` (5,467 `.bundle` files, of which 1,718 are `duplicateassetssorted…`). Also `aa\catalog.json` (12 MB) and `aa\settings.json`.
  Bundle names are lowercase prefab names plus a hash, e.g. `islandcave.prefab_<hash>.bundle`, `land_grass_01_green.prefab_<hash>.bundle`. FMOD `.bank` files are in `StreamingAssets\`. **VERIFIED (2026-11-19, listing)**

## 2. `Build18\` inventory (VERIFIED 2026-11-19, listing)
| File / folder | Count, size | Content |
|---|---|---|
| `CompiledOctreesCache\compiled-batch-X-Y-Z.optoctrees` | 5,416 files, 1,164 MB | Terrain voxels, one file per batch (§4) |
| `CellsCache\baked-batch-cells-X-Y-Z.bin` | 1,606 files, 164 MB | Placed objects per batch: doodads, plants, wrecks, lights, spawn slots (§5) |
| `BatchObjectsCache\batch-objects-X-Y-Z.bin` | 2,975 files, 12 MB | Per-batch roots: atmosphere/biome volumes, a few lights (§5) |
| `biomeMap.bin` | 1,048,578 B | 2D biome map (§6) |
| `biomes.csv` | 242 B | Biome names (§6) |
| `index.txt` | 46,008 B | World header plus one float per batch (§3) |
| `meta.txt` | 18 B | `39 BlockPrefabs` |
| `signals.csv` | 737 B | `biome,batch,position,description` rows (signal beacons). One row repeats the lava-zone position |
| `..\prefabs.db` (in `SNUnmanagedData\`) | 344 KB, 3,336 entries | ClassId → prefab path (§5) |
| `..\prefabpool.json`, `bytepool.json`, `streaming-*.json`, `clipmaps-*.json` | small | Streamer settings, not yet read |

Batch index ranges actually present:

| Folder | x | y | z |
|---|---|---|---|
| Octrees | 0–25 | 7–19 | 0–25 |
| Cells | 1–23 | 8–19 | 0–24 |
| Batch objects | 0–24 | 8–19 | 0–24 |

Octree files per y layer:

| y | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Files | 80 | 98 | 153 | 175 | 226 | 542 | 586 | 601 | 621 | 621 | 616 | 611 | 486 |

Missing files mean empty space (solid rock or open water).

## 3. World grid and coordinates
- `index.txt` lines: `0`, `4096 3200 4096` (world size in m), `128 100 128` (world size in 32 m octrees), `32` (octree size in m), `5 5 5` (octrees per batch), then
  13,520 floats. 13,520 = 26×20×26, which is one value per batch; 12,865 of them are 0. The meaning of the floats is UNTESTED. **VERIFIED (2026-11-19, file)**
- Batch = 160 m cube = 5×5×5 octrees of 32 m. World = 26×20×26 batches. Leaf voxel at depth 5 = 1 m.
- **Origin:** `batch = floor((unityPos + (2048, 3040, 2048)) / 160)`. All `signals.csv` rows fit this formula (VERIFIED 2026-11-19, signals.csv).
  - Batch y 19 covers Unity y 0…+160 m (above the sea surface: islands).
  - y 18 covers −160…0 m.
  - y 7 covers −1,920…−1,760 m, the deepest data.
- Unity is left-handed, Y-up, in metres (x right, y up, z forward). UE is left-handed, Z-up, in cm (X forward, Y right, Z up). **Correct mapping (UNTESTED derivation):**
  ```
  UE.X = 100 * unity.z ;  UE.Y = 100 * unity.x ;  UE.Z = 100 * unity.y      (+ map offset)
  quat: UE(X, Y, Z, W) = (q.z, q.x, q.y, q.w)
  scale: UE(X, Y, Z) = (s.z, s.x, s.y)
  ```
  This is a cyclic permutation, so it keeps handedness. The older `(x, z, y)` mapping in `03` §5 swaps two axes and would mirror the map. It is corrected there.
- Map offset in `L_SN2World`: (0, 0, 0), i.e. SN1 origin = SN2 origin, SN1 sea level = SN2 ocean surface (decided 2026-11-22, in-game check pending). Import: `03` §3 "Multi-tile SN1 terrain import".

## 4. Terrain: `.optoctrees` format
**VERIFIED (2026-11-19, parsed with a throwaway script).** For batch 12-18-12 (Safe Shallows), the parse ended exactly at the file size.
```
int32  version            // = 4
repeat 125 times (one per 32 m octree of the batch's 5x5x5):
    uint16 nodeCount
    nodeCount x { uint8 type; uint8 density; uint16 firstChild }   // 4 bytes, little-endian
// node 0 = root. firstChild == 0 -> leaf. Otherwise children are nodes firstChild .. firstChild+7.
```
Minimal reader:
```python
import struct
def read_batch(path):
    d = open(path, 'rb').read(); ver, = struct.unpack_from('<i', d, 0); p = 4; trees = []
    while p < len(d):
        n, = struct.unpack_from('<H', d, p); p += 2
        trees.append([struct.unpack_from('<BBH', d, p + 4*i) for i in range(n)]); p += 4*n
    return ver, trees
```
Results:

| Batch | Size | Trees | Subdivision depths | Nodes | Leaf types | Leaf densities |
|---|---|---|---|---|---|---|
| 12-18-12 | 931,986 B | 125 | 89 of depth 0 (uniform), 36 of depth 5 (down to 1 m) | 232,933 | 0, 1, 2, 3, 5, 7, 8, 10, 13, 14, 19, 20, 21, 22, 35, 50, 51, 52, 100, 101, 102, 104, 105, 172 | 68,769 are 0, 135,063 are 1–252 |
| 0-11-15 | 754 B | 125 | all depth 0 | 125 single-node trees | all 0 | — |

The 754-byte file is a fully empty batch: 4 + 125 × (2 + 4) = 754.

Answers (decompiled with ilspycmd to `<Workspace>\sn1_decompiled\`: `LargeWorldStreamer` and `Assembly-CSharp-firstpass.dll` types `Int3`, `VoxelandData`, `VoxelandChunk`, `Voxeland`):
- **Tree order: x*25 + y*5 + z (z fastest).** **VERIFIED (2026-11-22, decompile `Int3.RangeEnumerator.MoveNext` -> `p.Next(mins, maxs)`, z increments first; confirmed by the extractor reproducing the collider surface, see §7).**
- **Child order:** `child = firstChild + 4*(x>=half) + 2*(y>=half) + 1*(z>=half)`. **VERIFIED (2026-11-22, decompile `Octree.GetNodeId`: `firstChildId + ((x >= halfsize) ? 4 : 0) + ((y >= halfsize) ? 2 : 0) + ((z >= halfsize) ? 1 : 0)`).** `firstChild == 0` = leaf.
- **Density encoding:** signed distance in voxel units, `(d - 126) / 126` (`VoxelandData` line 170: `((float)(int)d - 126f) / 126f`; inverse `FloorToInt(dist*126)+126`). Positive = inside the solid, surface at d = 126. `IsBelowSurface(type, density)`: `density == 0 ? type > 0 : density >= 126`. So d == 0 means "far from the surface, no distance stored": type > 0 = deep inside, type 0 = open water/air. **VERIFIED (2026-11-22, decompile `VoxelandData.IsBelowSurface`).**
- **Materials:** type id to material is still unresolved (lives in a Unity asset, not in `Build18`). Leaf types reach 172. The extractor groups faces by `usemtl type_<n>` (type of the inside voxel). Open.
- **Mesher:** SN1 builds chunk meshes in `VoxelandChunk.BuildMesh/CalculateMesh` (blocky face mesher on the 1 m grid, then vertices moved using the densities, `Relax`, mesh normals). That exact smoothing is NOT ported; the extractor uses surface nets on the same inside/outside + crossing rule (`crossing_s` = `ComputeSurfaceIntersection`: both near: `dIn/(dIn-dOut)`; out far: `dIn`; in far: `1+dOut`; both far: 0.5). The result matches the in-game collider mean 0.03 m (§7), so the density-based placement is right.
- **Batch borders:** none needed in the data: each batch holds only its own 160 m, and the game voxel grid is global (`voxel index = floor(unity + (2048, 3040, 2048))`). Neighbouring batches are simply decoded into one global array before meshing (done in the extractor, overlapping batches read for the cube plus a 2-voxel margin). Missing batch file or octree = type 0, density 0 (outside). **VERIFIED (2026-11-22, extractor run: no seams at batch borders in the 500 m cube, which spans 4x4x4 batches; the 4,514 border open edges are only the cube's cut boundary, see §7).**

Size: a batch decoded to 1 m arrays is 160³ = 4.1 M voxels × 2 B ≈ 8 MB. Processing one batch at a time keeps RAM small.
Triangle estimate (UNTESTED): roughly 16.7 km² of seafloor plus caves and islands at 1 m gives tens of millions to about 100 M raw triangles. Meshes must be decimated, and placement relies on Nanite.

## 5. Objects: cells, batch objects, prefabs
- **Container format.** Files are UWE `ProtobufSerializer` (protobuf-net) GameObject trees. Each object has an id, a parent id, a ClassId (prefab GUID) and a Transform.
  The ClassId is stored as protobuf field 7, length 36: bytes `3A 24` + GUID text. The census below counted every `:$<36-char guid>` match:
  `grep -a -o ':\$[0-9a-f-]\{36\}'`. **VERIFIED (2026-11-19)**
- **Not yet decoded (UNTESTED):** the file header, the cell levels/sizes, the exact transform fields (local vs world, float layout) and component data beyond the Transform.
  - The cells file header starts `05 08 09 10 80 02 …`.
  - Decode it from the `ProtobufSerializer` / `CellManager` / `EntityCell` code. The protobuf-net attributes give the field numbers.
- **`prefabs.db`** (VERIFIED 2026-11-19): `int32 count` (= 3,336), then `count` × (string ClassId, string path), as .NET BinaryWriter strings (7-bit length prefix, then UTF-8).
  Example: `08 0d 00 00 | 24 <36-byte guid> | 2b WorldEntities/....prefab`.
  The path is the Addressables key. The bundle that holds it is found through `aa\catalog.json`.

**Census, CellsCache** (VERIFIED 2026-11-19): 409,386 objects, 1,195 distinct ClassIds.

| Kind | Count |
|---|---|
| `Misc/CellRoot` (grouping node) | 118,920 |
| `EntitySlotsPlaceholder` (random-spawn slots) | 90,289 |
| `Doodads/Coral_reef/*` (largest single prefab: `Coral_reef_tree_mushrooms_connector_01`, 22,290) | 167,032 |
| `FloatingStone*` | about 8.3 k |
| `Lost_river` | 6,480 |
| `Doodads/Land` | 4,708 |
| Lights (various) | about 3 k |
| `Coral_reef_Light` | 2,376 |
| `Doodads/Precursor` | 2,063 |
| `Debris` | 1,987 |
| `Doodads/Geometry` | 975 |
| VFX | 373 |
| Creatures | 261 |

`Environment` prefabs:

| Prefab | Count |
|---|---|
| `MembraneTree` | 389 |
| Precursor | 227 |
| Aurora | 210 |
| `FloaterLarge` | 136 |
| `BrainCoral` | 132 |
| … | … |

**Census, BatchObjectsCache** (VERIFIED 2026-11-19): 5,779 objects, 174 distinct.

| Kind | Count |
|---|---|
| `BatchRoot` | 2,975 |
| `Atmosphere` volumes (e.g. `CoralRootZone_Sphere` 305, `LostRiver_BonesField_Lake` 127, `GrassyPlateaus/Tower` 118) | 2,714 |
| Lights | 77 |
| Environment | 12 |

- `EntitySlotsPlaceholder` holds spawn slots for `LootDistributionData`. In SN2 these map to `UWEWorldPopulation2` (`04`). Do not import them as meshes.
- Atmosphere volumes (fog, light and music zones) map to SN2 `UWEWater` biome regions and `BoxWorldZones` / temperature / audio (`02`, `04`).
- UNTESTED: where the global unique objects (Aurora wreck, precursor facilities, the lifepod start) live. They are probably in these caches as large prefabs
  (Aurora 210 entries) or in a scene. Check this once transforms are decoded.

## 6. Biome map
- `biomeMap.bin` = 2-byte header + 1024 × 1024 `uint8` cells, 4 m per pixel across 4096 m. Values 0–18 index `biomes.csv`. **VERIFIED (2026-11-19, file)**
- `biomes.csv` has a header line `name`; skip it, then the order is 0-based (index mapping now confirmed by the signals.csv check below):

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

  - The most common value is 11 (359,220 px). This fits "void" around the edges.
  - 7, 8 and 9 never occur.
- Deep biomes (Lost River, Lava Zones) are not in this 2D map. They come from the atmosphere volumes (§5).
- **Axis orientation: `row = floor((unity.z + 2048) / 4)`, `col = floor((unity.x + 2048) / 4)`** (pixel centre: `x = col*4 - 2046`, `z = row*4 - 2046`). All 8 flips/transposes were tested against `signals.csv`; this one matches every row whose biome is in the 2D map (10/14). The 4 misses are floatingIsland, JellyshroomCaves, lavazone and one underwaterIslands entry at the lavazone position — all volume biomes. Pixel (512, 512) = origin/lifepod = safeShallows. **VERIFIED (2026-11-24, file + signals.csv)**
  ```python
  m = np.frombuffer(open(B + "biomeMap.bin", "rb").read()[2:], dtype=np.uint8).reshape(1024, 1024)  # m[row=z, col=x]
  names = [l.strip() for l in open(B + "biomes.csv").read().splitlines()[1:] if l.strip()]
  ```
- How SN1 picks the biome at a point (decompiled `WaterBiomeManager.GetBiome`): if an `AtmosphereVolume` encloses the point, its `overrideBiome` wins; otherwise `LargeWorld.GetBiome(pos)` reads this 2D map. So the map is only the open-water fallback. **VERIFIED (2026-11-24, decompiled code)**
- **Safe Shallows (value 0), 4-connected components** (Unity metres; computed from the file 2026-11-24):

  | Component | Pixels | Area | x range | z range | Centroid (x, z) |
  |---|---|---|---|---|---|
  | Main (contains origin) | 18,827 | 0.301 km² | -248 … 536 | -508 … 388 | (51, -83) |
  | West lobe | 4,394 | 0.070 km² | -924 … -388 | 60 … 260 | (-665, 157) |
  | Stray pixel | 1 | — | 508 | 104 | — |

  Main-area border pixels by neighbour: kelpForest 637, grassyPlateaus 270, crashZone 86, mushroomForest 12. The shape is irregular (not a box) — the SN2 transfer needs a box decomposition or a brush/mesh volume (see `04` biome look).

### Safe Shallows -> SN2 box regions (transfer plan, 2026-11-24)
- Tool: `python -I src/tools/sn1_biome_transfer.py <biome> [--cell 32] [--overlap 10] [--min-px 100] [--y-top 5] [--y-bottom -200] [--settings <waterbiomes dump>]`
  (offline, numpy, no heavy lock). Reads `<SN1Dir>` Build18 `biomeMap.bin` + `biomes.csv`, keeps 4-connected components >= `--min-px`, rasterises them to
  `--cell` m cells (a cell is in if >= half its pixels are the biome), covers the cells with a greedy exact rectangle cover, grows each rectangle by
  `--overlap` m per horizontal side, and writes `<Workspace>/sn1_biomes/<biome>.json`: `boxes[{unity_x, unity_z, unity_y, center_ue, half_ue}]`
  (UE cm, map offset 0), `mask_px`, `miss_px`, `extra_px`, and with `--settings` the SN1 settings, the converted `water_light` dict and `water_light_t3d`.
  **VERIFIED (2026-11-24, offline run; file written)**
- Safe Shallows (2 components kept, the stray pixel dropped), cell size vs. fit (missed = biome pixels outside every box, extra = non-biome pixels inside):

  | Cell | Boxes | Missed | Extra |
  |---|---|---|---|
  | 8 m | 192 | 0.6 % | 2.4 % |
  | 16 m | 95 | 2.5 % | 3.5 % |
  | 32 m (default) | 42 | 5.7 % | 6.3 % |
  | 64 m | 21 | 12.1 % | 9.1 % |

  Current file: 42 boxes, unity_y -200 ... +5 m (UE z -20000 ... +500). Example box: unity_x [-170,-54], z [-522,-246] -> center_ue (-38400,-11200,-9750),
  half_ue (13800,5800,10250). How SN2 blends overlapping/adjacent regions (seams at box edges) is UNTESTED; the 10 m overlap is a guess.
- Conversion formula v1 (UNTESTED, needs screenshot calibration; the modkit has no UWEWater shaders, see `04`): sigma_c = SN1 `derived_extinction_per_m`;
  `BiomeExtinction_c = exp(-sigma_c * K_M)` (K_M = 1); `BiomeExtinctionSkylight_c = LMAIN_SKY_c ** (sigma_c*K_M / -ln LMAIN_DIR_c)` (L_Main's ocean ratio kept);
  `BiomeAlbedo` = scattering_rgb / sigma normalised to max 1; `WaterFogDistance = 100 * 3 / mean(sigma)` cm clamped to [1000, 20000];
  `Advanced.BiomeEmissive` = SN1 derived emissive if non-zero; scales 12.5/17.5, fog thickness 10/4, blend XYSeperateZ (2000,100), DepthFadeMax 45000 kept from L_Main.
- SN1 safeShallows `WaterscapeVolume.Settings` (from the live dump `<Workspace>/sn1_shots/safeShallows_dump.json`) **VERIFIED (2026-11-26, live dump)**:
  absorption (125, 20, 4), scattering 1.2, scatteringColor (1,1,1,1), murkiness 0.18, emissive (0,0,0) x1, startDistance 25, sunlightScale 1,
  ambientScale 1.5, temperature 28 -> derived extinction per m (0.2272, 0.0382, 0.0094), scattering per m 0.00216 (white). Red dies fast, blue barely.
- Converted (formula v1, UNTESTED in SN2), in `<Workspace>/sn1_biomes/safeShallows.json` `water_light_t3d`: BiomeExtinction (0.797, 0.963, 0.991),
  BiomeExtinctionSkylight (0.304, 0.831, 0.956), BiomeAlbedo (0.041, 0.245, 1.0), WaterFogDistance 3277 cm, the rest kept from L_Main.
- Calibration shot pairs, now kept in the repo as samples `samples/safeShallows/<name>/{SN1,SN2}/` (moved 2026-11-26; procedure `samples/README.md`):
  - `shallow_ravine` (2026-11-26): SN1 camera (108.65, -49.68, 41.92), yaw 262.2, pitch +2.0, fovH 91.5, dayScalar 0.47; SN2 at (4190, 10850, -4971) yaw -97.76.
    SN1 view: from inside a rock arch at 50 m depth, looking out along a sandy ravine floor. Bright sunlit sand patches, a coral bush in the middle,
    a purple coral head, a fish. The ravine walls fade into teal-blue water at roughly 30-40 m. The near rock is olive-brown and the cave shadow dark teal.
  - `small_hill` (2026-11-26): SN1 camera (-28.76, -2.00, -115.03), yaw 147.5, pitch -31.7 (looking down), fovH 91.5, dayScalar 0.52; SN2 at (-11511, -2871, -213) yaw 147.49.
    SN1 view: from just under the surface on top of a sand mound, looking down into a bright sandy basin, sea floor about 10-15 m below. Pale sand with
    caustic light lines, rows of green coral bushes, a pitted brown rock spire on the left with purple shelf fungus, flat-topped rock pillars topped with
    blue plants. A creature hovers in the basin. Water is clear aquamarine near the camera and saturated blue in the distance. Tall dark-blue silhouettes
    in the upper right look like the kelp forest beyond the biome edge. Good for close colour, distance fade and the edge of the biome.
  - `natures_table` (2026-11-26): SN1 camera (-141.14, -10.92, 83.89), yaw 155.4, pitch +5.5, fovH 91.5, dayScalar 0.59; SN2 at (8376, -14108, -1095) yaw 155.36.
    SN1 view: 11 m deep, looking across a sand hill toward a large flat-topped rock table about 30-50 m away. The table has round arches in its side and
    pale fan-shaped plants. A row of green coral bushes in the foreground, pink/purple tube coral bottom left. The upper ~45 % of the frame is the
    underside of the water surface: bright, sparkling, with light shafts. Near water is clear cyan, far rock fades to flat blue-teal with almost no
    contrast at roughly 60 m. Good for the surface underside, light shafts and the colour of mid-to-far fog.
- Editor side: `src/modkit/scripts/sn1biome_regions.py` places the boxes (see `04` "Water colour / fog per area"). The 42 Safe Shallows regions with the
  converted settings are saved in L_SN2World **VERIFIED (2026-11-26, editor self-check)**. Redo after new settings: `python src/tools/sn1_live.py waterbiomes
  safeShallows_dump` while SN1 is in game -> the converter with `--settings <Workspace>/sn1_shots/safeShallows_dump.json` -> the placer -> cook.
- First in-game comparison, autotest plan `sn1cmp_shallows` (run `<Workspace>/autotest/20261126_175137_sn1cmp_shallows`, SN1 shots in
  `samples/safeShallows/<name>/SN1/shot.png`). **VERIFIED (2026-11-26, autotest screenshots): the 42 regions have no visible effect.** (Questioned by the
  timing observation below.)
  - `shallow_ravine` (4190,10850,-4971), yaw -97.8: terrain matches SN1 (rock arch framing a sand path, rock lip in the foreground). SN2 shows the
    rock and sand lit orange/brown with no blue-teal tint and no fog falloff; SN1 shows teal water, purple coral, plants and fish (no flora/fauna ported yet).
    HUD "Loading Shaders... 5,626".
  - `small_hill` (-11511,-2871,-213), yaw 147.5, pitch -31.7: layout matches (rock on the left, mesas, sand ridge, trench). SN2 is rust-orange with a
    grey-purple haze only at the far top right; SN1 is bright blue-turquoise water, cream sand, green plants, kelp silhouettes. HUD "Loading Shaders... 5,506".
  - `natures_table`: no valid shot; the game crashed during the SN2AutoTest PODDUMP at the same moment as the teleport (`01` "Crashes"; PODDUMP removed 2026-11-26). Valid shot from the rerun `20261126_180611_sn1cmp_shallows_env`.
  - Same run, settled log: `OCEAN settled BP_Ocean_C_0 BodySize=(0,0,0) WVC relLoc=0 relScale=0 ... WaterBoxVolume worldScale=0.00,0.00,0.00`.
  - Diagnostic rerun with `envprobe` at each view (plan `sn1cmp_shallows_env.json` = the same waypoints + `cmdAfter: envprobe`; run
    `<Workspace>/autotest/20261126_180611_sn1cmp_shallows_env`, DONE in 107 s, 3/3 shots, no crash, timeout 600 s):
    - **The 42 regions exist at runtime with the converted settings. VERIFIED (2026-11-26, UE4SS.log `ENVPROBE env REGION ... WLS`)**: e.g.
      `BP_UWEWaterBiomeRegionActor_C_100 WLS WaterFogDistance=3276.54 WaterFogThickness=10 WaterFogBaseThickness=4 WaterFogOpacityWeight=1
      BiomeExtinction=(0.797,0.963,0.991) BiomeExtinctionSkylight=(0.304,0.831,0.956) BiomeAlbedo=(0.0412,0.245,1)`; box centres at z -9750 as placed.
      `REGIONS 46` = 42 SN1Biome + the ocean region and its `WaterVolumeComponent_..._CAT_0`, each listed twice (the ocean class matches both FindAllOf queries).
    - The SN2 ocean region (`BP_UWEOceanBiomeRegionActor_C_1`, fog 7500, albedo (0.1,0.295,1)) is blue as well, and the neutral `..._CAT_0` (fog 10000,
      thickness 1, extinction 1, albedo 0) is still there. So **every region carries a blue look, yet the screen is orange/brown: the brown is not
      caused by region values** (LOGGED 2026-11-26). The render path that turns region settings into the water look is what fails in L_SN2World.
    - Which region applies at the camera: still unknown; `GetActorBounds` fails in Lua for every region (`boundsExtent=?`).
    - `natures_table` (8376,-14108,-1095), yaw 154.5: **VERIFIED (2026-11-26, autotest screenshot)** almost the whole frame is haze, brown on the
      left and grey-purple on the right; the table mesa is only a faint dark-red silhouette in the centre-right; the sea surface shows as white
      patches at the top; HUD "Loading Shaders... 5,017", 12 m marker, O2 45. SN1: clear blue-turquoise water, the table mesa with its arches and
      tube prefab sharp at ~30 m, sun rays, plants, coral, fish. Sight distance here is far shorter than in SN1; whether that comes from our
      33 m WaterFogDistance is UNTESTED (no shot of the same view without the regions).
  - **The look changes within seconds of arriving at a view. LOGGED (2026-11-26, screenshots of two runs at the same pose):** `shallow_ravine`
    shot 1 s after the view (run `20261126_175137_sn1cmp_shallows`, driver.log 17:53:45 -> 17:53:46) shows the rock arch and path lit bright orange;
    shot 4 s after (run `20261126_180611_sn1cmp_shallows_env`, envprobe in between, 18:07:25 -> 18:07:29) is one flat dark brown haze with no terrain.
    `small_hill` is likewise darker and hazier at 4 s. So a short-range brown fog may build up after the teleport, i.e. the regions (fog distance
    3277 cm) may act with the wrong colour rather than not at all. UNTESTED: shots at fixed delays after the teleport. The samples plan keeps the 4 s timing.
  - Baseline sample analysis (`samples/safeShallows/*/analysis.md`, metrics from `src/tools/samples.py analyze`, run 180611): blue/red ratio SN1 1.50 /
    1.64 / 2.30 vs SN2 0.90 / 0.89 / 1.04 (shallow_ravine / small_hill / natures_table); mean luminance SN1 46 / 136 / 144 vs SN2 30 / 42 / 50.
  - Next: diagnose the render path in L_SN2World vs L_Main (`UUWEBiomeTrackerSubsystem.Volumes`, `UUWEBiomeMapComponent` on BP_Ocean:
    RenderTarget/CaptureRadius/DefaultVolumeSettings, the BiomeMaterialParameterCollection values at the camera). Calibration of formula v1 waits for it.

## 7. Extraction pipeline (plan, UNTESTED)
Rule: **RAM is scarce, time is not.** Every step streams one batch at a time, writes results to disk and keeps nothing large in memory. Long runs (hours) are fine.

### Built 2026-11-22: terrain extractor `src/tools/sn1_extract_terrain.py` (spot cube)
Usage: `python -I src/tools/sn1_extract_terrain.py --center x y z [--size 500] [--tile 125] [--out <Workspace>/sn1_extract/spot1]` (Unity metres). Pure numpy, no installs. Heavy job: takes the lock (`sn1extract`).
- **Pipeline:** decode overlapping batches (iterative octree stack) into one global uint8 type + density grid (grid 505^3 incl. 2-voxel margin, ~21.7 s) -> sparse surface nets (one vertex per surface cell = mean of edge crossings from `ComputeSurfaceIntersection`; quads split on the shorter diagonal) -> keep triangles whose centroid is in the cube -> split into x/z tiles by centroid -> one OBJ per tile `tile_<i>_<k>.obj`.
- **OBJ format:** vertices in UE axes, cm, absolute (`UE.X=100*unity.z, UE.Y=100*unity.x, UE.Z=100*unity.y`); `usemtl type_<n>` groups; winding: numeric (b-a)x(c-a) points out of the solid (front-facing in UE, which is left-handed); seabed normals are +Z by that numeric formula. **Correction (VERIFIED 2026-11-22, `sn1terrain_import.py` NORMAL CHECK):** GeometryScript computes face normals with the opposite sign, so the UE importer MUST emit triangles as `a,d,b` (flipped). With `a,b,d`, seabed normals came out Z -0.97; with `a,d,b` they came out +0.97. This matches research/03 §3. Also writes `summary.json`, `preview_topdown.png`, `preview_section.png`.
- **Spot1 run** (cube Unity x -1495.47..-995.47, y -517.33..-17.33, z -39.55..460.45; 64 batches 3..6 x 15..18 x 12..15, all present): 567,664 vertices, 1,131,984 triangles meshed, **1,115,977 triangles kept in the cube** across 16 tiles of 125 m (tiles 0_0..3_3 in `<Workspace>/sn1_extract/spot1/`). Run time 39.8 s total (decode 21.7 s, mesh 24.0 s cumulative, rest = OBJ write + Python gap check). Peak RAM well under 2 GB.
- **Self-checks (VERIFIED 2026-11-22, run output):** spot (-1245.47,-267.33,210.45) is 0.509 m above the extracted surface (ray hit y -267.839), spot voxel outside solid; water point 15.67 m above the surface (hit y -267.661) and outside solid; 4,752 seabed triangles near the spot have mean UE nz 0.864 (92.6 % have nz > 0.5); no NaN vertices. Tile gap check: 1,675,371 edges, 4,765 single-use edges, of which 4,514 lie on the cube's cut border (expected), **251 interior open edges** (not investigated; tiny relative to the mesh, probably crossing-cell degeneracies at 1 voxel overhang spots). Previews (description): top-down height map -387 m (blue, west/left) to -92 m (red, east/right), smooth seabed rising to the east, a dark-blue pit pair left of centre, an elongated light ridge just below the marked spot, speckled small bumps top-right; section at z=210.5 shows flat seabed sloping up to the right with the spot circle 0.5 m over the surface and water circle just above, and one small enclosed void left of centre.
- **Ground truth VERIFIED (2026-11-22):** `src/tools/sn1_compare_terrain.py <extract_dir> <collider.obj>` against the other agent's in-game raycast heightfield `<Workspace>/reports/sn1_spot1_shots/spot1_terrain.obj` (3,668 vertices, Unity m, all inside the cube): distance to nearest extracted triangle **mean 0.029 m, median 0.017 m, p95 0.092 m, max 0.362 m** (target < 0.5 m). Writes `compare.json`. (The 481k-vertex `spot1_terrain_render.obj` render-piece mesh was not compared; the script loops per point in Python, so subsample it first.)
- **Open:** type id to material table; SN1's `Relax` smoothing and blocky mesher not ported (surface nets is smoother, same surface within ~0.1 m); the 251 interior open edges; decimation/Nanite size of 1.1 M triangles per 500 m cube is not yet tried in the editor.

**Stage 0: learn the formats (no game run).** Decompile `Assembly-CSharp.dll` with `ilspycmd`, one type at a time (`-t OctNode`, etc.), not the whole dll.
`ilspycmd` needs `dotnet tool install -g ilspycmd`; the .NET 8 SDK is present. Ask the user before installing.
Read the answers to the open questions in §4 and §5.

**Stage 1: offline converter (Python, outside the editor).** It writes to `<Workspace>\sn1_extract\`. Never commit its output.
1. **Terrain.**
   - For each `.optoctrees` file that is not empty: decode it into a 160³ type/density array, plus a 1-voxel border read from neighbour files.
   - Mesh it with the SN1 algorithm once known; marching cubes / surface nets is the fallback.
   - Decimate, with error-bounded simplification and flat areas first.
   - Write a per-batch mesh file: positions in UE axes/cm, indices, per-vertex or per-triangle material id.
   - Peak RAM is about 8 MB of voxels plus mesh buffers. Run sequentially, with no multiprocessing.
   - Order: first one batch (12-18-12, Safe Shallows), then the y 18/19 layers around the lifepod, then everything.
2. **Objects.**
   - Stream each cells/batch-objects file.
   - Resolve ClassId → prefab path through `prefabs.db`.
   - Compose parent transforms into world transforms and convert to UE axes (§3).
   - Write one CSV/JSON-lines file per batch: `classId, prefabPath, ue_location, ue_quat, ue_scale`. Write `EntitySlotsPlaceholder` and the atmosphere volumes to separate files.
3. **Biomes.** Convert `biomeMap.bin` plus the atmosphere volumes into SN2 biome-region boxes/volumes data.

**Stage 2: modkit editor import (editor Python through `src/modkit/tools/ue_run.py`, long-running, low RAM).**
1. **Terrain meshes.**
   - For each batch file, call `GeometryScript append_buffers_to_mesh`, then `create_new_static_mesh_asset_from_mesh` with Nanite (path VERIFIED in `03` §3, about 7.5 s per asset).
   - Save, unload and GC after every N assets so editor RAM stays flat. Restartable: skip assets that already exist.
   - Estimate: a few thousand non-empty batches × about 10 s gives many hours. That is acceptable.
   - Option: merge 2×2 batches into 320 m assets to cut the asset count.
2. **Placement.**
   - Put the meshes in `L_SN2World` (`/Game/Mods/SN2EmptyWorld/L_SN2World`), or better in World Partition / streamed sub-levels, so the whole map is never resident at once. Open question below.
   - Objects become instanced static meshes per prefab, about 200 k real objects after removing `CellRoot` and the slots.
3. **Cook and package** with `cook_install.sh` (IoStore).

**Object meshes (decision needed).**
- Option (a): map SN1 prefabs to similar SN2 assets with a hand-made table. This keeps the SN2 look and needs no asset extraction.
- Option (b): extract the SN1 meshes and textures from the Addressables bundles with UnityPy (`pip install UnityPy`, ask first) and import them as new assets in the converter.
  This gives a faithful look but costs more work, and the legal limits are the same as for terrain.
- Terrain materials need the same choice: SN1 textures (from the bundles) or SN2 terrain materials.

### Origin cube extraction (2026-11-23, `<Workspace>/sn1_extract/origin/`, log `<Workspace>/reports/origin_extract.log`)
- Command: `--center 0 -150 0 --size 500 --water 40 -18 -10` (output name `origin`). The default `--water` (spot-1 point) lies OUTSIDE this cube and made the extractor crash with `IndexError: index -994 out of bounds for axis 0 with size 504` at `ins[tuple(wv)]`; passing a water point inside the cube fixes it (no code change). VERIFIED (2026-11-23, run output).
- Grid 504^3 voxels, 64 batches decoded (all `ok`), decode 6.7 s, decode+mesh 9.1 s, total 31.0 s. 956,344 vertices, 1,908,950 triangles meshed, **1,885,806 kept in the cube** (16 tiles). Per-tile triangles: 0_0 219698, 0_1 171031, 0_2 104863, 0_3 96194, 1_0 197639, 1_1 90762, 1_2 90821, 1_3 103722, 2_0 214328, 2_1 75265, 2_2 87022, 2_3 103595, 3_0 136202, 3_1 66013, 3_2 72133, 3_3 56518. VERIFIED (2026-11-23).
- Self-check: water point (40,-18,-10) not inside solid, ray down hits y -27.125 (9.125 m below the point). Seabed normals near the centre: 7139 triangles, mean nz 0.582, 70.5% nz>0.5. Gap check: 2,829,469 edges, 7,402 open (6,867 on the cube XY border, 535 interior). VERIFIED (2026-11-23).
- Height range: min vertex y -307.7 m (a deep pit), max -0.91 m; the seabed does NOT touch the cube floor (y -400). Near the pod the seabed is shallow (about -17 m under the pod, vertices at UE z -1625 to -1943 cm within 5 m of the XY origin). VERIFIED (2026-11-23, OBJ vertices).
- Gotcha: the pod XY (0,0) lies exactly on the seam of tiles 1_x/2_x and 1_y/2_y; a vertical line trace exactly along x=0 or y=0 slips through the seam (no hit), offset the trace by a few cm.
- **Triangle holes: ROOT CAUSE (2026-11-23).** The mesh is complete but NON-MANIFOLD. Surface nets (one vertex per cell) makes 4 quads share one edge where a cell face is ambiguous (checkerboard, two diagonal corners inside). Index-based check on the origin OBJs (positions merged across tiles, 1,178 position-degenerate triangles removed): **1,445 edges shared by 4 triangles (2 per direction), 0 other bad edges, 6,860 open edges all on the cube border, 0 interior open edges.** `sn1terrain_import.py` appends via GeometryScript `append_buffers_to_mesh` into a DynamicMesh, which refuses the 3rd and 4th triangle of an edge, so about 2 triangles per bad edge vanish from render and collision (up to about 2.9 k triangles in the origin set; the import's "dynamic mesh has N triangles" note was only a log line). Sanity samples: the ray of report 001 passes 0.44 m from a 4-triangle edge at 1.9 m range, report 002 passes 0.38 m from one at 2.0 m range (VERIFIED 2026-11-23, offline OBJ analysis, scripts not kept). The old gap check was blind to it: 4-use edges balance (+1+1-1-1 = 0, even count) so they never count as open. The "535 interior open edges" were position-key artifacts (OBJ rounded to 0.01 cm collapses 1,178 near-zero-area triangles into index-degenerate ones, giving same-direction and odd-count edges); they disappear once those are ignored, and are not holes. The 1,178 near-zero-area triangles stay in the output (harmless, removing them would open cracks).
- **Fix (2026-11-23, code done, full re-extraction pending because the game was running):** `make_manifold()` in `src/tools/sn1_extract_terrain.py` runs right after `surface_nets`: every (triangle, corner) is a node, fans are joined across good edges, the two direction pairs of each bad edge are matched (preferring the pairing consistent at both endpoints) and joined at both endpoints, each remaining class of a vertex gets its own copy of the vertex at the same position. Geometry is identical (the sheets just stop sharing a vertex). Offline test on the existing origin OBJs: bad edges 1,445 -> 0 (passes 1,445, 4, 0), +1,541 vertices, open edges unchanged at 6,860 (all border), 4 s. New index-based `topo_check()` in the extractor summary (`selfcheck.tile_gap_check.topology_index_based`): `nonmanifold_edges` and `interior_open_edges` must both be 0; `interior_open_plus_nonmanifold` is the one number to assert. The old position-keyed `open_interior` is kept but cannot see split vertex copies. **Real extraction VERIFIED (2026-11-23, `<Workspace>/sn1_extract/origin_fix1/summary.json`, log `<Workspace>/reports/origin_fix1_extract.log`):** same command as `origin` plus `--out .../origin_fix1`, total about 35 s. `make_manifold {'bad_edges_per_pass': [1450, 4, 0], 'vertices_added': 1527, 'final_bad_edges': 0}`; `topology_index_based`: `nonmanifold_edges` 0, `interior_open_edges` 0, `interior_open_plus_nonmanifold` **0**, open edges 6,862 (all near the cube border). Triangles 1,908,950 meshed, identical to the old `origin` (only vertices changed: 957,871 vs 956,344). Per-tile triangle counts equal the old ones (e.g. 0_0 219698, 1_1 90762). The old output is kept as `<Workspace>/sn1_extract/origin_prefix`; `origin` now holds the fix1 data (importer reads `sn1_extract/<set>`). Importer now logs `WARNING <tile>: dynamic mesh kept N of M OBJ triangles` and a total "lost" line (must be 0).
- **Texture streaks (cause found 2026-11-23, not fixed):** `sn1terrain_import.py` uses planar UVs `(X,Y)/UV_CM` from world XY only, so near-vertical faces project along Z and stretch into long vertical streaks. Fixing needs triplanar projection in the material or per-triangle dominant-axis UVs (vertices would need splitting at axis changes); UNTESTED, not cheap.
- **Saw-toothed cube edge (user F1 `bugshots/20261123_181716_004`, +x face at SN1 x=249.6) and the chunk-seam hypothesis (2026-11-23, offline OBJ analysis).** (1) The extractor meshes ONE global grid (`build_grid` then a single `surface_nets` call); batch (160) and octree (32) boundaries only matter while decoding, so a mesher chunk loop seam cannot exist. (2) Binned midpoints of the 1,445 four-triangle edges, the 535 position-keyed "interior open" edges (reproduced exactly: tolerance 1 m, tot!=0 or odd count) and the 1,178 degenerate triangles by voxel index mod 32 and mod 160 on each axis: the fraction within 1.5 voxels of a plane is at or below the uniform expectation everywhere (e.g. mod 32: 0.05 to 0.09 vs 0.094; mod 160: 0.00 to 0.012 vs 0.019). No clustering on SN1 node/batch planes: hypothesis FAILED (2026-11-23). (3) The saw-tooth is the extractor's own cut: `keep = centroid inside cube` drops whole triangles, never clips them. At the +x face 410 triangles straddle x=250 and are removed whole (0 kept triangles have centroid >= 250); kept vertices reach up to 0.40 m past the plane, and the surface is an open sheet with no wall, so the boundary follows triangle edges (about 1 m cells) instead of the plane. VERIFIED (2026-11-23, OBJ data). Not fixed. Cheap fix if wanted: clip triangles to the 4 side planes (Sutherland-Hodgman, new vertices exactly on the plane) instead of the centroid rule; neighbouring cubes would then meet at the same plane, but the per-tile 125 m split would need the same clip. UNTESTED.

## 8. Open questions for SN2 (UNTESTED)
- **Ocean depth.** `BP_Ocean_C.BodySize` Z = 1 km (`02`), but SN1 goes down to about −1.9 km. Check whether swim physics, pressure and fog work below 1 km, or whether `BodySize` can be raised.
  Note: L_SN2World currently has no water physics outside the pod (FAIL, `00` / `09`).
- **Map footprint.** SN1 is 4.1 × 4.1 km. It fits inside the 10 × 10 km ocean body; the edge-of-world ring (`BP_EdgeOfWorldVolume_C`) needs to move to the SN1 void edge.
- **Streaming.** A plain (non-WP) level with thousands of Nanite meshes plus collision keeps everything loaded. Decide between World Partition in a modkit level and level streaming, for the "no hidden map in RAM" rule.
- **Triangle and disk budget** after decimation, and cook time and RAM for thousands of assets.
- **Lifepod.** Align the SN1 lifepod start (Safe Shallows, near Unity origin) with SN2's lifepod (`09`).

## 9. Legal position on shipping SN1-derived data (web check 2026-11-19; not legal advice)
Question: may the mod download contain pre-built assets made from SN1 data (terrain meshes, object placements, models)? This is "option 3".
The alternatives are: each user cooks locally (option 1), or the mod loads converted files at runtime (option 2).

**Primary source read: SN2 Terms of Service** (Steam EULA `1962700_eula_0`, effective 2026-05-21). Relevant clauses:
- §1: licence "solely for personal use". The only explicit creative permission is gameplay videos and screenshots.
- §3(e): no copies of the Game.
- §3(f): no distributing or uploading without prior written consent; no downloading content from the Game with any tool.
- §3(g): no "reverse engineer, derive source code, modify, decompile, disassemble, or create derivative works of the Game". Lawful modifications are "deemed assigned to … the Company".
- §3(l): no data that "mimic[s] the data or functionality in the Game".
- §5: "you may not create works based on the Game IP or modify, distribute, or transmit the Game IP".
- §6(a): fan content must follow the Fan Content Creation Guidelines (`subnautica.com/en/policy/content-guidelines`). That page renders client-side; its text was not readable and is NOT CHECKED.

**Informal statements, all secondary sources:**
- UWE community staff said they "will not be taking action against player made mods, as long as they follow the few simple rules … (like not selling the mods)".
- Official FAQ (`subnautica.com/en/policy_faq`): modding is not officially supported in Early Access, and making mods gives no ownership of the IP.
- A KRAFTON "June 2026 clarification", reported only by a third-party guide and not found at the source: donations are fine, no paywalls, no multiplayer or anti-cheat tampering.
- A ToS revision was promised after the May 2026 backlash. Later Steam EULA versions could not be loaded. Re-check before release.

**SN1's own terms:** not found. The Steam EULA page `264710_eula_0` fails to load, and nothing turned up on unknownworlds.com. Default copyright applies: SN1 terrain, placements and models are Unknown Worlds' copyrighted content.

**Conclusion:**
- Nothing published grants a right to redistribute SN1 content. The SN2 ToS forbids distributing or modifying game IP without written consent, and the tolerance statement covers mods in general, not shipping another game's assets.
- The whole SN2 modding scene, our UE4SS and modkit work included, already runs on informal tolerance rather than permission.
- Option 3 crosses a clearer line: it republishes a whole copyrighted map, and a convenient download could stand in for owning SN1.
- Options 1 and 2 ship no UWE content, only our code. The user extracts from their own copy.
- **Option 3 is viable only with written permission from Unknown Worlds / KRAFTON.** Ask through official support or community channels, and present it as non-commercial, free, and requiring ownership of SN1.

## 10. First-launch builder (design, 2026-11-19, UNTESTED unless marked)
User proposal (2026-11-19): ship a program, not a map. On first launch the mod finds the user's SN1 install and builds the SN1 world locally before
the player reaches the menu. No modkit or editor on the user's machine. Everything that does not contain SN1 content is built by us in advance and shipped.

**Constraint that shapes the design:** SN2 only loads cooked assets (IoStore paks) or meshes built at runtime. Cooking and Nanite building need the
editor, so the user's machine cannot produce cooked or Nanite assets. The builder therefore writes **our own cache format**, and a native runtime
loader turns it into meshes while the game runs.

**Runtime mesh APIs present in the SN2 shipping exe** (grep of `<GameDir>\Subnautica2\Binaries\Win64\Subnautica2-Win64-Shipping.exe`, 2026-11-19; the
string is present, callability UNTESTED): `BuildFromStaticMeshDescriptions` (1 line hit), `CreateStaticMeshDescription` (1), `StaticMeshDescription` (3),
`DynamicMeshComponent` (4), `NaniteBuilder` (0, as expected: no Nanite building at runtime). So `UStaticMesh::BuildFromStaticMeshDescriptions` is very
likely compiled in. Runtime-built static meshes are non-Nanite and need our own LODs. Underwater fog keeps draw distance short, which helps.

### What runs where
| Part | Who builds it | Ships? |
|---|---|---|
| Our level (ocean, sky, post-process, biome volumes from our rules, not SN1 data), materials, progress widget, streaming manager Blueprint | Us, modkit cook, IoStore pak | Yes |
| UE4SS C++ mod `SN1WorldLoader.dll`: reads the cache, builds meshes on worker threads, spawns/destroys chunks around the player | Us | Yes |
| Builder `sn1build.exe` (native C++ or Rust; Python would need a bundled interpreter and is slow) | Us | Yes |
| ClassId → SN2 asset mapping table (our choice of look-alike SN2 assets) | Us | Yes (low risk, see below) |
| Manifest of expected SN1 files (relative path, size, SHA-256) for `Build18` | Us | Yes (hashes are not content) |
| Terrain meshes, LODs, collision, object positions, biome map | Builder on the user's PC, from their SN1 files | **Never** |

The mapping table holds SN1 ClassId GUIDs plus our SN2 asset paths. Identifiers like these are low risk. If that is ever in doubt, key the table on
`prefabs.db` path patterns instead (e.g. `*/Coral/*` → an SN2 coral), resolved at build time.

### First-launch flow
1. **Mod start (before the menu):** `SN1WorldLoader.dll` checks `%LOCALAPPDATA%\Subnautica2\Saved\SN1World\cache.json`, keyed by (SN1 manifest hash,
   builder version). Valid → done. Missing or stale → step 2. The cache is outside the game folder, so SN2 updates and Steam verify leave it alone.
2. **Find SN1:** Steam `libraryfolders.vdf` → appid 264710; Epic `%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item`; otherwise ask for the
   folder. Game Pass installs (`WindowsApps`, access-restricted) are unsupported. Verify the files against the manifest. A mismatch (a different SN1
   build) stops the build with a clear message.
3. **Build:** the dll starts `sn1build.exe` as a **separate process**. This isolates crashes and frees all its RAM when it exits. The game shows the
   cooked progress widget. Do not block the game thread: a frozen window gets a Windows "Not responding" prompt. Either the menu appears with "play SN1
   world" disabled until the build finishes, or startup is held before the menu behind a loading screen that keeps the window responsive.
4. **Builder per batch** (5,416 octree files, 1,164 MB). It streams one batch per worker; worker count = min(cores - 1, RAM budget / per-batch peak).
   1. Read the `.optoctrees` → density grid → surface extraction (surface nets / dual contouring, matching SN1's look) → simplify → 2-3 LODs.
   2. Write `chunks\<x>-<y>-<z>.bin`: positions and normals quantised to 16 bits, indices, material ids, collision proxy.
   3. Objects: cells + batch objects → per-batch instance lists via the mapping table. Unmapped ClassIds are logged and skipped.
   4. Biome map → per-batch biome id (fog, colour, ambience in our level).
   5. Write each file to a temp name, then rename. Write `cache.json` last. An interrupted build then resumes per batch.

   Estimate: minutes in native code, cache a few hundred MB (both UNTESTED).
5. **Play:** the streaming manager loads chunks within a radius. The dll builds a `UStaticMesh` via `BuildFromStaticMeshDescriptions` (or fills a
   `DynamicMeshComponent`) on worker threads; only component registration runs on the game thread. Out-of-range chunks are destroyed, not hidden
   (project RAM rule).

### Why a C++ UE4SS mod and not Lua
- Lua cannot read binary files fast.
- Per-vertex reflected calls cost 0.27 s per chunk on the game thread (`03`).
- `AppendBuffersToMesh` FAILED from Lua (`03`).
- A cooked Blueprint cannot read files outside the pak.

Only native code can read the cache.

### Risks and open questions
- `BuildFromStaticMeshDescriptions` may be usable only from native code. Runtime collision cooking (Chaos) in the shipping exe is UNTESTED.
  Fallback: `DynamicMeshComponent` with complex-as-simple collision.
- UE4SS C++ mods depend on the UE4SS SDK and the game's engine version. Early Access patches can break them, like the Lua mods.
- Draw calls and RAM at a large radius without Nanite or HLOD need measuring. Distant batches could use a coarse LOD merged per 2×2×2 batches.
- Multiplayer: out of scope. **Local only, decided 2026-11-19 (user)**, see `00` "Distribution target".
  - The mod disables or hides host/join while the SN1 world is active.
  - The solo session's own server-side movement checks against our terrain are UNTESTED.
- **Stretch (avoids runtime building):** the builder writes cooked, non-Nanite `StaticMesh` packages into a local IoStore pak, from templates cooked by
  us plus UAssetAPI/retoc-style serialisation, so SN2 streams them like any asset. This is hard and tied to the exact engine version. Research it only
  if the runtime path hits a wall.

### First experiments (cheap, in order)
1. Prove runtime `UStaticMesh::BuildFromStaticMeshDescriptions` from a minimal UE4SS C++ mod: one mesh, visible, with collision.
2. Prototype the builder in Python on one batch (12-18-12) to settle the octree decode (§4 open points), then port the hot loop to native code.
3. Time and measure memory for one batch in native code, then extrapolate to all 5,416.
