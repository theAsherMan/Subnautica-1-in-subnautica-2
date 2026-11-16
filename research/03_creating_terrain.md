# Terrain: remove, add, generate

How SN2 terrain is built (VERIFIED 2026-11-14 via probe): World Partition level `L_Main`, 5,055 cells. Ground = Unreal **Landscape** heightmaps
(5 landscapes, split into `LandscapeStreamingProxy` tiles, rendered via `LandscapeNaniteComponent`, collision via `LandscapeHeightfieldCollisionComponent`)
**plus** dense dressing: `StaticMeshActor` (≈10.6k loaded), `PrefabActor` (≈300–400), environment Blueprints (rocks, corals, flora). Open sand is landscape;
pillars, plateaus, cliffs and caves are meshes. Not voxel.

Landscape tile naming: `LandscapeStreamingProxy_<LandscapeGUID>_<TileSizeCode>_<X>_<Y>_<LOD>[_<hash>]`. Tile location = min corner; bounds = location + extent.
Seen: `A7174N…` (Coral Gardens, 252 m tiles), `40BMEG…` (around the test save, 127 m tiles, extent 6350), `040AVI…` (coarse far seafloor, 1,240 m tiles, extent 62000),
`EK395O…` (deep, z ≈ −503 m).

## 1. Remove terrain
### By actor — VERIFIED 2026-11-14
```lua
actor:SetActorHiddenInGame(true); actor:SetActorEnableCollision(false)   -- hide (stays in RAM; testing only)
actor:K2_DestroyActor()                                                   -- destroy (frees after GC)
```
Rocks/scree/tufa meshes vanished and returned on toggle. Inside a base the floor is base meshes, not landscape.

### All loaded landscape — VERIFIED 2026-11-15 12:37 (SN2TerrainEdit Ctrl+F2)
Hide `LandscapeStreamingProxy` + `Landscape` actors **and** their `LandscapeComponent` / `LandscapeNaniteComponent` (`SetHiddenInGame(true,false)`,
`SetVisibility(false,false)`), and `LandscapeHeightfieldCollisionComponent:SetCollisionEnabled(0)`. Hiding only the proxy actor was LOGGED but never seen to work;
hide the components too. Counts at the time: 21 proxies, 5 landscapes, 39 components, 21 Nanite, 39 collision.

### Automatic region clearing on load — VERIFIED 2026-11-15 12:52 / 13:06
SN2TerrainEdit `REMOVE_REGIONS` + `LoopAsync` sweep every 1.5 s (on the game thread):
- Landscape: every `LandscapeStreamingProxy` whose XY bounds intersect the region circle → hide its components → `K2_DestroyActor` → `CollectGarbage`.
  Result: 18 tiles destroyed within 1.5 s of load; GC took proxies 22→4, components 40→16, Nanite 22→4, collision 40→16 (memory really freed).
- Dressing (`clearDressing = true`): `FindAllOf("Actor")`, actor location inside the region and class allowed → destroy. Allow-list:
  `StaticMeshActor`, `PrefabActor`, class name `BP_PCG_*`, class path under `/Game/Art/Environment/` **except** `/Game/Art/Environment/Set/` (Axum/Alterra structures).
  Already-judged actors are cached by address so later sweeps only test newly streamed actors (cache reset on world load).
  Result: ≈10.6k actors destroyed (≈9.2k StaticMeshActor, ≈400 Prefab, ≈970 env BP), new ones caught as they stream in, no crash, no visible hitch reported.
- Kept on purpose: bases (`/Game/Blueprints/AbandonedBases/**`, `BP_BaseModule_*`), lifepod, creatures, story actors, WorldPop resources/proxies.
- Not yet cleared (survivor log 13:06): `/Game/Blueprints/Environment/**` (BP_CG_BulbFlower 145, BP_CoralSeaWhip_02a 114, BP_FeelerTree_01a 45, BP_SplineTentacle 82),
  `/Game/Prototyping/Resources/CoralPads/**` (≈340), `/Game/Blueprints/Resources/BP_AcidAnemone` (77), `DecalActor` (256), `PointLight` (240) → add next.
