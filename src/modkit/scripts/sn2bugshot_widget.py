"""Runs INSIDE the Unreal editor. Creates the SN2BugShot mod scaffold (ModActor + PAL, chunk 3) and builds the bug-report popup
widget blueprint WBP_BugReport with the SN2GraphTools plugin (unreal.SN2GraphLibrary widget functions, see research/code/modkit_setup.md).

Widget tree (names are used by src/mods/SN2BugShot/Scripts/bugshot.lua):
  Root (CanvasPanel)
    Dim (Border, full-screen translucent black)
    Panel (Border, centred 900x500, dark)
      VBox (VerticalBox)
        Title (TextBlock "Bug report")
        Hint (TextBlock "Describe the problem. Ctrl+Enter = submit, Esc = cancel")
        DescBox (MultiLineEditableTextBox, variable, fills the remaining height)
        Buttons (HorizontalBox)
          SubmitBtn (Button, variable) > SubmitLbl "Submit"
          CancelBtn (Button, variable) > CancelLbl "Cancel"
Graph: member int Result (0 = open, 1 = submit, 2 = cancel); SubmitBtn.OnClicked -> Result=1; CancelBtn.OnClicked -> Result=2.
Re-runnable: recreates the widget blueprint from scratch. Output lines start with [SN2BugShot].
Run:  python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn2bugshot_widget.py
"""
import unreal

MOD = "SN2BugShot"
MOD_DIR = f"/Game/Mods/{MOD}"
BP_PATH = f"{MOD_DIR}/ModActor"
PAL_PATH = f"{MOD_DIR}/PAL_{MOD}"
WBP_NAME = "WBP_BugReport"
WBP_PATH = f"{MOD_DIR}/{WBP_NAME}"
CHUNK = 3

L = unreal.SN2GraphLibrary
eal = unreal.EditorAssetLibrary
errors = []


def log(m):
    unreal.log(f"[SN2BugShot] {m}")


def die(m):
    unreal.log_error(f"[SN2BugShot] STOP: {m}")
    raise RuntimeError(m)


# ---------- 1. scaffold (ModActor + PAL, chunk 3) ----------
tools = unreal.AssetToolsHelpers.get_asset_tools()
ar = unreal.AssetRegistryHelpers.get_asset_registry()
used = {}
for ad in ar.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "PrimaryAssetLabel")):
    try:
        used[str(ad.get_asset().get_path_name())] = ad.get_asset().get_editor_property("rules").get_editor_property("chunk_id")
    except Exception:  # noqa: BLE001
        pass
others = {p: c for p, c in used.items() if c == CHUNK and MOD not in p}
if others:
    die(f"chunk id {CHUNK} already used by {others}")
if not eal.does_asset_exist(BP_PATH):
    f = unreal.BlueprintFactory()
    f.set_editor_property("parent_class", unreal.Actor)
    tools.create_asset("ModActor", MOD_DIR, unreal.Blueprint, f)
    eal.save_asset(BP_PATH, only_if_is_dirty=False)
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

# ---------- 2. widget blueprint (recreated) ----------
if eal.does_asset_exist(WBP_PATH):
    eal.delete_asset(WBP_PATH)
    log("deleted old " + WBP_PATH)
fac = unreal.WidgetBlueprintFactory()
fac.set_editor_property("parent_class", unreal.UserWidget)
wbp = tools.create_asset(WBP_NAME, MOD_DIR, unreal.WidgetBlueprint, fac)
if wbp is None:
    die("could not create widget blueprint")


def add(cls, name, parent, var=False):
    w = L.add_widget(wbp, cls.static_class(), name, parent)
    if w is None:
        errors.append(f"add_widget {name} failed")
        die(f"add_widget {name} failed")
    if var:
        L.set_widget_is_variable(w, True)
    return w


def setp(w, prop, val):
    try:
        w.set_editor_property(prop, val)
    except Exception as e:  # noqa: BLE001
        errors.append(f"set {w.get_name()}.{prop}: {e!r}")


def font_size(w, size, prop="font"):
    try:
        ft = w.get_editor_property(prop)
        ft.set_editor_property("size", size)
        w.set_editor_property(prop, ft)
    except Exception as e:  # noqa: BLE001
        errors.append(f"font {w.get_name()}: {e!r}")


LC = unreal.LinearColor
M = unreal.Margin
V2 = unreal.Vector2D

root = add(unreal.CanvasPanel, "Root", None)
dim = add(unreal.Border, "Dim", root)
setp(dim, "brush_color", LC(0, 0, 0, 0.55))
if not L.set_canvas_slot(dim, V2(0, 0), V2(1, 1), V2(0, 0), V2(0, 0), V2(0, 0), 0):
    errors.append("canvas slot Dim")

panel = add(unreal.Border, "Panel", root)
setp(panel, "brush_color", LC(0.04, 0.07, 0.10, 0.97))
setp(panel, "padding", M(24, 20, 24, 20))
if not L.set_canvas_slot(panel, V2(0.5, 0.5), V2(0.5, 0.5), V2(0, 0), V2(900, 500), V2(0.5, 0.5), 1):
    errors.append("canvas slot Panel")

