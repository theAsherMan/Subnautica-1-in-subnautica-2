"""Runs INSIDE the Unreal editor. Builds the SN2Terrain ModActor event graph that clears SN2 terrain in a circular region
(port of the former Lua mod SN2TerrainEdit's region sweep), using the SN2GraphTools editor plugin (unreal.SN2GraphLibrary).

Behaviour of the generated graph:
  BeginPlay: if current level == L_Main -> bActive=true, looping timer (SweepInterval s) -> Sweep;  else -> destroy this actor (no mesh in the lobby).
  Sweep:  SweepCount++ ; DestroyedThisSweep=0
          1. every LandscapeStreamingProxy whose XY bounds box touches the circle -> DestroyActor, TilesDestroyed++
          2. if the StaticMeshActor count changed since the last scan (= cells streamed in/out):
             every Actor whose location is inside the circle and whose class is StaticMeshActor | PrefabActor | BP_PCG_* |
             under /Game/Art/Environment/ (but not /Game/Art/Environment/Set/) -> DestroyActor, DressingDestroyed++ ; ScanCount++
          3. if anything was destroyed this sweep -> CollectGarbage
  Same rules as the Lua isDressing()/regionFor(). Counters are public variables so Lua can log them.
Re-runnable: clears the event graph and recreates variables. Output lines start with [SN2Graph].
"""
import unreal

BP_PATH = "/Game/Mods/SN2Terrain/ModActor"
CENTER = (-331747.0, 420670.0)
RADIUS = 30000.0
SWEEP_INTERVAL = 1.5

L = unreal.SN2GraphLibrary
# load by engine path: Python renames some classes (KismetMathLibrary -> MathLibrary, ...)
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
errors = []


def log(m):
    unreal.log(f"[SN2Graph] {m}")


bp = unreal.EditorAssetLibrary.load_asset(BP_PATH)
g = L.get_event_graph(bp)
log(f"cleared {L.clear_graph(g)} nodes")

# ---------- variables ----------
VARS = [
    ("RegionCenter", "struct", "", unreal.Vector.static_struct(), f"X={CENTER[0]},Y={CENTER[1]},Z=0"),
    ("RegionRadius", "real", "double", None, str(RADIUS)),
    ("bActive", "bool", "", None, "false"),
    ("SweepCount", "int", "", None, "0"),
    ("ScanCount", "int", "", None, "0"),
    ("TilesDestroyed", "int", "", None, "0"),
    ("DressingDestroyed", "int", "", None, "0"),
    ("DestroyedThisSweep", "int", "", None, "0"),
    ("LastStaticMeshCount", "int", "", None, "-1"),
]
for name, cat, sub, obj, default in VARS:
    ok = L.add_member_variable(bp, name, cat, sub, obj, False, default)
    if not ok:
        errors.append(f"variable {name} not added")
L.compile_with_log(bp)   # skeleton class must know the variables before getter/setter nodes are made

# ---------- node helpers ----------
_x = [0]


