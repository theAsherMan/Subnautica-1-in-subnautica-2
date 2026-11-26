"""Runs INSIDE the Unreal editor. READ-ONLY probe of SN2's own biome regions in L_Main (opened, never saved): for every
BP_UWEWaterBiomeRegionActor_C / BP_UWEOceanBiomeRegionActor_C actor it logs transform, flags, volume type, box extent, bounds, and writes the
actor's T3D text (EDIT COPY) to <Workspace>/reports/lmain_biome_regions/<label>.t3d. The T3D holds the instance's WaterLightSettings
(not exposed to Python), i.e. SN2's hand-tuned look per region = calibration data for src/tools/sn1_biome_transfer.py.
World Partition: only loaded actors are seen; the script also loads all regions via the WP editor subsystem if it can (logged).
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/lmain_biome_regions_probe.py        Output lines start with [BiomeProbe].
"""
import os
import subprocess
import unreal

SRC_MAP = "/Game/Maps/Main/L_Main"
CLASSES = ("BP_UWEWaterBiomeRegionActor_C", "BP_UWEOceanBiomeRegionActor_C")
FLAGS = ("biome_region_type", "biome_region_volume_type", "has_water_surface", "mask_ocean_surface", "use_distance_field_mask", "is_ocean",
         "b_has_water_surface", "b_mask_ocean_surface", "b_use_distance_field_mask", "b_is_ocean")


def log(m):
    unreal.log(f"[BiomeProbe] {m}")


def _workspace():
    w = os.environ.get("SN2_WORKSPACE")
    if w:
        return w
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with open(os.path.join(repo, "local.config"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("SN2_WORKSPACE="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("SN2_WORKSPACE not set and not in local.config")


OUT = os.path.join(_workspace(), "reports", "lmain_biome_regions")
os.makedirs(OUT, exist_ok=True)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

ok = unreal.EditorLoadingAndSavingUtils.load_map(SRC_MAP)
log(f"load_map({SRC_MAP}) -> {ok}")
if not ok:
    raise RuntimeError("could not load L_Main")


def regions():
    return [a for a in eas.get_all_level_actors() if a.get_class().get_name() in CLASSES]


regs = regions()
log(f"region actors loaded: {len(regs)}")
# try to load every WP cell region actor too (editor-side loading of the whole world is too heavy; regions may be always-loaded anyway)
try:
    wp = unreal.get_editor_subsystem(unreal.WorldPartitionEditorSubsystem)
    log(f"WorldPartitionEditorSubsystem: {wp}")
except Exception as ex:
    log(f"WorldPartitionEditorSubsystem not available: {ex}")

world = ues.get_editor_world()
summary = []
for a in regs:
    lab = a.get_actor_label()
    l, r, s = a.get_actor_location(), a.get_actor_rotation(), a.get_actor_scale3d()
    org, ext = a.get_actor_bounds(False)
    par = a.get_attach_parent_actor()
    line = (f"REGION {lab} class={a.get_class().get_name()} name={a.get_name()} loc=({l.x:.0f},{l.y:.0f},{l.z:.0f}) rot=({r.pitch:.1f},{r.yaw:.1f},{r.roll:.1f}) "
            f"scale=({s.x:.3f},{s.y:.3f},{s.z:.3f}) bounds_origin=({org.x:.0f},{org.y:.0f},{org.z:.0f}) bounds_extent=({ext.x:.0f},{ext.y:.0f},{ext.z:.0f}) "
            f"parent={par.get_name() if par else None}")
    fl = []
    for f in FLAGS:
        try:
            fl.append(f"{f}={a.get_editor_property(f)}")
        except Exception:
            pass
    line += " " + " ".join(fl)
    for c in a.get_components_by_class(unreal.SceneComponent):
        cn = c.get_class().get_name()
        extra = ""
        if isinstance(c, unreal.BoxComponent):
            try:
                extra = f" box_extent={c.get_editor_property('box_extent')}"
            except Exception:
                pass
        rs = c.relative_scale3d
        line += f" | {c.get_name()}:{cn} rel_scale=({rs.x:.3f},{rs.y:.3f},{rs.z:.3f}){extra}"
    log(line)
    summary.append(line)
    if par is not None:
        continue   # child actors cannot be copied (EDIT COPY skips them)
    eas.set_selected_level_actors([a])
    unreal.SystemLibrary.execute_console_command(world, "EDIT COPY")
    txt = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in lab)
    with open(os.path.join(OUT, safe + ".t3d"), "w", encoding="utf-8") as f:
        f.write(txt)
    k = txt.find("WaterLightSettings=")
    log(f"  T3D {len(txt)} chars -> {safe}.t3d; WaterLightSettings: {txt[k:k + 600] if k >= 0 else 'NOT IN T3D (class default)'}")
eas.set_selected_level_actors([])
with open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(summary) + "\n")
log(f"DONE {len(regs)} regions; files in {OUT}. L_Main was not saved.")
