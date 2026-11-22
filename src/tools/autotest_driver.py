#!/usr/bin/env python3
"""Input driver for automated Subnautica 2 tests: simulated OS keyboard/mouse (SendInput) + screen capture. No extra packages except Pillow.

Subcommands (manual exploration):
  focus                      bring the game window to the foreground
  click X Y                  absolute left click at 1920x1080 screen coordinates
  key NAME [holdMs]          key press by scan code (e.g. esc, enter, w, f11, space)
  combo MOD+NAME             e.g. ctrl+f11, shift+tab
  mouse DX DY                relative mouse move (raw counts)
  shot FILE                  screenshot of the primary screen (Pillow ImageGrab) to FILE
  state                      press Ctrl+F11 and print the parsed STATE line from UE4SS.log
  arm PLAN.json RUN_DIR      write run/active_plan.lua for the Lua mod (before launching the game)
  dialogs                    list the game process's modal dialogs (class #32770): title, static texts, buttons (read-only)
  windows REASON [OUT_DIR]   save shots/stall_REASON.png (full desktop, no focus) + windows_REASON.txt (all visible top-level windows of the game) into OUT_DIR
  identify [FILE]            identify the menu screen of FILE (default: the live screen) with plans/screens.json
  screens-build [AUTOTEST_DIR] / screens-check [AUTOTEST_DIR] [--loo]   rebuild plans/screens.json from the labelled run folders / print the offline confusion table (autotest_screens.py)
  run PLAN.json              execute a whole plan (see run_plan); needs env SN2_UE4SS_DIR, optional SN2_AUTOTEST_OUT
Run results (last "[driver] RESULT <x>" line): DONE FAIL_LOBBY FAIL_LUA_LOAD FAIL_NOPAWN FAIL_MENU FAIL_QUIT FAIL_FOCUS(exit 3) FAIL_DIALOG(exit 4) FAIL_EXCEPTION
Every input action first brings Subnautica2-Win64-Shipping.exe to the foreground and checks GetForegroundWindow (abort with exit 3 otherwise).

INPUT MODES (--input os|engine anywhere on the command line, or env SN2_INPUT; default engine):
  os      (opt-in) simulated OS keyboard/mouse + full-screen grabs; the game window must stay in front.
  engine  (default) the game is driven from inside by the UE4SS mod SN2AutoTest (command file run/cmd.txt, verbs state/teleport/look/click/... see
          research/01_runbook.md 'Engine input mode'); screenshots are PrintWindow captures of the game window (src/tools/winshot.py), so the window may stay
          unfocused / covered by other windows. The driver never moves the real mouse, presses keys, focuses the game or grabs the screen: press, combo, click,
          mouse_move, focus and the full-screen ImageGrab helpers RAISE in engine mode.
"""
import ctypes, ctypes.wintypes as wt, json, math, os, re, subprocess, sys, time

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
EXE = "Subnautica2-Win64-Shipping.exe"
SW, SH = 1920, 1080
INPUT_MODE = os.environ.get("SN2_INPUT", "engine").strip().lower() or "engine"
ENG = INPUT_MODE == "engine"

class EngineModeError(RuntimeError):
    pass

def _no_real_input(what):
    """engine mode must never touch the user's mouse/keyboard/focus/screen (user decision 2026-11-19)"""
    if ENG:
        raise EngineModeError("%s is a real-input/real-screen action and is forbidden in engine input mode" % what)

# ---------------------------------------------------------------- SendInput plumbing
ULONG_PTR = ctypes.c_size_t
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]
class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]

KEYEVENTF_SCANCODE, KEYEVENTF_KEYUP, KEYEVENTF_EXTENDEDKEY = 0x8, 0x2, 0x1
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x1, 0x8000, 0x2, 0x4

def _send(inp):
    _no_real_input("SendInput")
    n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if n != 1:
        raise RuntimeError("SendInput failed (blocked by UIPI / elevated game window?)")

SCAN = {"esc": 0x01, "escape": 0x01, "enter": 0x1C, "return": 0x1C, "tab": 0x0F, "space": 0x39, "ctrl": 0x1D, "shift": 0x2A, "alt": 0x38,
        "backspace": 0x0E, "up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D, "f11": 0x57, "f12": 0x58}
for i, c in enumerate("1234567890"):
    SCAN[c] = 0x02 + i
for row, base in (("qwertyuiop", 0x10), ("asdfghjkl", 0x1E), ("zxcvbnm", 0x2C)):
    for i, c in enumerate(row):
        SCAN[c] = base + i
for i in range(1, 11):
    SCAN["f%d" % i] = 0x3A + i
EXTENDED = {"up", "down", "left", "right"}

def key_event(name, down):
    name = name.lower()
    sc = SCAN[name]
    fl = KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP) | (KEYEVENTF_EXTENDEDKEY if name in EXTENDED else 0)
    i = INPUT(type=1); i.u.ki = KEYBDINPUT(0, sc, fl, 0, 0)
    _send(i)

def mouse_event(dx, dy, flags):
    i = INPUT(type=0); i.u.mi = MOUSEINPUT(dx, dy, 0, flags, 0, 0)
    _send(i)

# ---------------------------------------------------------------- window focus
def game_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + EXE, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [int(l.split('","')[1]) for l in out.splitlines() if EXE.lower() in l.lower()]

def game_hwnd():
    pids = set(game_pids())
    found = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            pid = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value in pids:
                r = wt.RECT(); user32.GetWindowRect(h, ctypes.byref(r))
                found.append(((r.right - r.left) * (r.bottom - r.top), h))
        return True
    user32.EnumWindows(cb, 0)
    found.sort(reverse=True)
    return found[0][1] if found else None

