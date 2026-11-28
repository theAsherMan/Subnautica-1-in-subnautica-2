"""Shared helper (imported by sn1terrain_import.py and sn1terrain_ground_udata.py; runs INSIDE the editor).
Makes a StaticMesh count as a buildable ground surface for the Habitat Builder: its AssetUserData must hold a
/Script/UWEAssetRegistry.UWEAssetUserData whose DataAssets contains a UWESurfaceSpawnData with a ground tag (research/features/README.md, base building section).
"""
import unreal

UDATA_CLASS = "/Script/UWEAssetRegistry.UWEAssetUserData"
GROUND_DATA = "/Game/Data/SurfaceSpawnData/DA_SandSurfaceData"   # tag WorldPopulation.SpawnPoint.Sand


def _udata(mesh, cls):
    return mesh.get_asset_user_data_of_class(cls)


def has_ground_udata(mesh):
    cls = unreal.load_class(None, UDATA_CLASS)
    ud = _udata(mesh, cls) if cls else None
    if not ud:
        return False
    das = ud.get_editor_property("DataAssets")
    return any(d and d.get_path_name().split(".")[0] == GROUND_DATA for d in das)


def add_ground_udata(mesh):
    """Idempotent. Returns 'added', 'ok' (already there) or raises. Caller saves the asset."""
    cls = unreal.load_class(None, UDATA_CLASS)
    if not cls:
        raise RuntimeError("class not loadable: " + UDATA_CLASS)
    data = unreal.load_asset(GROUND_DATA)
    if not data:
        raise RuntimeError("asset not loadable: " + GROUND_DATA)
    ud = _udata(mesh, cls)
    if not ud:
        mesh.add_asset_user_data_of_class(cls)
        ud = _udata(mesh, cls)
        if not ud:
            raise RuntimeError("add_asset_user_data_of_class gave no object")
    if has_ground_udata(mesh):
        return "ok"
    das = [d for d in ud.get_editor_property("DataAssets") if d]
    das.append(data)
    ud.set_editor_property("DataAssets", das)
    mesh.modify()
    return "added"
