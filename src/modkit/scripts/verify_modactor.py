import unreal
L = unreal.SN2GraphLibrary
bp = unreal.EditorAssetLibrary.load_asset("/Game/Mods/SN2Terrain/ModActor")
gen = unreal.load_class(None, "/Game/Mods/SN2Terrain/ModActor.ModActor_C")
cdo = unreal.get_default_object(gen)
for k in ("RegionCenter", "RegionRadius", "bActive", "LastStaticMeshCount"):
    print("[verify] var", k, "=", cdo.get_editor_property(k))
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
lib = unreal.SubobjectDataBlueprintFunctionLibrary
for h in sds.k2_gather_subobject_data_for_blueprint(bp):
    o = lib.get_object(lib.get_data(h))
    if isinstance(o, unreal.StaticMeshComponent):
        print("[verify] component", o.get_name(), o.get_editor_property("static_mesh").get_name(), o.get_editor_property("relative_location"))
