# SN1 terrain import into SN2

Sources: 03_creating_terrain.md "Arbitrary meshes in the editor (modkit Python) — VERIFIED 20", 03_creating_terrain.md "Multi-tile SN1 terrain import (`src\modkit\scripts\sn1terrai", 03_creating_terrain.md "4. Memory requirement: no hidden SN2 terrain in RAM in the f", 03_creating_terrain.md "5. SN1 import design (UNTESTED plan)", 00_overview.md "State of play", 00_overview.md "Next steps" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## Arbitrary meshes in the **editor** (modkit Python) — VERIFIED 2026-11-16 (asset built, cooked, visible + collidable in game)
The same call works from editor Python, which is the intended production path (cooked assets, see `research/code/modkit_setup.md`):
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

## Multi-tile SN1 terrain import (`src\modkit\scripts\sn1terrain_import.py`) — VERIFIED 2026-11-22 (editor log, reload check, line trace; in-game look UNTESTED)
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

### Import an area: `sn1_import_area.sh` (built 2026-11-28; PAUSED, orchestrator never run)
- One command: `bash src/tools/sn1_import_area.sh "<area>" [--dry-run] [--replace-legacy spot1] [--reimport-all] [--no-test] [--regress]`; skill `import-area` (`.claude/skills/import-area/SKILL.md`). Registry `src/tools/sn1_areas.json`, resolver `sn1_area_resolve.py`, seam check `sn1_seam_check.py`, plan generator `sn1_area_plan.py`, helper `sn1_import_helper.py`, run check `sn1_import_check_run.sh`; editor scripts `sn1terrain_import.py` (any `c<i>_<j>_<k>` set), `sn1terrain_state.py` (writes `<Workspace>/sn1_import/state.json`), `sn1terrain_delete_set.py` (spot1 replace).
- `--dry-run "safe shallows"` VERIFIED (2026-11-28, console output): 7 cells, origin imported, 5 new (cm1_0_0, c0_0_m1, c0_0_1, c1_0_m1, c1_0_0), cm2_0_0 blocked by spot1; est 8.0 M triangles, 26 editor min, 1483 MB cooked (6 cells incl. cm2_0_0 about 9.7 M triangles).
- UNTESTED: everything after resolve (extract of new cells, topology gate, seam check, editor import, state.json, cook, in-game plan, idempotent second run). Stopped here because the user ordered a pause (2026-11-28); no extraction, editor, cook or game was run, no lock held. Resume: `SN2_LOCK_OWNER=implementer-area bash src/tools/sn1_import_area.sh "safe shallows" --replace-legacy spot1 --regress` (user asked for the FULL import, all 6 cells), then a second identical run (must print SUMMARY NO-OP), then update this section.

### Import by set, origin cube (2026-11-23)
- (2026-11-28) The import also gives each tile mesh the Habitat Builder ground user data (`sn1terrain_udata.add_ground_udata`, `DA_SandSurfaceData`), otherwise the builder refuses to place on it. One-off for existing tiles: `sn1terrain_ground_udata.py`. VERIFIED in game 2026-11-28, see `research/features/base_building.md` "Base building".
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
1. Extract SN1 terrain: SN1 stores voxel octrees per batch (160 m cubes, a 26×20×26 world). The file format is decoded and the extraction pipeline is planned in `research/sn1/README.md` (2026-11-19).
2. Mesh each batch (marching cubes / dual contouring) → triangles + material ids; decimate; write a chunk file (needs the arbitrary-mesh path, §3).
3. Deliver: stream chunk files around the player into `DynamicMeshActor`s (proven for one 160 m grid chunk in 0.27 s), or cook them as static meshes with the modkit.
4. Clear SN2 underneath (§1) or place the map in open ocean and move the `BP_EdgeOfWorldVolume_C` ring; `BP_Ocean_C.BodySize` = 10 km × 10 km × 1 km.
5. Coordinates: SN1 is Y-up metres, SN2 is Z-up centimetres. Both engines are left-handed. Use **UE (X, Y, Z) = 100 · (unity.z, unity.x, unity.y) + offset**,
   with quaternion UE (X, Y, Z, W) = (q.z, q.x, q.y, q.w) (UNTESTED derivation, `research/sn1/world_files.md` §3). The earlier formula here, (x·100, z·100, y·100), swaps two axes and would mirror the map. It is withdrawn (2026-11-19).
6. **Offset decision (decided 2026-11-22, in-game check pending):** offset (0, 0, 0). The SN1 origin is the `L_SN2World` origin (the lifepod start) and SN1 sea level (y = 0)
   is the SN2 ocean surface (Z = 0). The spot-1 tiles are therefore imported at their absolute UE coordinates (spot UE (21045, -124547, -26733) cm); the tile actors sit at the tile centres.
   Whether the pod ends up where the player should be, and whether the ocean surface lines up, is UNTESTED in game.

