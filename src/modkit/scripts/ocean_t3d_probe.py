"""Runs INSIDE the Unreal editor, read-only (never saves). For the map given in OCEAN_T3D_MAP (default: L_Main then L_SN2World, one per run via the
variable MAPS below) selects the BP_Ocean_C and WaterZone actors, runs the editor's EDIT COPY (T3D text with every non-default property, incl. the
ChildActorComponent template) and writes the clipboard to <ModkitDir>/ocean_t3d_<map>_<actor>.t3d through the PowerShell Get-Clipboard command.
Also logs [T3DPROBE] lines: external-actor / data-layer facts. Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/ocean_t3d_probe.py
"""
import os
import subprocess
import unreal

MAPS = ["/Game/Maps/Main/L_Main", "/Game/Mods/SN2EmptyWorld/L_SN2World"]


def _modkit_dir():
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with open(os.path.join(repo, "local.config"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("SN2_MODKIT_DIR="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("SN2_MODKIT_DIR not in local.config")


OUT_DIR = os.environ.get("OCEAN_T3D_OUT") or _modkit_dir()
CLASSES = ("BP_Ocean_C", "WaterZone")


def log(m):
    unreal.log(f"[T3DPROBE] {m}")


eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
for path in MAPS:
    tag = path.split("/")[-1]
    ok = unreal.EditorLoadingAndSavingUtils.load_map(path)
    log(f"=== load_map({path}) -> {ok}")
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn not in CLASSES:
            continue
        try:
            ext = a.is_package_external()
        except Exception as ex:
            ext = f"? ({ex})"
        try:
            dls = [str(x) for x in a.get_data_layer_assets()] if hasattr(a, "get_data_layer_assets") else "n/a"
        except Exception as ex:
            dls = f"? ({ex})"
        log(f"{tag} {cn} {a.get_name()} external_package={ext} data_layers={dls} package={a.get_package().get_name() if hasattr(a, 'get_package') else '?'}")
        eas.set_selected_level_actors([a])
        unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT COPY")
        try:
            txt = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
        except Exception as ex:
            txt = f"clipboard read failed: {ex}"
        fn = os.path.join(OUT_DIR, f"ocean_t3d_{tag}_{cn}.t3d")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(txt)
        log(f"{tag} {cn}: wrote {fn} ({len(txt)} chars)")
log("=== done")
