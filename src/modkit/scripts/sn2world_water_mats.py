"""Runs INSIDE the Unreal editor. Bakes a water-volume material (MaterialInstanceConstant of /Game/Materials/Water/MI_OceanVolume) into every
water region of L_SN2World: the standalone BP_UWEOceanBiomeRegionActor_C_1 (L_Main values) and the SN1Biome_<biome> boxes (converted SN1 values
from <Workspace>/sn1_biomes/<biome>.json "water_light_t3d"). Why: native AUWEWaterBiomeRegionActor::RecreateMaterials builds that MID only in the
editor construction script and the modkit C++ is a stub, so without this every region shipped a generic MID with 2 scalars (research/10 §6
"Brown / dry-land water").

  * assets : /Game/Mods/SN2EmptyWorld/WaterVolume/MI_WV_Ocean and MI_WV_SS_<NNN> (one per box; <NNN> = box index). Re-run replaces their values.
  * regions: WaterStaticMeshComponent.OverrideMaterials[0] = the MIC (component.set_material(0, mic)); level saved.
  * mapping WaterLightSettings field -> MI_OceanVolume parameter:
      BiomeExtinction (RGB)                      -> vector BiomeExtinctionColorDirectionalLight
      BiomeExtinctionSkylight (RGB)              -> vector BiomeExtinctionColorSkylight
      BiomeExtinctionScaleDirectionalLight       -> scalar BiomeExtinctionDistanceDirectionalLight
      BiomeExtinctionScaleSkylight               -> scalar BiomeExtinctionDistanceSkylight
      BiomeAlbedo (RGB)                          -> vector BiomeAlbedo
      WaterFogDistance                           -> scalar WaterFogDistance, and 1/x -> WaterFogDistanceRcp
      WaterFogThickness                          -> scalar WaterFogThickness
      WaterFogBaseThickness                      -> scalar BaseWaterFogThickness
    All other parameters take the L_Main values (BiomeAlbedoDesaturation 0, BiomeAlbedoBrightness 1, BiomeNeutralizationNear/Far 0,
    WaterFogOpacityWeight 1, CurrentWaterBodyIndex 0, CurrentWaterBodyBlendType 1, BiomeAlbedoPower/Tint (1,1,1,1), BiomeEmissive (0,0,0,1)).
    BasePropertyOverrides.BlendMode = BLEND_TranslucentGreyTransmittance on every MIC.
  * biome  : first line of <Workspace>/sn1_biome_set.txt, default "safeShallows".
Self-check: reload the map, assert every region's component material is its MIC with the wanted parameter values.
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2world_water_mats.py        Output lines start with [WaterMats].
"""
import json
import os
import re
import unreal

MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"
DIR = "/Game/Mods/SN2EmptyWorld/WaterVolume"
PARENT = "/Game/Materials/Water/MI_OceanVolume"
OCEAN_CLASS = "BP_UWEOceanBiomeRegionActor_C"


def log(m):
    unreal.log(f"[WaterMats] {m}")


def die(m):
    unreal.log_error(f"[WaterMats] STOP: {m}")
    raise RuntimeError(m)


