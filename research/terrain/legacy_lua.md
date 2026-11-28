# Terrain from Lua (legacy recipes)

Production terrain is the cooked modkit mod `SN2Terrain` / `SN2EmptyWorld` (`research/terrain/import.md`). The Lua terrain mod `SN2TerrainEdit` was deleted 2026-11-16 (recover: `git show e30f3d0:src/mods/SN2TerrainEdit/Scripts/main.lua`). These Lua recipes remain useful for tests and probes. Sources: 03_creating_terrain.md "Terrain: remove, add, generate" and sub-sections, 00_overview.md "State of play", "Next steps" (split 2026-11-28). Full pass-1 notes: `git show 3449200:research/terrain/legacy_lua.md`.

## How SN2 terrain is built (VERIFIED 2026-11-14 via probe)
World Partition level `L_Main`, 5,055 cells. Ground = Unreal **Landscape** heightmaps (5 landscapes, split into `LandscapeStreamingProxy` tiles, rendered via `LandscapeNaniteComponent`, collision via `LandscapeHeightfieldCollisionComponent`) **plus** dense dressing: `StaticMeshActor` (about 10.6k loaded), `PrefabActor` (about 300-400), environment Blueprints (rocks, corals, flora). Open sand is landscape; pillars, plateaus, cliffs and caves are meshes. Not voxel.

Landscape tile naming: `LandscapeStreamingProxy_<LandscapeGUID>_<TileSizeCode>_<X>_<Y>_<LOD>[_<hash>]`; location = min corner, bounds = location + extent. Seen: `A7174N...` (Coral Gardens, 252 m tiles), `40BMEG...` (around the test save, 127 m tiles, extent 6350), `040AVI...` (coarse far seafloor, 1,240 m tiles, extent 62000), `EK395O...` (deep, z about -503 m).

## 1. Remove terrain
- By actor, VERIFIED 2026-11-14: `actor:SetActorHiddenInGame(true); actor:SetActorEnableCollision(false)` (hide, stays in RAM; testing only) or `actor:K2_DestroyActor()` (frees after GC). Rocks/scree/tufa meshes vanished and returned on toggle. Inside a base the floor is base meshes, not landscape.
- All loaded landscape, VERIFIED 2026-11-15 12:37 (SN2TerrainEdit Ctrl+F2): hide `LandscapeStreamingProxy` + `Landscape` actors **and** their `LandscapeComponent` / `LandscapeNaniteComponent` (`SetHiddenInGame(true,false)`, `SetVisibility(false,false)`), and `LandscapeHeightfieldCollisionComponent:SetCollisionEnabled(0)`. Hiding only the proxy actor was LOGGED but never seen to work. Counts then: 21 proxies, 5 landscapes, 39 components, 21 Nanite, 39 collision.
- Automatic region clearing on load, VERIFIED 2026-11-15 12:52 / 13:06 (`REMOVE_REGIONS` + `LoopAsync` sweep every 1.5 s on the game thread):
  - Landscape: every proxy whose XY bounds intersect the region circle -> hide components -> `K2_DestroyActor` -> `CollectGarbage`. 18 tiles destroyed within 1.5 s of load; GC took proxies 22->4, components 40->16, Nanite 22->4, collision 40->16 (memory really freed).
  - Dressing: `FindAllOf("Actor")`, location inside the region and class allowed -> destroy. Allow-list: `StaticMeshActor`, `PrefabActor`, class name `BP_PCG_*`, class path under `/Game/Art/Environment/` **except** `/Game/Art/Environment/Set/` (Axum/Alterra structures). Judged actors cached by address (cache reset on world load). About 10.6k actors destroyed (9.2k StaticMeshActor, 400 Prefab, 970 env BP), later ones caught as they stream in, no crash, no visible hitch reported.
  - Kept on purpose: bases (`/Game/Blueprints/AbandonedBases/**`, `BP_BaseModule_*`), lifepod, creatures, story actors, WorldPop resources/proxies.
  - Survivors at 13:06, not yet cleared (open: extend the allow-list): `/Game/Blueprints/Environment/**` (BP_CG_BulbFlower 145, BP_CoralSeaWhip_02a 114, BP_FeelerTree_01a 45, BP_SplineTentacle 82), `/Game/Prototyping/Resources/CoralPads/**` (about 340), `/Game/Blueprints/Resources/BP_AcidAnemone` (77), `DecalActor` (256), `PointLight` (240).
  - Landscape-only clearing leaves a "fissure" (gaps between meshes, flora floating); full clearing leaves only the allow-listed survivors.
