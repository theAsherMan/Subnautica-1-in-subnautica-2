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

### Multi-tile SN1 terrain import (`src\modkit\scripts\sn1terrain_import.py`) — VERIFIED 2026-11-22 (editor log, reload check, line trace; in-game look UNTESTED)
- Input: 16 OBJ tiles (125 m each) of the SN1 spot-1 500 m cube, UE cm axes, absolute (`<Workspace>\sn1_extract\spot1\tile_<i>_<k>.obj`, only `v`, `usemtl`, `f a b c`).
  Output: one static mesh per tile `/Game/Mods/SN2EmptyWorld/SN1Terrain/SM_spot1_tile_<i>_<k>`, recentred on the tile bounds centre; one `StaticMeshActor` per tile in
  `L_SN2World` at that centre, tag `SN1Terrain`, outliner folder `SN1Terrain`. Idempotent: it deletes tagged actors first, overwrites assets.
- **Winding (contradicts the extractor note "outward, do not flip"):** feeding OBJ faces `a,b,d` unchanged gave GeometryScript face normals pointing DOWN on all 16 tiles
  (sampled mean Z -0.35..-0.86; nearest triangle below the spot (-0.109, 0.213, -0.971)). With `IntVector(a, d, b)` the same triangle is (0.109, -0.213, 0.971) and the
  sampled mean Z is +0.35..+0.86. Same rule as the grid note above: UE buffers want `a,d,b`. VERIFIED 2026-11-22 (script NORMAL CHECK, run 1 vs runs 2/3).
- Normals: `unreal.GeometryScriptCalculateNormalsOptions` properties are `angle_weighted` and `area_weighted` (not `weight_by_*`); both set True, then `recompute_normals`.
- UVs: planar world UVs (X, Y)/100 cm, because the material is triplanar (UVs unused by it).
- Material (all tiles, slot 0): `/Game/Art/Environment/Biome/CoralGarden/Rocks/Material/MI_CG_RockSmooth_01a_Triplanar` (MaterialInstanceConstant, parent
  `/Game/Materials/_Master/Master/M_LayerStandard`). Chosen for the name "Triplanar" (no UV layout needed). Other seabed candidates in the packaged list:
  `MI_CG_SandPlaneBlend_01a/b/c`, `MI_CG_RockSmooth_01a_TopSand`, `M_Landscape_*`. Triplanar behaviour and look in game: UNTESTED.
- Nanite ON (`mesh.nanite_settings` set directly: enabled, fallback PERCENT_TRIANGLES 1.0; `enable_nanite` in the create options does not stick). Collision:
  `body_setup.collision_trace_flag = CTF_USE_COMPLEX_AS_SIMPLE`, checked after reload for all 16 actors.
- Triangle counts (dynamic mesh; the OBJ has up to 32 more per tile that GeometryScript drops as degenerate/duplicate): 0_0 67010, 0_1 70496, 0_2 68164, 0_3 70974,
  1_0 56299, 1_1 54118, 1_2 113823, 1_3 60150, 2_0 51970, 2_1 71148, 2_2 52096, 2_3 59212, 3_0 84958, 3_1 73071, 3_2 66390, 3_3 95777; total 1,115,656.
- Timing: 16 tiles built in 143-148 s (about 9 s per tile: ~0.5 s parse/buffers/normals, ~7-8 s asset creation + save); whole script about 150 s incl. reload check.
- Self-check: after `new_blank_map` + `load_map`, 16 tagged actors at the expected locations (< 1 cm), complex-as-simple, folder and tag OK. Line trace
  `SystemLibrary.line_trace_single(world, spot+3 m, spot-30 m, TRACE_TYPE_QUERY1, trace_complex=True, ...)` hit `SM_spot1_tile_2_1` at (21045,-124547,-26784), 3.51 m below
  spot+3 m (0.51 m below the spot), normal Z 0.971. VERIFIED 2026-11-22.
- Python gotchas: `line_trace_single` returns only a `HitResult` (or `None` = no hit, the bool is dropped). `HitResult` has no editor properties in Python; use
  `hit.to_tuple()` = (blocking_hit, initial_overlap, time, distance, location, impact_point, normal, impact_normal, phys_mat, hit_actor, hit_component, ...).
- After a rebuild of `L_SN2World` (`sn2world_map.py`) re-run this script; a fresh level has no tile actors.