def _text(h):
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(max(n, 4096) + 2)
    user32.GetWindowTextW(h, b, len(b))
    if not b.value:   # e.g. read-only Edit controls: ask the control itself (WM_GETTEXT, 1 s timeout)
        res = wt.WPARAM(0)
        user32.SendMessageTimeoutW(h, 0x000D, len(b), ctypes.cast(b, ctypes.c_void_p), 2, 1000, ctypes.byref(res))
    return b.value

def _cls(h):
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, b, 256)
    return b.value

def find_game_dialogs():
    """visible top-level windows of the game process with class #32770: [{hwnd,title,texts,buttons:[{text,hwnd,rect}]}]"""
    pids = set(game_pids())
    dialogs = []
    if not pids:
        return dialogs
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h) and _cls(h) == "#32770":
            pid = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value in pids:
                d = {"hwnd": h, "title": _text(h), "texts": [], "buttons": [], "classes": []}
                @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
                def cb2(c, _2):
                    k = _cls(c)
                    d["classes"].append(k)
                    if k != "Button":
                        t = _text(c)
                        if t: d["texts"].append(t)
                    if k == "Button":
                        r = wt.RECT(); user32.GetWindowRect(c, ctypes.byref(r))
                        d["buttons"].append({"text": _text(c).replace("&", ""), "hwnd": c, "rect": (r.left, r.top, r.right, r.bottom)})
                    return True
                user32.EnumChildWindows(h, cb2, 0)
                dialogs.append(d)
        return True
    user32.EnumWindows(cb, 0)
    return dialogs

def list_game_windows():
    """every visible top-level window of the game process (not only #32770 dialogs): text lines with class, title, rect, child controls (WM_GETTEXT)"""
    pids = set(game_pids())
    if not pids:
        return ["no %s process running" % EXE]
    lines = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            pid = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value in pids:
                r = wt.RECT(); user32.GetWindowRect(h, ctypes.byref(r))
                fg = " FOREGROUND" if user32.GetForegroundWindow() == h else ""
                lines.append("WINDOW hwnd=%s pid=%d class=%r title=%r rect=(%d,%d)-(%d,%d)%s" % (h, pid.value, _cls(h), _text(h)[:200], r.left, r.top, r.right, r.bottom, fg))
                @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
                def cb2(c, _2):
                    rc = wt.RECT(); user32.GetWindowRect(c, ctypes.byref(rc))
                    lines.append("    child hwnd=%s class=%r text=%r rect=(%d,%d)-(%d,%d)%s" % (c, _cls(c), _text(c)[:300], rc.left, rc.top, rc.right, rc.bottom, "" if user32.IsWindowVisible(c) else " hidden"))
                    return True
                user32.EnumChildWindows(h, cb2, 0)
        return True
    user32.EnumWindows(cb, 0)
    return lines or ["game process running (pids %s) but no visible top-level window" % sorted(pids)]

def save_stall(out, reason):
    """research/01 rule 2026-11-19: before any failure report / forced kill save (a) a full-desktop screenshot WITHOUT focusing the game and
    (b) the list of the game's visible top-level windows. Never raises."""
    got = []
    try:
        p = os.path.join(out, "shots", "stall_%s.png" % reason)
        shot_nofocus(p); got.append(p)
    except Exception as e:
        print("[driver] stall screenshot failed: %s" % e, flush=True)
    try:
        lines = list_game_windows()
        p = os.path.join(out, "windows_%s.txt" % reason)
        with open(p, "w", encoding="utf-8") as f:
            f.write("windows of %s at %s (reason %s)\n" % (EXE, time.strftime("%Y-%m-%d %H:%M:%S"), reason))
            f.write("\n".join(lines) + "\n")
        got.append(p)
        print("[driver] STALL_ARTEFACTS %s : %d window line(s)" % (reason, len(lines)), flush=True)
    except Exception as e:
        print("[driver] window list failed: %s" % e, flush=True)
    return got

def focus(h=None):
    _no_real_input("focus()")
    h = h or game_hwnd()
    if not h:
        raise RuntimeError("game window not found")
    for _ in range(5):
        if user32.GetForegroundWindow() == h:
            return h
        if user32.IsIconic(h):
            user32.ShowWindow(h, 9)
        # allow SetForegroundWindow: tap Alt, attach to foreground thread
        user32.keybd_event(0x12, 0, 0, 0); user32.keybd_event(0x12, 0, 2, 0)
        fg = user32.GetForegroundWindow()
        t1 = user32.GetWindowThreadProcessId(fg, None); t2 = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(t2, t1, True)
        user32.BringWindowToTop(h); user32.SetForegroundWindow(h)
        user32.AttachThreadInput(t2, t1, False)
        time.sleep(0.3)
    if user32.GetForegroundWindow() != h:
        raise RuntimeError("could not focus the game window")
    return h

class FocusError(RuntimeError):
    pass

def need_focus():
    try:
        focus()
    except RuntimeError as e:
        print("ERROR focus:", e, flush=True)
        raise FocusError(str(e))

# ---------------------------------------------------------------- actions
def press(name, hold_ms=60):
    _no_real_input("press(%s)" % name)
    need_focus()
    key_event(name, True); time.sleep(hold_ms / 1000.0); key_event(name, False)

def combo(spec, hold_ms=80):
    _no_real_input("combo(%s)" % spec)
    need_focus()
    parts = spec.lower().split("+")
    for p in parts[:-1]:
        key_event(p, True); time.sleep(0.03)
    key_event(parts[-1], True); time.sleep(hold_ms / 1000.0); key_event(parts[-1], False)
    for p in reversed(parts[:-1]):
        time.sleep(0.03); key_event(p, False)

