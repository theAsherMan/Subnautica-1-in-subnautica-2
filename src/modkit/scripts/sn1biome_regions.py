"""Runs INSIDE the Unreal editor. Places one SN1 biome's water look in /Game/Mods/SN2EmptyWorld/L_SN2World as a set of box-shaped
BP_UWEWaterBiomeRegionActor_C actors, each carrying the converted WaterLightSettings (research/features/biome_look.md "Water colour / fog per area", research/features/biome_look.md §6).

  * input   : <Workspace>/sn1_biomes/<biome>.json, written by src/tools/sn1_biome_transfer.py (boxes in UE cm + water_light_t3d). Refuses if
              water_light_t3d is null (run the converter with --settings <SN1 waterbiomes dump> first).
  * biome   : first line of <Workspace>/sn1_biome_set.txt, default "safeShallows" (ue_run.py does not forward environment variables).
  * actors  : one region per box; location = center_ue, scale 1, WaterBoxVolumeComponent BoxExtent = half_ue (class default 0; the modkit C++ is a stub,
              so SetBoxExtent does nothing in the editor; the component is a UWEVolumeTracker.BoxVolumeComponent, not an engine BoxComponent,
              and box_extent is not exposed: set in the T3D text), BiomeRegionVolumeType = BRVT_Shape (class default BRVT_Brush; not exposed to Python, set in the
              T3D text), tags "SN1Biome" + "SN1Biome_<biome>", label "SN1Biome_<biome>_<i>", outliner folder "SN1Biome/<biome>".
  * settings: BiomeVolumeComponent.WaterLightSettings is not exposed to Python, so it goes in as T3D text (same method as sn2world_map.py
              paste_region_with_water_light): EDIT COPY all new regions -> add "WaterLightSettings=(...)" to every BiomeVolumeComponent property
              block -> destroy -> EDIT PASTE -> re-copy and check every pasted region carries it.
Idempotent per biome: deletes only actors tagged "SN1Biome_<biome>" first. MUST be re-run after a rebuild of L_SN2World (sn2world_map.py makes a
fresh level). Self-check: reload from disk, assert count / transforms / WaterFogDistance of every region.
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn1biome_regions.py        Output lines start with [SN1Biome].
"""
import json
import os
import re
import subprocess
import time
import unreal

MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"
REGION_PATH = "/Game/Blueprints/World/Water/BP_UWEWaterBiomeRegionActor.BP_UWEWaterBiomeRegionActor_C"
REGION_CLS = "BP_UWEWaterBiomeRegionActor_C"
TAG = "SN1Biome"
T0 = time.time()


def log(m):
    unreal.log(f"[SN1Biome] {m}")


def die(m):
    unreal.log_error(f"[SN1Biome] STOP: {m}")
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


def _biome():
    try:
        with open(os.path.join(WS, "sn1_biome_set.txt"), encoding="utf-8") as f:
            n = f.readline().strip()
            if n:
                return n
    except OSError:
        pass
    return "safeShallows"


BIOME = _biome()
SET_TAG = f"{TAG}_{BIOME}"
FOLDER = f"{TAG}/{BIOME}"
plan_path = os.path.join(WS, "sn1_biomes", BIOME + ".json")
with open(plan_path, encoding="utf-8") as f:
    PLAN = json.load(f)
WL = PLAN.get("water_light_t3d")
if not WL:
    die(f"{plan_path} has no water_light_t3d: run src/tools/sn1_biome_transfer.py {BIOME} --settings <waterbiomes dump> first")
m = re.search(r"WaterFogDistance=([-0-9.eE+]+)", WL)
WANT_FOG = float(m.group(1)) if m else None
BOXES = PLAN["boxes"]
log(f"biome {BIOME}: {len(BOXES)} boxes from {plan_path}; WaterLightSettings={WL}")

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def clip_get():
    return subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")


def clip_set(txt):
    rc = subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"], input=txt.encode("utf-8"),
                        capture_output=True, timeout=120)
    if rc.returncode != 0:
        die(f"Set-Clipboard failed: {rc.stderr[:200]!r}")