- (2026-11-28) The import also gives each tile mesh the Habitat Builder ground user data (`sn1terrain_udata.add_ground_udata`, `DA_SandSurfaceData`), otherwise the builder refuses to place on it. One-off for existing tiles: `sn1terrain_ground_udata.py`. VERIFIED in game 2026-11-28, see `04` "Base building".
#### Import by set, origin cube (2026-11-23)
- `sn1terrain_import.py` is parametrised by set (`spot1` | `origin`). The set name is read from the first line of `<Workspace>/sn1_import_set.txt` (`ue_run.py` does not forward environment variables to the editor), else env `SN1_SET`, else `spot1`. Input `<Workspace>/sn1_extract/<set>`, assets `SM_<set>_tile_<i>_<k>`, actor tags `SN1Terrain` (common, so the autotest `sn1probe` count works) + `SN1Terrain_<set>`. Only the actors of the set being imported are deleted (own set tag, or label prefix for old spot-1 actors that only carry `SN1Terrain`). Remove the set file afterwards (it was deleted after the origin import).
- Origin import: log `deleted 0 existing actors of set origin; kept 16 actors of other sets`, `RELOAD CHECK PASSED: 16 actors of set origin ...; total tagged SN1Terrain: 32`, 214-226 s. The second import run logged `deleted 16 existing actors of set origin; kept 16 actors of other sets` (idempotence). VERIFIED (2026-11-23, editor log `<Workspace>/reports/origin_import.log`).
- Viewpoint trace (Unity (40,-18,-10) = UE (-1000,4000,-1800), seabed UE z -2712): hit `SM_origin_tile_2_1` at z -2712, normal Z 0.996. VERIFIED (2026-11-23).
- Pod `BP_StaticLifepod_Surface_C` at UE (0,0,100): no terrain within 3 m (nearest origin vertex 13.84 m away, at (-1025,100,-825)); the seabed under the pod is at UE z about -1737 cm (down trace at (37,53)), i.e. 18.4 m below the pod origin. Upward traces from far below did not hit (backface culling of complex traces from below the surface), use downward traces. VERIFIED (2026-11-23).
- Tadpole spawn (-731,-951,-300): seabed below at z -1661 (`SM_origin_tile_1_1`), clearance 13.6 m; no terrain above; nearest vertex 9.19 m. VERIFIED (2026-11-23).
- Cook: `SN2_ALLOW_ATTACH_ABORTS=1 bash src/modkit/tools/cook_install.sh SN2EmptyWorld 2`, `Packages Cooked: 17` (16 origin + map; spot-1 packages incrementally skipped), installed `SN2EmptyWorld.ucas` 348,139,104 B. `retoc list --path` (saved in `<Workspace>/reports/retoc_origin_list.txt`): 16 `SM_spot1_tile_*.uasset`, 16 `SM_origin_tile_*.uasset`, 1 `.umap`. VERIFIED (2026-11-23).

## 4. Memory requirement: no hidden SN2 terrain in RAM in the finished mod
- Hide = everything stays resident → testing only.
- Destroy on stream-in (current) = actors/components freed after GC (VERIFIED by object counts), but each WP cell still loads and is torn down whenever it streams in;
  cell package and HLOD proxies remain. Process memory is too noisy to show the delta (`reports\memory_log.csv`, world load adds ~1.7 GB at the same moment).
- Never load = data-level change, UNTESTED: (a) override `_Generated_` cell packages without landscape/dressing (modkit + IoStore; breaks on every game patch since cells
  are regenerated/renamed); (b) deactivate Data Layers that carry dressing; (c) **preferred end state: don't load `L_Main` at all — load our own level containing SN1
  terrain plus the SN2 systems the game needs (BP_UWESky, BP_Ocean + ocean biome region, player start, WorldPop storage, edge-of-world ring)**.

## 5. SN1 import design (UNTESTED plan)
1. Extract SN1 terrain: SN1 stores voxel octrees per batch (160 m cubes, a 26×20×26 world). The file format is decoded and the extraction pipeline is planned in `10_sn1_world_data.md` (2026-11-19).
2. Mesh each batch (marching cubes / dual contouring) → triangles + material ids; decimate; write a chunk file (needs the arbitrary-mesh path, §3).
3. Deliver: stream chunk files around the player into `DynamicMeshActor`s (proven for one 160 m grid chunk in 0.27 s), or cook them as static meshes with the modkit.
4. Clear SN2 underneath (§1) or place the map in open ocean and move the `BP_EdgeOfWorldVolume_C` ring; `BP_Ocean_C.BodySize` = 10 km × 10 km × 1 km.
5. Coordinates: SN1 is Y-up metres, SN2 is Z-up centimetres. Both engines are left-handed. Use **UE (X, Y, Z) = 100 · (unity.z, unity.x, unity.y) + offset**,
   with quaternion UE (X, Y, Z, W) = (q.z, q.x, q.y, q.w) (UNTESTED derivation, `10` §3). The earlier formula here, (x·100, z·100, y·100), swaps two axes and would mirror the map. It is withdrawn (2026-11-19).
6. **Offset decision (decided 2026-11-22, in-game check pending):** offset (0, 0, 0). The SN1 origin is the `L_SN2World` origin (the lifepod start) and SN1 sea level (y = 0)
   is the SN2 ocean surface (Z = 0). The spot-1 tiles are therefore imported at their absolute UE coordinates (spot UE (21045, -124547, -26733) cm); the tile actors sit at the tile centres.
   Whether the pod ends up where the player should be, and whether the ocean surface lines up, is UNTESTED in game.