def click(x, y):
    _no_real_input("click(%s,%s)" % (x, y))
    need_focus()
    ax, ay = int(round(x * 65535 / (SW - 1))), int(round(y * 65535 / (SH - 1)))
    # approach from a few pixels away: a cursor that already sits on the target (same position as the previous screen's button, e.g. notice ->
    # title CONTINUE (960,930)) sends no mouse-move, so the new button may never get its hover and ignores the click (hypothesis 2026-11-19)
    jx, jy = int(round(max(0, x - 37) * 65535 / (SW - 1))), int(round(max(0, y - 23) * 65535 / (SH - 1)))
    mouse_event(jx, jy, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.15)
    mouse_event(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.25)
    mouse_event(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.1)
    mouse_event(0, 0, MOUSEEVENTF_LEFTDOWN); time.sleep(0.08); mouse_event(0, 0, MOUSEEVENTF_LEFTUP)

def click_window_button(btn):
    """click the centre of a dialog button's screen rect (no game-window focus check; the dialog is brought to the front first)"""
    _no_real_input("click_window_button")
    l, t, r, b = btn["rect"]
    x, y = (l + r) // 2, (t + b) // 2
    ax, ay = int(round(x * 65535 / (SW - 1))), int(round(y * 65535 / (SH - 1)))
    mouse_event(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.25)
    mouse_event(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.1)
    mouse_event(0, 0, MOUSEEVENTF_LEFTDOWN); time.sleep(0.08); mouse_event(0, 0, MOUSEEVENTF_LEFTUP)

def screen_grab():
    """the ONLY full-screen grab (OS mode); raises in engine mode"""
    _no_real_input("ImageGrab.grab()")
    from PIL import ImageGrab
    return ImageGrab.grab()

def shot_nofocus(path):
    """OS mode: full-desktop grab without focusing the game. Engine mode: PrintWindow capture of the game window (no desktop grab)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if ENG:
        grab_win().save(path); return
    screen_grab().save(path)

def mouse_move(dx, dy, step=40, delay=0.012):
    """relative move in chunks of at most `step` counts (large single deltas can be clipped by the game)"""
    _no_real_input("mouse_move")
    need_focus()
    n = max(1, int(math.ceil(max(abs(dx), abs(dy)) / float(step))))
    sx = sy = 0
    for i in range(1, n + 1):
        tx, ty = int(round(dx * i / n)), int(round(dy * i / n))
        mouse_event(tx - sx, ty - sy, MOUSEEVENTF_MOVE); sx, sy = tx, ty
        time.sleep(delay)

def shot_array():
    import numpy as np
    im = grab_win() if ENG else screen_grab()
    return np.asarray(im.resize((240, 135)), dtype="float32")

def mean_diff(a, b):
    import numpy as np
    return float(np.mean(np.abs(a - b)))

def wait_stable(timeout=20):
    """wait until the screen is neither black nor animating (two captures 0.5 s apart differ < 0.5 and mean > 2): a click on a screen that is
    still fading in is ignored by the game (seen 2026-11-18: notice screen clicked 1.2 s after the lobby line). Condition, not a fixed wait."""
    t_end = time.time() + timeout
    a = shot_array()
    while time.time() < t_end:
        time.sleep(0.5)
        b = shot_array()
        if mean_diff(a, b) < 0.5 and float(b.mean()) > 2:
            return True
        a = b
    return False

def shot(path):
    """OS mode: focus the game + full-screen grab. Engine mode: PrintWindow capture of the game window (no focus, works while covered)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if ENG:
        im = grab_win(); im.save(path); return im
    need_focus()
    im = screen_grab()
    im.save(path)
    return im

# ---------------------------------------------------------------- engine mode: window capture + command channel (no OS input)
_cap_warned = [False]
def grab_win():
    """PrintWindow(PW_CLIENTONLY|PW_RENDERFULLCONTENT) of the game window's client area, always returned as 1920x1080 RGB (WGC fallback is not
    available: no package installed). Raises RuntimeError when the window is missing or minimized (engine mode never minimizes)."""
    import winshot
    h = game_hwnd()
    if not h:
        raise RuntimeError("game window not found")
    if user32.IsIconic(h):
        raise RuntimeError("game window is minimized (PrintWindow cannot capture it)")
    im, ok = winshot.capture(h)
    if im.size != (SW, SH):
        if not _cap_warned[0]:
            _cap_warned[0] = True
            print("[driver] WARNING game client size is %dx%d, not %dx%d: captures are resized" % (im.size[0], im.size[1], SW, SH), flush=True)
        from PIL import Image
        im = im.resize((SW, SH), Image.LANCZOS)
    return im

def run_dir():
    d = os.environ.get("SN2_RUN_DIR")
    if d:
        return d
    return os.path.join(os.path.dirname(ue4ss_log_path()), "Mods", "SN2AutoTest", "run")

_seq = [int(time.time()) - 1700000000]   # monotonic across driver processes: Lua only runs seq > lastSeq
def send_cmd(verb, args="", timeout=20):
    """engine mode: write run/cmd.txt atomically (tmp + os.replace) as '<seq> <verb> <args>' and wait for the Lua line
    '[SN2AutoTest] CMD <seq> <verb> ok|fail <detail>'. Returns (ok, detail, log_text_since_send); ok is None on timeout."""
    sp = os.path.join(run_dir(), "seq.txt")   # shared counter: each driver process (cmd subcommand) must continue the sequence, Lua only runs seq > lastSeq
    try: last = int(open(sp).read().strip() or 0)
    except (OSError, ValueError): last = 0
    _seq[0] = max(_seq[0], last) + 1; seq = _seq[0]
    try: open(sp, "w").write(str(seq))
    except OSError: pass
    off = log_size()
    path = os.path.join(run_dir(), "cmd.txt"); tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("%d %s %s%s" % (seq, verb, args, chr(10)))
    for _ in range(40):
        try:
            os.replace(tmp, path); break
        except PermissionError:
            time.sleep(0.05)
    else:
        raise RuntimeError("could not replace cmd.txt")
    rx = re.compile(r"\[SN2AutoTest\] CMD %d %s (ok|fail) ?([^\r\n]*)" % (seq, re.escape(verb)))
    t_end = time.time() + timeout
    while time.time() < t_end:
        txt = log_since(off)
        m = rx.search(txt)
        if m:
            return m.group(1) == "ok", m.group(2).strip(), txt
        time.sleep(0.1)
    return None, "timeout after %d s waiting for CMD %d %s" % (timeout, seq, verb), log_since(off)

