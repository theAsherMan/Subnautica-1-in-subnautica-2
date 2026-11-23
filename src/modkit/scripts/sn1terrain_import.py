"""Runs INSIDE the Unreal editor (Python). Imports the extracted Subnautica 1 terrain tiles (OBJ, UE axes, cm, absolute) into the SN2 replacement
map /Game/Mods/SN2EmptyWorld/L_SN2World as cooked static meshes with collision.

  * input   : <Workspace>/sn1_extract/spot1/tile_<i>_<k>.obj  (SN1_TILE_DIR env var overrides the folder; SN2_WORKSPACE env var gives <Workspace>)
  * assets  : /Game/Mods/SN2EmptyWorld/SN1Terrain/SM_spot1_tile_<i>_<k>   (vertices recentred on the tile bounds centre; Nanite on; complex-as-simple collision)
  * actors  : one StaticMeshActor per tile in L_SN2World, tag "SN1Terrain", outliner folder "SN1Terrain", located at the tile bounds centre
  * normals : recomputed (angle + area weighted, smooth); UVs: planar world-space (X,Y)/100 cm
  * material: one SN2 material for every tile (MATERIAL below; research/03 section 3)
  * the OBJ winding is used AS IS (VERIFIED seabed normals +Z under UE's convention, see the self-check; do not flip)
Idempotent: deletes the actors already tagged SN1Terrain and overwrites the assets. Safe to re-run. MUST be re-run after a rebuild of L_SN2World
(sn2world_map.py creates a fresh level without these actors).
Self-check at the end: reload the level from disk, assert 16 tagged actors at the expected locations, assert collision complex-as-simple, line trace
straight down from spot + 3 m.
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn1terrain_import.py        Output lines start with [SN1Terrain].
"""
import glob
import math
import os
import re
import time
import unreal

MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"
ASSET_DIR = "/Game/Mods/SN2EmptyWorld/SN1Terrain"
TAG = "SN1Terrain"
FOLDER = "SN1Terrain"
EXPECTED_TILES = 16
SPOT = (21045.0, -124547.0, -26733.0)          # SN1 spot centre in UE cm (map offset 0,0,0)
MATERIAL = "/Game/Art/Environment/Biome/CoralGarden/Rocks/Material/MI_CG_RockSmooth_01a_Triplanar"
UV_CM = 100.0

