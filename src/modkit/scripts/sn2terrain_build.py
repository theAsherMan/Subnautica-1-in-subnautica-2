"""Runs INSIDE the Unreal editor (Python). Builds the SN2Terrain test mod:
  1. creates /Game/Mods/SN2Terrain/{ModActor, PAL_SN2Terrain} if missing (same as SN2 Mod Tools "New mod...")
  2. builds a static mesh from the Lua test heightfield (same data as SN2TerrainEdit/data/seafloor_test.txt)
     via Geometry Script AppendBuffersToMesh (arbitrary triangle buffers) -> Nanite + complex-as-simple collision
  3. assigns the game's rock material (from SM_CG_RockRubble_BoulderMed_6a, as the Lua test did)
  4. adds/updates a StaticMeshComponent "Seafloor" on ModActor at the Lua test position
Safe to re-run: replaces the mesh asset and updates the component.
Run from the repo root:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2terrain_build.py
or type  py "<RepoDir>/src/modkit/scripts/sn2terrain_build.py"  in the editor's Cmd box.
All output lines start with [SN2Terrain].
"""
import os
import time
import unreal

MOD = "SN2Terrain"
MOD_DIR = f"/Game/Mods/{MOD}"
MESH_PATH = f"{MOD_DIR}/SM_SeafloorTest"
# repo root from this file's location (src/modkit/scripts/), or SN2_REPO (set by src/modkit/Launch-Editor.cmd)
try:
    REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
except NameError:
    REPO = os.environ["SN2_REPO"]
HEIGHTFIELD = os.path.join(REPO, "src", "mods", "SN2TerrainEdit", "data", "seafloor_test.txt")
TARGET = unreal.Vector(-331747.0, 420670.0, -6224.0)   # Lua test position (old landscape mean height)
ROCK_MESH = "/Game/Art/Environment/Biome/CoralGarden/Rocks/SM_CG_RockRubble_BoulderMed_6a.SM_CG_RockRubble_BoulderMed_6a"
UV_METRES = 4.0

T0 = time.time()


def log(msg):
    unreal.log(f"[SN2Terrain] {msg}")


def warn(msg):
    unreal.log_warning(f"[SN2Terrain] {msg}")


def setp(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:  # noqa: BLE001
        warn(f"set {type(obj).__name__}.{name} failed: {e}")
        return False


eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


# ---------- 1. mod scaffold ----------
def used_chunk_ids():
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    ids = set()
    for ad in ar.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "PrimaryAssetLabel")):
        try:
            lab = ad.get_asset()
            cid = lab.get_editor_property("rules").get_editor_property("chunk_id")
            if cid > 0:
                ids.add(cid)
        except Exception:  # noqa: BLE001
            pass
    return ids


def ensure_mod():
    bp_path = f"{MOD_DIR}/ModActor"
    if not eal.does_asset_exist(bp_path):
        f = unreal.BlueprintFactory()
        f.set_editor_property("parent_class", unreal.Actor)
        tools.create_asset("ModActor", MOD_DIR, unreal.Blueprint, f)
        log(f"created {bp_path}")
    pal_path = f"{MOD_DIR}/PAL_{MOD}"
    if not eal.does_asset_exist(pal_path):
        used = used_chunk_ids()
        cid = next(i for i in range(1, 301) if i not in used)
        f = unreal.DataAssetFactory()
        f.set_editor_property("data_asset_class", unreal.PrimaryAssetLabel)
        lab = tools.create_asset(f"PAL_{MOD}", MOD_DIR, unreal.PrimaryAssetLabel, f)
        rules = lab.get_editor_property("rules")
        rules.set_editor_property("chunk_id", cid)
        rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
        lab.set_editor_property("rules", rules)
        setp(lab, "label_assets_in_my_directory", True)
        eal.save_asset(pal_path, only_if_is_dirty=False)
        log(f"created {pal_path} chunk_id={cid} (used before: {sorted(used)})")
    lab = eal.load_asset(pal_path)
    r = lab.get_editor_property("rules")
    log(f"PAL chunk_id={r.get_editor_property('chunk_id')} cook_rule={r.get_editor_property('cook_rule')}")
    return eal.load_asset(bp_path)


# ---------- 2. mesh ----------
def read_heightfield(path):
    with open(path, encoding="ascii") as fh:
        n, sp = fh.readline().split()
        n, sp = int(n), float(sp)
        h = [float(x) for x in fh.read().split()]
    assert len(h) == n * n, (len(h), n)
    return n, sp, h