def engine_look(yaw, pitch, timeout=30):
    """camera turn by Enhanced Input injection (closed loop inside the Lua mod); returns the final 'LOOK seq=..' status line, or None"""
    off = log_size()
    ok, d, _ = send_cmd("look", "%.2f %.2f" % (yaw, pitch))
    if not ok:
        return None
    rx = re.compile(r"\[SN2AutoTest\] LOOK seq=%d (?:done|timeout|fail)[^\r\n]*" % _seq[0])
    t_end = time.time() + timeout
    while time.time() < t_end:
        m = rx.search(log_since(off))
        if m:
            return m.group(0)
        time.sleep(0.15)
    return None

def engine_fps(seconds=2.0):
    """measured game frame rate = GetFrameCount delta (verb 'frame') over driver wall time; None if unavailable"""
    ok1, d1, _ = send_cmd("frame"); t1 = time.time()
    if not ok1: return None
    time.sleep(seconds)
    ok2, d2, _ = send_cmd("frame"); t2 = time.time()
    if not ok2: return None
    try:
        return (int(d2) - int(d1)) / (t2 - t1)
    except ValueError:
        return None

# ---------------------------------------------------------------- UE4SS log access
def ue4ss_log_path():
    d = os.environ.get("SN2_UE4SS_DIR")
    if not d:
        cfg = os.path.join(os.path.dirname(__file__), "..", "..", "local.config")
        for l in open(cfg):
            if l.startswith("SN2_GAME_DIR="):
                d = l.split("=", 1)[1].strip().strip('"') + "/Subnautica2/Binaries/Win64/ue4ss"
    return os.path.join(d, "UE4SS.log")

def log_size():
    try:
        return os.path.getsize(ue4ss_log_path())
    except OSError:
        return 0

def log_since(offset):
    try:
        with open(ue4ss_log_path(), "rb") as f:
            f.seek(offset); return f.read().decode("utf-8", "replace")
    except OSError:
        return ""

def wait_log(pattern, since=0, timeout=60):
    rx = re.compile(pattern); t0 = time.time()
    while time.time() - t0 < timeout:
        m = rx.search(log_since(since))
        if m:
            return m
        time.sleep(0.5)
    return None

NUM = r"(-?[\d.]+(?:e[+-]?\d+)?|nan|-nan\(ind\))"
STATE_RX = re.compile(r"STATE world=(\S+) pawn=\(%s,%s,%s\) cam=\(%s,%s,%s\) yaw=%s pitch=%s lifepod=\(%s,%s,%s\)" % ((NUM,) * 11))

def get_state(timeout=6):
    off = log_size()
    if ENG:
        send_cmd("state", "", timeout)
    else:
        combo("ctrl+f11")
    m = wait_log(STATE_RX.pattern, off, timeout)
    if not m:
        return None
    g = m.groups()
    return {"world": g[0], "pawn": tuple(map(float, g[1:4])), "cam": tuple(map(float, g[4:7])), "yaw": float(g[7]), "pitch": float(g[8]), "lifepod": tuple(map(float, g[9:12]))}

def wrap(a):
    while a > 180: a -= 360
    while a <= -180: a += 360
    return a

def turn_to(target_yaw, target_pitch, cal, tol=3.0):
    """turn the camera with the mouse until measured yaw/pitch are within tol degrees (up to 4 corrections); returns final state"""
    st = get_state()
    if ENG:   # closed loop runs inside the game (Enhanced Input injection); verify with the STATE line afterwards
        for _ in range(2):
            line = engine_look(wrap(target_yaw), target_pitch)
            print("[driver] %s" % (line or "LOOK no result line"), flush=True)
            st = get_state()
            if st and abs(wrap(target_yaw - st["yaw"])) <= tol and abs(target_pitch - st["pitch"]) <= tol:
                break
        return st
    for _ in range(4):
        if not st:
            return st
        dy_ = wrap(target_yaw - st["yaw"]); dp = target_pitch - st["pitch"]
        if abs(dy_) <= tol and abs(dp) <= tol:
            return st
        mouse_move(int(round(dy_ * cal["yaw_counts_per_deg"])), int(round(-dp * cal["pitch_counts_per_deg"] * cal.get("pitch_sign", 1))))
        time.sleep(0.5)
        st = get_state()
    return st

