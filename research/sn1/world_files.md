# SN1 world files: install, grid, terrain format

Sources: 10_sn1_world_data.md "10 — Subnautica 1 world data: files, formats, extraction pla", 10_sn1_world_data.md "1. Install and build", 10_sn1_world_data.md "2. `Build18\` inventory (VERIFIED 2026-11-19, listing)", 10_sn1_world_data.md "3. World grid and coordinates", 10_sn1_world_data.md "4. Terrain: `.optoctrees` format", 00_overview.md "State of play" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## 10 — Subnautica 1 world data: files, formats, extraction plan

What the Subnautica 1 (SN1) install contains for the world map, which parts have been decoded, and the planned pipeline into SN2.
Investigation 2026-11-19: files were read and parsed offline only. The game was not run, and nothing was implemented in `src/`.

`<SN1Dir>` is the SN1 Steam install folder, the one that contains `Subnautica_Data\`. It is resolved from `SN1_GAME_DIR` in `local.config`.
Legal: SN1 data must never be committed or distributed. The finished mod ships a converter that each user runs against their own SN1 install (see `research/status.md` → Distribution).

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
  This is a cyclic permutation, so it keeps handedness. The older `(x, z, y)` mapping in `research/terrain/import.md` §5 swaps two axes and would mirror the map. It is corrected there.
- Map offset in `L_SN2World`: (0, 0, 0), i.e. SN1 origin = SN2 origin, SN1 sea level = SN2 ocean surface (decided 2026-11-22, in-game check pending). Import: `research/terrain/legacy_lua.md` §3, "Multi-tile SN1 terrain import".

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

## State of play detail (moved from 00_overview.md, 2026-11-28)

| Capability | Status |
|---|---|
| Reading Subnautica 1 terrain files | **Started 2026-11-19 (offline investigation, nothing implemented).** VERIFIED: data location, batch grid and origin, `.optoctrees` binary layout (parsed exactly), object caches (protobuf, ClassIds counted: 409 k cell objects), `prefabs.db` layout, biome map layout. Open: tree/child order, density encoding, type → material table. Protobuf transform fields VERIFIED 2026-11-26 (row "SN1 placed objects"). See `research/sn1/README.md` |