def build_mesh():
    n, sp, h = read_heightfield(HEIGHTFIELD)
    half = (n - 1) * sp / 2
    buf = unreal.GeometryScriptSimpleMeshBuffers()
    verts, uvs, tris = [], [], []
    for j in range(n):
        for i in range(n):
            verts.append(unreal.Vector(i * sp - half, j * sp - half, h[j * n + i]))
            uvs.append(unreal.Vector2D(i * sp / (UV_METRES * 100), j * sp / (UV_METRES * 100)))
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            b, c, d = a + 1, a + n, a + n + 1
            tris.append(unreal.IntVector(a, b, d))
            tris.append(unreal.IntVector(a, d, c))
    buf.set_editor_property("vertices", verts)
    buf.set_editor_property("uv0", uvs)
    buf.set_editor_property("triangles", tris)
    t1 = time.time()

    dm = unreal.DynamicMesh()
    res = unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(dm, buf, 0, False)
    log(f"AppendBuffersToMesh returned {type(res).__name__}; vertices={len(verts)} triangles={len(tris)}")
    tc = unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm)
    log(f"dynamic mesh triangle count = {tc}")

    # make sure faces point up (+Z); flip if the winding came out reversed
    fn = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0)
    nrm = fn[0] if isinstance(fn, tuple) else fn
    log(f"triangle 0 face normal = ({nrm.x:.3f}, {nrm.y:.3f}, {nrm.z:.3f})")
    if nrm.z < 0:
        unreal.GeometryScript_Normals.flip_normals(dm)
        log("winding reversed -> FlipNormals applied")
    unreal.GeometryScript_Normals.recompute_normals(dm, unreal.GeometryScriptCalculateNormalsOptions())
    t2 = time.time()

    if eal.does_asset_exist(MESH_PATH):
        eal.delete_asset(MESH_PATH)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    setp(opts, "enable_nanite", True)
    setp(opts, "enable_collision", True)
    setp(opts, "collision_mode", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    setp(opts, "enable_recompute_normals", False)
    setp(opts, "enable_recompute_tangents", True)
    out = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, MESH_PATH, opts)
    log(f"CreateNewStaticMeshAssetFromMesh returned {out}")
    mesh = eal.load_asset(MESH_PATH)
    if not mesh:
        raise RuntimeError("static mesh asset was not created")

    rock = eal.load_asset(ROCK_MESH)
    mat = rock.get_material(0) if rock else None
    if mat:
        mesh.set_material(0, mat)
        log(f"material = {mat.get_path_name()}")
    else:
        warn(f"could not load rock material from {ROCK_MESH}")
    bs = mesh.get_editor_property("body_setup")
    if bs:
        setp(bs, "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    # CreateNewStaticMeshAssetFromMesh's enable_nanite did not stick (2026-11-16) -> set NaniteSettings directly.
    # Fallback at 100 % so the non-Nanite LOD0 (also used for complex collision, LODForCollision=0) keeps full detail.
    nan = mesh.get_editor_property("nanite_settings")
    setp(nan, "enabled", True)
    setp(nan, "fallback_target", unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
    setp(nan, "fallback_percent_triangles", 1.0)
    setp(mesh, "nanite_settings", nan)
    nan = mesh.get_editor_property("nanite_settings")
    log(f"nanite enabled = {nan.get_editor_property('enabled')}; collision = {bs.get_editor_property('collision_trace_flag') if bs else None}")
    b = mesh.get_bounds()
    log(f"bounds origin=({b.origin.x:.0f},{b.origin.y:.0f},{b.origin.z:.0f}) extent=({b.box_extent.x:.0f},{b.box_extent.y:.0f},{b.box_extent.z:.0f})")
    eal.save_asset(MESH_PATH, only_if_is_dirty=False)
    log(f"mesh saved {MESH_PATH} | buffers {1000*(t1-T0):.0f} ms, dynmesh {1000*(t2-t1):.0f} ms, asset {1000*(time.time()-t2):.0f} ms")
    return mesh


# ---------- 3. ModActor component ----------
def place_on_modactor(bp, mesh):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    root_h, comp = None, None
    for hd in handles:
        obj = lib.get_object(lib.get_data(hd))
        if obj is None:
            continue
        name = obj.get_name()
        if isinstance(obj, unreal.StaticMeshComponent) and name.startswith("Seafloor"):
            comp = obj
        elif isinstance(obj, unreal.SceneComponent) and root_h is None:
            root_h = hd
    if root_h is None:
        root_h = handles[0]
    if comp is None:
        params = unreal.AddNewSubobjectParams(parent_handle=root_h, new_class=unreal.StaticMeshComponent, blueprint_context=bp)
        new_h, fail = sds.add_new_subobject(params)
        if not fail.is_empty():
            raise RuntimeError(f"add_new_subobject failed: {fail}")
        sds.rename_subobject(new_h, unreal.Text("Seafloor"))
        comp = lib.get_object(lib.get_data(new_h))
        log("added StaticMeshComponent 'Seafloor' to ModActor")
    setp(comp, "static_mesh", mesh)
    setp(comp, "relative_location", TARGET)
    setp(comp, "mobility", unreal.ComponentMobility.MOVABLE)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    eal.save_asset(bp.get_path_name(), only_if_is_dirty=False)
    loc = comp.get_editor_property("relative_location")
    log(f"ModActor saved: Seafloor mesh={comp.get_editor_property('static_mesh').get_name()} at ({loc.x:.0f},{loc.y:.0f},{loc.z:.0f})")


try:
    bp = ensure_mod()
    m = build_mesh()
    place_on_modactor(bp, m)
    log(f"DONE in {time.time() - T0:.1f} s")
except Exception as e:  # noqa: BLE001
    import traceback
    unreal.log_error("[SN2Terrain] FAILED: " + repr(e) + "\n" + traceback.format_exc())