#### In-game check, spot-1 open-water views (2026-11-22, autotest `spot1`, run folder `autotest/20261122_163326_spot1`)
- **FAILED (2026-11-22): no shots; the game crashed while leaving the lobby for `L_SN2World`.** The Start click worked and the log shows
  `LoadMap: /Game/Mods/SN2EmptyWorld/L_SN2World??game=Survival` at 08:34:36. 23 s later (08:34:59) the log has `LogGarbage: Warning: Spent more than 20.00s on routing FinishDestroy to objects (objects in queue: 22795)`
  (last object a `SphereComponent`, i.e. the teardown of `L_ClientLobby`), then `UObject::AbortInsideMemberFunction`, and a minidump `crash/crash_2026_11_22_16_34_59.8237556.dmp`.
- Dump (`<Workspace>\reports\spot1_crash_mdmp.txt`, via `src/tools/mdmp.py`): exception 0xC0000005, access violation WRITE at address 0x0, rip = `Subnautica2-Win64-Shipping.exe+0x1626F24`, thread 9196. No symbols, so no function name.
- The process then stayed alive with no visible window; the screen was the LOADING screen (`shots/stall_menu.png`). The harness reported FAIL_MENU (step `create_new_game_survival_play` end condition not met within 300 s) and force-killed it. Not a CRASH verdict, so this is a classification gap.
- Reading: the crash is in lobby-world teardown, before `L_SN2World` content was loaded, so it is not yet shown to be caused by the SN1Terrain tiles. The pak itself loaded (BPModLoader listed SN2EmptyWorld). UNTESTED: whether the same crash happens with the previous SN2EmptyWorld (no tiles), or with SN2Census/other Lua mods disabled.
- Test world: none created (`slot_cleanup.txt`: "SLOT_CLEANUP none (no new slot created)").

#### In-game check 2, spot-1 open-water views, reproduction (2026-11-22, runs `autotest/20261122_164700_spot1` then `autotest/20261122_165749_spot1`)
- Attempt 1 = CRASH (reclassified from TIMEOUT by the new harness rule). The lobby teardown was normal this time (`LoadMap` 16:47:32 -> `Took 1.99 s`), `WORLD L_SN2World` and `PAWN possessed spawn=(-16,-28,235)` logged, 7 of 10 shots taken, then dump `crash_2026_11_22_16_47_46.9544883.dmp`: 0xC0000005 READ at 0x10068746281 inside `UE4SS.dll+0x9347F0`, thread 16508 (last game log line a story-goal unlock at 08:47:46). Shots k4..k6 are byte-identical (UNCHANGED), i.e. the render froze. The driver did not notice and ran to the 600 s timeout. So the 16:34 lobby-teardown crash (previous block) did not recur; a different crash (inside UE4SS.dll, mid-run) did. Both are UNDIAGNOSED. LOGGED (2026-11-22).
- Machine at launch, attempt 1: 9.7 GB free of 15.9, no UnrealEditor/zenserver/ShaderCompileWorker, MsMpEng running (`machine.txt`). Attempt 2: 10.0 GB free. So RAM starvation is not shown for the failed 16:47 run.
- Attempt 2 = DONE, 10 of 10 shots, DEATHS 0. `CAMOFFSET camera-pawn=(0.0,0.0,79.7)`; camera held at (20950,-124513,-25253..-25255): X/Y exact, Z about 55 cm below the target -25199 (cause UNEXPLAINED, perhaps the pawn sinking before the shots). All VIEWERR `OK` (yaw error 1.45 deg at most, up/down pitch within 0.9 deg). `FOVSET target=91.49 before=90.00 after=90.00` = the FOV could not be changed (stays 90, vs SN1 91.49; difference small). Map load took 8.08 s (2.0 s in attempt 1), consistent with the tile content loading.
- **Terrain is NOT visible in any of the 10 views (VERIFIED (2026-11-22, `<run 165749>/shots/00_spot1_water_k0..k9.png`, contact sheet `<Workspace>/reports/spot1_compare.png` SN1 left | SN2 right)).** k0..k3 (yaw 0..135) show a featureless amber/brown haze, brighter at the top; k4..k7 (yaw 180..315) and k8 (up) are uniform dark grey-purple haze; k9 (down) shows the player's own arm and tool and a few floating particles, no seabed. SN1 side: seabed and rock arches from yaw 090..225, sand and a rock wall below. No tile, seam or rock shape of the SN1 terrain appears in any SN2 view. HUD: depth 253 m (SN1 252 m), O2 about 41 falling to about 3 over the 10 shots (drowning pressure, no death).
- Cause not established: the pak (`SN2EmptyWorld.pak/.ucas/.utoc`, ucas 123 518 704 bytes, toc EntryCount=36) mounted and the map opened with no asset-load error in `Subnautica2.log`; no `SN1Terrain` string appears in either log. UNTESTED (needs an approved run): whether the 16 tile actors exist in-world (Lua FindAllOf StaticMeshActor count / tag), their world location and bounds, whether Nanite meshes render with the triplanar material at that depth, and SN2 water fog/visibility at 15 m (the down view shows nothing beyond arm length, so fog could hide terrain 16 m away).

