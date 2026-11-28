"""Runs INSIDE the Unreal editor. Creates the SN2EmptyWorld mod scaffold (ModActor + PAL, chunk 2) and builds its event graph
with the SN2GraphTools plugin (unreal.SN2GraphLibrary). Design: research/sn2/l_sn2world_map.md "Empty world".

Generated behaviour:
  BeginPlay: read + set cvar wp.Runtime.UpdateStreamingSources 0 (value read back into public vars; wp.Runtime.HLOD does not exist in this build);
             lobby -> UWELobbyStatics.SetWorldLevel(WORLD_LEVEL) then destroy self; L_SN2World (ocean is saved in the level) -> for every BP_UWEOceanBiomeRegionActor_C call KismetSystemLibrary.SetBytePropertyByName(BiomeRegionVolumeType, 1 = BRVT_Shape) (the saved value cannot persist: editor stub default is Shape, game default is Brush, so a saved Shape is never serialized), then destroy self; any other non-L_Main world -> destroy self;
             if current level == L_Main: bActive=true, call Purge once, looping 1 s timer -> Purge; else destroy self (lobby).
  Purge:     PurgeCount++; destroy creatures (UWEAIPawn/UWEAICharacter), UWEWorldPopGlobalResourcesDataStorage, and every actor whose
             name contains "_UAID_" unless it is a PlayerStart or its class display name is on the KEEP list; GC if anything was destroyed.
Re-runnable: clears the event graph and re-adds variables. Output lines start with [SN2EmptyWorld].
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2emptyworld_graph.py
"""
import unreal

MOD = "SN2EmptyWorld"
MOD_DIR = f"/Game/Mods/{MOD}"
BP_PATH = f"{MOD_DIR}/ModActor"
PAL_PATH = f"{MOD_DIR}/PAL_{MOD}"
CHUNK = 2
PURGE_INTERVAL = 1.0
WORLD_LEVEL = "/Game/Mods/SN2EmptyWorld/L_SN2World"

KEEP_BP = [
    "BP_Ocean_C", "BP_UWEOceanBiomeRegionActor_C", "BP_UWESky_C", "BP_StaticLifepod_Surface_C",
    "BP_LifePod_Lighting_Surface_C", "BP_LifepodManager_C", "BP_BioBed_Lifepod_C", "BP_Fabricator_Lifepod_C",
    "BP_LifepodWallLocker_C", "BP_ComputerTextInterface_Terminal_Mini_Lifepod_C", "BP_BaseRuntimeManager_C",
    "BP_BlightZoneManager_C", "BP_MPC_ScalabilityLinker_C", "BP_MeshBlend_Activator_C",
]
KEEP_NATIVE = ["WaterZone", "PCGWorldActor"]

L = unreal.SN2GraphLibrary
eal = unreal.EditorAssetLibrary
errors = []


def log(m):
    unreal.log(f"[SN2EmptyWorld] {m}")


def die(m):
    unreal.log_error(f"[SN2EmptyWorld] STOP: {m}")
    raise RuntimeError(m)


def _cls(path):
    c = unreal.load_class(None, path)
    if c is None:
        raise RuntimeError("class not found: " + path)
    return c


KML = _cls("/Script/Engine.KismetMathLibrary")
KSL = _cls("/Script/Engine.KismetSystemLibrary")
KSTR = _cls("/Script/Engine.KismetStringLibrary")
GS = _cls("/Script/Engine.GameplayStatics")
ARR = _cls("/Script/Engine.KismetArrayLibrary")
ACTOR = _cls("/Script/Engine.Actor")

# ---------- 1. scaffold ----------
tools = unreal.AssetToolsHelpers.get_asset_tools()


def used_chunk_ids():
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    ids = {}
    for ad in ar.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "PrimaryAssetLabel")):
        try:
            cid = ad.get_asset().get_editor_property("rules").get_editor_property("chunk_id")
            ids[str(ad.get_asset().get_path_name())] = cid
        except Exception:  # noqa: BLE001
            pass
    return ids


