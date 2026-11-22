"""Runs INSIDE the Unreal editor. Builds /Game/Mods/SN2EmptyWorld/L_SN2World: a NON-World-Partition level holding the kept objects of L_Main
(lifepod set, sky, water zone, managers, PlayerStarts) copied with the editor's copy/paste (Method 1, keeps instance-edited properties).
L_Main is opened read-only and never saved.

Findings baked into this script (2026-11-18, see research/09 "Replacement map L_SN2World"):
 * BP_Ocean_C is copied like every other actor (instance values kept: CollisionExtents 816,000 x 816,000 x 5,000,000). Saving it fails with
   "Illegal reference to private object ... Default__BP_Ocean_C:OceanCollisionBoxComponent_1 ... CollisionBoxes" because the WaterBodyOceanComponent's
   CollisionBoxes array points at the CDO's subobject. Fix (step 2 of the 2026-11-18 work): after the paste, clear CollisionBoxes and CollisionHullSets via
   unreal.SN2GraphLibrary.clear_object_array and call notify_property_changed(comp, "CollisionExtents") so the water body rebuilds its own collision.
   BP_UWEOceanBiomeRegionActor_C is the ocean's child actor and is NOT copied (the ChildActorComponent recreates it).
   If the save still fails, put "BP_Ocean_C" back into RUNTIME_SPAWNED (ModActor then spawns it; every far actor is shifted so the pod is at the origin).
 * Every root actor farther than FAR from the origin is SHIFTED so the lifepod lands at the origin (kept from the earlier design).
 * BP_LifePod_Lighting_Surface_C and BP_LifepodWallLocker_C have no attach parent in the editor world but are attached to the lifepod at runtime in L_Main
   (values relative to the pod) -> attached here with KEEP_RELATIVE.
 * 2026-11-19 water fix (research/09 "Root cause of the zero water volume"): the modkit's ocean C++ is a stub, so BP_Ocean_C's construction script bakes the
   water volume (its ChildActorComponent region) to scale 0 in the COOK. The map therefore also holds (a) a STANDALONE BP_UWEOceanBiomeRegionActor_C
   (step 4e: spawned, because EDIT COPY/PASTE skips child actors; transform = our ocean actor + L_Main's offset (0,0,-5e6), scale (1e6,1e6,1e5);
   every property that differs from the class default is copied from L_Main's child actor) and (b) the origin BP_BoxVolume_C air volume
   ("BP_AirVolumeAboveOcean", scale 1e5). check_region() asserts both, in memory and after a reload from disk.
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2world_map.py       Output lines start with [SN2World].
"""
import time
import unreal

SRC_MAP = "/Game/Maps/Main/L_Main"
NEW_MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"
KEEP = [
    "BP_Ocean_C", "BP_UWEOceanBiomeRegionActor_C", "WaterZone", "BP_UWESky_C", "BP_StaticLifepod_Surface_C",
    "BP_LifePod_Lighting_Surface_C", "BP_LifepodManager_C", "BP_BioBed_Lifepod_C", "BP_Fabricator_Lifepod_C",
    "BP_LifepodWallLocker_C", "BP_ComputerTextInterface_Terminal_Mini_Lifepod_C", "BP_BaseRuntimeManager_C",
    "BP_MPC_ScalabilityLinker_C", "BP_MeshBlend_Activator_C", "BP_ShallowsPlayerStart_C", "BP_LifepodPlayerStart_C",
    "BP_CreativeModePlayerStart_C",
    "BP_BoxVolume_C",   # ONLY the origin one ("BP_AirVolumeAboveOcean", Air, priority 10, scale 100000); see keep_source()
]
REGION_CLS = "BP_UWEOceanBiomeRegionActor_C"   # copied from L_Main as a STANDALONE actor (see 2026-11-19 fix below)
RUNTIME_SPAWNED = ()   # classes NOT saved in the level (spawned by the ModActor); fallback: ("BP_Ocean_C",)
NOT_COPIED = (REGION_CLS,)   # EDIT COPY/PASTE skips child actors (VERIFIED 2026-11-19: 0 standalone after pasting it); the standalone region is spawned in step 4e
POD_CHILDREN = {   # runtime-attached to the pod in L_Main; expected WORLD transforms after the shift (loc cm, yaw deg)
    "BP_LifePod_Lighting_Surface_C": ((0.0, 0.0, 100.0), 52.44),
    "BP_LifepodWallLocker_C": ((31.90, -228.87, 300.0), 97.44),
}
FAR = 100000.0


def log(m):
    unreal.log(f"[SN2World] {m}")


def die(m):
    unreal.log_error(f"[SN2World] STOP: {m}")
    raise RuntimeError(m)


eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

# ---------- 1. open L_Main ----------
t0 = time.time()
ok = unreal.EditorLoadingAndSavingUtils.load_map(SRC_MAP)
log(f"load_map({SRC_MAP}) -> {ok} in {time.time() - t0:.1f} s")
if not ok:
    die("could not load L_Main")
if unreal.EditorAssetLibrary.does_asset_exist(NEW_MAP):
    log(f"removing stale {NEW_MAP}: {unreal.EditorAssetLibrary.delete_asset(NEW_MAP)}")   # new_level refuses to overwrite
all_actors = eas.get_all_level_actors()
log(f"L_Main level actors: {len(all_actors)}")

# ---------- 2. source actors ----------
def keep_source(a, cn, l):
    """BP_BoxVolume_C: only the origin air volume (L_Main has 3; the other two sit near (-326673,574924))."""
    if cn == "BP_BoxVolume_C":
        return (l.x ** 2 + l.y ** 2) ** 0.5 < 1000.0 and abs(l.z) < 1000.0
    return True


