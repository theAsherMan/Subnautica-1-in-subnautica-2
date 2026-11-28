"""Runs INSIDE the editor. One-off: adds the ground AssetUserData (see sn1terrain_udata.py) to every existing SN1 terrain tile mesh
/Game/Mods/SN2EmptyWorld/SN1Terrain/SM_*_tile_* (sets spot1 and origin), saves them, then reloads one and reads the data back.
Idempotent. Run: python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn1terrain_ground_udata.py   (lines start with [SN1Ground])
"""
import os
import sys
import unreal

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
except NameError:
    pass
import importlib
import sn1terrain_udata as U  # noqa: E402
importlib.reload(U)  # the editor keeps imported modules between runs

ASSET_DIR = "/Game/Mods/SN2EmptyWorld/SN1Terrain"
eal = unreal.EditorAssetLibrary


def log(m):
    unreal.log("[SN1Ground] " + m)


paths = [p for p in eal.list_assets(ASSET_DIR, recursive=False, include_folder=False) if "_tile_" in p]
log(f"{len(paths)} tile assets")
added = ok = bad = 0
for p in sorted(paths):
    mesh = eal.load_asset(p.split(".")[0])
    if not isinstance(mesh, unreal.StaticMesh):
        continue
    try:
        r = U.add_ground_udata(mesh)
    except Exception as e:
        log(f"FAIL {p}: {e}")
        bad += 1
        continue
    if r == "added":
        eal.save_asset(p.split(".")[0], only_if_is_dirty=False)
        added += 1
    else:
        ok += 1
log(f"patched={added} alreadyOK={ok} failed={bad}")
if paths:
    chk = eal.load_asset(sorted(paths)[0].split(".")[0])
    cls = unreal.load_class(None, U.UDATA_CLASS)
    ud = chk.get_asset_user_data_of_class(cls)
    log(f"readback {chk.get_name()}: has_ground={U.has_ground_udata(chk)} data_assets={[d.get_path_name() for d in ud.get_editor_property('DataAssets')]}")
