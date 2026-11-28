# SN1 placed objects

Sources: 10_sn1_world_data.md "5. Objects: cells, batch objects, prefabs", 00_overview.md "State of play" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## 5. Objects: cells, batch objects, prefabs
- **Container format: DECODED (2026-11-26).** Files are UWE `ProtobufSerializer` (protobuf-net) GameObject trees. The recipe is in "Decoding recipe" below; the decoder is `src/tools/sn1_objects.py`.
  The ClassId is protobuf field 7 of `GameObjectData` (`3A 24` + 36 GUID chars); the first census (below) counted `grep -a -o ':\$[0-9a-f-]\{36\}'` matches. **VERIFIED (2026-11-19)**
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

- `EntitySlotsPlaceholder` holds spawn slots for `LootDistributionData`. In SN2 these map to `UWEWorldPopulation2` (`research/features/README.md`). Do not import them as meshes.
- Atmosphere volumes (fog, light and music zones) map to SN2 `UWEWater` biome regions and `BoxWorldZones` / temperature / audio (`research/sn2/world_systems.md`, `research/features/README.md`).
- UNTESTED: where the global unique objects (Aurora wreck, precursor facilities, the lifepod start) live. They are probably in these caches as large prefabs
  (Aurora 210 entries) or in a scene. Check this once transforms are decoded.

### Decoding recipe: `CellsCache` and `BatchObjectsCache` (VERIFIED 2026-11-26, decompile of `CellManager`, `ProtobufSerializer`, `ProtobufSerializerPrecompiled`, `EntityCell`, `BatchCells`; decoder `src/tools/sn1_objects.py`, parse ends exactly at file size for all 30 cells files and all `batch-objects` files of the origin cube)
All messages are protobuf-net, each prefixed only by a base128 varint length (`PrefixStyle.Base128`, field number 0: no field header). Floats are fixed32. `Int3` = `{1 x, 2 y, 3 z}` varints.
```
baked-batch-cells-X-Y-Z.bin
  CellsFileHeader   {1 version (9 or 10), 2 numCells}
  numCells x [ CellHeaderEx {1 cellId Int3, 2 level, 3 dataLength, 4 legacyDataLength, 5 waiterDataLength, 6 allowSpawnRestrictions}
               dataLength bytes (serialData) , legacyDataLength bytes, waiterDataLength bytes ]      // legacy and waiter are 0 in the origin cube
serialData   = StreamHeader {1 signature=1369164567, 2 version=4}  LoopHeader {1 count}  then `count` objects
object       = GameObjectData {1 CreateEmptyObject, 2 IsActive, 3 Layer, 4 Tag, 6 Id (GUID text), 7 ClassId (GUID text), 8 Parent (Id of parent object), 9 OverridePrefab, 10 MergeObject}
               LoopHeader {1 componentCount}
               componentCount x [ ComponentHeader {1 TypeName, 2 IsEnabled}  <component message, length-prefixed> ]
Transform    = {1 localPosition {1 x,2 y,3 z}, 2 localRotation {1 x,2 y,3 z,4 w}, 3 localScale {1 x,2 y,3 z}}      // component TypeName "UnityEngine.Transform"
batch-objects-X-Y-Z.bin = StreamHeader + one object tree (BatchRoot first, atmosphere volumes / lights as its children), same object encoding
```
- **Cell grid:** a batch (160 m) has 10x10x10 level-0 cells of **16 m** (`BatchCells.GetCellSize`: `blocksPerBatch/10`); levels 1-3 use **32 m** cells (file version >= 9). Cell min corner (Unity) = `batchMin + cellId*cellSize`, `batchMin = batch*160 - (2048, 3040, 2048)`. Level = `LargeWorldEntity.CellLevel` of the entity (0 near ... 3 very far); the cell file is only an acceleration structure, an object lives in exactly one cell. **VERIFIED (2026-11-26)**
- **First object of every cell is `Misc/CellRoot`** (ClassId 55d7ab35-...) at the **absolute world position of the cell centre** (e.g. cell (0,7,7) of batch 12-18-12 -> (-120,-40,-8)), rotation identity, scale 1 (all 1,875 CellRoots in the origin cube). Every other object has `Parent` = that CellRoot's `Id`, and its Transform is **local to the CellRoot**. In `batch-objects` the root is `Misc/BatchRoot` at the batch min corner (e.g. batch 12-17-12 -> (-128,-320,-128)). In the origin cube every non-root object has depth 1 (parent = CellRoot/BatchRoot). **VERIFIED (2026-11-26)**
- **World transform (Unity space):** `world = compose(parentWorld, local)`, parents precede children in the file:
  ```python
  pos = parent.pos + qrot(parent.rot, parent.scale * local.pos)   # component-wise scale
  rot = parent.rot * local.rot ;  scale = parent.scale * local.scale
  ```
  Reading is `SetParent(parent, worldPositionStays:false)` followed by writing `localPosition/Rotation/Scale`, and the host (`cellsRoot`, `land`) transforms are identity. **VERIFIED (2026-11-26)**: slot-spawned limestone/quartz at spot 1 are within 7 mm of the composed slot position (see "Ground truth"). Convert to UE with the §3 mapping (`UE = 100*(z, x, y)`, quat `(q.z, q.x, q.y, q.w)`, scale `(s.z, s.x, s.y)`).