## State of play detail (moved from 00_overview.md, 2026-11-28)

| Capability | Status |
|---|---|
| One-call arbitrary mesh (`AppendBuffersToMesh`) for non-grid meshes (caves, overhangs) | FAILED from Lua (out-param error); **works from editor Python** 2026-11-16 → saved Nanite static mesh asset, see `research/terrain/README.md` |
| Cooked terrain mod (`SN2Terrain`: ModActor + SM_SeafloorTest, built by editor Python, packaged as pak chunk 1 in `LogicMods`) appearing in game | **VERIFIED 2026-11-16** — visible at the Lua test spot + collision (the tester); region still cleared by Lua |
| Never loading SN2 terrain at all (RAM requirement) | UNTESTED — design notes in `research/terrain/README.md` |
| SN1 terrain import into L_SN2World (`src/modkit/scripts/sn1terrain_import.py`, 16 Nanite StaticMeshActors tagged `SN1Terrain`, winding `a,d,b`) | **VERIFIED 2026-11-22 (editor):** reload + line trace hit the seabed; cooked + installed (pak contains the 16 `SM_spot1_tile_*` assets, read from the IoStore listing). See `research/terrain/legacy_lua.md` §3 |

## Next steps history (moved from 00_overview.md, 2026-11-28)

0a8. **(2026-11-28) PAUSED by the user order: SN1 area import tooling** (`src/tools/sn1_import_area.sh`, skill `import-area`, see `research/terrain/import.md` "Import an area"). Built and dry-run VERIFIED; the real import (6 Safe Shallows cells, full, with `--replace-legacy spot1`) is UNTESTED. Resume when the user says so.

0a3. **(2026-11-23) Terrain holes FIXED, VERIFIED in game 2026-11-23: root cause = non-manifold edges (1,445 four-triangle edges) dropped by the DynamicMesh at import; extractor `make_manifold` fix re-extracted (0 bad edges), imported (`lost 0`), cooked; the three reported spots show no holes (autotest `holes_recheck`, run `<Workspace>/autotest/20261123_190031_holes_recheck`).** The tile render-settings dump found nothing explaining the user's 'map disappeared' report (all settings default, see `research/terrain/README.md`); that report stays open (candidates UNTESTED: Nanite/GPU memory, camera). **Story-goal burst ruled out as the trigger in an autotest (VERIFIED 2026-11-23, screenshots, run `<Workspace>/autotest/20261123_191841_vanish_proof`): the natural burst fired at t=296 s and the origin terrain stayed visible before, at and 200 s after it.** Cause of the user's vanish still UNKNOWN (differs from the autotest in play length, real input, or other state). The `terraincensus` verb was broken in that run (matched actor names `StaticMeshActor_N`, not mesh names); fixed but UNTESTED. Cube-edge clipping dropped (user decision 2026-11-23). Next: texture streaks. Details in `research/sn1/README.md`.

3. Subnautica 1 terrain (2026-11-22: first 500 m cube extracted, imported, cooked; NOT yet visible in game). Next steps:
   1. The SN1Terrain actors render and are visible from the open-water point (run `spot1_vis`). Open items:
      - (a) Water look in L_SN2World: SOLVED 2026-11-27 (VERIFIED, run `20261127_211152_uwconfirm_sn2`), recipe in `research/sn2/l_sn2world_water.md` "Region water volume in L_SN2World: SOLVED". Remaining: the per-run haze variation (weather: L_SN2World started with DA_CloudyB, L_Main with DA_CloudyA; UNTESTED) and the SN1 box local looks (boxes are volType 0, no effect yet). Target (user, 2026-11-23): clear, blue water; fog deferred to later.
      - (b) Check whether the SN1 arch and tower at spot 1 are voxel terrain or placed rock prefabs (SN1Inspector `near` in that direction, plus a raycast against the extracted mesh). Only voxel terrain is extracted so far.
      - (c) Test-only `o2fill` (exact `Oxygen` attribute write) is UNTESTED, because the first version only toggled the oxygen cheat.
   2. Close the 251 open edges, add an SN1 material table (per-voxel type to SN2 material), and decide whether to reproduce SN1 `Relax` smoothing (`research/sn1/README.md`).
   (2026-11-23: a second cube around the origin/lifepod is done and visible, see the State of play row. `sn1terrain_import.py` now takes a set name via `<Workspace>/sn1_import_set.txt`; the next cube only needs a new `SETS` entry and extract run.)
   3. Scale the extractor beyond one cube: per-batch streaming, low RAM, under the heavy lock.
   4. (2026-11-19, needed for the first-launch builder, `research/sn1/first_launch_builder.md` §10) Prove runtime `BuildFromStaticMeshDescriptions` from a minimal UE4SS C++ mod: one mesh, visible, with collision.

4. Streaming design for many chunks + the "never load SN2 terrain" RAM requirement (project requirement: the finished mod must not keep hidden SN2 map in RAM).
