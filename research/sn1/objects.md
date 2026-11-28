# SN1 placed objects

Pass 2 (2026-11-28): census tables condensed to lines, State-of-play tail folded in (full notes: `git show 3449200:research/sn1/objects.md`).

## 5. Objects: cells, batch objects, prefabs
- **Container format: DECODED (2026-11-26).** Files are UWE `ProtobufSerializer` (protobuf-net) GameObject trees. The recipe is in "Decoding recipe" below; the decoder is `src/tools/sn1_objects.py`.
  The ClassId is protobuf field 7 of `GameObjectData` (`3A 24` + 36 GUID chars); the first census (below) counted `grep -a -o ':\$[0-9a-f-]\{36\}'` matches. **VERIFIED (2026-11-19)**
- **`prefabs.db`** (VERIFIED 2026-11-19): `int32 count` (= 3,336), then `count` × (string ClassId, string path), as .NET BinaryWriter strings (7-bit length prefix, then UTF-8).
  Example: `08 0d 00 00 | 24 <36-byte guid> | 2b WorldEntities/....prefab`.
  The path is the Addressables key. The bundle that holds it is found through `aa\catalog.json`.

**Census, CellsCache** (VERIFIED 2026-11-19): 409,386 objects, 1,195 distinct ClassIds. By kind: `Doodads/Coral_reef/*` 167,032 (largest single prefab `Coral_reef_tree_mushrooms_connector_01`, 22,290), `Misc/CellRoot` (grouping node) 118,920, `EntitySlotsPlaceholder` (random-spawn slots) 90,289, `FloatingStone*` about 8.3 k, `Lost_river` 6,480, `Doodads/Land` 4,708, lights about 3 k (`Coral_reef_Light` 2,376), `Doodads/Precursor` 2,063, `Debris` 1,987, `Doodads/Geometry` 975, VFX 373, creatures 261. `Environment` prefabs: `MembraneTree` 389, Precursor 227, Aurora 210, `FloaterLarge` 136, `BrainCoral` 132.

**Census, BatchObjectsCache** (VERIFIED 2026-11-19): 5,779 objects, 174 distinct: `BatchRoot` 2,975, `Atmosphere` volumes 2,714 (e.g. `CoralRootZone_Sphere` 305, `LostRiver_BonesField_Lake` 127, `GrassyPlateaus/Tower` 118), lights 77, Environment 12.

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
  Reading is `SetParent(parent, worldPositionStays:false)` followed by writing `localPosition/Rotation/Scale`, and the host (`cellsRoot`, `land`) transforms are identity. **VERIFIED (2026-11-26)**: slot-spawned limestone/quartz at spot 1 are within 7 mm of the composed slot position (see "Ground truth" in `objects_slots.md`). Convert to UE with the §3 mapping (`UE = 100*(z, x, y)`, quat `(q.z, q.x, q.y, q.w)`, scale `(s.z, s.x, s.y)`).
- Component payloads other than `Transform` are skipped by their length prefix. Decoded so far: `EntitySlotsPlaceholder` (`objects_slots.md`) and `LargeWorldEntity {2 cellLevel}`. Others seen in the origin cube: `LargeWorldBatchRoot` (BatchRoot only).
- 62 objects in the origin cube are classId-less `CreateEmptyObject` nodes (components Transform + LargeWorldEntity) whose parent CellRoot is (-280,-72,-264) with local (280,72,264): they sit at **world (0,0,0)**, all in cell (0,5,1) of batch 11-18-11. They are not scenery (no prefab); ignore them (category `empty_marker`). **VERIFIED (2026-11-26)**
- `prefabs.db` maps every ClassId in the baked files (0 unknown ClassIds in the origin cube). `Resources/WorldEntities/WorldEntityData` (`objects_slots.md`) has exactly the same 3,336 ClassIds.

Runtime entity slots (what is NOT baked), ground truth at test spot 1, the origin-cube census and the `sn1_objects.py` tools: `research/sn1/objects_slots.md`.

### Status (2026-11-28)
Placed objects for the origin cube are decoded offline (**VERIFIED 2026-11-26**, `src/tools/sn1_objects.py`, `<Workspace>/sn1_objects/origin_cube.jsonl`). Limestone/quartz/sandstone and creatures are not baked: they come from the 22,156 slots rolled unseeded at runtime (matched 6/6 live outcrops at test spot 1); seeded draw `sample --seed 1`. Seafloor grass is per terrain chunk (`VoxelandGrassBuilder`), not placed objects. Porting in progress: asset extraction `research/sn1/assets.md`, SN2 resource mapping `research/features/README.md`.