def _workspace():
    w = os.environ.get("SN2_WORKSPACE")
    if w:
        return w
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with open(os.path.join(repo, "local.config"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("SN2_WORKSPACE="):
                return line.split("=", 1)[1].strip().strip('"')
    die("SN2_WORKSPACE not set and not in local.config")


WS = _workspace()
try:
    with open(os.path.join(WS, "sn1_biome_set.txt"), encoding="utf-8") as f:
        BIOME = f.readline().strip() or "safeShallows"
except OSError:
    BIOME = "safeShallows"
SET_TAG = f"SN1Biome_{BIOME}"
with open(os.path.join(WS, "sn1_biomes", BIOME + ".json"), encoding="utf-8") as f:
    WL = json.load(f).get("water_light_t3d")
if not WL:
    die("plan json has no water_light_t3d")

# L_Main values (UWPROBE CAT_0 MAT, run 20261127_170201_uwprobe_lmain)
BASE_S = {
    "BiomeExtinctionDistanceDirectionalLight": 12.5, "BiomeExtinctionDistanceSkylight": 17.5, "BiomeAlbedoDesaturation": 0.0,
    "BiomeAlbedoBrightness": 1.0, "BiomeNeutralizationNear": 0.0, "BiomeNeutralizationFar": 0.0, "WaterFogDistanceRcp": 1.0 / 7500.0,
    "WaterFogDistance": 7500.0, "WaterFogThickness": 10.0, "BaseWaterFogThickness": 4.0, "WaterFogOpacityWeight": 1.0,
    "CurrentWaterBodyIndex": 0.0, "CurrentWaterBodyBlendType": 1.0,
}
BASE_V = {
    "BiomeExtinctionColorDirectionalLight": (0.90725, 0.94516, 0.955, 1.0), "BiomeExtinctionColorSkylight": (0.90725, 0.94516, 0.955, 1.0),
    "BiomeAlbedo": (0.1, 0.295, 1.0, 1.0), "BiomeAlbedoPower": (1.0, 1.0, 1.0, 1.0), "BiomeAlbedoTint": (1.0, 1.0, 1.0, 1.0),
    "BiomeEmissive": (0.0, 0.0, 0.0, 1.0),
}


def rgb(name):
    m = re.search(name + r"=\(R=([-0-9.eE+]+),G=([-0-9.eE+]+),B=([-0-9.eE+]+)", WL)
    if not m:
        die(f"WaterLightSettings has no {name}")
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)), 1.0)


def num(name):
    m = re.search(r"[(,]" + name + r"=([-0-9.eE+]+)", WL)
    if not m:
        die(f"WaterLightSettings has no {name}")
    return float(m.group(1))


SS_S, SS_V = dict(BASE_S), dict(BASE_V)
SS_V["BiomeExtinctionColorDirectionalLight"] = rgb("BiomeExtinction")
SS_V["BiomeExtinctionColorSkylight"] = rgb("BiomeExtinctionSkylight")
SS_V["BiomeAlbedo"] = rgb("BiomeAlbedo")
SS_S["BiomeExtinctionDistanceDirectionalLight"] = num("BiomeExtinctionScaleDirectionalLight")
SS_S["BiomeExtinctionDistanceSkylight"] = num("BiomeExtinctionScaleSkylight")
SS_S["WaterFogDistance"] = num("WaterFogDistance")
SS_S["WaterFogDistanceRcp"] = 1.0 / SS_S["WaterFogDistance"]
SS_S["WaterFogThickness"] = num("WaterFogThickness")
SS_S["BaseWaterFogThickness"] = num("WaterFogBaseThickness")

# ---- calibration overrides (2026-11-28): applied to the ocean MIC and the box MICs alike, edited per bake iteration ----
TUNE_S = {}
TUNE_V = {"BiomeAlbedo": (0.02, 0.45, 1.0, 1.0),
          "BiomeExtinctionColorDirectionalLight": (0.40, 0.92, 0.97, 1.0), "BiomeExtinctionColorSkylight": (0.40, 0.92, 0.97, 1.0)}
TUNE_MUL = {}  # empty = original L_Main ocean values / converted SN1 box values (reset 2026-11-28)
for _d, _t in ((BASE_S, TUNE_S), (SS_S, TUNE_S), (BASE_V, TUNE_V), (SS_V, TUNE_V)):
    _d.update(_t)
for _d in (BASE_S, SS_S):
    for _k, _m in TUNE_MUL.items():
        _d[_k] *= _m

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
parent = unreal.load_asset(PARENT)
if parent is None:
    die("parent MI_OceanVolume not found")