used = used_chunk_ids()
others = {p: c for p, c in used.items() if c == CHUNK and MOD not in p}
if others:
    die(f"chunk id {CHUNK} already used by {others}")
if not eal.does_asset_exist(BP_PATH):
    f = unreal.BlueprintFactory()
    f.set_editor_property("parent_class", unreal.Actor)
    tools.create_asset("ModActor", MOD_DIR, unreal.Blueprint, f)
    log(f"created {BP_PATH}")
if not eal.does_asset_exist(PAL_PATH):
    f = unreal.DataAssetFactory()
    f.set_editor_property("data_asset_class", unreal.PrimaryAssetLabel)
    lab = tools.create_asset(f"PAL_{MOD}", MOD_DIR, unreal.PrimaryAssetLabel, f)
    rules = lab.get_editor_property("rules")
    rules.set_editor_property("chunk_id", CHUNK)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    lab.set_editor_property("rules", rules)
    lab.set_editor_property("label_assets_in_my_directory", True)
    eal.save_asset(PAL_PATH, only_if_is_dirty=False)
    log(f"created {PAL_PATH} (chunk ids in use before: {sorted(set(used.values()))})")
lab = eal.load_asset(PAL_PATH)
r = lab.get_editor_property("rules")
if r.get_editor_property("chunk_id") != CHUNK:
    die(f"PAL chunk_id is {r.get_editor_property('chunk_id')}, expected {CHUNK}")
log(f"PAL chunk_id={r.get_editor_property('chunk_id')} cook_rule={r.get_editor_property('cook_rule')} "
    f"label_dir={lab.get_editor_property('label_assets_in_my_directory')}")

# ---------- 2. display-name check ----------
ocean = unreal.load_class(None, "/Game/Blueprints/World/Water/BP_Ocean.BP_Ocean_C")
if ocean is None:
    die("BP_Ocean_C not loadable")
disp = unreal.SystemLibrary.get_class_display_name(ocean)
log(f"get_class_display_name(BP_Ocean_C) = '{disp}'")
if disp.endswith("_C"):
    KEEP = KEEP_BP + KEEP_NATIVE
else:
    KEEP = [n[:-2] if n.endswith("_C") else n for n in KEEP_BP] + KEEP_NATIVE
log(f"KEEP ({len(KEEP)}): {KEEP}")

