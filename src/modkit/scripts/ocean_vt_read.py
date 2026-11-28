"""Runs INSIDE the editor. Reads BiomeRegionVolumeType of the placed ocean region(s) via T3D copy. Lines start [VT]."""
import subprocess
import unreal

MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
unreal.EditorLoadingAndSavingUtils.load_map(MAP)
for a in eas.get_all_level_actors():
    if a.get_class().get_name() == "BP_UWEOceanBiomeRegionActor_C" and a.get_attach_parent_actor() is None:
        eas.set_selected_level_actors([a])
        unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT COPY")
        t = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        unreal.log("[VT] " + a.get_name() + " " + str([l.strip() for l in t.splitlines() if "VolumeType=" in l]))