- Visual result of landscape-only clearing: a "fissure" — gaps between meshes, flora floating. Full clearing (landscape + dressing) leaves only the allow-listed survivors.

## 2. Add the game's own meshes — VERIFIED 2026-11-14/15
```lua
local gs  = StaticFindObject("/Script/Engine.Default__GameplayStatics")
local cls = StaticFindObject("/Script/Engine.StaticMeshActor")
local T = { Rotation={X=0,Y=0,Z=0,W=1}, Translation={X=x,Y=y,Z=z}, Scale3D={X=1,Y=1,Z=1} }
local a = gs:BeginDeferredActorSpawnFromClass(world, cls, T, 1, pawn, 0)
local c = a.StaticMeshComponent
c:SetMobility(2)                  -- Movable: mesh can be assigned after spawn
gs:FinishSpawningActor(a, T, 0)
c:SetStaticMesh(mesh)             -- mesh: StaticFindObject(path) or LoadAsset(path) on the game thread
c:SetCollisionEnabled(3)
```
Verified meshes: `/Game/Art/Environment/Biome/CoralGarden/Rocks/SM_CG_RockBoulderMed_02a.SM_CG_RockBoulderMed_02a` (radius 7.5 m), `SM_CG_RockRubble_ScreePile_2a`,
`/Game/Art/Environment/Biome/OvergrownRuins/Inorganic/SM_OR_LimestoneRubbleBoulder_02a`. Path list: `tools\sn2_packaged_files.txt` (`Subnautica2/Content/X` = `/Game/X`).
No HLOD for spawned actors (pop-in at stream distance), no landscape blending, nav (Mercuna) not rebuilt.

## 3. Generate new geometry (Geometry Script) — VERIFIED 2026-11-15
The game ships `Engine/Plugins/Runtime/GeometryScripting` and `ProceduralMeshComponent`, plus `/Engine/BasicShapes/{Cube,Sphere,Cylinder,Cone,Plane}`.
Libraries are CDOs under `/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_<Name>`: `MeshPrimitiveFunctions`, `MeshBasicEditFunctions`,
`MeshQueryFunctions`, `MeshNormalsFunctions` (also present: booleans, voxel functions — UNTESTED).

### Star prism (F3) — VERIFIED 12:24
Spawn `/Script/GeometryFramework.DynamicMeshActor`; `dm = actor.DynamicMeshComponent:GetDynamicMesh()`;
`MeshPrimitiveFunctions:AppendSimpleExtrudePolygon(dm, {PolygroupMode=0,bFlipOrientation=false,UVMode=0}, identityT, {{X=,Y=},...}, height, 0, true, 1, nil)`;
material borrowed from any resident rock: `StaticMesh:GetMaterial(0)` → `comp:SetMaterial(0, m)`. 56 tris, 0.16 s.

### Heightfield from a data file — VERIFIED 13:07 (rendered + player collides)
File `mods\SN2TerrainEdit\data\seafloor_test.txt`: line 1 `<n> <spacing_cm>`, then n×n heights in cm, row-major (Y outer). Generator: `tools\make_test_heightfield.py <out>`
(101×101, 1.6 m spacing = 160 m, ridge + crater). Build:
```lua
prim:AppendRectangleXY(dm, opts, identityT, (n-1)*sp, (n-1)*sp, n-1, n-1, nil)    -- flat grid centred on the actor
for vid = 0, vc-1 do
  local p = query:GetVertexPosition(dm, vid, {})
  -- grid index from p.X/p.Y, look up height
  edit:SetVertexPosition(dm, vid, {X=p.X, Y=p.Y, Z=h}, {}, vid < vc-1)   -- defer all but the LAST, or the edit never reaches the renderer
end
nlib:RecomputeNormals(dm, {bAngleWeighted=true, bAreaWeighted=true}, false, nil)
comp:SetMaterial(0, rockMat); comp:SetCollisionEnabled(3); comp:EnableComplexAsSimpleCollision(); comp:UpdateCollision(false)
```
19,602 tris; 260–272 ms total on the game thread (read 12, buffers 62, mesh 134 ms). Bounds: 160×160 m, 24.5 m relief. Placed at the mean bounds-centre Z of the
destroyed fine landscape tiles (−62 m here). First attempt deferred every vertex → mesh existed but was invisible (FAILED, fixed by the rule above).
`comp:NotifyMeshUpdated()` is not callable (returns error) — not needed.