def comp_rows(actor):
    """[(name, class, world loc, world scale, rel loc, rel scale)] of the SceneComponents of an actor."""
    rows = []
    for c in actor.get_components_by_class(unreal.SceneComponent):
        wl, ws, rl, rs = c.get_world_location(), c.get_world_scale(), c.relative_location, c.relative_scale3d
        rows.append((c.get_name(), c.get_class().get_name(), (wl.x, wl.y, wl.z), (ws.x, ws.y, ws.z), (rl.x, rl.y, rl.z), (rs.x, rs.y, rs.z)))
    return rows


SNAP_SKIP = {   # per-instance / hierarchy / transform properties that must NOT be copied from L_Main's child actor
    "relative_location", "relative_rotation", "relative_scale3d", "attach_parent", "attach_children", "attach_socket_name", "owner",
    "root_component", "children", "parent_component", "attached_parent", "net_owner", "instigator", "relative_transform",
    "component_to_world", "creation_method", "ucs_serialization_index", "child_actor_template", "child_actor",
    "relative_translation", "cached_max_draw_distance", "tags",   # alias of relative_location / derived value (set refused) / list compare noise
}
import re as _re


def _norm(v):
    """Comparable text of a property value (no object addresses)."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return repr(v)
    if isinstance(v, unreal.Object):
        return "OBJ:" + v.get_path_name()
    try:
        if isinstance(v, (list, tuple)) or hasattr(v, "__len__") and not hasattr(v, "get_editor_property"):
            return "[" + ",".join(_norm(x) for x in v) + "]"
    except Exception:
        pass
    return _re.sub(r"0x[0-9A-Fa-f]+", "0x", str(v))


def _props(o):
    """{name: (normalised text, value to re-apply)} of every readable editor property of o. Level-instance object references are skipped
    (they point into L_Main); asset references are kept as their path (re-loaded on apply)."""
    out = {}
    for n in dir(o):
        if n.startswith("_") or n in SNAP_SKIP:
            continue
        try:
            v = o.get_editor_property(n)
        except Exception:
            continue
        if isinstance(v, unreal.Object):
            p = v.get_path_name()
            if "PersistentLevel" in p or isinstance(v, (unreal.Actor, unreal.ActorComponent)):
                continue
            out[n] = (_norm(v), ("PATH", p))
        else:
            try:
                val = v.copy() if hasattr(v, "copy") else v
            except Exception:
                val = v
            out[n] = (_norm(v), ("VAL", val))
    return out


def snapshot(actor):
    snap = {None: _props(actor)}
    for c in actor.get_components_by_class(unreal.ActorComponent):
        snap[c.get_name()] = _props(c)
    return snap


def apply_snapshot(snap, actor, tag):
    """Sets every property of the new actor/components whose value differs from the L_Main snapshot. Returns (n differences, n set, n failed)."""
    comps = {c.get_name(): c for c in actor.get_components_by_class(unreal.ActorComponent)}
    ndiff = nset = nfail = 0
    for key, props in snap.items():
        obj = actor if key is None else comps.get(key)
        if obj is None:
            log(f"  [{tag}] component {key} missing on the new actor")
            nfail += 1
            continue
        for n, (txt, (kind, payload)) in props.items():
            try:
                cur = obj.get_editor_property(n)
            except Exception:
                continue
            if _norm(cur) == txt:
                continue
            ndiff += 1
            try:
                val = unreal.load_object(None, payload) if kind == "PATH" else payload
                obj.set_editor_property(n, val)
                nset += 1
                log(f"  [{tag}] {key or 'ACTOR'}.{n}: {_norm(cur)[:90]} -> {txt[:90]}")
            except Exception as ex:
                nfail += 1
                log(f"  [{tag}] {key or 'ACTOR'}.{n}: set FAILED ({str(ex)[:100]}); was {_norm(cur)[:60]} want {txt[:60]}")
    return ndiff, nset, nfail


src, counts = [], {k: 0 for k in KEEP}
MAIN = {}   # L_Main reference values captured before the new level replaces it (2026-11-19)
for a in all_actors:
    cn = a.get_class().get_name()
    if cn in counts and keep_source(a, cn, a.get_actor_location()):
        counts[cn] += 1
        l, r = a.get_actor_location(), a.get_actor_rotation()
        par = a.get_attach_parent_actor()
        src.append(dict(obj=a, cls=cn, name=a.get_name(), loc=(l.x, l.y, l.z), rot=(r.pitch, r.yaw, r.roll),
                        parent=par.get_name() if par else None))
for k in KEEP:
    log(f"source {k}: {counts[k]}")
for e in src:
    log(f"  src {e['cls']} '{e['name']}' loc=({e['loc'][0]:.1f},{e['loc'][1]:.1f},{e['loc'][2]:.1f}) yaw={e['rot'][1]:.2f} parent={e['parent']}")
log(f"source actors total: {len(src)}")
if not src:
    die("no source actors found")
pod = [e for e in src if e["cls"] == "BP_StaticLifepod_Surface_C"][0]
SHIFT = (-pod["loc"][0], -pod["loc"][1], 0.0)
log(f"SHIFT applied to far root actors = {SHIFT}")

# ---------- 2b. L_Main reference values for the standalone water region and the air volume ----------
def one(cls):
    got = [e for e in src if e["cls"] == cls]
    if len(got) != 1:
        die(f"expected exactly 1 source {cls}, found {len(got)}")
    return got[0]["obj"]


m_oc, m_reg, m_air = one("BP_Ocean_C"), one(REGION_CLS), one("BP_BoxVolume_C")
if m_reg.get_attach_parent_actor() != m_oc:
    die("L_Main region actor is not the ocean's child actor")
m_ol, m_or, m_os = m_oc.get_actor_location(), m_oc.get_actor_rotation(), m_oc.get_actor_scale3d()
if max(abs(m_or.pitch), abs(m_or.yaw), abs(m_or.roll)) > 1e-4 or max(abs(m_os.x - 1), abs(m_os.y - 1), abs(m_os.z - 1)) > 1e-6:
    die(f"L_Main ocean actor has rotation/scale ({m_or}, {m_os}); the simple offset composition below does not apply")
m_cac = m_oc.get_components_by_class(unreal.ChildActorComponent)[0]
m_cl, m_cs = m_cac.relative_location, m_cac.relative_scale3d
m_rl, m_rr, m_rs = m_reg.get_actor_location(), m_reg.get_actor_rotation(), m_reg.get_actor_scale3d()
MAIN["ocean_loc"] = (m_ol.x, m_ol.y, m_ol.z)
# the region's transform relative to the ocean actor (ocean has identity rotation/scale, so this is a plain offset + scale)
MAIN["reg_rel_loc"] = (m_rl.x - m_ol.x, m_rl.y - m_ol.y, m_rl.z - m_ol.z)
MAIN["reg_scale"] = (m_rs.x, m_rs.y, m_rs.z)
MAIN["reg_rot"] = (m_rr.pitch, m_rr.yaw, m_rr.roll)
MAIN["reg_comps"] = comp_rows(m_reg)
MAIN["reg_class"] = m_reg.get_class()
MAIN["reg_snap"] = snapshot(m_reg)
log(f"L_Main region property snapshot: {sum(len(v) for v in MAIN['reg_snap'].values())} values in {len(MAIN['reg_snap'])} objects (actor + components)")
MAIN["air_comps"] = comp_rows(m_air)
MAIN["air_loc"] = (m_air.get_actor_location().x, m_air.get_actor_location().y, m_air.get_actor_location().z)
s3 = m_air.get_actor_scale3d()
MAIN["air_scale"] = (s3.x, s3.y, s3.z)
log(f"L_Main ocean actor loc {MAIN['ocean_loc']}; CAC rel loc ({m_cl.x:.0f},{m_cl.y:.0f},{m_cl.z:.0f}) rel scale ({m_cs.x:.0f},{m_cs.y:.0f},{m_cs.z:.0f})")
log(f"L_Main region actor '{m_reg.get_name()}' world loc ({m_rl.x:.0f},{m_rl.y:.0f},{m_rl.z:.0f}) rot {MAIN['reg_rot']} scale {MAIN['reg_scale']} -> offset from ocean {MAIN['reg_rel_loc']}")
for row in MAIN["reg_comps"]:
    log(f"  L_Main region comp {row[0]} ({row[1]}) world loc {row[2]} world scale {row[3]} rel scale {row[5]}")
log(f"L_Main air volume '{m_air.get_name()}' loc {MAIN['air_loc']} scale {MAIN['air_scale']}")
for row in MAIN["air_comps"]:
    log(f"  L_Main air comp {row[0]} ({row[1]}) world loc {row[2]} world scale {row[3]} rel loc {row[4]} rel scale {row[5]}")
# the region transform must be what the CAC would produce (CAC rel loc/scale, parent chain identity): cross-check, so a wrong reading cannot slip through
if abs(MAIN["reg_rel_loc"][2] - m_cl.z) > 1.0 or abs(MAIN["reg_scale"][0] - m_cs.x) > 1.0 or abs(MAIN["reg_scale"][2] - m_cs.z) > 1.0:
    die("L_Main region transform differs from the ocean CAC relative transform; stop")

# ---------- 3. copy / new level / paste ----------
paste_set = [e["obj"] for e in src if e["cls"] not in RUNTIME_SPAWNED and e["cls"] not in NOT_COPIED]
eas.set_selected_level_actors(paste_set)
log(f"selected {len(eas.get_selected_level_actors())} of {len(paste_set)} actors")
unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT COPY")
try:
    created = les.new_level(NEW_MAP, False)
except TypeError:
    created = les.new_level(NEW_MAP)
log(f"new_level({NEW_MAP}, partitioned=False) -> {created}")
if not created:
    die("new_level failed")
unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT PASTE")
acts = eas.get_all_level_actors()
log(f"after paste: {len(acts)} actors")
extra = []
for a in acts:
    n = a.get_class().get_name()
    if n not in KEEP and n not in ("WorldSettings", "Brush", "WorldDataLayers"):
        extra.append(f"{n}:{a.get_name()}")
        eas.destroy_actor(a)
log(f"deleted default/extra actors: {extra}")

# ---------- 4. shift far root actors ----------
for a in eas.get_all_level_actors():
    cn = a.get_class().get_name()
    if cn not in KEEP or cn == REGION_CLS:   # the standalone region gets its transform in step 4e
        continue
    l = a.get_actor_location()
    if a.get_attach_parent_actor() is None and (l.x ** 2 + l.y ** 2) ** 0.5 > FAR:
        a.set_actor_location(unreal.Vector(l.x + SHIFT[0], l.y + SHIFT[1], l.z), False, True)
        log(f"  shifted {cn} ({l.x:.1f},{l.y:.1f},{l.z:.1f}) -> {a.get_actor_location()}")

# ---------- 4b. attach lifepod children ----------
pod_actor = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_StaticLifepod_Surface_C"][0]
# The game's pod has a STATIC RootComponent (runtime dump 2026-11-19); the modkit copy reads MOVABLE, and the cooker then refuses to attach the STATIC
# top-level components ("AttachTo: ... is not static, cannot attach ... which is static to it. Aborting."). Make the root STATIC like the game.
pod_root = pod_actor.root_component
log(f"pod root {pod_root.get_name()} mobility {pod_root.mobility} -> STATIC")
pod_root.set_mobility(unreal.ComponentMobility.STATIC)
log(f"pod root mobility now {pod_root.mobility}")
for a in eas.get_all_level_actors():
    cn = a.get_class().get_name()
    if cn in POD_CHILDREN:
        b_l, b_r = a.get_actor_location(), a.get_actor_rotation()
        # a STATIC root cannot be attached to the MOVABLE pod root ("AttachTo: ... is not static, cannot attach ... which is static to it. Aborting.")
        rc = a.root_component
        log(f"  {cn} root {rc.get_name()} mobility {rc.mobility} -> MOVABLE")
        rc.set_mobility(unreal.ComponentMobility.MOVABLE)
        att = a.attach_to_actor(pod_actor, "", unreal.AttachmentRule.KEEP_RELATIVE, unreal.AttachmentRule.KEEP_RELATIVE,
                          unreal.AttachmentRule.KEEP_RELATIVE, False)
        a_l, a_r = a.get_actor_location(), a.get_actor_rotation()
        log(f"  attach_to_actor({cn}) -> {att}; before world ({b_l.x:.2f},{b_l.y:.2f},{b_l.z:.2f}) yaw {b_r.yaw:.2f} -> after ({a_l.x:.2f},{a_l.y:.2f},{a_l.z:.2f}) yaw {a_r.yaw:.2f}")

# ---------- 4d. re-attach the pod's top-level components to its RootComponent ----------
# In the editor (both the opened L_Main and the pasted copy) these components have NO attach parent (probe 2026-11-19, pod_components_probe.py);
# at runtime in L_Main they hang under RootComponent. Root is STATIC (4b) and the children stay STATIC (as in the game); no MOVABLE fallback.
POD_TOP_COMPS = ("Hull", "Door", "UWELadder", "SM_Lifedpod_Glass", "First Entry Trigger Sphere", "PingLocation", "AscendEndPlayerTransform",
                 "PlayerTriggerExit", "PlayerTrigger")
for c in pod_actor.get_components_by_class(unreal.SceneComponent):
    if c.get_name() not in POD_TOP_COMPS:
        continue
    p0 = c.get_attach_parent()
    if p0 == pod_root:
        log(f"  comp {c.get_name()} already attached to RootComponent")
        continue
    b = c.get_world_location()
    rl0, rr0 = c.relative_location, c.relative_rotation
    c.attach_to_component(pod_root, "", unreal.AttachmentRule.KEEP_RELATIVE, unreal.AttachmentRule.KEEP_RELATIVE,
                          unreal.AttachmentRule.KEEP_RELATIVE, False)
    if c.get_attach_parent() != pod_root:
        die(f"attach of {c.get_name()} to RootComponent refused (child mobility {c.mobility}, root mobility {pod_root.mobility})")
    a2 = c.get_world_location()
    rl1, rr1 = c.relative_location, c.relative_rotation
    log(f"  comp {c.get_name()}: parent {p0.get_name() if p0 else None} -> {c.get_attach_parent().get_name() if c.get_attach_parent() else None}; "
        f"rel ({rl0.x:.2f},{rl0.y:.2f},{rl0.z:.2f}) yaw {rr0.yaw:.2f} -> ({rl1.x:.2f},{rl1.y:.2f},{rl1.z:.2f}) yaw {rr1.yaw:.2f}; "
        f"world ({b.x:.2f},{b.y:.2f},{b.z:.2f}) -> ({a2.x:.2f},{a2.y:.2f},{a2.z:.2f}); mobility {c.mobility}")

# ---------- 4c0. ocean BodySize (water volume scale) ----------
# The pasted BP_Ocean_C instance reads BodySize (0,0,0) (L_Main's instance reads 0 too, but its WaterVolumeComponent ChildActorComponent keeps the
# construction-script output). In the paste the construction script ran with 0 -> the ChildActorComponent got relScale (0,0,0), so the child
# BP_UWEOceanBiomeRegionActor_C (water/biome VolumeTracker volumes) has world scale 0 = no water volume = free fall, HUD depth 0 (2026-11-19 probe).
# The class default is (1,000,000, 1,000,000, 100,000). Setting it on the instance re-runs the construction script -> relLoc (0,0,-5,000,000),
# relScale (1e6,1e6,1e5), same as L_Main.
OCEAN_BODYSIZE = (1000000.0, 1000000.0, 100000.0)
OCEAN_VOL_LOC_Z = -5000000.0
for oc in [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_Ocean_C"]:
    log(f"ocean {oc.get_name()} BodySize before {oc.get_editor_property('BodySize')}")
    oc.set_editor_property("BodySize", unreal.Vector(*OCEAN_BODYSIZE))
    log(f"ocean {oc.get_name()} BodySize now {oc.get_editor_property('BodySize')}")

# ---------- 4c. ocean collision fix ----------
if "BP_Ocean_C" not in RUNTIME_SPAWNED:
    oceans = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_Ocean_C"]
    for oc in oceans:
        comps = [c for c in oc.get_components_by_class(unreal.ActorComponent) if c.get_class().get_name() == "WaterBodyOceanComponent"]
        log(f"ocean {oc.get_name()}: WaterBodyOceanComponent count {len(comps)}")
        for comp in comps:
            for prop in ("CollisionBoxes", "CollisionHullSets"):
                log(f"  BEFORE {prop}: {list(unreal.SN2GraphLibrary.describe_object_array(comp, prop))}")
            for prop in ("CollisionBoxes", "CollisionHullSets"):
                log(f"  clear_object_array({prop}) -> {unreal.SN2GraphLibrary.clear_object_array(comp, prop)}")
            unreal.SN2GraphLibrary.notify_property_changed(comp, "CollisionExtents")
            for prop in ("CollisionBoxes", "CollisionHullSets"):
                log(f"  AFTER {prop}: {list(unreal.SN2GraphLibrary.describe_object_array(comp, prop))}")
            try:
                log(f"  collision_extents = {comp.get_editor_property('collision_extents')}")
            except Exception as ex:
                log(f"  collision_extents unreadable: {ex}")

# ---------- 4e. standalone water/biome region (does NOT depend on BP_Ocean_C's construction script) ----------
# Why: the modkit's AUWEWaterBodyOcean is a logic-free stub, so BodySize is 0 when the cooker re-runs BP_Ocean_C's construction script and the ocean's
# own ChildActorComponent (the region) bakes to scale 0 in the COOKED map (research/09 "Root cause of the zero water volume"). A placed actor's own
# root transform is saved data, so a standalone copy of L_Main's region (same properties via copy/paste) at the same world transform survives.
# World transform = our ocean actor's world transform composed with the L_Main offset (ocean at identity rotation/scale: loc + offset, scale unchanged).
def region_actors():
    regs = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == REGION_CLS]
    child = [a for a in regs if a.get_attach_parent_actor() is not None]
    alone = [a for a in regs if a.get_attach_parent_actor() is None]
    return child, alone


def region_target():
    """(loc, scale) the standalone region must have in our map."""
    ocs = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_Ocean_C"]
    if len(ocs) != 1:
        die(f"{len(ocs)} oceans in the new map (want 1)")
    ol = ocs[0].get_actor_location()
    off = MAIN["reg_rel_loc"]
    return (ol.x + off[0], ol.y + off[1], ol.z + off[2]), MAIN["reg_scale"]


# Values read from the COOKED shipped L_Main (retoc to-legacy + UAssetAPI): export <ocean child actor "WaterVolumeComponent_BP_UWEOceanBiomeRegionActor_C_CAT_0">.BiomeVolumeComponent
# property WaterLightSettings (only the non-default fields are stored in the cooked file, so this text is the complete delta from the class default).
WATER_LIGHT_SETTINGS = "(BiomeExtinction=(R=0.9072499871253967,G=0.9451580047607422,B=0.9549999833106995,A=1.0),BiomeExtinctionSkylight=(R=0.6000000238418579,G=0.7607219815254211,B=0.800000011920929,A=1.0),BiomeExtinctionScaleDirectionalLight=12.5,BiomeExtinctionScaleSkylight=17.5,BiomeAlbedo=(R=0.10000000149011612,G=0.29499998688697815,B=1.0,A=1.0),WaterFogDistance=7500.0,WaterFogThickness=10.0,WaterFogBaseThickness=4.0,BiomeBlendType=XYSeperateZ,BiomeBlendDistanceXYAndZ=(X=2000.0,Y=100.0),CausticsSettings=(DepthFadeMax=45000.0))"


def paste_region_with_water_light(actor):
    """Copy `actor` as T3D, add WaterLightSettings to its BiomeVolumeComponent block, paste, delete the original; returns the pasted actor."""
    import subprocess
    world = ues.get_editor_world()
    eas.set_selected_level_actors([actor])
    unreal.SystemLibrary.execute_console_command(world, "EDIT COPY")
    txt = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
    marker = 'Begin Object Name="BiomeVolumeComponent"'
    i = txt.find(marker)
    j = txt.find('AttachParent="RootComponent"', i) if i >= 0 else -1
    if i < 0 or j < 0:
        die("T3D of the standalone region has no BiomeVolumeComponent block to extend")
    edited = txt[:j] + "WaterLightSettings=" + WATER_LIGHT_SETTINGS + "\r\n            " + txt[j:]
    rc = subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"], input=edited.encode("utf-8"), capture_output=True, timeout=60)
    if rc.returncode != 0:
        die(f"Set-Clipboard failed: {rc.stderr[:200]!r}")
    eas.destroy_actor(actor)
    unreal.SystemLibrary.execute_console_command(world, "EDIT PASTE")
    new = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == REGION_CLS and a.get_attach_parent_actor() is None]
    if len(new) != 1:
        die(f"after the T3D paste there are {len(new)} standalone region actors (want 1)")
    # verify: the pasted actor's own T3D must now carry the setting
    eas.set_selected_level_actors([new[0]])
    unreal.SystemLibrary.execute_console_command(world, "EDIT COPY")
    back = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
    k = back.find("WaterLightSettings=")
    ok = k >= 0 and "BiomeExtinctionScaleDirectionalLight=12.5" in back[k:k + 1200] and "WaterFogDistance=7500" in back[k:k + 1200]
    log(f"  WaterLightSettings on the pasted region: {back[k:k + 160]!r} -> {'ok' if ok else 'BAD'}")
    if not ok:
        die("the pasted standalone region does not carry the WaterLightSettings")
    return new[0]


r_child, r_alone = region_actors()
log(f"regions after paste: {len(r_child)} child-actor (attached), {len(r_alone)} standalone (the paste cannot copy the child actor, so it is spawned)")
if r_alone:
    die(f"unexpected standalone region actors after paste: {len(r_alone)}")
tl, ts = region_target()
reg_new = eas.spawn_actor_from_class(MAIN["reg_class"], unreal.Vector(*tl), unreal.Rotator(*MAIN["reg_rot"]))
if reg_new is None:
    die("spawn_actor_from_class(region) returned None")
reg_new.set_actor_scale3d(unreal.Vector(*ts))
reg_new.set_actor_label("BP_UWEOceanBiomeRegionActor_Standalone")
log(f"standalone region '{reg_new.get_name()}' spawned: loc {reg_new.get_actor_location()} scale {reg_new.get_actor_scale3d()}")
nd, ns, nf = apply_snapshot(MAIN["reg_snap"], reg_new, "regprops")
log(f"region properties copied from L_Main's child actor: {nd} differed from the class defaults, {ns} set, {nf} failed")
# BiomeVolumeComponent.WaterLightSettings: the shipped (cooked) L_Main child actor has it baked (the water colours / fog), but the editor rebuilds child actors
# from the BP template, so the snapshot above cannot see it, the property is not exposed to Python, and the modkit's stub C++ never fills it (cooked-file
# comparison 2026-11-19: ours = default, L_Main = WATER_LIGHT_SETTINGS below). Put it in through T3D text: copy the actor, add the property to the
# BiomeVolumeComponent block, paste the edited text, delete the original. (The `Set <Class> <Prop> <Value>` console command did nothing.)
reg_new = paste_region_with_water_light(reg_new)
log(f"standalone region after the T3D round trip: {reg_new.get_name()} loc {reg_new.get_actor_location()} scale {reg_new.get_actor_scale3d()}")
# the spawn / property sets may re-run the construction script: put the transform back and make it explicit
reg_new.set_actor_transform(unreal.Transform(unreal.Vector(*tl), unreal.Rotator(*MAIN["reg_rot"]), unreal.Vector(*ts)), False, True)
log(f"standalone region final: loc {reg_new.get_actor_location()} scale {reg_new.get_actor_scale3d()}")

# ---------- 5. check ----------
good = True
by = {}
for a in eas.get_all_level_actors():
    by.setdefault(a.get_class().get_name(), []).append(a)
for k in KEEP:
    if k == REGION_CLS:
        continue   # checked by check_region (1 standalone + the ocean's own child actor)
    if k in NOT_COPIED:
        continue
    if k in RUNTIME_SPAWNED:
        log(f"  {k}: NOT in level (spawned by the ModActor at runtime); found in level: {len(by.get(k, []))}")
        if by.get(k):
            good = False
        continue
    srcs = [e for e in src if e["cls"] == k]
    news = by.get(k, [])
    if k in POD_CHILDREN:
        want_l, want_yaw = POD_CHILDREN[k]
        if len(news) != 1:
            good = False
            log(f"  {k}: count {len(news)} (want 1)")
            continue
        n = news[0]
        nl, nr, par = n.get_actor_location(), n.get_actor_rotation(), n.get_attach_parent_actor()
        d = ((nl.x - want_l[0]) ** 2 + (nl.y - want_l[1]) ** 2 + (nl.z - want_l[2]) ** 2) ** 0.5
        dy = abs((nr.yaw - want_yaw + 180.0) % 360.0 - 180.0)
        okp = d <= 1.0 and dy <= 0.1 and par is not None and par == pod_actor
        log(f"  {k}: world ({nl.x:.2f},{nl.y:.2f},{nl.z:.2f}) yaw {nr.yaw:.2f}; expected {want_l} yaw {want_yaw}; dist {d:.3f} cm, dyaw {dy:.3f}, attach parent is pod: {par == pod_actor if par else False} -> {'ok' if okp else 'BAD'}")
        if not okp:
            good = False
        continue
    if len(news) != len(srcs):
        good = False
    for e in srcs:
        sl = e["loc"]
        far = (sl[0] ** 2 + sl[1] ** 2) ** 0.5 > FAR   # children of the lifepod move with it
        want = (sl[0] + SHIFT[0], sl[1] + SHIFT[1], sl[2]) if far else sl
        best = min((((n.get_actor_location().x - want[0]) ** 2 + (n.get_actor_location().y - want[1]) ** 2 + (n.get_actor_location().z - want[2]) ** 2) ** 0.5
                    for n in news), default=None)
        if best is None or best > 1.0:
            good = False
        log(f"  {k}: src=({sl[0]:.1f},{sl[1]:.1f},{sl[2]:.1f}) expected=({want[0]:.1f},{want[1]:.1f},{want[2]:.1f}) nearest new distance={'none' if best is None else f'{best:.3f}'} cm")
def check_pod(pod, tag):
    """Returns True if the pod's nine top-level components hang under RootComponent, root is STATIC, Hull is at world (0,0,-57) yaw 52.44,
    and the lighting / locker actors are attached to the pod. Used in memory (before save) and after a reload from disk."""
    ok_all = True
    root = pod.root_component
    okr = root.mobility == unreal.ComponentMobility.STATIC
    log(f"  [{tag}] pod root {root.get_name()} mobility {root.mobility} -> {'ok' if okr else 'BAD (want STATIC)'}")
    ok_all &= okr
    seen = set()
    for c in pod.get_components_by_class(unreal.SceneComponent):
        if c.get_name() not in POD_TOP_COMPS:
            continue
        seen.add(c.get_name())
        okc = c.get_attach_parent() == root
        log(f"  [{tag}] pod comp {c.get_name()}: attach parent {c.get_attach_parent().get_name() if c.get_attach_parent() else None}, mobility {c.mobility} -> {'ok' if okc else 'BAD'}")
        ok_all &= okc
        if c.get_name() == "Hull":
            hl, hr = c.get_world_location(), c.get_world_rotation()
            dh = ((hl.x) ** 2 + (hl.y) ** 2 + (hl.z + 57.0) ** 2) ** 0.5
            dyh = abs((hr.yaw - 52.44 + 180.0) % 360.0 - 180.0)
            okh = dh <= 1.0 and dyh <= 0.1
            log(f"  [{tag}] Hull world ({hl.x:.2f},{hl.y:.2f},{hl.z:.2f}) yaw {hr.yaw:.2f}; dist to (0,0,-57) {dh:.3f}, dyaw {dyh:.3f} -> {'ok' if okh else 'BAD'}")
            ok_all &= okh
    if seen != set(POD_TOP_COMPS):
        log(f"  [{tag}] missing pod components: {sorted(set(POD_TOP_COMPS) - seen)} -> BAD")
        ok_all = False
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn in POD_CHILDREN:
            par = a.get_attach_parent_actor()
            okp = par is not None and par == pod
            log(f"  [{tag}] {cn} attach parent actor = {par.get_name() if par else None} -> {'ok' if okp else 'BAD'}")
            ok_all &= okp
    return ok_all


def check_ocean(tag, check_bodysize=True):
    """True if the ocean's water volume matches L_Main: BodySize (1e6,1e6,1e5), the WaterVolumeComponent ChildActorComponent at relLoc z -5e6 with
    relScale (1e6,1e6,1e5), and the child biome actor's water volumes (WaterBoxVolumeComponent, WaterVolumeComponent, BiomeVolumeComponent) at
    world scale (1e6,1e6,1e5). Zero scale = no water physics (2026-11-19)."""
    ok_all = True

    def near(v, w, tol=1.0):
        return abs(v.x - w[0]) <= tol and abs(v.y - w[1]) <= tol and abs(v.z - w[2]) <= tol
    oceans = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_Ocean_C"]
    if len(oceans) != 1:
        log(f"  [{tag}] oceans {len(oceans)} (want 1) -> BAD")
        return False
    oc = oceans[0]
    bs = oc.get_editor_property("BodySize")
    # BodySize is NOT serialized (reads 0 after a reload, also in L_Main); only the construction-script output (the CAC transform) persists -> checked in memory only
    okb = near(bs, OCEAN_BODYSIZE) or not check_bodysize
    log(f"  [{tag}] BodySize ({bs.x:.0f},{bs.y:.0f},{bs.z:.0f}) -> {'ok' if okb else 'BAD'}{'' if check_bodysize else ' (not checked after reload: not serialized)'}")
    ok_all &= okb
    cacs = oc.get_components_by_class(unreal.ChildActorComponent)
    if len(cacs) != 1:
        log(f"  [{tag}] ChildActorComponents {len(cacs)} (want 1) -> BAD")
        return False
    cac = cacs[0]
    rl, rs = cac.relative_location, cac.relative_scale3d
    okc = near(rl, (0.0, 0.0, OCEAN_VOL_LOC_Z)) and near(rs, OCEAN_BODYSIZE)
    log(f"  [{tag}] {cac.get_name()} relLoc ({rl.x:.0f},{rl.y:.0f},{rl.z:.0f}) relScale ({rs.x:.0f},{rs.y:.0f},{rs.z:.0f}) -> {'ok' if okc else 'BAD'}")
    ok_all &= okc
    ch = cac.get_editor_property("child_actor")
    if ch is None:
        log(f"  [{tag}] no child actor -> BAD")
        return False
    seen = set()
    for c in ch.get_components_by_class(unreal.SceneComponent):
        if c.get_name() in ("WaterBoxVolumeComponent", "WaterVolumeComponent", "BiomeVolumeComponent"):
            seen.add(c.get_name())
            ws = c.get_world_scale()
            okw = near(ws, OCEAN_BODYSIZE)
            log(f"  [{tag}] child comp {c.get_name()} ({c.get_class().get_name()}) world scale ({ws.x:.0f},{ws.y:.0f},{ws.z:.0f}) -> {'ok' if okw else 'BAD'}")
            ok_all &= okw
    if len(seen) != 3:
        log(f"  [{tag}] missing child volume components, seen {sorted(seen)} -> BAD")
        ok_all = False
    return ok_all


def check_region(tag):
    """True if the standalone BP_UWEOceanBiomeRegionActor_C and the origin air volume (BP_BoxVolume_C) are present with L_Main's transforms,
    and the vertical relationship ocean surface / region top+bottom / air-volume bottom equals L_Main's (relative to the ocean actor Z)."""
    ok_all = True

    def close(v, w, rel=1e-4, ab=1.0):
        return all(abs(v[i] - w[i]) <= ab + rel * abs(w[i]) for i in range(3))
    child, alone = region_actors()
    log(f"  [{tag}] region actors: {len(child)} child-actor, {len(alone)} standalone (want 1 standalone)")
    if len(alone) != 1:
        return False
    reg = alone[0]
    tl, ts = region_target()
    l, s, r = reg.get_actor_location(), reg.get_actor_scale3d(), reg.get_actor_rotation()
    okt = close((l.x, l.y, l.z), tl) and close((s.x, s.y, s.z), ts)
    log(f"  [{tag}] standalone region '{reg.get_name()}' loc ({l.x:.1f},{l.y:.1f},{l.z:.1f}) scale ({s.x:.1f},{s.y:.1f},{s.z:.1f}) want loc {tl} scale {ts} -> {'ok' if okt else 'BAD'}")
    ok_all &= okt
    main_rows = {row[0]: row for row in MAIN["reg_comps"]}
    ocs = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_Ocean_C"]
    oz = ocs[0].get_actor_location().z
    dz = oz - MAIN["ocean_loc"][2]
    for row in comp_rows(reg):
        mrow = main_rows.get(row[0])
        if mrow is None:
            log(f"  [{tag}] region comp {row[0]} not in L_Main (ignored)")
            continue
        want_loc = (mrow[2][0] + (tl[0] - (MAIN["ocean_loc"][0] + MAIN["reg_rel_loc"][0])), mrow[2][1] + (tl[1] - (MAIN["ocean_loc"][1] + MAIN["reg_rel_loc"][1])),
                    mrow[2][2] + dz)
        okc = close(row[3], mrow[3]) and close(row[2], want_loc)
        log(f"  [{tag}] region comp {row[0]} ({row[1]}) world scale ({row[3][0]:.1f},{row[3][1]:.1f},{row[3][2]:.1f}) world loc z {row[2][2]:.1f} vs L_Main scale {mrow[3]} loc z {want_loc[2]:.1f} -> {'ok' if okc else 'BAD'}")
        ok_all &= okc
    if set(main_rows) - {row[0] for row in comp_rows(reg)}:
        log(f"  [{tag}] region comps missing vs L_Main: {sorted(set(main_rows) - {row[0] for row in comp_rows(reg)})} -> BAD")
        ok_all = False
    airs = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_BoxVolume_C"]
    log(f"  [{tag}] BP_BoxVolume_C count {len(airs)} (want 1)")
    if len(airs) != 1:
        return False
    air = airs[0]
    al, asc = air.get_actor_location(), air.get_actor_scale3d()
    oka = close((al.x, al.y, al.z), MAIN["air_loc"]) and close((asc.x, asc.y, asc.z), MAIN["air_scale"])
    log(f"  [{tag}] air volume '{air.get_actor_label()}' loc ({al.x:.1f},{al.y:.1f},{al.z:.1f}) scale ({asc.x:.0f},{asc.y:.0f},{asc.z:.0f}) want loc {MAIN['air_loc']} scale {MAIN['air_scale']} -> {'ok' if oka else 'BAD'}")
    ok_all &= oka
    # vertical relationship relative to the ocean actor Z (the value that feeds the MPC OceanLevel)
    mrows = {row[0]: row for row in MAIN["air_comps"]}
    for row in comp_rows(air):
        mrow = mrows.get(row[0])
        if mrow is None:
            log(f"  [{tag}] air comp {row[0]} not in L_Main -> BAD")
            ok_all = False
            continue
        dz_now, dz_main = row[2][2] - oz, mrow[2][2] - MAIN["ocean_loc"][2]
        okv = abs(dz_now - dz_main) <= 1.0 + 1e-4 * abs(dz_main) and close(row[3], mrow[3])
        log(f"  [{tag}] air comp {row[0]} ({row[1]}) world z relative to ocean Z {dz_now:.1f} (L_Main {dz_main:.1f}), world scale ({row[3][0]:.0f},{row[3][1]:.0f},{row[3][2]:.0f}) (L_Main {mrow[3][0]:.0f},{mrow[3][1]:.0f},{mrow[3][2]:.0f}) -> {'ok' if okv else 'BAD'}")
        ok_all &= okv
    return ok_all


