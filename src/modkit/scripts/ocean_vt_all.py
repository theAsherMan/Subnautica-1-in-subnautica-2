import subprocess
import unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
res = {}
for a in eas.get_all_level_actors():
    if "BiomeRegion" in a.get_class().get_name():
        eas.set_selected_level_actors([a])
        unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT COPY")
        t = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        k = (a.get_class().get_name(), tuple(l.strip() for l in t.splitlines() if "VolumeType=" in l))
        res[k] = res.get(k, 0) + 1
for k, v in res.items():
    unreal.log("[VT] %s x%d" % (k, v))