#### In-game check 3, diagnostic run with the `sn1probe` verb (2026-11-22, run `autotest/20261122_170305_spot1_diag`, plan `spot1_diag.json`, DONE, 22/22 shots, no crash)
- Plan: A = 120 s wait at the lifepod (probe at start, +40, +80, end), B = teleport to (21045,-124547,-26433) (3 m above the traced seabed) with abs8ud shots and probes before and after, C = the old spot-1 point (20950,-124513,-25199), abs8ud.
- **H1 (tiles not in the world) is REFUTED. VERIFIED (2026-11-22, Lua probe log lines)**: every probe: `COUNT staticMeshActors=16 tagged_or_named=16`; each tile line shows `isVisible=true hiddenInGame=false collision=3` (material of `StaticMeshActor_9`: `/Game/Art/Environment/Biome/CoralGarden/Rocks/Material/MI_CG_RockSmooth_01a_Triplanar`). `registered=?` = `IsRegistered()` failed in pcall (not informative).
- Trace straight down from camera at B: `HIT owner=StaticMeshActor_9 comp=StaticMeshComponent0 impact=(21045,-124547,-26784) dist=295.8` (the actor is `SM_spot1_tile_2_1`). VERIFIED (2026-11-22, log).
- **H2 (drawn only after shaders finish) is REFUTED for the draw itself. VERIFIED (2026-11-22, screenshot `<run>/shots/01_seabed_close_k9.png`)**: looking straight down at B (camera 2.96 m above) the whole frame is the SN1 seabed: rust-brown speckled rock, a lit orange-tan area on the right and a shadowed dark area on the left, with the player's arms; HUD top-left "Loading Shaders... 81". So tile geometry and material render while shaders are still loading. The HUD counter does count down (shots: 727 at B k0, 449 at B k4, 81 at B k9); the `{a}` placeholder is only unreadable in the text widget that the Lua probe reads (`SHADERTEXT` stays "Compiling|Loading Shaders... {a}"; the first read was `PrecacheRequestsLabel|Compiling Initial Shaders...`). The 120 s wait did not finish shader compilation.
- **H3 (visibility distance / water fog) is the open explanation. VERIFIED (2026-11-22, screenshots)**: at B (3 m above the seabed) all 8 horizontal views (`01_seabed_close_k0..k7`) show only dark blue/grey-purple haze with no seabed at the horizon (k0 lum 67, k4 shows a pale light shaft top-left and a few bubble-like objects; no terrain), while the down view shows terrain 3 m away. So water fog hides terrain at grazing angles and at a distance of more than a few metres in this world; at 253 m depth (the HUD depth) there is no sunlight, only the haze colour. UNTESTED: the actual fog start/density, and whether terrain at ~15 m is visible looking down (point C had no valid down view, see next).
- Point C (`02_water_repeat`): k0..k3 lum 42.7, 11.2, 1.2, 1.1 (black, drowning vignette); the player died of `ReceivedDamage.OutOfOxygen` between k3 and k4 and the driver respawned (`RESPAWN pos=-16,-28,235 after=3.1`). k4..k9 are therefore NOT at C: k4 and k8 show haze, k9 shows a very bright white blackbox beacon (dropped items) below the player at the respawn, i.e. these shots are not a valid test of the terrain at C. No O2 management exists in the plan, so every point deeper than the O2 time (about 45 s at 253 m depth after the wait) risks death.
- Reading for the planner: the import itself works (tiles loaded, collidable, rendered). Why the first spot-1 point showed only haze: that point is 15.8 m above the seabed and the sight distance in this world's water is shorter than that; the earlier 10 views were never taken looking at terrain within sight distance. Next: shots at 2-8 m above the seabed (down and obliquely), and find the fog settings (SN2 water/fog volume or post-process), then compare with SN1 visibility (SN1 sees about 20-30 m at this depth near the surface lit area).
- Timeout used: 700 s (last DONE spot1 run 104 s + 120 s wait + variance); actual run about 230 s.

