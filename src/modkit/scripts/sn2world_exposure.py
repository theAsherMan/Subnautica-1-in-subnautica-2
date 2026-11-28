"""Runs INSIDE the Unreal editor. Idempotent: adds (or updates) one unbound PostProcessVolume in L_SN2World that fixes the auto-exposure bias at source.
Why: DS_Main_Day rewrites the sky post process AutoExposureBias to 0.5 every frame; SN1's look is about 2.3 EV brighter (research/features/biome_look.md §6c).
A PPV with Priority 10 and only bOverride_AutoExposureBias set wins over the sky PP for that one field.
Edit EXPOSURE_BIAS and rebake. Loads the CURRENT saved map, touches only the actor labelled SN2_ExposurePPV.
Run: python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2world_exposure.py   Lines start [Exposure].
"""
import unreal

MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"
LABEL = "SN2_ExposurePPV"
EXPOSURE_BIAS = 2.4
PRIORITY = 10.0


def log(m):
    unreal.log(f"[Exposure] {m}")


if not unreal.EditorLoadingAndSavingUtils.load_map(MAP):
    raise RuntimeError("load_map failed")
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
mine = [a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL]
if len(mine) > 1:
    raise RuntimeError(f"{len(mine)} actors labelled {LABEL}")
if mine:
    ppv = mine[0]
    log("updating existing volume")
else:
    ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
    ppv.set_actor_label(LABEL)
    log("spawned new volume")
ppv.set_editor_property("unbound", True)
ppv.set_editor_property("priority", PRIORITY)
ppv.set_editor_property("enabled", True)
st = ppv.get_editor_property("settings")
st.set_editor_property("override_auto_exposure_bias", True)
st.set_editor_property("auto_exposure_bias", EXPOSURE_BIAS)
ppv.set_editor_property("settings", st)
st2 = ppv.get_editor_property("settings")
log(f"unbound={ppv.get_editor_property('unbound')} priority={ppv.get_editor_property('priority')} "
    f"override={st2.get_editor_property('override_auto_exposure_bias')} bias={st2.get_editor_property('auto_exposure_bias')}")
log(f"save_current_level -> {les.save_current_level()}")