vbox = add(unreal.VerticalBox, "VBox", panel)

title = add(unreal.TextBlock, "Title", vbox)
setp(title, "text", "Bug report")
font_size(title, 32)
L.set_box_slot(title, M(0, 0, 0, 6), 0, 1, 0)

hint = add(unreal.TextBlock, "Hint", vbox)
setp(hint, "text", "Describe the problem. Ctrl+Enter = submit, Esc = cancel")
setp(hint, "color_and_opacity", unreal.SlateColor(LC(0.65, 0.75, 0.85, 1)))
font_size(hint, 18)
L.set_box_slot(hint, M(0, 0, 0, 10), 0, 1, 0)

desc = add(unreal.MultiLineEditableTextBox, "DescBox", vbox, var=True)
setp(desc, "hint_text", "What went wrong? What were you doing?")
setp(desc, "allow_context_menu", True)
try:
    st = desc.get_editor_property("widget_style")
    ts = st.get_editor_property("text_style")
    ft = ts.get_editor_property("font")
    ft.set_editor_property("size", 20)
    ts.set_editor_property("font", ft)
    st.set_editor_property("text_style", ts)
    desc.set_editor_property("widget_style", st)
except Exception as e:  # noqa: BLE001
    errors.append(f"DescBox style: {e!r}")
L.set_box_slot(desc, M(0, 0, 0, 12), 1.0, 0, 0)

btns = add(unreal.HorizontalBox, "Buttons", vbox)
L.set_box_slot(btns, M(0, 0, 0, 0), 0, 3, 0)

submit = add(unreal.Button, "SubmitBtn", btns, var=True)
setp(submit, "background_color", LC(0.10, 0.45, 0.25, 1))
lbl = add(unreal.TextBlock, "SubmitLbl", submit)
setp(lbl, "text", "Submit")
font_size(lbl, 22)
L.set_box_slot(submit, M(0, 0, 16, 0), 0, 0, 0)

cancel = add(unreal.Button, "CancelBtn", btns, var=True)
setp(cancel, "background_color", LC(0.45, 0.15, 0.15, 1))
lbl2 = add(unreal.TextBlock, "CancelLbl", cancel)
setp(lbl2, "text", "Cancel")
font_size(lbl2, 22)
L.set_box_slot(cancel, M(0, 0, 0, 0), 0, 0, 0)

# button label padding: Button content slot is a ButtonSlot (padding via editor property on the slot)
for w in (lbl, lbl2):
    try:
        w.slot.set_editor_property("padding", M(28, 8, 28, 8))
    except Exception as e:  # noqa: BLE001
        errors.append(f"button label padding: {e!r}")

# ---------- 3. graph: Result variable + two bound events ----------
if not L.add_member_variable(wbp, "Result", "int", "", None, False, "0"):
    errors.append("add_member_variable Result failed")
graph = L.get_event_graph(wbp)
_y = [0]


def bound(widget_name, value):
    ok_msg = L.add_widget_bound_event(wbp, widget_name, "OnClicked")
    node, msg = (ok_msg if isinstance(ok_msg, tuple) else (ok_msg, ""))
    if node is None:
        errors.append(f"bound event {widget_name}.OnClicked: {msg}")
        return
    setter = L.add_variable_node(wbp, graph, "Result", True, 500, _y[0])
    _y[0] += 220
    if setter is None:
        errors.append("set Result node")
        return
    L.set_pin_default(setter, "Result", str(value))
    pins = list(L.describe_pins(node))
    log(f"{widget_name} event pins: {pins}")
    # unreal.py: a bool-returning function with an out message returns the message string on success and None on failure
    c = L.connect(node, "then", setter, "execute")
    if c is None:
        log(f"setter pins: {list(L.describe_pins(setter))}")
        errors.append(f"connect {widget_name} event -> Result setter failed")


bound("SubmitBtn", 1)
bound("CancelBtn", 2)

# ---------- 4. compile, read back, save ----------
res = L.compile_with_log(wbp)   # unreal.py: out-array + bool -> the message list on success, None on compile error
ok, msgs = (res is not None), list(res or [])
for m in msgs:
    log(f"compiler: {m}")
log(f"compile ok: {ok} | {len(errors)} build errors")
for e in errors:
    log(f"ERROR {e}")
tree = list(L.describe_widget_tree(wbp))
log("widget tree read back (%d widgets):" % len(tree))
for t in tree:
    log("  " + t)
if ok and not errors:
    eal.save_asset(WBP_PATH, only_if_is_dirty=False)
    eal.save_asset(BP_PATH, only_if_is_dirty=False)
    eal.save_asset(PAL_PATH, only_if_is_dirty=False)
    log("WBP_BugReport + ModActor + PAL saved")
    gen = unreal.load_class(None, WBP_PATH + "." + WBP_NAME + "_C")
    log(f"generated class loadable: {gen is not None}")
else:
    log("NOT saved (errors above)")