def _workspace():
    """SN2_WORKSPACE from the environment, else from <RepoDir>/local.config (git-ignored)."""
    w = os.environ.get("SN2_WORKSPACE")
    if w:
        return w
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with open(os.path.join(repo, "local.config"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("SN2_WORKSPACE="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("SN2_WORKSPACE not set and not in local.config")


WORKSPACE = _workspace()
TILE_DIR = os.environ.get("SN1_TILE_DIR", os.path.join(WORKSPACE, "sn1_extract", "spot1"))

T0 = time.time()
eal = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def log(m):
    unreal.log(f"[SN1Terrain] {m}")


def die(m):
    unreal.log_error(f"[SN1Terrain] STOP: {m}")
    raise RuntimeError(m)


def setp(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:  # noqa: BLE001
        unreal.log_warning(f"[SN1Terrain] set {type(obj).__name__}.{name} failed: {e}")
        return False


def parse_obj(path):
    """stdlib-only OBJ parse -> (verts [(x,y,z)], tris [(a,b,c)] 0-based, material-group counts)"""
    verts, tris, groups, cur = [], [], {}, None
    with open(path, encoding="ascii") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
                for j in range(1, len(idx) - 1):
                    tris.append((idx[0], idx[j], idx[j + 1]))
                    groups[cur] = groups.get(cur, 0) + 1
            elif line.startswith("usemtl"):
                cur = line.split()[1]
    return verts, tris, groups


def tile_files():
    out = []
    for f in glob.glob(os.path.join(TILE_DIR, "tile_*_*.obj")):
        m = re.match(r"tile_(\d+)_(\d+)\.obj$", os.path.basename(f))
        if m:
            out.append((int(m.group(1)), int(m.group(2)), f))
    return sorted(out)


def first(res):
    return res[0] if isinstance(res, tuple) else res


# ---------- 0. level ----------
files = tile_files()
if len(files) != EXPECTED_TILES:
    die(f"expected {EXPECTED_TILES} tile OBJs in {TILE_DIR}, found {len(files)}")
ok = unreal.EditorLoadingAndSavingUtils.load_map(MAP)
log(f"load_map({MAP}) -> {ok}")
if not ok:
    die("could not load L_SN2World")
old = [a for a in eas.get_all_level_actors() if a.actor_has_tag(TAG)]
for a in old:
    eas.destroy_actor(a)
log(f"deleted {len(old)} existing {TAG} actors")

mat = eal.load_asset(MATERIAL)
if not mat:
    die(f"material {MATERIAL} not found")
try:
    parent = mat.get_editor_property("parent")
    log(f"material {mat.get_path_name()} ({type(mat).__name__}) parent = {parent.get_path_name() if parent else None}")
except Exception:  # noqa: BLE001
    log(f"material {mat.get_path_name()} ({type(mat).__name__})")

# ---------- 1. build assets + actors ----------
expected = {}      # actor label -> expected centre
best_spot = [1e30, None, None]    # (dist, dm, tri id) closest triangle below the spot, for the normal check
tri_total = 0
for (ti, tk, path) in files:
    t1 = time.time()
    name = f"SM_spot1_tile_{ti}_{tk}"
    asset_path = f"{ASSET_DIR}/{name}"
    verts, tris, groups = parse_obj(path)
    if not verts or not tris:
        die(f"{path}: empty")
    mn = [min(v[i] for v in verts) for i in range(3)]
    mx = [max(v[i] for v in verts) for i in range(3)]
    c = [(mn[i] + mx[i]) / 2 for i in range(3)]
    vecs = [unreal.Vector(v[0] - c[0], v[1] - c[1], v[2] - c[2]) for v in verts]
    uvs = [unreal.Vector2D(v[0] / UV_CM, v[1] / UV_CM) for v in verts]
    buf = unreal.GeometryScriptSimpleMeshBuffers()
    buf.set_editor_property("vertices", vecs)
    buf.set_editor_property("uv0", uvs)
    buf.set_editor_property("triangles", [unreal.IntVector(a, d, b) for (a, b, d) in tris])
    dm = unreal.DynamicMesh()
    unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(dm, buf, 0, False)
    nt = unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm)
    if nt != len(tris):
        log(f"  note: dynamic mesh has {nt} triangles, OBJ {len(tris)} (degenerate/duplicate dropped by the mesh)")
    nopt = unreal.GeometryScriptCalculateNormalsOptions()
    setp(nopt, "area_weighted", True)
    setp(nopt, "angle_weighted", True)
    unreal.GeometryScript_Normals.recompute_normals(dm, nopt)
    t2 = time.time()

    # normal check: mean face-normal Z over a sample + the face normal of the triangle (by CPU centroid) just below the spot
    step = max(1, len(tris) // 300)
    sz, n = 0.0, 0
    for k in range(0, len(tris), step):
        fnv = first(unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, k))
        sz += fnv.z
        n += 1
    log(f"  {name}: sampled mean face-normal Z = {sz / n:.3f} over {n} triangles")
    for k in range(0, len(tris), 1):
        a, b, d = tris[k]
        cx = (verts[a][0] + verts[b][0] + verts[d][0]) / 3
        cy = (verts[a][1] + verts[b][1] + verts[d][1]) / 3
        cz = (verts[a][2] + verts[b][2] + verts[d][2]) / 3
        if cz > SPOT[2] + 300:
            continue
        dist = math.hypot(cx - SPOT[0], cy - SPOT[1])
        if dist < best_spot[0]:
            best_spot[:] = [dist, name, (cx, cy, cz, first(unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, k)))]

    if eal.does_asset_exist(asset_path):
        eal.delete_asset(asset_path)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    setp(opts, "enable_nanite", True)
    setp(opts, "enable_collision", True)
    setp(opts, "collision_mode", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    setp(opts, "enable_recompute_normals", False)
    setp(opts, "enable_recompute_tangents", True)
    out = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, asset_path, opts)
    mesh = eal.load_asset(asset_path)
    if not mesh:
        die(f"{asset_path} not created ({out})")
    mesh.set_material(0, mat)
    bs = mesh.get_editor_property("body_setup")
    if bs:
        setp(bs, "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    nan = mesh.get_editor_property("nanite_settings")
    setp(nan, "enabled", True)
    setp(nan, "fallback_target", unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
    setp(nan, "fallback_percent_triangles", 1.0)
    setp(mesh, "nanite_settings", nan)
    eal.save_asset(asset_path, only_if_is_dirty=False)

    actor = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(c[0], c[1], c[2]))
    actor.set_actor_label(name)
    actor.tags = [unreal.Name(TAG)]
    actor.set_folder_path(FOLDER)
    actor.static_mesh_component.set_static_mesh(mesh)
    expected[name] = tuple(c)
    tri_total += nt
    log(f"{name}: verts {len(verts)} tris {nt} groups {groups} centre ({c[0]:.1f},{c[1]:.1f},{c[2]:.1f}) "
        f"size ({mx[0] - mn[0]:.0f},{mx[1] - mn[1]:.0f},{mx[2] - mn[2]:.0f}) | parse+buf+normals {t2 - t1:.1f} s, asset+actor {time.time() - t2:.1f} s")

log(f"built {len(expected)} tiles, {tri_total} triangles in {time.time() - T0:.1f} s")
if best_spot[1]:
    d, nm, (cx, cy, cz, fnv) = best_spot
    log(f"NORMAL CHECK: triangle nearest below the spot is in {nm} at ({cx:.0f},{cy:.0f},{cz:.0f}) {d:.0f} cm from the spot XY; "
        f"GeometryScript face normal = ({fnv.x:.3f},{fnv.y:.3f},{fnv.z:.3f})  {'OK (Z>0)' if fnv.z > 0 else 'FAIL (Z<=0)'}")

# ---------- 2. save ----------
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
log(f"save_current_level -> {les.save_current_level()}")
log(f"save_dirty_packages -> {unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)}")

# ---------- 3. self-check on a fresh load from disk ----------
unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
if not unreal.EditorLoadingAndSavingUtils.load_map(MAP):
    die("reload failed")
got = [a for a in eas.get_all_level_actors() if a.actor_has_tag(TAG)]
log(f"after reload: {len(got)} actors tagged {TAG}")
assert len(got) == EXPECTED_TILES, f"expected {EXPECTED_TILES} tagged actors, found {len(got)}"
for a in got:
    lab = a.get_actor_label()
    e = expected[lab]
    l = a.get_actor_location()
    assert max(abs(l.x - e[0]), abs(l.y - e[1]), abs(l.z - e[2])) < 1.0, f"{lab} at ({l.x},{l.y},{l.z}) expected {e}"
    comp = a.static_mesh_component
    sm = comp.static_mesh
    assert sm is not None and sm.get_name() == lab, f"{lab}: mesh {sm}"
    flag = sm.get_editor_property("body_setup").get_editor_property("collision_trace_flag")
    assert flag == unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE, f"{lab}: collision {flag}"
    assert a.get_editor_property("tags")[0] == TAG, lab
    assert str(a.get_folder_path()) == FOLDER, f"{lab}: folder {a.get_folder_path()}"
    nanite = sm.get_editor_property("nanite_settings").get_editor_property("enabled")
    log(f"  ok {lab}: loc ({l.x:.1f},{l.y:.1f},{l.z:.1f}) complex-as-simple nanite={nanite} folder={a.get_folder_path()} "
        f"material={comp.get_material(0).get_name() if comp.get_material(0) else None}")
log("RELOAD CHECK PASSED: 16 actors, locations, complex-as-simple collision")

world = ues.get_editor_world()
start = unreal.Vector(SPOT[0], SPOT[1], SPOT[2] + 300.0)
end = unreal.Vector(SPOT[0], SPOT[1], SPOT[2] - 3000.0)
ignore = []
result = None
for attempt in range(6):
    try:
        res = None
        for chan in (unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, unreal.TraceTypeQuery.TRACE_TYPE_QUERY2):
            res = unreal.SystemLibrary.line_trace_single(world, start, end, chan, True, ignore,
                                                         unreal.DrawDebugTrace.NONE, True)
            log(f"  trace channel {chan}: res={res!r}")
            if res is not None:
                break
    except Exception as e:  # noqa: BLE001
        log(f"TRACE call failed: {e!r}")
        break
    hit = res[-1] if isinstance(res, tuple) else res
    if hit is None or (isinstance(res, tuple) and len(res) == 2 and res[0] is False):
        log(f"TRACE attempt {attempt}: no hit (res={res!r})")
        break
    # Python HitResult exposes no editor properties; use to_tuple()
    # (blocking_hit, initial_overlap, time, distance, location, impact_point, normal, impact_normal, phys_mat, hit_actor, ...)
    tp = hit.to_tuple()
    log(f"  hit tuple: {[str(x)[:60] for x in tp]}")
    act = tp[9]
    loc = tp[5]
    nrm = tp[7]
    dist = start.z - loc.z
    lab = act.get_actor_label() if act else "?"
    log(f"TRACE attempt {attempt}: hit '{lab}' ({act.get_class().get_name() if act else '?'}) at ({loc.x:.0f},{loc.y:.0f},{loc.z:.0f}) "
        f"distance from spot+3m = {dist / 100:.2f} m, impact normal ({nrm.x:.3f},{nrm.y:.3f},{nrm.z:.3f})")
    if act and act.actor_has_tag(TAG):
        result = (dist, lab, nrm.z)
        break
    if not act:
        break
    ignore.append(act)
if result:
    log(f"TRACE RESULT: hit SN1Terrain actor {result[1]} {result[0] / 100:.2f} m below spot+3m (so {(result[0] - 300) / 100:.2f} m below the spot), normal Z {result[2]:.3f}")
else:
    log("TRACE RESULT: NO SN1Terrain hit")
log(f"DONE in {time.time() - T0:.1f} s")
