"""Runs INSIDE the Unreal editor, read-only. Logs every SceneComponent of BP_StaticLifepod_Surface_C in the currently open level, then in L_Main
(opened, never saved) and in L_SN2World (if it exists). Output lines start with [PODPROBE].
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/pod_components_probe.py
"""
import unreal

MAPS = ["/Game/Maps/Main/L_Main", "/Game/Mods/SN2EmptyWorld/L_SN2World"]


def log(m):
    unreal.log(f"[PODPROBE] {m}")


def nm(o):
    return o.get_name() if o else "None"


eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for path in MAPS:
    ok = unreal.EditorLoadingAndSavingUtils.load_map(path)
    log(f"=== load_map({path}) -> {ok}")
    if not ok:
        continue
    pods = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_StaticLifepod_Surface_C"]
    log(f"pods: {len(pods)}")
    for pod in pods:
        try:   # class template (CDO) root mobility vs the instance's
            cdo = unreal.get_default_object(pod.get_class())
            croot = cdo.root_component
            log(f"CLASS {pod.get_class().get_path_name()} CDO root={nm(croot)} class={croot.get_class().get_name() if croot else None} "
                f"CDO root_mobility={croot.mobility if croot else None}")
            for cc in cdo.get_components_by_class(unreal.SceneComponent):
                log(f"  CDO comp {cc.get_name()} mobility={cc.mobility} parent={nm(cc.get_attach_parent())}")
        except Exception as ex:
            log(f"CDO read failed: {ex}")
        root = pod.root_component
        log(f"pod {pod.get_name()} root={nm(root)} root_mobility={root.mobility}")
        for c in pod.get_components_by_class(unreal.SceneComponent):
            p = c.get_attach_parent()
            rl, rr = c.relative_location, c.relative_rotation
            wl, wr = c.get_world_location(), c.get_world_rotation()
            log(f"  comp {c.get_name()} class={c.get_class().get_name()} parent={nm(p)} mobility={c.mobility} "
                f"rel=({rl.x:.2f},{rl.y:.2f},{rl.z:.2f}) relrot=({rr.pitch:.2f},{rr.yaw:.2f},{rr.roll:.2f}) "
                f"world=({wl.x:.2f},{wl.y:.2f},{wl.z:.2f}) worldyaw={wr.yaw:.2f}")
log("done")