def pos():
    _x[0] += 1
    return (_x[0] % 40) * 260, (_x[0] // 40) * 300


def must(node, what):
    if node is None:
        errors.append(f"could not create {what}")
        raise RuntimeError(f"could not create {what}")
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
    # UE Python: bool+out-param functions return the out-param, or None when the bool is false
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
    """exec_from.exec_pin -> counter = counter + 1 ; returns the setter (chain on 'then')."""
    get = var(counter)
    add = call(KML, "Add_IntInt", B=1)
    link(get, counter, add, "A")
    s = var(counter, True)
    link(add, "ReturnValue", s, counter)
    link(exec_from, exec_pin, s, "execute")
    return s


def actors_of(cls_obj, exec_from, exec_pin):
    n = call(GS, "GetAllActorsOfClass")
    L.set_pin_default_object(n, "ActorClass", cls_obj)
    link(exec_from, exec_pin, n, "execute")
    return n


def destroy_and_count(exec_from, exec_pin, elem_node, elem_pin, counter):
    d = call(ACTOR, "K2_DestroyActor")
    link(exec_from, exec_pin, d, "execute")
    link(elem_node, elem_pin, d, "self")
    s1 = inc(counter, d, "then")
    inc("DestroyedThisSweep", s1, "then")


def center_xy():
    c = var("RegionCenter")
    br = call(KML, "BreakVector")
    link(c, "RegionCenter", br, "InVec")
    return br


def in_box_cond(origin_node, origin_pin, extent_node, extent_pin):
    """bool node: XY box (origin, extent) touches the circle. Returns (node, pin)."""
    c = center_xy()
    o = call(KML, "BreakVector")
    link(origin_node, origin_pin, o, "InVec")
    e = call(KML, "BreakVector")
    link(extent_node, extent_pin, e, "InVec")
    sq = []
    for axis in ("X", "Y"):
        sub = call(KML, "Subtract_DoubleDouble")
        link(c, axis, sub, "A")
        link(o, axis, sub, "B")
        ab = call(KML, "Abs")
        link(sub, "ReturnValue", ab, "A")
        sub2 = call(KML, "Subtract_DoubleDouble")
        link(ab, "ReturnValue", sub2, "A")
        link(e, axis, sub2, "B")
        mx = call(KML, "FMax", B=0)
        link(sub2, "ReturnValue", mx, "A")
        mul = call(KML, "Multiply_DoubleDouble")
        link(mx, "ReturnValue", mul, "A")
        link(mx, "ReturnValue", mul, "B")
        sq.append(mul)
    add = call(KML, "Add_DoubleDouble")
    link(sq[0], "ReturnValue", add, "A")
    link(sq[1], "ReturnValue", add, "B")
    r = var("RegionRadius")
    r2 = call(KML, "Multiply_DoubleDouble")
    link(r, "RegionRadius", r2, "A")
    link(r, "RegionRadius", r2, "B")
    le = call(KML, "LessEqual_DoubleDouble")
    link(add, "ReturnValue", le, "A")
    link(r2, "ReturnValue", le, "B")
    return le, "ReturnValue"


def in_circle_cond(elem_node, elem_pin):
    loc = call(ACTOR, "K2_GetActorLocation")
    link(elem_node, elem_pin, loc, "self")
    c = var("RegionCenter")
    d = call(KML, "Vector_Distance2D")
    link(loc, "ReturnValue", d, "v1")
    link(c, "RegionCenter", d, "v2")
    r = var("RegionRadius")
    le = call(KML, "LessEqual_DoubleDouble")
    link(d, "ReturnValue", le, "A")
    link(r, "RegionRadius", le, "B")
    return le, "ReturnValue"


def bool_op(fn, a, pa, b=None, pb=None):
    n = call(KML, fn)
    link(a, pa, n, "A")
    if b is not None:
        link(b, pb, n, "B")
    return n, "ReturnValue"


def is_dressing_cond(elem_node, elem_pin):
    """Same rules as Lua isDressing(): exact class names, BP_PCG_ prefix, /Game/Art/Environment/ minus /Set/."""
    cls = call(GS, "GetObjectClass")
    link(elem_node, elem_pin, cls, "Object")
    # class pins don't connect to Object pins -> class-specific helpers
    name = call(KSL, "GetClassDisplayName")
    link(cls, "ReturnValue", name, "Class")
    soft = call(KSL, "Conv_ClassToSoftClassReference")
    link(cls, "ReturnValue", soft, "Class")
    path = call(KSL, "Conv_SoftClassReferenceToString")
    link(soft, "ReturnValue", path, "SoftClassReference")
    eq_sma = call(KSTR, "EqualEqual_StrStr", B="StaticMeshActor")
    link(name, "ReturnValue", eq_sma, "A")
    eq_pre = call(KSTR, "EqualEqual_StrStr", B="PrefabActor")
    link(name, "ReturnValue", eq_pre, "A")
    pcg = call(KSTR, "StartsWith", InPrefix="BP_PCG_")
    link(name, "ReturnValue", pcg, "SourceString")
    env = call(KSTR, "Contains", Substring="/Game/Art/Environment/")
    link(path, "ReturnValue", env, "SearchIn")
    setp = call(KSTR, "Contains", Substring="/Game/Art/Environment/Set/")
    link(path, "ReturnValue", setp, "SearchIn")
    not_set = bool_op("Not_PreBool", setp, "ReturnValue")
    env_ok = bool_op("BooleanAND", env, "ReturnValue", *not_set)
    o1 = bool_op("BooleanOR", eq_sma, "ReturnValue", eq_pre, "ReturnValue")
    o2 = bool_op("BooleanOR", *o1, pcg, "ReturnValue")
    return bool_op("BooleanOR", *o2, *env_ok)


try:
    # ---------- BeginPlay ----------
    bpn = must(L.add_event_override(bp, g, "ReceiveBeginPlay", 0, -600), "BeginPlay")
    sweep = must(L.add_custom_event(g, "Sweep", 0, 0), "Sweep event")
    lvl = call(GS, "GetCurrentLevelName", bRemovePrefixString=True)
    is_main = call(KSTR, "EqualEqual_StrStr", B="L_Main")
    link(lvl, "ReturnValue", is_main, "A")
    b0 = branch(is_main, "ReturnValue")
    if any(p.split()[1] == "execute" for p in L.describe_pins(lvl)):   # impure -> must be on the exec chain
        link(bpn, "then", lvl, "execute")
        link(lvl, "then", b0, "execute")
    else:
        link(bpn, "then", b0, "execute")
    act = var("bActive", True)
    L.set_pin_default(act, "bActive", "true")
    link(b0, "then", act, "execute")
    timer = call(KSL, "K2_SetTimerDelegate", Time=SWEEP_INTERVAL, bLooping=True)
    link(act, "then", timer, "execute")
    link(sweep, "OutputDelegate", timer, "Delegate")
    gone = call(ACTOR, "K2_DestroyActor")
    link(b0, "else", gone, "execute")

    # ---------- Sweep ----------
    seq = must(L.add_sequence(g, 4, *pos()), "sequence")
    link(sweep, "then", seq, "execute")
    s = inc("SweepCount", seq, "then_0")
    zero = var("DestroyedThisSweep", True)
    L.set_pin_default(zero, "DestroyedThisSweep", "0")
    link(s, "then", zero, "execute")

    # 1. landscape tiles
    proxy_cls = unreal.load_class(None, "/Script/Landscape.LandscapeStreamingProxy")
    ga = actors_of(proxy_cls, seq, "then_1")
    fe = macro("ForEachLoop")
    link(ga, "then", fe, "Exec")
    link(ga, "OutActors", fe, "Array")
    bounds = call(ACTOR, "GetActorBounds", bOnlyCollidingComponents=False)
    link(fe, "Array Element", bounds, "self")
    cond = in_box_cond(bounds, "Origin", bounds, "BoxExtent")
    bt = branch(*cond)
    if any(p.split()[1] == "execute" for p in L.describe_pins(bounds)):   # impure in this engine -> put it on the exec chain
        link(fe, "LoopBody", bounds, "execute")
        link(bounds, "then", bt, "execute")
    else:
        link(fe, "LoopBody", bt, "execute")
    destroy_and_count(bt, "then", fe, "Array Element", "TilesDestroyed")

    # 2. dressing, only when StaticMeshActor count changed
    sma_cls = unreal.StaticMeshActor.static_class()
    ga2 = actors_of(sma_cls, seq, "then_2")
    ln = call(ARR, "Array_Length")
    link(ga2, "OutActors", ln, "TargetArray")
    last = var("LastStaticMeshCount")
    ne = call(KML, "NotEqual_IntInt")
    link(ln, "ReturnValue", ne, "A")
    link(last, "LastStaticMeshCount", ne, "B")
    bchg = branch(ne, "ReturnValue")
    link(ga2, "then", bchg, "execute")
    all_a = actors_of(ACTOR, bchg, "then")
    fe2 = macro("ForEachLoop")
    link(all_a, "then", fe2, "Exec")
    link(all_a, "OutActors", fe2, "Array")
    bin_ = branch(*in_circle_cond(fe2, "Array Element"))
    link(fe2, "LoopBody", bin_, "execute")
    bdr = branch(*is_dressing_cond(fe2, "Array Element"))
    link(bin_, "then", bdr, "execute")
    destroy_and_count(bdr, "then", fe2, "Array Element", "DressingDestroyed")
    # remember the post-scan StaticMeshActor count
    ga3 = actors_of(sma_cls, fe2, "Completed")
    ln3 = call(ARR, "Array_Length")
    link(ga3, "OutActors", ln3, "TargetArray")
    setlast = var("LastStaticMeshCount", True)
    link(ln3, "ReturnValue", setlast, "LastStaticMeshCount")
    link(ga3, "then", setlast, "execute")
    inc("ScanCount", setlast, "then")

    # 3. GC if anything went
    dts = var("DestroyedThisSweep")
    gt = call(KML, "Greater_IntInt", B=0)
    link(dts, "DestroyedThisSweep", gt, "A")
    bgc = branch(gt, "ReturnValue")
    link(seq, "then_3", bgc, "execute")
    gc = call(KSL, "CollectGarbage")
    link(bgc, "then", gc, "execute")
except Exception as ex:  # noqa: BLE001
    errors.append(f"EXCEPTION {ex!r}")

msgs = L.compile_with_log(bp)
ok = msgs is not None
msgs = list(msgs or [])
for m in msgs:
    log(f"compiler: {m}")
log(f"nodes created: {_x[0] + 2} | build errors: {len(errors)} | compile ok: {ok}")
for e in errors:
    log(f"ERROR {e}")
if ok and not errors:
    unreal.EditorAssetLibrary.save_asset(BP_PATH, only_if_is_dirty=False)
    log("ModActor saved")
