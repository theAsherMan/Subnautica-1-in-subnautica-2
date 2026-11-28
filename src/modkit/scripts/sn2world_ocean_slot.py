"""Runs INSIDE the Unreal editor. Fixes the water volume in L_SN2World at source (research/sn2/l_sn2world_water.md "region water volume"):
  1. BP_Ocean_C_0.WaterVolumeComponent (ChildActorComponent): ChildActorClass = None, so the zero-size child region CAT_0 no longer spawns
     and no longer owns the biome tracker's slot 15.
  2. standalone BP_UWEOceanBiomeRegionActor_C_1: BiomeRegionVolumeType = BRVT_Shape through T3D text. DOES NOT PERSIST (2026-11-27: Shape equals the editor stub default, so it is never serialized; the game reads Brush). The volume type is set at runtime by the SN2EmptyWorld ModActor graph (sn2emptyworld_graph.py). Only step 1 (child_actor_class=None) is load-bearing.
Run: python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2world_ocean_slot.py   Lines start [OceanSlot].
"""
import subprocess
import unreal

MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"
SA_NAME = "BP_UWEOceanBiomeRegionActor_C_1"


def log(m):
    unreal.log(f"[OceanSlot] {m}")


def clip_get():
    return subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")


def clip_set(txt):
    rc = subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"], input=txt.encode("utf-8"),
                        capture_output=True, timeout=120)
    if rc.returncode != 0:
        raise RuntimeError(f"Set-Clipboard failed: {rc.stderr[:200]!r}")


def vt_lines(txt):
    return [l.strip() for l in txt.splitlines() if "VolumeType" in l]


if not unreal.EditorLoadingAndSavingUtils.load_map(MAP):
    raise RuntimeError("load_map failed")
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = {a.get_name(): a for a in eas.get_all_level_actors()}
ocean = actors["BP_Ocean_C_0"]
sa = actors[SA_NAME]
world = ues.get_editor_world()

# 1. ocean child region class -> None
for c in ocean.get_components_by_class(unreal.ChildActorComponent):
    log(f"ChildActorComponent {c.get_name()} class={c.get_editor_property('child_actor_class')}")
    if c.get_name() == "WaterVolumeComponent":
        c.set_editor_property("child_actor_class", None)
        log(f"  -> class now {c.get_editor_property('child_actor_class')}")

# 2. standalone volume type through T3D
loc, rot, scl = sa.get_actor_location(), sa.get_actor_rotation(), sa.get_actor_scale3d()
eas.set_selected_level_actors([sa])
unreal.SystemLibrary.execute_console_command(world, "EDIT COPY")
txt = clip_get()
log(f"before: VolumeType lines {vt_lines(txt)}")
if "BiomeRegionVolumeType=" in txt:
    import re
    edited = re.sub(r"BiomeRegionVolumeType=\w+", "BiomeRegionVolumeType=BRVT_Shape", txt)
else:
    k = txt.rfind("End Actor")
    edited = txt[:k] + "   BiomeRegionVolumeType=BRVT_Shape\r\n" + txt[k:]
clip_set(edited)
eas.destroy_actor(sa)
unreal.SystemLibrary.execute_console_command(world, "EDIT PASTE")
new = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "BP_UWEOceanBiomeRegionActor_C" and a.get_attach_parent_actor() is None]
log(f"standalone actors after paste: {[(a.get_name(), str(a.get_actor_location()), str(a.get_actor_scale3d())) for a in new]} (want 1, loc {loc} scale {scl})")
if len(new) != 1:
    raise RuntimeError("paste did not yield exactly 1 standalone region")
new[0].set_actor_transform(unreal.Transform(loc, rot, scl), False, True)
eas.set_selected_level_actors([new[0]])
unreal.SystemLibrary.execute_console_command(world, "EDIT COPY")
log(f"after paste: VolumeType lines {vt_lines(clip_get())}")
log(f"save_current_level -> {unreal.EditorLevelLibrary.save_current_level()}")

# self-check after reload
unreal.EditorLoadingAndSavingUtils.load_map(MAP)
actors = {a.get_name(): a for a in eas.get_all_level_actors()}
for c in actors["BP_Ocean_C_0"].get_components_by_class(unreal.ChildActorComponent):
    log(f"RELOAD ChildActorComponent {c.get_name()} class={c.get_editor_property('child_actor_class')}")
regs = [a for a in actors.values() if a.get_class().get_name() == "BP_UWEOceanBiomeRegionActor_C"]
log(f"RELOAD region actors: {[(a.get_name(), str(a.get_actor_location()), str(a.get_actor_scale3d()), a.get_attach_parent_actor() is None) for a in regs]}")
for a in regs:
    if a.get_attach_parent_actor() is None:
        eas.set_selected_level_actors([a])
        unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT COPY")
        log(f"RELOAD standalone {a.get_name()} VolumeType lines {vt_lines(clip_get())}")