if not check_pod(pod_actor, "memory"):
    good = False
if not check_ocean("memory"):
    good = False
if not check_region("memory"):
    good = False
log(f"check {'PASSED' if good else 'FAILED'}")
if not good:
    die("check failed; NOT saving")

# ---------- 6. save ----------
saved = les.save_current_level()
log(f"save_current_level -> {saved}")
final = {}
for a in eas.get_all_level_actors():
    final[a.get_class().get_name()] = final.get(a.get_class().get_name(), 0) + 1
log(f"FINAL {sum(final.values())} actors: {final}")
log(f"RESULT method=1 (copy/paste; ocean in level={'BP_Ocean_C' not in RUNTIME_SPAWNED}) level={NEW_MAP} saved={saved} exists={unreal.EditorAssetLibrary.does_asset_exist(NEW_MAP)}")
if not saved:
    die("save failed")

# ---------- 7. reload from disk and re-check (an in-memory check does not prove what the cooker loads) ----------
OTHER_MAP = SRC_MAP
log(f"reload check: load_map({OTHER_MAP}) -> {unreal.EditorLoadingAndSavingUtils.load_map(OTHER_MAP)}")
okl = unreal.EditorLoadingAndSavingUtils.load_map(NEW_MAP)
log(f"reload check: load_map({NEW_MAP}) from disk -> {okl}")
if not okl:
    die("could not reload L_SN2World")
pods2 = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_StaticLifepod_Surface_C"]
if len(pods2) != 1:
    die(f"after reload: {len(pods2)} pods (want 1)")
okre = check_pod(pods2[0], "reload")
okro = check_ocean("reload", False)
okrr = check_region("reload")
log(f"reload check {'PASSED' if okre and okro and okrr else 'FAILED'} (pod {okre}, ocean {okro}, region+air {okrr})")
okre = okre and okro and okrr
if not okre:
    die("reload check FAILED: the saved map does not hold the pod attachments / ocean water volume (see [reload] lines); do NOT cook/install")