def copy_t3d(actors):
    eas.set_selected_level_actors(actors)
    unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT COPY")
    return clip_get()


def mine():
    return [a for a in eas.get_all_level_actors() if SET_TAG in [str(t) for t in a.tags]]


def fog_values(txt):
    """WaterFogDistance of every WaterLightSettings= in a T3D text."""
    return [float(x) for x in re.findall(r"WaterLightSettings=\(.*?WaterFogDistance=([-0-9.eE+]+)", txt)]


def actor_blocks(txt):
    """Split a T3D text into (actor label, actor block text) pairs, in order; the text between blocks is returned as (None, text)."""
    out, pos = [], 0
    for m in re.finditer(r"[ \t]*Begin Actor .*?End Actor[^\n]*\n", txt, re.S):
        out.append((None, txt[pos:m.start()]))
        lab = re.search(r'ActorLabel="([^"]+)"', m.group(0))
        out.append((lab.group(1) if lab else "", m.group(0)))
        pos = m.end()
    out.append((None, txt[pos:]))
    return out


def insert_after_line(block, marker, line):
    i = block.find(marker)
    if i < 0:
        die(f"T3D actor block has no '{marker}'")
    eol = block.find("\n", i)
    return block[:eol + 1] + "            " + line + "\r\n" + block[eol + 1:]


def box_index(lab):
    try:
        return int(lab.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return None


# ---------- 1. load map, remove this biome's previous regions ----------
if not unreal.EditorLoadingAndSavingUtils.load_map(MAP):
    die(f"load_map({MAP}) failed")
old = mine()
for a in old:
    eas.destroy_actor(a)
log(f"removed {len(old)} previous {SET_TAG} actors")

cls = unreal.load_class(None, REGION_PATH)
if cls is None:
    die(f"load_class({REGION_PATH}) returned None")

# ---------- 2. spawn one region per plan box (transform, label, tags, folder) ----------
spawned = []
for i, b in enumerate(BOXES):
    a = eas.spawn_actor_from_class(cls, unreal.Vector(*b["center_ue"]), unreal.Rotator(0, 0, 0))
    if a is None:
        die(f"spawn_actor_from_class failed for box {i}")
    a.set_actor_scale3d(unreal.Vector(1, 1, 1))
    a.set_actor_label(f"{SET_TAG}_{i:03d}")
    a.tags = [unreal.Name(TAG), unreal.Name(SET_TAG)]
    a.set_folder_path(FOLDER)
    spawned.append(a)
log(f"spawned {len(spawned)} regions")

# ---------- 3. BoxExtent, volume type and WaterLightSettings through T3D ----------
# The modkit's C++ is a stub: SetBoxExtent / GetUnscaledBoxExtent do nothing in the editor, and none of these properties is exposed to Python.
txt = copy_t3d(spawned)
if "WaterLightSettings=" in txt or "BoxExtent=" in txt or "BRVT_Shape" in txt:
    die("fresh regions already carry WaterLightSettings / BoxExtent / BRVT_Shape in T3D (unexpected; would duplicate)")
parts, n = [], 0
for lab, blk in actor_blocks(txt):
    if lab is None:
        parts.append(blk)
        continue
    i = box_index(lab)
    if i is None or not lab.startswith(SET_TAG) or i >= len(BOXES):
        die(f"unexpected actor in the copied T3D: {lab!r}")
    h = BOXES[i]["half_ue"]
    if blk.count("BiomeRegionVolumeType=BRVT_Brush") != 1:
        die(f"{lab}: T3D has no single 'BiomeRegionVolumeType=BRVT_Brush' line")
    # a fresh spawn exports BRVT_Brush; after the paste the line is gone = equals the class default, BRVT_Shape (2026-11-26 T3D dump)
    blk = blk.replace("BiomeRegionVolumeType=BRVT_Brush", "BiomeRegionVolumeType=BRVT_Shape")
    blk = insert_after_line(blk, 'Begin Object Name="WaterBoxVolumeComponent"', f"BoxExtent=(X={h[0]:.6f},Y={h[1]:.6f},Z={h[2]:.6f})")
    blk = insert_after_line(blk, 'Begin Object Name="BiomeVolumeComponent"', "WaterLightSettings=" + WL)
    parts.append(blk)
    n += 1
if n != len(spawned):
    die(f"T3D of {len(spawned)} regions has {n} actor blocks")
clip_set("".join(parts))
for a in spawned:
    eas.destroy_actor(a)
unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "EDIT PASTE")
eas.set_selected_level_actors([])