#### In-game check 4, visibility vs height and valid open-water repeat (2026-11-22, run `autotest/20261122_171228_spot1_vis`, plan `spot1_vis.json`, DONE, 18/18 shots, DEATHS 0, run time 152 s, timeout 600 s)
- Test slot: none created (`SLOT_CLEANUP none`), nothing to delete. Comparison sheet: `<Workspace>/reports/spot1_compare2.png` (SN1 left, SN2 right, `compare_shots.py`).
- **A `open_water` (camera 20950,-124513,-25199, 10 shots, no drowning; HUD depth 253 m, SN1 reference 252 m). VERIFIED (2026-11-22, `<run>/shots/00_open_water_k0..k9.png`)**: SN1 terrain is visible at every yaw but the look is entirely different. SN2 shows the seabed as overexposed cream/beige sand (lum 145-212, SN1 is dark blue-teal), no blue water tint, no fog, no particles. yaw0 and yaw45: a sloping sand bank filling the lower two thirds with orange-brown silhouettes (coral-like fingers) on the crest against a dark amber sky region. yaw90: sand slope, amber upper left. yaw135 and yaw180: a large sand mass with a black jagged cut-out at the top (black = void/unrendered background, not an SN1-looking arch). yaw225: sand wall on the left, black on the right. yaw270 and yaw315: dark navy water above, sand slope in the lower right. Up (k8): a circular bright blue sky disc in a dark amber surround. Down (k9): sand, the player's legs/boots. SN1 arch and outcrops at yaw 90-180 are NOT recognisably reproduced: the shapes differ (SN1 has an arch at yaw 90 and a rock tower at yaw 180; SN2 shows smooth sand banks). Shape match not established, possibly just different overall lighting hiding them (UNTESTED).
- **B vertical columns at (21045,-124547), h = camera height above traced seabed -26784 (h2 = -26584 ... h16 = -25184). VERIFIED (2026-11-22, `<run>/sheets/0[1-4]_column_h*.png`, lum 208-218)**: the seabed is clearly visible at ALL tested heights (2, 5, 10 and 16 m), both straight down (-89) and at pitch -45; sand texture with ripples, no fading toward the bottom. So within 16 m SN2 water fog does not hide the terrain; the horizontal haze in the first check is not explained by distance fog at these ranges (which fits `WaterFogOpacityWeight` below).
- **Probe (`envprobe` at h2) VERIFIED (2026-11-22, UE4SS.log lines `ENVPROBE column_h2_env_before ...`)**: two biome region actors, `WaterVolumeComponent_BP_UWEOceanBiomeRegionActor_C_CAT_0` (WaterFogDistance 10000, thickness 1, extinction (1,1,1), albedo (0,0,0): neutral/no tint) and `BP_UWEOceanBiomeRegionActor_C_1` at (0,0,-5000000) (WaterFogDistance 7500, thickness 10, base thickness 4, extinction (0.907,0.945,0.955), skylight ext (0.6,0.761,0.8), albedo (0.1,0.295,1)). Bounds and BiomeData unreadable via Lua ("?"). `BP_Ocean_C_0` WaterLightingSettings: same 7500/10/4 values but `WaterFogOpacityWeight=0.0`. Pawn physics volume line not captured in the filtered output. ExponentialHeightFog on `BP_UWESky_C_0`: FogDensity 0.0157, HeightFalloff 0.0467, StartDistance 50000, MaxOpacity 1, volumetric fog on (50000). PostProcessVolume count 0. BP_Fog_Sphere_C count 0 (the earlier 6 count was a different map). Reading (UNTESTED hypothesis): the ocean region in use has no extinction/albedo tint at depth, hence the beige unlit-water look; the blue underwater look likely needs the biome region setup (extinction/albedo) to apply to the camera volume.
- **O2 approach: FAILED to refill (2026-11-22).** `SN2CheatManager:Oxygen()` is called fine (`FindFirstOf("SN2CheatManager")`) but is a TOGGLE: the HUD showed "[Cheat ...] Oxygen cheat enabled / disabled" messages and the HUD O2 fell 46 -> 17 over the run; probe `Oxygen cur=35 base=35 MaxOxygen=45`. My attribute fallback matched `DashOxygenCost` (first name containing "oxygen") and overwrote it with 45 (harmless in a deleted test world). No death only because underwater time stayed about 40 s per run. Fixed in Lua afterwards (exact `Oxygen`/`MaxOxygen` match, cheat called once per game); the fixed version is UNTESTED (no run). If the exact-name attribute write does not hold, fall back to `podtp` between waypoints.