- Component payloads other than `Transform` are skipped by their length prefix. Decoded so far: `EntitySlotsPlaceholder` (below) and `LargeWorldEntity {2 cellLevel}`. Others seen in the origin cube: `LargeWorldBatchRoot` (BatchRoot only).
- 62 objects in the origin cube are classId-less `CreateEmptyObject` nodes (components Transform + LargeWorldEntity) whose parent CellRoot is (-280,-72,-264) with local (280,72,264): they sit at **world (0,0,0)**, all in cell (0,5,1) of batch 11-18-11. They are not scenery (no prefab); ignore them (category `empty_marker`). **VERIFIED (2026-11-26)**
- `prefabs.db` maps every ClassId in the baked files (0 unknown ClassIds in the origin cube). `Resources/WorldEntities/WorldEntityData` (below) has exactly the same 3,336 ClassIds.

### Runtime spawning (what is NOT in the baked placed-object list) (VERIFIED 2026-11-26 from decompile + file reads; model checked against live SN1 at spot 1)
1. **Entity slots.** The 90,289 `WorldEntities/Slots/EntitySlotsPlaceholder` objects are the only slot carriers in the cells (all other `Slots/*` prefabs, 746 of them, live inside prefabs, see 3). Component `EntitySlotsPlaceholder` = `{1 version, 2 repeated EntitySlotData}`; `EntitySlotData = {1 version, 2 biomeType (int, enum BiomeType), 3 allowedTypes (flags Small 1, Medium 2, Large 4, Tall 8, Creature 16), 4 density (float), 5 localPosition, 6 localRotation}`. Slot world pose = `placeholderWorld * (localPosition, localRotation)`. In the origin cube: 778 placeholders, **22,156 slots** (9,566 type 3 = Small|Medium resource slots, 12,590 type 16 = creature slots). Placeholder scale is 1 everywhere.
2. **What a slot spawns.** `EntitySlotsPlaceholder.Start` -> for each slot `CellManager.GetPrefabForSlot` -> `CSVEntitySpawner.GetPrefabForSlot` (decompiled), then the placeholder destroys itself:
   - Candidates = `LootDistributionData.dstDistribution[slot.biomeType]` (built from the JSON, per biome a list of `{classId, count, probability}` in file order). Skip `"None"`, skip ids without `WorldEntityInfo`, skip if `slot.IsTypeAllowed(info.slotType)` is false (`WorldEntityInfo.slotType` Small..Creature), `p = probability / slot.density` (skip `p <= 0`).
   - One roll `r = UnityEngine.Random.value`; if `sum(p) > 1` then `r *= sum`; the first candidate whose running sum `>= r` wins, else nothing spawns (probability `1 - sum`). Fragment items are re-weighted only when the player already scanned that fragment (`PDAScanner.ContainsCompleteEntry`), so a new game uses the plain weights. Winner `{classId, count}`: `count` copies, copies 2.. at `localPosition + Random.insideUnitSphere*4`; rotation = slot rotation, times `Quaternion.Euler(-90,0,0)` (right-multiplied) when `WorldEntityInfo.prefabZUp`; scale = `WorldEntityInfo.localScale`; `LargeWorldEntity.cellLevel = WorldEntityInfo.cellLevel`. The virtual entity is later replaced by the real prefab (`VirtualPrefabIdentifier.SpawnPrefab`, same local pose and scale), at the cell of its world position.
   - **Randomness: no seed.** `UnityEngine.Random` is never seeded in the game code (`grep Random.InitState/seed`: none), so every new game rolls anew; the result is then stored in the user's save (cells serialise their entities). `SpawnRestrictionEnforcer` reads `spawnrestrictions-<quality>.csv` from `SNUnmanagedData`, which does not exist in this install, so it never vetoes a spawn. The Safe Shallows slot rolls are therefore **not reproducible from files** in the sense of "the same objects as SN1 had"; only the slot positions, the biome per slot, the density and the probability table are fixed. They **can** be reproduced as a distribution or as one seeded sample.
