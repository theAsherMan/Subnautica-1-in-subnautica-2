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