# ---------- 3. native classes ----------
def resolve(name, module_fallbacks, creature_walk=False):
    c = None
    try:
        c = getattr(unreal, name).static_class()
    except Exception as e:  # noqa: BLE001
        log(f"unreal.{name}.static_class() failed: {e!r}")
    if c is None:
        for m in module_fallbacks:
            c = unreal.load_class(None, f"/Script/{m}.{name}")
            if c is not None:
                break
    if c is None and creature_walk:
        cands = []
        import os
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        with open(os.path.join(repo, "src", "tools", "sn2_packaged_files.txt"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if "/Content/Blueprints/AI/Agents/" in line and line.endswith(".uasset") and "_Held" not in line:
                    cands.append(line)
        for line in cands[:200]:
            base = line.split("/Content/", 1)[1][:-len(".uasset")]
            nm = base.rsplit("/", 1)[1]
            k = unreal.load_class(None, f"/Game/{base}.{nm}_C")
            while k is not None:
                if k.get_name() == name:
                    c = k
                    break
                k = k.get_super_class()
            if c is not None:
                break
    return c


MODS = ["UWEAI", "UWEAIWorld", "UWEAIMovement", "UWEWorldPopulation2", "UWEGameplay", "Subnautica2"]
PLAYERSTART = unreal.PlayerStart.static_class()
AIPAWN = resolve("UWEAIPawn", MODS, True)
AICHAR = resolve("UWEAICharacter", MODS, True)
STORAGE = resolve("UWEWorldPopGlobalResourcesDataStorage", MODS)
for nm, c in (("PlayerStart", PLAYERSTART), ("UWEAIPawn", AIPAWN), ("UWEAICharacter", AICHAR), ("UWEWorldPopGlobalResourcesDataStorage", STORAGE)):
    log(f"resolved {nm} = {c.get_path_name() if c else None}")
if not (PLAYERSTART and AIPAWN and AICHAR):
    die("a creature/PlayerStart class could not be resolved")
# STORAGE is only needed by name (display-name compare), so it may stay unresolved

bp = eal.load_asset(BP_PATH)
g = L.get_event_graph(bp)
log(f"cleared {L.clear_graph(g)} nodes")

# ---------- 4. variables ----------
VARS = [
    ("bActive", "bool", False, "false"),
    ("CVarStreamingSourcesBefore", "int", False, "-1"),
    ("CVarStreamingSources", "int", False, "-1"),
    ("CVarHLODBefore", "int", False, "-1"),
    ("CVarHLOD", "int", False, "-1"),
    ("PurgeCount", "int", False, "0"),
    ("MapActorsDestroyed", "int", False, "0"),
    ("CreaturesDestroyed", "int", False, "0"),
    ("ResourceStorageDestroyed", "int", False, "0"),
    ("DestroyedThisPurge", "int", False, "0"),
    ("LastActorCount", "int", False, "-1"),
    ("DestroyedClassNames", "string", True, ""),
]
for name, cat, arr, default in VARS:
    if not L.add_member_variable(bp, name, cat, "", None, arr, default):
        errors.append(f"variable {name} not added")
L.compile_with_log(bp)

# ---------- node helpers ----------
_x = [0]
_n = [0]


def pos():
    _x[0] += 1
    return (_x[0] % 40) * 260, (_x[0] // 40) * 300


def must(node, what):
    if node is None:
        errors.append(f"could not create {what}")
        raise RuntimeError(f"could not create {what}")
    _n[0] += 1
    return node


def call(owner, fn, **defaults):
    n = must(L.add_call_function(g, owner, fn, *pos()), f"{owner.get_name()}.{fn}")
    for k, v in defaults.items():
        if isinstance(v, unreal.Object):
            L.set_pin_default_object(n, k, v)
        else:
            L.set_pin_default(n, k, str(v).lower() if isinstance(v, bool) else str(v))
    return n


def var(name, setter=False):
    return must(L.add_variable_node(bp, g, name, setter, *pos()), f"var {name}")


def link(a, pa, b, pb):
    r = L.connect(a, pa, b, pb)
    if r is None:
        pins_a = [p for p in L.describe_pins(a) if p.startswith("out")]
        pins_b = [p for p in L.describe_pins(b) if p.startswith("in")]
        errors.append(f"connect {a.get_name()}.{pa} -> {b.get_name()}.{pb} refused | from outs: {pins_a} | to ins: {pins_b}")
        return False
    return True


def macro(name):
    return must(L.add_standard_macro(g, name, *pos()), f"macro {name}")


def branch(cond_node, cond_pin):
    b = must(L.add_branch(g, *pos()), "branch")
    link(cond_node, cond_pin, b, "Condition")
    return b


def inc(counter, exec_from, exec_pin):
    get = var(counter)
    add = call(KML, "Add_IntInt", B=1)
    link(get, counter, add, "A")
    s = var(counter, True)
    link(add, "ReturnValue", s, counter)
    link(exec_from, exec_pin, s, "execute")
    return s


def set_const(name, value, exec_from, exec_pin):
    s = var(name, True)
    L.set_pin_default(s, name, value)
    link(exec_from, exec_pin, s, "execute")
    return s


def set_from(name, src, src_pin, exec_from, exec_pin):
    s = var(name, True)
    link(src, src_pin, s, name)
    link(exec_from, exec_pin, s, "execute")
    return s


def bool_op(fn, a, pa, b=None, pb=None):
    n = call(KML, fn)
    link(a, pa, n, "A")
    if b is not None:
        link(b, pb, n, "B")
    return n, "ReturnValue"


def console_cmd(cmd, exec_from, exec_pin):
    n = call(KSL, "ExecuteConsoleCommand", Command=cmd)
    link(exec_from, exec_pin, n, "execute")
    return n


def read_cvar_into(cvar_name, var_name, exec_from, exec_pin):
    """GetConsoleVariableIntValue is impure in this engine (has exec pins) -> put it on the exec chain. Returns (node, pin) to chain on."""
    n = call(KSL, "GetConsoleVariableIntValue", VariableName=cvar_name)
    impure = any(p.split()[1] == "execute" for p in L.describe_pins(n))
    if impure:
        link(exec_from, exec_pin, n, "execute")
        s = set_from(var_name, n, "ReturnValue", n, "then")
    else:
        s = set_from(var_name, n, "ReturnValue", exec_from, exec_pin)
    return s, "then"


def is_child(cls_node, cls_pin, parent):
    n = call(KML, "ClassIsChildOf")
    link(cls_node, cls_pin, n, "TestClass")
    L.set_pin_default_object(n, "ParentClass", parent)
    return n, "ReturnValue"


def destroy_and_count(exec_from, exec_pin, elem_node, elem_pin, counter, clsname_node):
    d = call(ACTOR, "K2_DestroyActor")
    link(exec_from, exec_pin, d, "execute")
    link(elem_node, elem_pin, d, "self")
    s1 = inc(counter, d, "then")
    s2 = inc("DestroyedThisPurge", s1, "then")
    au = call(ARR, "Array_AddUnique")
    link(var("DestroyedClassNames"), "DestroyedClassNames", au, "TargetArray")
    link(clsname_node, "ReturnValue", au, "NewItem")
    link(s2, "then", au, "execute")


try:
    # ---------- Purge event (created first so BeginPlay can call it) ----------
    purge = must(L.add_custom_event(g, "Purge", 0, 0), "Purge event")
    L.compile_with_log(bp)
    gen = unreal.load_class(None, BP_PATH + ".ModActor_C")
    direct_ok = False

    # ---------- BeginPlay ----------
    bpn = must(L.add_event_override(bp, g, "ReceiveBeginPlay", 0, -600), "BeginPlay")
    s1 = read_cvar_into("wp.Runtime.UpdateStreamingSources", "CVarStreamingSourcesBefore", bpn, "then")
    e1 = console_cmd("wp.Runtime.UpdateStreamingSources 0", *s1)
    s4 = read_cvar_into("wp.Runtime.UpdateStreamingSources", "CVarStreamingSources", e1, "then")
    lvl = call(GS, "GetCurrentLevelName", bRemovePrefixString=True)
    is_main = call(KSTR, "EqualEqual_StrStr", B="L_Main")
    link(lvl, "ReturnValue", is_main, "A")
    b0 = branch(is_main, "ReturnValue")
    if any(p.split()[1] == "execute" for p in L.describe_pins(lvl)):
        link(*s4, lvl, "execute")
        link(lvl, "then", b0, "execute")
    else:
        link(*s4, b0, "execute")
    act = set_const("bActive", "true", b0, "then")
    tail, tail_pin = act, "then"
    direct = L.add_call_function(g, gen, "Purge", *pos())
    if direct is not None:
        _n[0] += 1
        link(act, "then", direct, "execute")
        tail, tail_pin = direct, "then"
        direct_ok = True
    log(f"direct Purge call node created: {direct_ok}")
    timer = call(KSL, "K2_SetTimerDelegate", Time=PURGE_INTERVAL, bLooping=True)
    link(tail, tail_pin, timer, "execute")
    link(purge, "OutputDelegate", timer, "Delegate")
    # not L_Main: lobby -> select the replacement world level; anything else -> destroy self
    is_lobby = call(KSTR, "EqualEqual_StrStr", B="L_ClientLobby")
    link(lvl, "ReturnValue", is_lobby, "A")
    b1 = branch(is_lobby, "ReturnValue")
    link(b0, "else", b1, "execute")
    LOBBY = _cls("/Script/UWELobby.UWELobbyStatics")
    setwl = call(LOBBY, "SetWorldLevel", LevelName=WORLD_LEVEL)
    link(b1, "then", setwl, "execute")
    gone1 = call(ACTOR, "K2_DestroyActor")
    link(setwl, "then", gone1, "execute")
    # L_SN2World: the ocean is saved in the level itself (sn2world_map.py clears its CollisionBoxes) -> the ModActor only destroys itself
    is_new = call(KSTR, "EqualEqual_StrStr", B="L_SN2World")
    link(lvl, "ReturnValue", is_new, "A")
    b2 = branch(is_new, "ReturnValue")
    link(b1, "else", b2, "execute")
    # The editor's stub class default for BiomeRegionVolumeType is Shape, the game's real default is Brush, so a Shape saved in the map is never
    # serialized (research/sn1/README.md). Set it on the saved ocean region(s) here, then destroy self.
    OCEAN = _cls("/Game/Blueprints/World/Water/BP_UWEOceanBiomeRegionActor.BP_UWEOceanBiomeRegionActor_C")
    gao = call(GS, "GetAllActorsOfClass")
    L.set_pin_default_object(gao, "ActorClass", OCEAN)
    link(b2, "then", gao, "execute")
    fe2 = macro("ForEachLoop")
    link(gao, "then", fe2, "Exec")
    link(gao, "OutActors", fe2, "Array")
    sb = call(KSL, "SetBytePropertyByName", PropertyName="BiomeRegionVolumeType", Value=1)
    link(fe2, "LoopBody", sb, "execute")
    link(fe2, "Array Element", sb, "Object")
    # the SN1Biome_* boxes (BP_UWEWaterBiomeRegionActor_C) need the same Shape type, otherwise their volumes are ignored (2026-11-28)
    WATER = _cls("/Game/Blueprints/World/Water/BP_UWEWaterBiomeRegionActor.BP_UWEWaterBiomeRegionActor_C")
    gaw = call(GS, "GetAllActorsOfClass")
    L.set_pin_default_object(gaw, "ActorClass", WATER)
    link(fe2, "Completed", gaw, "execute")
    fe3 = macro("ForEachLoop")
    link(gaw, "then", fe3, "Exec")
    link(gaw, "OutActors", fe3, "Array")
    sbw = call(KSL, "SetBytePropertyByName", PropertyName="BiomeRegionVolumeType", Value=1)
    link(fe3, "LoopBody", sbw, "execute")
    link(fe3, "Array Element", sbw, "Object")
    gone3 = call(ACTOR, "K2_DestroyActor")
    link(fe3, "Completed", gone3, "execute")
    gone2 = call(ACTOR, "K2_DestroyActor")
    link(b2, "else", gone2, "execute")

    # ---------- Purge ----------
    p1 = inc("PurgeCount", purge, "then")
    p2 = set_const("DestroyedThisPurge", "0", p1, "then")
    ga = call(GS, "GetAllActorsOfClass")
    L.set_pin_default_object(ga, "ActorClass", ACTOR)
    link(p2, "then", ga, "execute")
    ln = call(ARR, "Array_Length")
    link(ga, "OutActors", ln, "TargetArray")
    p3 = set_from("LastActorCount", ln, "ReturnValue", ga, "then")
    fe = macro("ForEachLoop")
    link(p3, "then", fe, "Exec")
    link(ga, "OutActors", fe, "Array")
    ELEM = (fe, "Array Element")

    cls = call(GS, "GetObjectClass")
    link(*ELEM, cls, "Object")
    cname = call(KSL, "GetClassDisplayName")
    link(cls, "ReturnValue", cname, "Class")
    oname = call(KSL, "GetObjectName")
    link(*ELEM, oname, "Object")

    is_creature = bool_op("BooleanOR", *is_child(cls, "ReturnValue", AIPAWN), *is_child(cls, "ReturnValue", AICHAR))
    is_storage = call(KSTR, "EqualEqual_StrStr", B="UWEWorldPopGlobalResourcesDataStorage")
    link(cname, "ReturnValue", is_storage, "A")
    is_map = call(KSTR, "Contains", Substring="_UAID_")
    link(oname, "ReturnValue", is_map, "SearchIn")
    kept = is_child(cls, "ReturnValue", PLAYERSTART)
    for k in KEEP:
        eq = call(KSTR, "EqualEqual_StrStr", B=k)
        link(cname, "ReturnValue", eq, "A")
        kept = bool_op("BooleanOR", *kept, eq, "ReturnValue")
    not_kept = bool_op("Not_PreBool", *kept)
    map_cond = bool_op("BooleanAND", is_map, "ReturnValue", *not_kept)

    b_cr = branch(*is_creature)
    link(fe, "LoopBody", b_cr, "execute")
    destroy_and_count(b_cr, "then", *ELEM, "CreaturesDestroyed", cname)
    b_st = branch(is_storage, "ReturnValue")
    link(b_cr, "else", b_st, "execute")
    destroy_and_count(b_st, "then", *ELEM, "ResourceStorageDestroyed", cname)
    b_map = branch(*map_cond)
    link(b_st, "else", b_map, "execute")
    destroy_and_count(b_map, "then", *ELEM, "MapActorsDestroyed", cname)

    dts = var("DestroyedThisPurge")
    gt = call(KML, "Greater_IntInt", B=0)
    link(dts, "DestroyedThisPurge", gt, "A")
    bgc = branch(gt, "ReturnValue")
    link(fe, "Completed", bgc, "execute")
    gc = call(KSL, "CollectGarbage")
    link(bgc, "then", gc, "execute")
except Exception as ex:  # noqa: BLE001
    errors.append(f"EXCEPTION {ex!r}")

msgs = L.compile_with_log(bp)
ok = msgs is not None
for m in list(msgs or []):
    log(f"compiler: {m}")
log(f"{_n[0]} nodes created | {len(errors)} build errors | compile ok: {ok}")
for e in errors:
    log(f"ERROR {e}")
if ok and not errors:
    eal.save_asset(BP_PATH, only_if_is_dirty=False)
    eal.save_asset(PAL_PATH, only_if_is_dirty=False)
    log("ModActor + PAL saved")

    # ---------- CDO verification ----------
    gen = unreal.load_class(None, BP_PATH + ".ModActor_C")
    cdo = unreal.get_default_object(gen)
    expect = {"bActive": False, "CVarStreamingSourcesBefore": -1, "CVarStreamingSources": -1, "CVarHLODBefore": -1, "CVarHLOD": -1,
              "PurgeCount": 0, "MapActorsDestroyed": 0, "CreaturesDestroyed": 0, "ResourceStorageDestroyed": 0,
              "DestroyedThisPurge": 0, "LastActorCount": -1}
    bad = []
    for k, v in expect.items():
        try:
            got = cdo.get_editor_property(k)
        except Exception as e:  # noqa: BLE001
            got = f"ERR {e}"
        if got != v:
            bad.append((k, got, v))
    try:
        arr = list(cdo.get_editor_property("DestroyedClassNames"))
        if arr:
            bad.append(("DestroyedClassNames", arr, []))
    except Exception as e:  # noqa: BLE001
        bad.append(("DestroyedClassNames", f"ERR {e}", []))
    log(f"CDO check: {'all {} variables have their defaults'.format(len(expect) + 1) if not bad else 'MISMATCH ' + repr(bad)}")