# ---------------------------------------------------------------- plan runner
def run_plan(plan_path):
    plan = json.load(open(plan_path))
    menus = json.load(open(os.path.join(os.path.dirname(plan_path), "menus.json")))
    out = os.environ.get("SN2_AUTOTEST_OUT") or os.path.join(os.path.dirname(plan_path), "..", "run_out")
    shots_dir = os.path.join(out, "shots"); os.makedirs(shots_dir, exist_ok=True)
    manifest = os.path.join(out, "manifest.tsv")
    with open(manifest, "w") as f:
        f.write("idx\twaypoint\tk\tyaw\tpawnX\tpawnY\tpawnZ\tcamX\tcamY\tcamZ\tunixTime\tfile\n")
    menu_n = [0]
    first_click_logged = [False]
    pawn_ok = [False]
    def say(m): print("[driver] " + m, flush=True)
    def fallback_close():
        """graceful close without input: engine mode posts WM_CLOSE to the game window (no keys/focus); OS mode presses Alt+F4"""
        if ENG:
            h = game_hwnd()
            if h: user32.PostMessageW(h, 0x0010, 0, 0)
        else:
            combo("alt+f4")
    def fg_probe(label):
        """engine mode: does the game window hold the foreground / is it minimized? (the harness never focuses it)"""
        h = game_hwnd()
        if not h:
            say("FG %s: no game window" % label); return
        fg = user32.GetForegroundWindow()
        say("FG %s: game_is_foreground=%s minimized=%s foreground_class=%r foreground_title=%r" % (label, fg == h, bool(user32.IsIconic(h)), _cls(fg), _text(fg)[:60]))
    def fps_probe(label):
        if not ENG: return
        f = engine_fps(2.0)
        say("FPS %s: %s" % (label, "n/a" if f is None else "%.1f" % f))
    def clean_exit(pawn):
        """close the game cleanly after a failed run so the watchdog marks are removed; never hides the RESULT line already printed"""
        try:
            if not game_pids():
                return
            if pawn:
                say("clean exit: Escape menu -> EXIT WITHOUT SAVING -> main menu QUIT")
                try:
                    do_steps(menus["quit_game"])
                except FocusError:
                    if game_pids(): raise
                except MenuFail as e:
                    say("QUIT_FAILED during clean exit: %s -> %s" % (e, "WM_CLOSE" if ENG else "Alt+F4"))
                    if game_pids(): fallback_close()
            else:
                say("clean exit: %s" % ("WM_CLOSE" if ENG else "Alt+F4"))
                fallback_close()
            t_end = time.time() + 20
            while time.time() < t_end and game_pids():
                time.sleep(1)
            say("clean exit: game %s" % ("gone" if not game_pids() else "still running"))
        except Exception as e:
            say("clean exit failed: %s" % e)
    def menu_shot(screen):
        menu_n[0] += 1
        shot(os.path.join(shots_dir, "menu_%02d_%s.png" % (menu_n[0], screen)))
    class MenuFail(Exception):
        def __init__(self, screen, what, kind="menu"):
            Exception.__init__(self, "%s %s" % (screen, what)); self.screen, self.what, self.kind = screen, what, kind
    scr = [None]
    def grab_ident():
        from PIL import ImageGrab
        if scr[0] is None:
            from autotest_screens import Screens
            scr[0] = Screens()
        return scr[0].identify(ImageGrab.grab())
    def fmt(r):
        return "%s (best=%s d=%.3f, 2nd=%s d=%.3f)" % (r[0] or "unknown", r[1], r[2], r[3], r[4])
    def settle(expect, timeout):
        """wait until the same identity (or 'unknown' = expect 'ingame') was seen in 3 polls >= 1 s apart with a steady UI-box luminance
        (a screen that is still fading in is identified early but ignores clicks). Condition + timeout, no fixed wait."""
        t0 = time.time(); t_end = t0 + timeout
        hist = []; last_logged = None
        while time.time() < t_end:
            r = grab_ident()
            hist.append((time.time(), r[0], r[5]))
            hist = hist[-3:]
            key = r[0]
            if key != last_logged:
                say("  identify: %s" % fmt(r)); last_logged = key
            if len(hist) == 3 and (r[0] is not None or expect == "ingame") and len({h[1] for h in hist}) == 1 and hist[-1][0] - hist[0][0] >= 0.8 and abs(hist[-1][2] - hist[0][2]) < 1.5:
                say("  stable: %s after %.1f s" % (fmt(r), time.time() - t0))
                return r
            time.sleep(0.4)
        say("  NOT stable within %d s, last: %s" % (timeout, fmt(r)))
        return r
    def act(a):
        if "key" in a:
            say("  press %s" % a["key"]); press(a["key"])
        else:
            say("  click (%d,%d)" % (a["x"], a["y"])); click(a["x"], a["y"])
    def poll_change(s, exp, mark, timeout):
        """after an action: True once the screen is identified as something other than `exp` in 2 consecutive polls (or the step's log condition is met)"""
        t_end = time.time() + timeout; n = 0; last = None
        while time.time() < t_end:
            if s.get("post_log") and re.search(s["post_log"], log_since(mark)):
                say("  log condition met: %s" % s["post_log"]); return True
            if s.get("done_log") and re.search(s["done_log"], log_since(mark)):
                say("  log condition met: %s" % s["done_log"]); return True
            if s.get("post") == "exit":
                if not game_pids():
                    say("  game process gone"); return True
            elif not s.get("post_log"):
                r = grab_ident()
                same = (r[0] is None) if exp == "ingame" else (r[0] == exp)
                if r[0] != last:
                    say("  poll: %s" % fmt(r)); last = r[0]
                n = 0 if same else n + 1
                if n >= 2:
                    return True
            time.sleep(0.4)
        return False
    def visible_buttons():
        """engine mode: ask the Lua mod for the visible buttons; returns a list of dicts parsed from the 'BTN class= name= label= ...' log lines"""
        ok, d, txt = send_cmd("buttons", "", 20)
        res = []
        for m in re.finditer(r"\[SN2AutoTest\] BTN ([^\r\n]*)", txt):
            line = m.group(1)
            kv = dict((k, v) for k, v in re.findall(r"(\w+)=(.*?)(?= \w+=|$)", line))
            res.append(kv)
        return res
    def do_steps_engine(steps):
        """engine-mode menu navigation, SCREEN-DRIVEN: every poll asks the Lua mod for the truly visible buttons (own + ancestors visible, active
        WidgetSwitcher branch) and picks the highest allowed step whose key button is live (autotest_menu_pick.pick). Steps are therefore skipped
        when the game jumps past them (title screen not shown), and a step is retried when its screen persists. FAIL_MENU only for a real stall:
        no known screen for 90 s (45 s later in the chain), or the same screen unchanged after 3 actions. A step ends when its post_log/done_log
        shows, the process is gone (post == exit), or after its settle wait. Never touches the real mouse/keyboard."""
        from autotest_menu_pick import pick
        is_quit = steps is menus["quit_game"]
        kind = "quit" if is_quit else "menu"
        todo = [s for s in steps if s.get("engine")]
        if not todo:
            raise MenuFail("engine", "menus.json has no steps with an 'engine' entry for this chain")
        last_k = -1; attempts = 0; t_act = 0.0; t_known = time.time(); idle_limit = 90
        while True:
            k, b = pick(todo, visible_buttons(), last_k)
            if k is None:
                if time.time() - t_known > idle_limit:
                    raise MenuFail(todo[max(last_k, 0)]["screen"], "no known menu screen for %d s (after step %d/%d)" % (idle_limit, last_k + 1, len(todo)), kind)
                time.sleep(1.0); continue
            t_known = time.time(); idle_limit = 60
            s = todo[k]; e = s["engine"]
            if k == last_k:
                if time.time() - t_act < e.get("retry_after", 20):
                    time.sleep(1.0); continue
                attempts += 1
                if attempts >= 3:
                    raise MenuFail(s["screen"], "screen unchanged after 3 actions (button %r still live)" % e["label"], kind)
                say("step %s: screen unchanged -> acting again (attempt %d/3)" % (s["screen"], attempts + 1))
            else:
                skipped = [t["screen"] for t in todo[last_k + 1:k]]
                if skipped:
                    say("skipped (screen not shown, a later step's button is live): %s" % ", ".join(skipped))
                attempts = 0
            mark = log_size()
            say("step %s: button %r live (%s path=%s...), activating with %s" % (s["screen"], e["label"], b.get("class"), b.get("path", "")[:60], e.get("method", "auto")))
            if not first_click_logged[0] and not is_quit:
                first_click_logged[0] = True
                print("[driver] FIRST_CLICK_AT %.3f" % time.time(), flush=True)
            ok, d, _ = send_cmd("click", "%s %s" % (e.get("method", "auto"), e["label"]))
            say("  CMD click -> ok=%s %s" % (ok, d))
            if not ok:
                raise MenuFail(s["screen"], "click %r failed: %s" % (e["label"], d), kind)
            last_k = k; t_act = time.time()
            if s.get("post_log") or s.get("done_log") or s.get("post") == "exit":
                t_end = time.time() + s.get("poll", 15); done = False
                while time.time() < t_end:
                    txt = log_since(mark)
                    if (s.get("post_log") and re.search(s["post_log"], txt)) or (s.get("done_log") and re.search(s["done_log"], txt)) \
                            or (s.get("post") == "exit" and not game_pids()):
                        done = True; break
                    time.sleep(0.5)
                if not done:
                    raise MenuFail(s["screen"], "step end condition not met within %ds" % s.get("poll", 15), kind)
                say("  step %s done (end condition met)" % s["screen"])
                try: menu_shot(s["screen"])
                except (FocusError, RuntimeError):
                    if game_pids(): raise
                if k == len(todo) - 1:
                    return
                last_k = k; t_known = time.time(); idle_limit = 120   # the next screen (main menu after a world exit) can take ~30-90 s
                continue
            time.sleep(e.get("settle", 3))
            say("  step %s done" % s["screen"])
            try: menu_shot(s["screen"])
            except (FocusError, RuntimeError):
                if game_pids(): raise
    def do_steps(steps):
        """screen-identity navigation (research/01 'Screen-identity menu navigation'): per step wait until the expected screen is stably identified,
        act, poll (<= 10 s) until the screen is something else, re-act only if it is still the same screen (max 3), skip ahead when a later step's
        screen is showing, FAIL_MENU when stuck."""
        if ENG:
            return do_steps_engine(steps)
        i = 0; acts = 0; regress = 0
        is_quit = steps is menus["quit_game"]
        while i < len(steps):
            s = steps[i]; exp = s["expect"]
            if acts > 24:
                raise MenuFail(s["screen"], "more than 24 actions without finishing")
            r = settle(exp, 90 if (i == 0 and not is_quit) else 45)
            name = r[0]
            ok = (name is None) if exp == "ingame" else (name == exp)
            if not ok:
                later = next((k for k in range(i + 1, len(steps)) if name is not None and steps[k]["expect"] == name), None)
                earlier = next((k for k in range(i - 1, -1, -1) if name is not None and steps[k]["expect"] == name), None)
                if later is not None:
                    say("step %s: screen is %s -> skip ahead to step %s" % (s["screen"], name, steps[later]["screen"])); i = later; continue
                if earlier is not None and regress < 4:
                    regress += 1; say("step %s: screen is %s -> back to step %s" % (s["screen"], name, steps[earlier]["screen"])); i = earlier; continue
                raise MenuFail(s["screen"], "expected %s, identified %s" % (exp, fmt(r)))
            say("step %s (expect %s): screen confirmed, acting" % (s["screen"], exp))
            if not first_click_logged[0] and not is_quit:
                first_click_logged[0] = True
                print("[driver] FIRST_CLICK_AT %.3f" % time.time(), flush=True)
            acts_list = s.get("actions") or [s]
            for attempt in range(1, 4):
                mark = log_size()
                act(acts_list[(attempt - 1) % len(acts_list)]); acts += 1
                if s.get("settle"):
                    time.sleep(s["settle"]); break
                tmo = s.get("poll", 10)
                if poll_change(s, exp, mark, tmo):
                    break
                if s.get("post_log") or s.get("post") == "exit":
                    kind = "quit" if is_quit else "menu"
                    raise MenuFail(s["screen"], "condition %r not met within %d s after the click" % (s.get("post_log") or "process exit", tmo), kind)
                say("  still identified as %s after %d s (attempt %d/3)%s" % (exp, tmo, attempt, " -> acting again" if attempt < 3 else ""))
            else:
                raise MenuFail(s["screen"], "screen still %s after 3 attempts: %s" % (exp, fmt(grab_ident())))
            try:
                menu_shot(s["screen"])
            except (FocusError, RuntimeError):
                if game_pids(): raise
            i += 1
    try:
        # lobby: poll the log line every 1 s; handle the game's modal start-up dialogs (class #32770) on the way
        off = 0
        m = None
        t_wait_end = time.time() + 180
        n_dialogs = 0
        dialog_shot = False
        while time.time() < t_wait_end:
            m = re.search(r"\[SN2AutoTest\] WORLD L_ClientLobby", log_since(off))
            if m:
                break
            le = re.search(r"Error loading script[^\r\n]*SN2[^\r\n]*", log_since(off))
            if le:   # a Lua syntax error in an SN2* mod: fail fast instead of waiting out the lobby timeout
                say("FAIL Lua load error: %s" % le.group(0)[:300]); save_stall(out, "lua_load")
                print("[driver] RESULT FAIL_LUA_LOAD %s" % le.group(0)[:300], flush=True); clean_exit(False); return 1
            dlgs = find_game_dialogs()
            if dlgs and n_dialogs < 3:
                d = dlgs[0]
                labels = [b["text"] for b in d["buttons"]]
                say("DIALOG title=%r text=%r buttons=%r" % (d["title"], " | ".join(d["texts"]), labels))
                if not dialog_shot:
                    dialog_shot = True
                    try: shot_nofocus(os.path.join(shots_dir, "menu_00_dialog.png"))
                    except Exception as e: say("dialog screenshot failed: %s" % e)
                n_dialogs += 1
                pick = next((b for b in d["buttons"] if b["text"].strip().lower() in ("ok", "continue", "close")), None)
                if not pick:
                    save_stall(out, "dialog")
                    print("[driver] RESULT FAIL_DIALOG buttons=%r" % labels, flush=True)
                    return 4
                if ENG:
                    user32.PostMessageW(pick["hwnd"], 0x00F5, 0, 0)   # BM_CLICK: no focus, no mouse
                else:
                    focus(d["hwnd"])
                    click_window_button(pick)
                say("DIALOG_DISMISSED %s" % pick["text"])
                t_gone = time.time() + 5
                while time.time() < t_gone and any(x["hwnd"] == d["hwnd"] for x in find_game_dialogs()):
                    time.sleep(0.5)
                if any(x["hwnd"] == d["hwnd"] for x in find_game_dialogs()):
                    say("WARNING dialog still present 5 s after the click")
                continue
            time.sleep(1.0)
        if not m:
            say("FAIL lobby not reached"); save_stall(out, "lobby"); print("[driver] RESULT FAIL_LOBBY"); clean_exit(False); return 1
        # menu ready = lobby WORLD line seen + two captures 1 s apart differ by < 0.5 (menu finished animating in). NO fixed wait.
        t_lobby = time.time()
        if ENG:
            fg_probe("at_lobby")
        else:
            need_focus()
        t_end = time.time() + 120
        while True:
            d = mean_diff(shot_array(), (time.sleep(1.0), shot_array())[1])
            if d < 0.5 or time.time() > t_end:
                break
        if plan.get("worldLevel"):
            if not wait_log(r"\[SN2AutoTest\] worldLevel set", off, 60):
                say("WARNING worldLevel set line not seen")
        t_ready = time.time()
        say("menu ready %.1f s after the lobby WORLD line (frame diff %.2f); first click now" % (t_ready - t_lobby, d))
        fps_probe("menu_ready")
        print("[driver] MENU_READY_AT %.3f" % t_ready, flush=True)
        mark = log_size()
        do_steps(menus["load_game" if plan.get("start") == "load" else "new_game"])
        # world
        if not wait_log(r"\[SN2AutoTest\] PAWN possessed", mark, 240):
            time.sleep(0.1)
            save_stall(out, "nopawn")
            shot(os.path.join(shots_dir, "00_nopawn.png"))
            print("[driver] RESULT FAIL_NOPAWN"); clean_exit(False); return 1
        pawn_ok[0] = True
        say("pawn possessed; settle %ss" % plan.get("settleSeconds", 15))
        time.sleep(plan.get("settleSeconds", 15))
        fg_probe("ingame"); fps_probe("ingame_after_settle")
        menu_shot("ingame_first")
        cal = menus["calibration"]
        n = 0
        for wi, wp in enumerate(plan["waypoints"]):
            if wi < 5:
                if ENG: send_cmd("teleport", str(wi + 1))
                else: combo("ctrl+shift+" + "zxcvb"[wi])
            time.sleep(3.0)
            fps_probe("waypoint_%s" % wp["name"])
            st = get_state()
            if wp.get("offset") and st:
                dx, dy_ = st["lifepod"][0] - st["pawn"][0], st["lifepod"][1] - st["pawn"][1]
                front = math.degrees(math.atan2(dy_, dx))
            else:
                front = st["yaw"] if st else 0.0
            say("waypoint %s front yaw %.1f" % (wp["name"], front))
            for k in range(8):
                if wi < 5:
                    if ENG: send_cmd("teleport", str(wi + 1))
                    else: combo("ctrl+shift+" + "zxcvb"[wi])
                st = turn_to(wrap(front + 45 * k), 0.0, cal)
                time.sleep(3.0 if k == 0 else 0.8)
                fn = "%02d_%s_k%d.png" % (wi, wp["name"], k)
                shot(os.path.join(shots_dir, fn))
                st = get_state() or st or {"pawn": (0, 0, 0), "cam": (0, 0, 0), "yaw": float("nan"), "pitch": float("nan")}
                with open(manifest, "a") as f:
                    f.write("%d\t%s\t%d\t%.2f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%s\n" % (wi, wp["name"], k, st["yaw"], *st["pawn"], *st["cam"], int(time.time()), fn))
                n += 1
                print("[driver] SHOT %s yaw=%.1f pitch=%.1f pawn=%s" % (fn, st["yaw"], st["pitch"], st["pawn"]), flush=True)
        say("all shots done: %d" % n)
        # quit through the Escape menu (autotest.sh kills the process after 60 s if this did not end it)
        try:
            do_steps(menus["quit_game"])
        except FocusError:
            if game_pids():
                raise
            say("game window closed after the last quit click (expected)")
        if game_pids():
            save_stall(out, "quit"); say("QUIT_FAILED game process still running after the quit steps")
            print("[driver] RESULT FAIL_QUIT game still running"); clean_exit(False); return 1
        print("[driver] RESULT DONE"); return 0
    except MenuFail as e:
        reason = "quit" if e.kind == "quit" else "menu"
        save_stall(out, reason)
        if e.kind == "quit":
            say("QUIT_FAILED %s" % e)
            print("[driver] RESULT FAIL_QUIT %s %s" % (e.screen, e.what), flush=True)
        else:
            print("[driver] RESULT FAIL_MENU %s %s" % (e.screen, e.what), flush=True)
        clean_exit(pawn_ok[0] and e.kind != "quit"); return 1
    except FocusError as e:
        save_stall(out, "focus")
        print("[driver] RESULT FAIL_FOCUS", e); return 3
    except Exception as e:
        import traceback; traceback.print_exc()
        save_stall(out, "exception")
        print("[driver] RESULT FAIL_EXCEPTION", repr(e), flush=True)
        clean_exit(pawn_ok[0]); return 1

