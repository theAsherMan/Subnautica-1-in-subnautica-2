"""Print the start-selection data of every PlayerStart actor in a map (default: the built L_SN2World).
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/playerstart_probe.py     Output lines start with [PSProbe].
"""
import unreal

MAPS = ["/Game/Mods/SN2EmptyWorld/L_SN2World"]
PROPS = ["PlayerStartTag", "DefaultForGameModeClass", "bDefaultStart", "StartPriority", "Priority", "bEnabled",
         "bOnlyForGameModes", "GameModeClasses", "PlayerStoryGoals", "GrantTags", "RemoveTags", "InventoryItems", "EquippedItems"]


def log(s):
    unreal.log("[PSProbe] " + str(s))


for m in MAPS:
    unreal.EditorLevelLibrary.load_level(m) if hasattr(unreal.EditorLevelLibrary, "load_level") else None
    for a in unreal.EditorLevelLibrary.get_all_level_actors():
        if "PlayerStart" not in a.get_class().get_name():
            continue
        log("== %s class=%s loc=%s" % (a.get_name(), a.get_class().get_name(), a.get_actor_location()))
        for p in PROPS:
            try:
                log("   %s = %s" % (p, a.get_editor_property(p)))
            except Exception as e:  # noqa
                pass
        try:
            log("   ALLPROPS(export) = %s" % unreal.EditorLevelLibrary.get_actor_reference(a.get_path_name()))
        except Exception:
            pass
