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
- `biomes.csv` order, 0-based (index mapping LIKELY, not confirmed in code):

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
- Pixel row/column axis vs Unity x/z: UNTESTED. Check it against `signals.csv` positions and their biome column.

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