def lua_val(v):
    if v is None: return "nil"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, str): return json.dumps(v)
    if isinstance(v, list): return "{" + ",".join(lua_val(x) for x in v) + "}"
    if isinstance(v, dict): return "{" + ",".join("%s=%s" % (k, lua_val(x)) for k, x in v.items() if x is not None) + "}"
    raise TypeError(v)

def arm(plan_path, run_dir):
    """write run/active_plan.lua (name, worldLevel, waypoints) for the observe-only Lua mod"""
    plan = json.load(open(plan_path))
    os.makedirs(run_dir, exist_ok=True)
    keep = {k: plan.get(k) for k in ("name", "worldLevel", "waypoints")}
    keep["inputMode"] = "engine" if ENG else "os"
    if ENG and plan.get("lookFallback"): keep["lookFallback"] = True
    open(os.path.join(run_dir, "active_plan.lua"), "w").write("return " + lua_val(keep) + chr(10))

def main(argv):
    global INPUT_MODE, ENG
    argv = list(argv)
    if "--input" in argv:   # --input engine|os (strip it; same effect as env SN2_INPUT)
        i = argv.index("--input")
        INPUT_MODE = argv[i + 1].strip().lower(); ENG = INPUT_MODE == "engine"
        del argv[i:i + 2]
    if len(argv) < 2:
        print(__doc__); return 2
    c = argv[1]
    try:
        if c == "cmd":   # engine mode: cmd VERB [ARGS...] -> writes run/cmd.txt, prints the CMD result and the log lines it produced
            ENG = True
            ok, d, txt = send_cmd(argv[2], " ".join(argv[3:]), 60)
            print("ok=%s detail=%s" % (ok, d))
            for l in txt.splitlines():
                if "[SN2AutoTest]" in l: print(l)
            return 0 if ok else 1
        if c == "dismiss":   # engine mode: BM_CLICK (no focus/mouse) on ok/continue/close of the game's start-up dialog(s)
            for d in find_game_dialogs():
                pick = next((b for b in d["buttons"] if b["text"].strip().lower() in ("ok", "continue", "close")), None)
                print("DIALOG title=%r texts=%r buttons=%r -> %s" % (d["title"], d["texts"], [b["text"] for b in d["buttons"]], pick and pick["text"]))
                if pick: user32.PostMessageW(pick["hwnd"], 0x00F5, 0, 0)
            return 0
        if c == "grabwin":   # engine mode: PrintWindow capture of the game window -> FILE
            ENG = True
            im = grab_win(); os.makedirs(os.path.dirname(os.path.abspath(argv[2])), exist_ok=True); im.save(argv[2])
            import numpy as np
            print("saved", argv[2], im.size, "mean=%.1f" % float(np.asarray(im).mean())); return 0
        if c == "focus": focus(); print("focused")
        elif c == "click": click(int(argv[2]), int(argv[3])); print("clicked")
        elif c == "key": press(argv[2], int(argv[3]) if len(argv) > 3 else 60); print("key sent")
        elif c == "combo": combo(argv[2]); print("combo sent")
        elif c == "mouse": mouse_move(int(argv[2]), int(argv[3])); print("mouse moved")
        elif c == "shot": im = shot(argv[2]); print("saved", argv[2], im.size)
        elif c == "state": print(get_state())
        elif c == "dialogs":
            ds = find_game_dialogs()
            for d in ds:
                print("DIALOG hwnd=%s title=%r texts=%r childClasses=%r buttons=%r" % (d["hwnd"], d["title"], d["texts"], d["classes"], [(b["text"], b["hwnd"], b["rect"]) for b in d["buttons"]]))
            print("done: %d dialog(s)" % len(ds))
        elif c == "windows":
            reason = argv[2] if len(argv) > 2 else "manual"
            out = argv[3] if len(argv) > 3 else os.environ.get("SN2_AUTOTEST_OUT") or "."
            save_stall(out, reason)
            print("\n".join(list_game_windows()))
        elif c == "screens-build":
            import autotest_screens; return autotest_screens.main(["x", "build"] + argv[2:])
        elif c == "screens-check":
            import autotest_screens; return autotest_screens.main(["x", "check"] + argv[2:])
        elif c == "identify":
            from PIL import ImageGrab, Image
            from autotest_screens import Screens
            im = Image.open(argv[2]) if len(argv) > 2 else ImageGrab.grab()
            r = Screens().identify(im); print("identified=%s best=%s d=%.3f second=%s d=%.3f lum=%.1f" % r)
        elif c == "arm": arm(argv[2], argv[3]); print("armed")
        elif c == "run": return run_plan(argv[2])
        else: print(__doc__); return 2
    except FocusError:
        return 3
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