#### In-game check 5, origin cube (2026-11-23, run `autotest/20261123_173439_origin`, plan `origin.json`, DONE, 12/12 shots, DEATHS 0, run time 191 s, timeout 600 s / check 240 s, hidden desktop, engine input; no test slot created: `SLOT_CLEANUP none`)
- SN1 reference: run `sn1_runs/20261123_170955` (script `origin_shots.sn1s`, DONE, 138 s, 10 shots, no slot left), viewpoint Unity (40,-18,-10) = UE (-1000,4000,-1800), about 41 m from the pod (10 m west, 40 m south of it, so SSW; 19 m below sea level, 9.1 m above the seabed). HUD depth 18 m in SN1, 19 m in SN2. Sheet `<Workspace>/reports/origin_compare.png` (SN1 left, SN2 right).
- `sn1probe`: `COUNT staticMeshActors=32 tagged_or_named=32` (16 spot1 + 16 origin tiles). VERIFIED (2026-11-23, UE4SS.log).
- Terrain shape: VERIFIED (2026-11-23, sheet `origin_compare.png`) the SN2 terrain matches the SN1 shape at the yaws where the water is clear: at yaw 270 the flat-topped rock slab in the foreground and the rock spire behind it appear at the same place as in SN1, yaw 315 shows the slab at the left edge as in SN1, the down view shows the seabed with a pit at the same place where SN1 shows a placed tube-shaped prefab. Yaws 0-135 are almost black/brown haze in SN2 (the SN1 rocks and ridges there cannot be compared); the up view shows the sea surface as grey-white with black holes (water look problem).
- Missing SN1 features (placed prefabs, not voxel terrain): the floating rock with pink coral at upper left (yaw 0), all plants and corals (kelp-like bushes, orange coral), fish, and the tube-like prefab in the down view (in SN2 only a dark hole is left where it stood).
- Lifepod: not visible in any shot (the under-surface waypoint at UE (0,800,-200) looks down at 3 m depth and shows only seabed). The seabed is 18.4 m below the pod origin, so the pod floats sensibly in open water over the seabed.
- Water look (known, not part of this task): SN2 shots are dark brown/orange haze, "Loading Shaders... 5.x" still on the HUD, no blue fog; appears here too.
- **Water-look target (user, 2026-11-23):** the water should look clear and blue. The fog is "a later problem" (deferred). Not scheduled yet.
- **Triangle-shaped holes in the origin terrain. VERIFIED (2026-11-23, user F1 bug reports `<Workspace>/bugshots/20261123_181123_001` and `..._181156_002`, user: "there is a hole into the world").** Both are in a rock crevice below the seabed level, about 30-45 m W/SW of the pod, `movementMode` 4 (swimming), `L_SN2World`. The tile is `SM_origin_tile_1_1` (crosshair hit in report 001).
  - Report 001: camera UE (-1636,-2279,-2161) = SN1 (-22.8,-21.6,-16.4), HUD 22 m, looking up (pitch 45.5, yaw -155.5). The screenshot shows rock walls all around, with one clean single-triangle hole just above the crosshair. Through it, bright blue sky with clouds is visible, with no water surface or fog between. The crosshair hit is 2.09 m away at UE (-1769.8,-2340.1,-2011.4) = SN1 (-23.4,-20.1,-17.7), normal (0.995,-0.054,-0.082).
  - Report 002: camera UE (-2813,-3308,-2448) = SN1 (-33.1,-24.5,-28.1), HUD 25 m, looking down (pitch -41.6, yaw -171.3). The screenshot shows a narrow dark triangular gap in the floor where two rock faces meet. The crosshair is inside it and the trace has `hit=false`, so collision is missing there too.
  - Also seen in 002: the vertical rock faces show long vertical streaks of stretched texture.
  - Report 003 (`..._181232_003`): camera UE (-2092,-4313,-2597) = SN1 (-43.1,-26.0,-20.9), HUD 26 m, looking up (pitch 53.2, yaw -51.2). The screenshot shows a pale sandy rock ceiling filling the view, with one thin single-triangle hole (dark at one end, blue at the other) just below the crosshair. The crosshair hit is 3.72 m away on `SM_origin_tile_1_1` at UE (-1952.4,-4487.0,-2275.4) = SN1 (-44.9,-22.8,-19.5), normal (0.131,-0.131,-0.983), a downward-facing ceiling.
  - User, 2026-11-23: "there are a lot of them". The user has stopped reporting individual holes. The task is the root cause, not patching these three spots.
  - Fits the 535 interior open edges counted by the extractor gap check (`10`, origin set: 7,402 open, 6,867 on the cube border). It is not a tile seam: the tiles are 125 m and neither point is near a tile border. Cause UNTESTED; the candidates are the surface-nets mesher (missing faces in ambiguous or non-manifold cells, or one of two quad triangles dropped) and the import (degenerate-triangle filtering in `sn1terrain_import.py` or the mesh build).
  - **Cause (2026-11-23, offline analysis of the origin OBJs): non-manifold edges from the surface-nets mesher, dropped by the DynamicMesh at import.** 1,445 edges are shared by 4 triangles (checkerboard cell faces); GeometryScript `append_buffers_to_mesh` keeps only 2 per edge. Both reports' view rays pass within 0.4 m of such an edge at the hit range. A third report (`bugshots/20261123_181232_003`, hole just below the crosshair on a ceiling, SN1 about (-44.9,-22.8,-19.5)) is the same kind of hole by the user's description; the user says holes are everywhere, consistent with 1,445 bad edges. The 535 "interior open edges" were a separate rounding artifact (see `10`). Fix in the extractor (`make_manifold`, vertex splitting).
  - **Fix result (2026-11-23).** Re-extracted (`origin_fix1`, 35 s): `make_manifold` bad edges per pass [1450, 4, 0], +1,527 vertices, `interior_open_plus_nonmanifold` 0, 1,908,950 triangles (same as before). Imported into `L_SN2World` replacing the 16 `SM_origin_tile_*` actors in place: log `triangles in OBJ files vs kept by DynamicMesh: lost 0 (must be 0)`, `RELOAD CHECK PASSED`. Cooked (`cook_install.sh SN2EmptyWorld 2`, 5 min 12 s, 17 packages cooked), `.ucas` 348,352,096 B. **VERIFIED (2026-11-23, autotest `holes_recheck`, bugshot engine shots `<Workspace>/bugshots/20261123_190147_001`, `..._190155_001`, `..._190203_001`).** At the three report camera positions and rotations (measured within about 1.5 deg), the crosshair ray hits `SM_origin_tile_1_1` in all three (`hit:true`, distances 2.7 m, 1.5 m, 4.9 m). Screenshots: 001 shows a continuous rock ceiling and an overhang with a darker cave pocket, no sky triangle (jagged cube edges and texture streaks remain); 002 shows rock walls, hands visible and stretched planar-UV streaks, no void; 003 shows an unbroken pale sandy ceiling, no hole where the thin triangle was. The 8-direction plus up/down shots at 003 (`shots/03_r003_8_k0..k9.png`) were taken but not examined in detail. Report 002 previously had no hit (a hole); now `hit:true`. Streaks: planar XY UVs, see `10`.
  - **Cube-edge saw-tooth (report `bugshots/20261123_181716_004`) is not the same bug and not a chunk seam:** the extractor drops whole triangles by centroid at the cube border instead of clipping to the plane; no clustering of mesh anomalies on SN1 batch/node planes. Details and status in `10`.