def make_mic(name, S, V):
    path = f"{DIR}/{name}"
    if eal.does_asset_exist(path):
        mic = unreal.load_asset(path)
    else:
        mic = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DIR, unreal.MaterialInstanceConstant,
                                                                      unreal.MaterialInstanceConstantFactoryNew())
    if mic is None:
        die(f"create/load {path} failed")
    mel.set_material_instance_parent(mic, parent)
    mic.set_editor_property("scalar_parameter_values", [])  # drop stale entries of earlier runs
    mic.set_editor_property("vector_parameter_values", [])
    for k, v in S.items():
        # returns False for parameters the modkit's (cooked, partly stripped) M_OceanVolume does not list, but still stores them (VERIFIED 2026-11-27)
        mel.set_material_instance_scalar_parameter_value(mic, k, float(v))
    for k, v in V.items():
        mel.set_material_instance_vector_parameter_value(mic, k, unreal.LinearColor(*v))
    bpo = unreal.MaterialInstanceBasePropertyOverrides()
    bpo.set_editor_property("override_blend_mode", True)
    bpo.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)  # BLEND_TranslucentGreyTransmittance is an alias of BLEND_Translucent in 5.6
    mic.set_editor_property("base_property_overrides", bpo)
    mel.update_material_instance(mic)
    if not eal.save_asset(path, only_if_is_dirty=False):
        die(f"save_asset {path} failed")
    return mic


if not unreal.EditorLoadingAndSavingUtils.load_map(MAP):
    die("load_map failed")

targets = []  # (actor, mic name, S, V)
boxes = sorted([a for a in eas.get_all_level_actors() if SET_TAG in [str(t) for t in a.tags]], key=lambda a: a.get_actor_label())
ocean = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == OCEAN_CLASS]  # object names are not stable across saves (_1, _3 ...)
if len(ocean) != 1:
    die(f"{len(ocean)} actors of class {OCEAN_CLASS} (expected 1)")
targets.append((ocean[0], "MI_WV_Ocean", BASE_S, BASE_V))
for a in boxes:
    i = int(a.get_actor_label().rsplit("_", 1)[1])
    targets.append((a, f"MI_WV_SS_{i:03d}", SS_S, SS_V))
log(f"{len(boxes)} {SET_TAG} boxes + ocean region")


def smc(actor):
    cs = [c for c in actor.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == "WaterStaticMeshComponent"]
    if len(cs) != 1:
        die(f"{actor.get_name()}: {len(cs)} WaterStaticMeshComponent")
    return cs[0]


targets = [(a.get_name(), name, S, V, a) for a, name, S, V in targets]
for _n, name, S, V, a in targets:
    mic = make_mic(name, S, V)
    c = smc(a)
    c.set_material(0, mic)
    a.modify()
saved = les.save_current_level()
log(f"save_current_level -> {saved}")
if not saved:
    die("save failed")
if not unreal.EditorLoadingAndSavingUtils.load_map(MAP):
    die("reload failed")

# ---------- self-check after reload ----------
bad = 0
actors = {a.get_name(): a for a in eas.get_all_level_actors()}
for a0n, name, S, V, _stale in targets:
    a = actors.get(a0n)
    if a is None:
        log(f"BAD missing {a0n}")
        bad += 1
        continue
    m = smc(a).get_material(0)
    ok = m is not None and m.get_name() == name and m.get_class().get_name() == "MaterialInstanceConstant"
    if ok:
        ns = len(m.get_editor_property("scalar_parameter_values"))
        nv = len(m.get_editor_property("vector_parameter_values"))
        fd = mel.get_material_instance_scalar_parameter_value(m, "WaterFogDistance")
        ok = ns == len(S) and nv == len(V) and abs(fd - S["WaterFogDistance"]) < 1e-3 * S["WaterFogDistance"]
        bo = m.get_editor_property("base_property_overrides")
        ok = ok and bo.get_editor_property("override_blend_mode")
        if name == "MI_WV_Ocean" or name.endswith("_000"):
            log(f"{name}: {ns} scalars {nv} vectors fog={fd} blend={bo.get_editor_property('blend_mode')} parent={m.get_editor_property('parent').get_name()}")
    if not ok:
        log(f"BAD {a0n} material={m.get_path_name() if m else None} want {name}")
        bad += 1
log(f"self-check: {len(targets)} regions, {bad} bad")
if bad:
    die("self-check failed")
log("DONE. Next: tools/cook_install.sh SN2EmptyWorld 2")
