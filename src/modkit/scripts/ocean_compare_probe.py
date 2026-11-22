"""Runs INSIDE the Unreal editor, read-only. Dumps the ocean/water actors (BP_Ocean_C, BP_UWEOceanBiomeRegionActor_C, WaterZone and any other actor whose
class name contains Water/Swim/Volume/Ocean) of L_Main (opened, never saved) and of L_SN2World (loaded from disk), plus the BP_Ocean_C class CDO.
Output lines start with [OCEANPROBE]. Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/ocean_compare_probe.py
"""
import unreal

MAPS = ["/Game/Maps/Main/L_Main", "/Game/Mods/SN2EmptyWorld/L_SN2World"]
WORDS = ("water", "swim", "volume", "ocean")
SKIP_PROPS = {"cast", "static_class", "get_default_object"}


def log(m):
    unreal.log(f"[OCEANPROBE] {m}")


def nm(o):
    return o.get_name() if o else "None"


def v3(v):
    return f"({v.x:.2f},{v.y:.2f},{v.z:.2f})" if v is not None else "?"


def comp_row(tag, c):
    try:
        p = c.get_attach_parent() if isinstance(c, unreal.SceneComponent) else None
        if isinstance(c, unreal.SceneComponent):
            rs = c.relative_scale3d
            ws = c.get_world_scale()
            log(f"{tag} comp {c.get_name()} class={c.get_class().get_name()} parent={nm(p)} relLoc={v3(c.relative_location)} "
                f"relRot=({c.relative_rotation.pitch:.2f},{c.relative_rotation.yaw:.2f},{c.relative_rotation.roll:.2f}) relScale={v3(rs)} "
                f"worldLoc={v3(c.get_world_location())} worldScale={v3(ws)} mobility={c.mobility}")
        else:
            log(f"{tag} acomp {c.get_name()} class={c.get_class().get_name()}")
    except Exception as ex:
        log(f"{tag} comp row failed {c}: {ex}")


def props(tag, o, names=None):
    """Print python-visible editor properties (dir() lowercase non-callables) of o."""
    try:
        cand = names or [n for n in dir(o) if not n.startswith("_") and n.islower() and n not in SKIP_PROPS]
        for n in cand:
            try:
                v = o.get_editor_property(n)
            except Exception:
                continue
            if callable(v):
                continue
            s = str(v)
            if len(s) > 160:
                s = s[:160] + "..."
            log(f"{tag}   prop {n} = {s}")
    except Exception as ex:
        log(f"{tag} props failed: {ex}")


def dump_actor(tag, a, deep=True):
    l, r = a.get_actor_location(), a.get_actor_rotation()
    log(f"{tag} ACTOR {a.get_name()} class={a.get_class().get_name()} loc={v3(l)} rot=({r.pitch:.2f},{r.yaw:.2f},{r.roll:.2f}) scale={v3(a.get_actor_scale3d())} "
        f"parentActor={nm(a.get_attach_parent_actor())}")
    comps = a.get_components_by_class(unreal.ActorComponent)
    for c in comps:
        comp_row(tag, c)
        cn = c.get_class().get_name()
        if not deep:
            continue
        if cn == "WaterBodyOceanComponent" or "WaterBody" in cn:
            props(tag + f" [{c.get_name()}]", c)
            try:
                log(f"{tag}   CollisionBoxes={list(unreal.SN2GraphLibrary.describe_object_array(c, 'CollisionBoxes'))}")
                log(f"{tag}   CollisionHullSets={list(unreal.SN2GraphLibrary.describe_object_array(c, 'CollisionHullSets'))}")
            except Exception as ex:
                log(f"{tag}   describe_object_array failed: {ex}")
        if "BoxCollision" in cn or "BoxComponent" in cn:
            try:
                log(f"{tag}   box {c.get_name()} unscaled_extent={v3(c.get_editor_property('box_extent'))} scaled={v3(c.get_scaled_box_extent())}")
            except Exception as ex:
                log(f"{tag}   box extent failed: {ex}")
        if cn == "ChildActorComponent":
            try:
                ca = c.get_editor_property("child_actor_class")
                log(f"{tag}   ChildActorComponent class={ca.get_path_name() if ca else None} childActor={nm(c.get_child_actor())}")
                tmpl = c.get_editor_property("child_actor_template")
                log(f"{tag}   template={tmpl.get_path_name() if tmpl else None}")
                if tmpl:
                    for tc in tmpl.get_components_by_class(unreal.SceneComponent):
                        comp_row(tag + " TEMPLATE", tc)
                ch = c.get_child_actor()
                if ch:
                    for cc in ch.get_components_by_class(unreal.ActorComponent):
                        comp_row(tag + " CHILD", cc)
                    props(tag + " CHILDACTOR", ch)
            except Exception as ex:
                log(f"{tag}   child actor read failed: {ex}")
    if deep:
        props(tag + " [actor]", a)


eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for path in MAPS:
    tag = path.split("/")[-1]
    ok = unreal.EditorLoadingAndSavingUtils.load_map(path)
    log(f"=== load_map({path}) -> {ok}")
    if not ok:
        continue
    acts = eas.get_all_level_actors()
    hits = [a for a in acts if any(w in a.get_class().get_name().lower() for w in WORDS)]
    log(f"{tag}: {len(acts)} actors; water-like: {sorted(set(a.get_class().get_name() for a in hits))}")
    for a in hits:
        dump_actor(tag, a)
    # BP_Ocean_C CDO
    if tag == "L_Main":
        try:
            cls = unreal.load_class(None, "/Game/Blueprints/Water/BP_Ocean.BP_Ocean_C")
        except Exception:
            cls = None
        oc = [a for a in hits if a.get_class().get_name() == "BP_Ocean_C"]
        if oc:
            cls = oc[0].get_class()
        if cls:
            log(f"CDO class {cls.get_path_name()}")
            cdo = unreal.get_default_object(cls)
            dump_actor("CDO", cdo)
log("=== done")