def check(tag):
    regs = sorted(mine(), key=lambda a: a.get_actor_label())
    ok = len(regs) == len(BOXES)
    log(f"[{tag}] {len(regs)} {SET_TAG} regions (want {len(BOXES)})")
    for a in regs:
        lab = a.get_actor_label()
        i = box_index(lab)
        if i is None or i >= len(BOXES):
            log(f"[{tag}] BAD label {lab}")
            ok = False
            continue
        b = BOXES[i]
        l, s = a.get_actor_location(), a.get_actor_scale3d()
        okt = all(abs(v - w) <= 1.0 for v, w in zip((l.x, l.y, l.z), b["center_ue"])) and \
            all(abs(v - 1.0) <= 1e-3 for v in (s.x, s.y, s.z)) and a.get_class().get_name() == REGION_CLS
        if not okt:
            log(f"[{tag}] BAD {lab}: loc ({l.x:.0f},{l.y:.0f},{l.z:.0f}) scale ({s.x:.2f},{s.y:.2f},{s.z:.2f}) want {b['center_ue']} scale 1")
            ok = False
    back = copy_t3d(regs)
    eas.set_selected_level_actors([])
    nblk, bad = 0, []
    for lab, blk in actor_blocks(back):
        if lab is None:
            continue
        nblk += 1
        i = box_index(lab)
        m = re.search(r"BoxExtent=\(X=([-0-9.eE+]+),Y=([-0-9.eE+]+),Z=([-0-9.eE+]+)\)", blk)
        fog = fog_values(blk)
        good = i is not None and i < len(BOXES) and m is not None and \
            all(abs(float(m.group(k + 1)) - BOXES[i]["half_ue"][k]) <= 0.5 for k in range(3)) and \
            ("BRVT_Brush" not in blk or tag != "in memory") and len(fog) == 1 and \
            (WANT_FOG is None or abs(fog[0] - WANT_FOG) <= 1e-3 * abs(WANT_FOG) + 1e-3)
        if not good:
            bad.append(lab)
    # After a reload the editor shows BRVT_Brush again (construction on load; the saved file has no volume-type delta = class default Shape,
    # 2026-11-26), so only the in-memory check requires "no BRVT_Brush". Which value the cooked game uses: see research/features/README.md.
    log(f"[{tag}] regions showing BRVT_Brush: {back.count('BiomeRegionVolumeType=BRVT_Brush')}")
    okf = nblk == len(BOXES) and not bad
    k = back.find("BoxExtent=")
    log(f"[{tag}] T3D: {nblk} region blocks, bad (BoxExtent / no BRVT_Brush / WaterFogDistance {WANT_FOG}): {bad[:5]} -> {'ok' if okf else 'BAD'}; "
        f"sample {back[k:k + 120]!r}")
    return ok and okf

if not check("in memory"):
    die("in-memory check failed (level NOT saved)")
saved = les.save_current_level()
log(f"save_current_level -> {saved}")
if not saved:
    die("save failed")
if not unreal.EditorLoadingAndSavingUtils.load_map(MAP):
    die("reload failed")
if not check("after reload"):
    die("after-reload check failed")
log(f"DONE {BIOME}: {len(BOXES)} regions in {time.time() - T0:.1f} s. Next: tools/cook_install.sh SN2EmptyWorld 2")