- The cooked mod now does this deletion (ModActor graph built by `src/modkit/scripts/sn2terrain_removal_graph.py`): **VERIFIED 2026-11-16**, tester "its all there" (ground and dressing gone, custom seafloor present); log: proxies 22 -> 4 within 4 s of load with the Lua sweep disabled; ModActor self-destroys in the lobby. The Lua counter logger hit `A function requiring userdata as param #1 was called without userdata` once and logged nothing (cause not found).

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
Verified meshes: `/Game/Art/Environment/Biome/CoralGarden/Rocks/SM_CG_RockBoulderMed_02a.SM_CG_RockBoulderMed_02a` (radius 7.5 m), `SM_CG_RockRubble_ScreePile_2a`, `/Game/Art/Environment/Biome/OvergrownRuins/Inorganic/SM_OR_LimestoneRubbleBoulder_02a`. Path list: `tools\sn2_packaged_files.txt` (`Subnautica2/Content/X` = `/Game/X`). No HLOD for spawned actors (pop-in at stream distance), no landscape blending, nav (Mercuna) not rebuilt.

## 3. Generate new geometry (Geometry Script) — VERIFIED 2026-11-15
The game ships `Engine/Plugins/Runtime/GeometryScripting` and `ProceduralMeshComponent`, plus `/Engine/BasicShapes/{Cube,Sphere,Cylinder,Cone,Plane}`. Libraries are CDOs under `/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_<Name>`: `MeshPrimitiveFunctions`, `MeshBasicEditFunctions`, `MeshQueryFunctions`, `MeshNormalsFunctions` (booleans and voxel functions present, UNTESTED).
- Star prism (F3), VERIFIED 12:24: spawn `/Script/GeometryFramework.DynamicMeshActor`; `dm = actor.DynamicMeshComponent:GetDynamicMesh()`; `MeshPrimitiveFunctions:AppendSimpleExtrudePolygon(dm, {PolygroupMode=0,bFlipOrientation=false,UVMode=0}, identityT, {{X=,Y=},...}, height, 0, true, 1, nil)`; material borrowed from a resident rock: `StaticMesh:GetMaterial(0)` -> `comp:SetMaterial(0, m)`. 56 tris, 0.16 s.
- Heightfield from a data file, VERIFIED 13:07 (rendered + player collides). File `mods\SN2TerrainEdit\data\seafloor_test.txt`: line 1 `<n> <spacing_cm>`, then n x n heights in cm, row-major (Y outer); generator `tools\make_test_heightfield.py <out>` (101x101, 1.6 m spacing = 160 m, ridge + crater).
```lua
prim:AppendRectangleXY(dm, opts, identityT, (n-1)*sp, (n-1)*sp, n-1, n-1, nil)    -- flat grid centred on the actor
for vid = 0, vc-1 do
  local p = query:GetVertexPosition(dm, vid, {})
  edit:SetVertexPosition(dm, vid, {X=p.X, Y=p.Y, Z=h}, {}, vid < vc-1)   -- defer all but the LAST, or the edit never reaches the renderer
end
nlib:RecomputeNormals(dm, {bAngleWeighted=true, bAreaWeighted=true}, false, nil)
comp:SetMaterial(0, rockMat); comp:SetCollisionEnabled(3); comp:EnableComplexAsSimpleCollision(); comp:UpdateCollision(false)
```
19,602 tris; 260-272 ms on the game thread (read 12, buffers 62, mesh 134 ms); 160x160 m, 24.5 m relief; placed at the mean bounds-centre Z of the destroyed fine landscape tiles (-62 m). `comp:NotifyMeshUpdated()` is not callable (error), not needed.

## Dead ends
- **FAILED (2026-11-15)** deferring every vertex edit: mesh existed but was invisible; fix = leave the last `SetVertexPosition` undeferred.
- **FAILED (2026-11-15)** arbitrary meshes from Lua: `MeshBasicEditFunctions:AppendBuffersToMesh(dm, {Vertices=V, UV0=UV, Triangles={{X=a,Y=b,Z=c},...}}, {}, 0, false, nil)` -> "Tried storing reference to a Lua table for an 'Out' parameter when calling a UFunction but no table was on the stack". Untried alternatives: per-element `AddVertexToMesh`/`AddTriangleToMesh`, `ProceduralMeshComponent:CreateMeshSection_LinearColor` (UNTESTED). Solved via editor Python (`research/terrain/import.md`), so no longer needed.
- Hiding only the landscape proxy actor (no component hiding): LOGGED, never seen to work.