### Arbitrary meshes — FAILED 2026-11-15
`MeshBasicEditFunctions:AppendBuffersToMesh(dm, {Vertices=V, UV0=UV, Triangles={{X=a,Y=b,Z=c},...}}, {}, 0, false, nil)` →
"Tried storing reference to a Lua table for an 'Out' parameter when calling a UFunction but no table was on the stack". Needed for non-grid meshes (SN1 caves/overhangs).
Ideas: pass the out-param as a named local; check exact 5.6 signature via UE4SS "Generate Lua Types"/CXX header dump; alternative routes — `AddVertexToMesh`/
`AddTriangleToMesh` per element with deferral (slower), `ProceduralMeshComponent:CreateMeshSection_LinearColor(0, V, I, N, UV, C, Tan, true)` (UNTESTED),
or Geometry Script list types via `GeometryScriptLibrary_ListUtilityFunctions` conversions.

### Arbitrary meshes in the **editor** (modkit Python) — VERIFIED 2026-11-16 (asset built, cooked, visible + collidable in game)
The same call works from editor Python, which is the intended production path (cooked assets, see `08_modkit_setup.md`):
```python
buf = unreal.GeometryScriptSimpleMeshBuffers()
buf.set_editor_property("vertices", [unreal.Vector(x, y, z), ...])      # cm, Z up
buf.set_editor_property("uv0", [unreal.Vector2D(u, v), ...])
buf.set_editor_property("triangles", [unreal.IntVector(a, d, b), ...])  # a,b,d CCW-from-above came out facing -Z -> use a,d,b (or flip_normals)
dm = unreal.DynamicMesh()
unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(dm, buf, 0, False)          # returns tuple
unreal.GeometryScript_Normals.recompute_normals(dm, unreal.GeometryScriptCalculateNormalsOptions())
mesh, outcome = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, "/Game/Mods/<Mod>/SM_x", opts)
```
101×101 grid (20k tris): buffers 58 ms, dynamic mesh 199 ms, asset creation + save 7.5 s. Full script: `src\modkit\scripts\sn2terrain_build.py`.
This unblocks SN1 terrain import (marching-cubes output = arbitrary triangle soup) without the Lua out-param problem.

## 4. Memory requirement: no hidden SN2 terrain in RAM in the finished mod
- Hide = everything stays resident → testing only.
- Destroy on stream-in (current) = actors/components freed after GC (VERIFIED by object counts), but each WP cell still loads and is torn down whenever it streams in;
  cell package and HLOD proxies remain. Process memory is too noisy to show the delta (`reports\memory_log.csv`, world load adds ~1.7 GB at the same moment).
- Never load = data-level change, UNTESTED: (a) override `_Generated_` cell packages without landscape/dressing (modkit + IoStore; breaks on every game patch since cells
  are regenerated/renamed); (b) deactivate Data Layers that carry dressing; (c) **preferred end state: don't load `L_Main` at all — load our own level containing SN1
  terrain plus the SN2 systems the game needs (BP_UWESky, BP_Ocean + ocean biome region, player start, WorldPop storage, edge-of-world ring)**.

## 5. SN1 import design (UNTESTED plan)
1. Extract SN1 terrain: SN1 stores voxel octrees per batch (160 m cubes; map ≈ 26×26 batches horizontally). Format/location still to research.
2. Mesh each batch (marching cubes / dual contouring) → triangles + material ids; decimate; write a chunk file (needs the arbitrary-mesh path, §3).
3. Deliver: stream chunk files around the player into `DynamicMeshActor`s (proven for one 160 m grid chunk in 0.27 s), or cook them as static meshes with the modkit.
4. Clear SN2 underneath (§1) or place the map in open ocean and move the `BP_EdgeOfWorldVolume_C` ring; `BP_Ocean_C.BodySize` = 10 km × 10 km × 1 km.
5. Coordinates: SN1 is Y-up metres, SN2 is Z-up centimetres → SN2 (x·100, z·100, y·100) + offset.