- **Edge of the origin cube: VERIFIED (2026-11-23, user F1 report `..._181716_004`, from inside a Tadpole).**
  - Camera: UE (-2882,24957,-6669) = SN1 (249.6,-66.7,-28.8), i.e. on the +x border of the 500 m cube. Looking along SN1 -z (yaw -179.6, pitch -32.8).
  - The screenshot is split by a vertical, saw-toothed line. To the right is the origin terrain: a sandy rock pillar and a reddish seabed. To the left is plain dark blue water with no terrain at all.
  - The crosshair hit `SM_origin_tile_3_1` 19.9 m away.
  - This is the expected end of the extract (nothing outside the cube is imported). It is not a hole.
  - User, 2026-11-23: "the edges of the copied space look not flat". The cube face is cut along whole mesher cells, not clipped to the plane.
  - **Decision (user, 2026-11-23): no straight-edge clip.** "in the end product the jagardness of the world boundary wont matter". Leave the centroid cut as it is.
  - Raised as a possible lead for the holes (cells dropped at internal chunk boundaries) and passed to the hole agent. The offline analysis above places the hole cause elsewhere (non-manifold edges). The jagged face still matters later: when neighbouring cubes or the full map are tiled, the faces must meet without gaps (UNTESTED).
- **Imported terrain disappears: user-reported, cause UNTESTED.**
  - User, 2026-11-23: "the map just disappeared". It happened once in the origin cube (the session around 18:17-18:21 local, the user was in or near an F4 Tadpole) and once earlier on the first copied patch (spot 1). No F1 report was taken.
  - The game log for 10:17-10:21 UTC has no streaming, unload or level event before the user's quit to menu at 10:21:21. The only recurring item is `Failed to find console variable 'wp.Runtime.HLOD'` every 2 min (known harmless, see `09`).
  - `L_SN2World` is not World Partition, so WP cell streaming cannot unload the tiles.
  - Candidates to check: mesh bounds vs vertex extent (frustum or occlusion culling of a whole tile), draw or cull distances, HLOD, and occlusion with very large meshes. A tile render-settings dump is requested (`<Workspace>/reports/origin_tile_render_settings.txt`).
  - **User details (2026-11-23):**
    - PDA voice at the moment of disappearance: unknown (user had no headphones on, 2026-11-23).
    - Only the terrain vanished. The lifepod may have gone too ("I could not see it"). The Tadpole the user was driving stayed.
    - It was instant, and the terrain did not come back.
    - 1st time: swimming near the northern copied area (spot 1). 2nd time: driving the Tadpole at the northern end of the origin cube ("northern end of the shallows").
  - **Log correlation (2026-11-23, game logs `%LOCALAPPDATA%\Subnautica2\Saved\Logs\Subnautica2-backup-2026.11.23-*.log`), cause still UNTESTED.** Every long user session logs the same story-goal burst a few minutes after the world loads, and the user leaves the world soon after it:

    | Session log | World loaded (UTC) | Story-goal burst (UTC) | User leaves the world |
    |---|---|---|---|
    | `08.42.44` | 08:29:10 | 08:36:08 | lobby 08:37:45, world reloaded 08:37:56 (11 s later) |
    | `09.03.13` | 08:57:33 | 09:02:35 | lobby 09:02:51 (16 s later), then quit |
    | `10.21.30` | 10:11:05 | 10:17:44 (28 s after F1 report `_004` at 10:17:16) | lobby 10:21:2x, then quit |

    - The burst is `LogStoryGoals: Unlocked story goal DA_Investigation_BioBed_Unlock_CoralGardens_StoryGoal`, then `DA_Player_NoA_FirstRadioMessage_StoryGoal`, then `DA_Player_NoA_FirstRadioMessage_without_BaseNoA_StoryGoal`, and `LogDialogue: Playing FMOD event voiceover_PDA_2D/Alert_Research1_PDA_1` (`..._PDA_2` 8 s later). It comes 5 to 7 min after the world loads.
    - No other event in the window: no streaming, level, unload or GC line. There is only a periodic `FlushAsyncLoading(...): 1 QueuedPackages, 0 AsyncPackages` about once a minute, and a weather change `CloudyB -> Misty` at 10:20:26.
    - Hypothesis (UNTESTED): something bound to this story goal (or to the time that triggers it) hides or removes the imported terrain. Test: one long autotest that stays in view of terrain past the burst, taking a screenshot and a count of `SM_origin_tile_*` actors (valid, hidden, visible) before and after it.
    - **Hypothesis DISPROVED for this scenario (VERIFIED 2026-11-23, autotest run `<Workspace>/autotest/20261123_191841_vanish_proof`, plan `vanish_proof`, screenshots `shots/00_vp_k8.png` before, `00_vp_k9.png` at, `00_vp_k10.png` +33 s, `00_vp_k16.png` +200 s).** Camera at UE (-2092,-4313,-2597), yaw -50.4, pitch ~53, HUD 27 m. A natural burst fired at t=295.6 s (log `LogStoryGoals: Display: Unlock...`; the k9 shot shows the HUD toast `PDA: The Noetic Advisor has transmitted an alert...`). In all shots from t=0 to t=497 s the origin terrain still fills the view (pale rock ceiling with the zigzag seam, identical before, at and after the burst). The 10 `abs8ud` shots after the wait (`01_vp_after_k*.png`) show the surrounding cave walls intact. So the burst alone does not remove or hide the imported terrain in an autotest. Open: the user sessions that saw it vanish differ in some way (longer play, real input, other state); the cause stays unknown.
    - **The TCENSUS numbers of that run are INVALID.** `origin=0/0 spot1=0/0` at every census because the verb matched the ACTOR name, but the imported actors are `StaticMeshActor_N` and only their MESH assets are `SM_origin_tile_*`. Fixed in `terraincensus` (also matches `StaticMeshComponent.StaticMesh` name), UNTESTED, no run approved. The lifepod census line is valid: `BP_StaticLifepod_Surface_C_0 bHidden=false rootVisible=true hullVisible=true wasRecentlyRendered=true` at t=157 and at the end (LOGGED, not seen in a shot: the view was inside a crevice).
    - **The burst is not a fixed timer (LOGGED 2026-11-23, from run `<Workspace>/autotest/20261122_121230_sn2world_load`, plan `sn2world_load`, `L_SN2World` before any terrain import, `game=Survival`).** The same three goals and `Alert_Research1_PDA_1` fired 61 s after `LoadMap` (04:14:03 -> 04:15:04 UTC), not 5-7 min. That run spawned and died at once (`00_spawn_death.png`). No other kept autotest `Subnautica2.log` contains the burst (e.g. `spot1_diag` waited 120 s at the pod without it). Trigger UNKNOWN; a proof test must check that the burst really fired, or force the goal.
  - **Render-settings dump DONE (2026-11-23, editor script `src/modkit/scripts/sn1tile_render_dump.py`, read-only, output `<Workspace>/reports/origin_tile_render_settings.txt`, 2,280 lines, all 32 tile actors).** VERIFIED (2026-11-23, read from the loaded L_SN2World in the editor): nothing found that explains a tile vanishing.
    - Actor/component, identical on all 32 tiles (origin and spot 1): `StaticMeshActor`, Mobility STATIC, `visible` True, `hidden_in_game` False, `hidden` False; `ld_max_draw_distance` 0, `cached_max_draw_distance` 0, `min_draw_distance` 0 (no cull distance); `never_distance_cull` False, `allow_cull_distance_volume` True (no CullDistanceVolume in the level); `bounds_scale` 1.0; `use_as_occluder` True; `hlod_layer` None, `hlod_batching_policy` NONE, `data_layers` [], no HLOD/WorldPartition/DataLayer/CullDistance/PostProcess/PrecomputedVisibility actors in the level; `kill_z` -1048575; world settings class plain `WorldSettings`. `is_spatially_loaded` True is an actor default and has no effect in a non-WP level.
    - Mesh: Nanite enabled (`position_precision` auto, `fallback_relative_error` 1.0, `keep_percent_triangles` 1.0), 1 LOD, 1 section, complex-as-simple, `BlockAll`, `never_needs_cooked_collision_data` False, `generate_mesh_distance_field` True, no bounds extensions. Editor triangle counts are a few tens lower than the OBJ (1_1: 90,706 vs 90,762 imported), i.e. the static-mesh build drops degenerate triangles.
    - **Bounds match the vertices exactly:** for all 16 origin tiles the component bounds origin and box extent equal the OBJ vertex min/max centre and half-size to 0.1 cm (e.g. 1_1 origin (-6252.1,-6248.4,-1884.3), extent (6286.6,6284.5,1670.1), sphere radius 8999.7; the tallest, 2_0, origin z -15537, extent z 15237, radius 17,088 cm). No tiny or wrong bounds.
    - Spot-1 tiles (`SM_spot1_tile_*`, still in the level): same settings; only the placement differs (centres near UE y -105,000 to -143,000, z -15,000 to -34,000, 63-m half-extents, 51 to 114 k triangles each). No difference in any render setting.
    - Not tested: Nanite streaming-pool or GPU-memory pressure (very large single Nanite meshes: tile 0_0 to 3_0 columns up to 30 km tall bounds), Lumen/VSM, and the Tadpole's own camera or render pass. These stay candidates for "map disappeared" (UNTESTED); the settings the dump covers are cleared.