3. **Prefab-internal children.** `PrefabPlaceholdersGroup` / `PrefabPlaceholder` (and `EntitySlot`, one per `Slots/*` prefab) are inside the prefab assets: on instantiation each `PrefabPlaceholder` spawns a virtual entity of `prefabClassId` at its local pose (deterministic, no RNG); a placeholder whose target is a `Slots/*` prefab then rolls like a slot. These children are in the Addressables bundles, not in the baked cells. Origin cube prefabs that contain a `PrefabPlaceholdersGroup` (scan of the bundles, `sn1_objects.py prefabscan`, 104 prefabs, 96 bundles found; the 8 missing are atmosphere/light prefabs with spaces or duplicate names): `Environment/CrashHome` x7 (child slot `SafeShallows_Loot_CrashHome`), `Doodads/Coral_reef/Crab_snake_mushrooms_01/03/04` x14 (slots `Jellyshroom_Loot_InsideShroom`, `Jellyshroom_Creature_CrabSnake`), `Natural/FloatingStone4_Floaters` and `FloatingStone5_Floaters` x10 (child `Environment/Floater`), and the 4 wrecks `Environment/Wrecks/ExplorableWreck_SafeShallows_38..41` (25-35 GUID strings each: `Doodads/Debris/*`, `Wrecks/Decoration/*`, slots `SafeShallows_Loot_TechSite_Scatter_Small/Medium`). The child transforms need the prefab's serialized Transforms (asset extraction, not done). Result list: `<Workspace>/sn1_objects/origin_prefab_children.json`. **LOGGED (2026-11-26)** (GUID-string scan of the decompressed bundle, placeholder flag = string `PrefabPlaceholdersGroup` in the serialized file; GUIDs are candidates, not all are placeholders).
4. **Terrain grass is not an object.** Dense seafloor grass is built per terrain chunk (`VoxelandGrassBuilder`, `VoxelandBlockType.grassMesh/grassMaterial`, seeded `VoxelandMisc.CreateRandom(chunk.offset*...)`), part of the terrain rendering. **LOGGED (2026-11-26, decompile only)**.
5. **Not in cells at all:** the lifepod (`EscapePod`, new game spawns it at a random start position, see `research/sn1/README.md`), the player, the Aurora/scene objects. **UNTESTED** for the Aurora.
6. **Sources of the slot data (offline):** `Subnautica_Data/resources.assets` holds `Balance/EntityDistributions` (a plain-text TextAsset, JSON with `//` comments, 190 entries `{prefabPath, distribution:[{biome, count, probability}]}`, covers only Environment/wrecks 47, Natural 44, Creatures 42, Fragments 37, Eggs 13, Spawns 3, Tools 2, Doodads 1 (`Coral_reef_jelly_plant_01_01`): **no flora, no limestone-style terrain props other than Natural/*)** and `WorldEntities/WorldEntityData` (3,336 records of 68 bytes: `string classId; int techType; int slotType; bool prefabZUp (4 bytes); int cellLevel; Vector3 localScale`; int32 count right before the first record). `sn1_objects.py exportdata` writes both to `<Workspace>/sn1_objects/EntityDistributions.json` / `WorldEntityData.json`. The enum names (`BiomeType`, `TechType`) come from the decompiled `<Workspace>/sn1_decompiled/*/BiomeType.cs`. **VERIFIED (2026-11-26, parsed; 190 + 3,336 entries; all distribution ClassIds have a WorldEntityData record)**
7. **Limestone / sandstone / quartz outcrops** (`WorldEntities/Natural/limestone|sandstone|quartz|salt|shale...`) in Safe Shallows and the dunes **come from slots, not from baked cells**. The baked `Natural/*` objects in the origin cube are only 24 `FloatingStone*` scenery props. **VERIFIED (2026-11-26)**

### Ground truth at test spot 1 (VERIFIED 2026-11-26; report `<Workspace>/reports/sn1_testspot1_near_20261122.txt`, 13 live objects with ClassId within 20 m, batch 5-17-14)
- Baked non-slot objects within 25 m: none (only CellRoots and 2 placeholders), so there is nothing to match for doodads here; a baked-doodad ground truth would need a live `near` in the origin cube (not run).
- Slot-spawned static objects: **6/6** live limestone (3) and quartz (3) coincide with a decoded slot position, errors 0.004-0.007 m (the live print is rounded to 0.01 m). Quartz sat on the `Dunes_Grass` slots (p 0.47-0.59), limestone on `Dunes_SandPlateau` slots (p 0.11-0.22); the 4th eligible quartz slot (p 0.40) was empty, as the model allows.
- Creatures (7: CaveCrawler x2, SandShark, BoomerangFishSchool x2, Boomerang, Jumper): each has an eligible creature slot of the right biome within 2.2-10.9 m (they swim away); 0 live objects without a baked object or an eligible slot.
- The live ClassIds (`7e07fce9` limestone, `8ef17c52` quartz) are in `EntityDistributions` for biomes 1701 `Dunes_SandPlateau` and 1702 `Dunes_Grass` as the model needs.

### Origin cube census (box Unity x -250..250, y -400..100, z -250..250; batches x 11..14, y 16..19, z 11..14: 30 cells files, 7,995 cells, levels 0/1/2/3 = 6,040/505/183/1,267) (VERIFIED 2026-11-26, `<Workspace>/sn1_objects/origin_cube.jsonl`)
Baked placed objects, 12,362 (world position in the box):

| Category | Count | Top prefabs |
|---|---|---|
| `doodad_coral_reef` (Coral_reef scenery: mushrooms, jeweled disks, plants, kelp, shells, stingers) | 9,215 | `Coral_reef_purple_mushrooms_01_04` 3261, `_01_01` 582, `_01_03` 468, `coral_reef_small_deco_15_red` 462, `_01_02` 460, `coral_reef_small_deco_12` 447, `Coral_reef_jeweled_disk_red_01_01` 391 |
| `cellroot` (grouping node, ignore) | 1,875 | CellRoot |
| `slots` (EntitySlotsPlaceholder, see below) | 778 | EntitySlotsPlaceholder |
| `doodad_other` (`Doodads/Geometry/SafeShallows`) | 150 | `Coral_Clump02b` 102, `02c` 35, `02d` 9 |
| `atmosphere` volumes (batch-objects, scale = volume size) | 127 | `SafeShallows/Caves Entrance (Sphere)` 42, `Caves` 21, `Caves Entrance` 17, `Caves (Sphere)` 14, `HugeTube (Sphere)` 12 |
| `light` | 62 | `Point_Cave_Mushroom` 35, `Giant_Mushroom_Light` 15, `Bounce` 8, `Stinger_Light` 4 |
| `empty_marker` (classId-less, at world 0,0,0; ignore) | 62 | - |
| `environment` | 39 | `BrainCoral` 29, `CrashHome` 7, `Geyser` 1, 2 deprecated atmosphere |
| `scenery_floating_stone` | 24 | `FloatingStone5` 9, `FloatingStone5_Floaters` 6, `FloatingStone4_Floaters` 4, `FloatingStone4` 3, `FloatingStone7` 2 |
| `batchroot` (ignore) | 23 | BatchRoot |
| `wreck` | 4 | `ExplorableWreck_SafeShallows_38..41` |
| `vfx` | 3 | `xBubbleColumn_big` 2, `_medium` 1 |

No creatures, resource outcrops, plants, eggs or fragments are baked in the origin cube; 9,049 of the 12,362 have a non-identity rotation, 5,229 a non-unit scale (208 non-uniform).
Slot spawning in the same box (`sn1_objects.py slots` -> `origin_slots.jsonl`; `expected`): 22,156 slots, 21,489 with at least one candidate; top biomes `SafeShallows_Wall` 3292, `SafeShallows_OpenShallow_CreatureOnly` 3128, `JellyshroomCaves_CaveWall` 2389, `SafeShallows_SandFlat` 2213, `SafeShallows_Grass` 1938, `Kelp_Wall` 1533, `SafeShallows_Plants` 1111. **Expected spawned entities about 3,800** (model sum of p*count): creatures ~2,780 (Peeper 572, Eyeye 465, Boomerang 442, Bladderfish 229, GarryFish 204, Oculus 129), resource outcrops ~910 (limestone 377, quartz 139, sandstone 91, salt 71, shale 52, scrap metal 35), eggs ~93, fragments ~22. One seeded realisation (`sample --seed 1` -> `origin_spawned_sample_seed1.jsonl`): 3,903 entities (2,851 creatures, 932 outcrops, 92 eggs, 28 fragments). **LOGGED (2026-11-26)** (model validated on 13 live objects only, no statistical test of the probabilities).

### Tools (2026-11-26)
`python -I src/tools/sn1_objects.py <cmd>` (stdlib only; paths from `local.config`): `dump --box x0 x1 y0 y1 z0 z1 --name N` (JSON lines to `<Workspace>/sn1_objects/N.jsonl`: classId, prefab, kind, batch, cell, level, id, parent, world pos/quat/scale, local lpos/lquat/lscale, components, slotCount), `census --box ... | --jsonl F`, `near --pos x y z --radius R`, `match --live <near report> --pos x y z` (baked / slot-spawned / creature classification), `slots --box ... --name N` (every slot with world pose, biome, types, density, per-slot outcome probabilities), `expected --box ...`, `sample --box ... --seed S --name N`, `exportdata`, `prefabscan --jsonl F --name N`. `src/tools/sn1_unityfs.py` = pure-Python UnityFS (LZ4) bundle reader used by `prefabscan`. All offline, light (origin cube dump 3 s; whole world 85 s).

## State of play detail (moved from 00_overview.md, 2026-11-28)

| Capability | Status |
|---|---|
| SN1 placed objects (decorations, outcrops, creatures) for the origin cube, `src/tools/sn1_objects.py` | **VERIFIED 2026-11-26 (offline):** `CellsCache` / `BatchObjectsCache` fully decoded with world transforms (12,362 baked objects in the origin cube, `<Workspace>/sn1_objects/origin_cube.jsonl`); limestone/quartz/sandstone and creatures are NOT baked — they come from 22,156 `EntitySlotsPlaceholder` slots rolled unseeded at runtime (`EntityDistributions` + `WorldEntityData`, matched 6/6 live outcrops at test spot 1); seeded draw `sample --seed 1`. Seafloor grass is per-terrain-chunk (`VoxelandGrassBuilder`), not placed objects. Porting in progress (asset extraction `research/sn1/assets.md`, SN2 resource mapping `research/features/README.md`). See `research/sn1/objects.md` §5 |
