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
    if os.environ.get("SN2_HIDDEN_DESKTOP") == "1":   # game runs on the hidden desktop (src/tools/hidden_desktop.py): enumerate that desktop only
        user32.OpenDesktopW.restype = wt.HANDLE
        hd = user32.OpenDesktopW("SN2Test", 0, False, 0x01FF | 0x000F0000)
        if not hd:
            return None
        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cbh(h, _):
            if user32.IsWindowVisible(h):
                pid = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                if pid.value in pids:
                    r = wt.RECT(); user32.GetWindowRect(h, ctypes.byref(r))
                    found.append(((r.right - r.left) * (r.bottom - r.top), h))
            return True
        user32.EnumDesktopWindows(hd, cbh, 0)
        user32.CloseDesktop(hd)
        found.sort(reverse=True)
        return found[0][1] if found else None
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

def _on_hidden_desktop(fn):
    """run fn() in a worker thread attached (SetThreadDesktop) to the hidden desktop SN2Test: EnumWindows / EnumChildWindows / WM_GETTEXT / PostMessage
    only see windows of the calling thread's desktop. Never switches the input desktop. Returns fn()'s result, or None if the desktop is missing."""
    import threading
    box = {}
    def work():
        user32.OpenDesktopW.restype = wt.HANDLE
        user32.SetThreadDesktop.argtypes = [wt.HANDLE]
        hd = user32.OpenDesktopW("SN2Test", 0, False, 0x01FF | 0x000F0000)
        if not hd:
            box["r"] = None; return
        try:
            if not user32.SetThreadDesktop(hd):
                box["err"] = "SetThreadDesktop failed %d" % ctypes.get_last_error(); box["r"] = None; return
            box["r"] = fn()
        except Exception as e:
            box["err"] = repr(e); box["r"] = None
        finally:
            pass
    t = threading.Thread(target=work); t.start(); t.join(30)
    if "err" in box: print("[driver] hidden-desktop worker: %s" % box["err"], flush=True)
    return box.get("r")

def post_click(hwnd):
    """BM_CLICK on a button (no focus, no mouse); on the hidden desktop through an attached worker thread"""
    if os.environ.get("SN2_HIDDEN_DESKTOP") == "1":
        _on_hidden_desktop(lambda: user32.PostMessageW(hwnd, 0x00F5, 0, 0)); return
    user32.PostMessageW(hwnd, 0x00F5, 0, 0)

def find_game_dialogs():
    """visible top-level windows of the game process with class #32770: [{hwnd,title,texts,buttons:[{text,hwnd,rect}]}]
    (hidden-desktop runs: the SN2Test desktop only, never the user's)"""
    if os.environ.get("SN2_HIDDEN_DESKTOP") == "1":
        return _on_hidden_desktop(_find_game_dialogs_here) or []
    return _find_game_dialogs_here()

def _find_game_dialogs_here():
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

class FocusGuard:
    """engine mode only: the game (and its UE4SS GUI window) activates itself on creation / after map loads and captures the mouse, which
    steals the user's pointer. A thread polls the foreground window; when it belongs to the game process it gives the foreground back to the
    last window the user was working in (never the game) and releases ClipCursor. No mouse/keyboard input is sent (no Alt tap). Task 3, 2026-11-22."""
    def __init__(self, say):
        import threading
        self.say = say; self.prev = None; self.stolen = 0; self.restored = 0; self.stop_ev = threading.Event(); self.pids = set(); self.pids_t = 0.0
        self.samples = 0; self.game_fg_samples = 0
        self.th = threading.Thread(target=self.loop, daemon=True)
    def pid_of(self, h):
        pid = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid)); return pid.value
    def start(self):
        fg = user32.GetForegroundWindow()
        if fg and self.pid_of(fg) not in set(game_pids()): self.prev = fg
        self.say("FOCUS guard start prev_fg=%s class=%r" % (self.prev, _cls(self.prev) if self.prev else None)); self.th.start()
    def give_back(self, h):
        fgw = user32.GetForegroundWindow()
        t1 = user32.GetWindowThreadProcessId(fgw, None); t2 = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(t2, t1, True)
        try:
            if user32.IsIconic(h): user32.ShowWindow(h, 9)
            user32.SetForegroundWindow(h)
        finally:
            user32.AttachThreadInput(t2, t1, False)
    def loop(self):
        while not self.stop_ev.is_set():
            try:
                if time.time() - self.pids_t > 2.0:
                    self.pids = set(game_pids()); self.pids_t = time.time()
                fg = user32.GetForegroundWindow()
                if fg and self.pids:
                    self.samples += 1
                    if self.pid_of(fg) in self.pids:
                        self.game_fg_samples += 1; self.stolen += 1
                        target = self.prev if (self.prev and user32.IsWindow(self.prev)) else user32.FindWindowW("Shell_TrayWnd", None)
                        if target: self.give_back(target)
                        user32.ClipCursor(None)
                        ok = user32.GetForegroundWindow() == target
                        if ok: self.restored += 1
                        if self.stolen <= 12 or self.stolen % 20 == 0:
                            self.say("FOCUS restored hwnd=%s game_fg=%s clip=released (stolen_count=%d, was class=%r)" % (target, not ok, self.stolen, _cls(fg)))
                    elif self.pid_of(fg) not in self.pids:
                        self.prev = fg
            except Exception as e:
                self.say("FOCUS guard error: %r" % e)
            self.stop_ev.wait(0.2)
    def stop(self):
        self.stop_ev.set()
        self.say("FOCUS_GUARD summary: samples=%d game_foreground_samples=%d stolen=%d restored=%d" % (self.samples, self.game_fg_samples, self.stolen, self.restored))

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
    if os.environ.get("SN2_HIDDEN_DESKTOP") == "1" and im.size != (SW, SH) and im.size[0] >= SW and im.size[1] >= SH:
        # cross-desktop capture is the whole window (GetClientRect is 0x0 there): crop the frame (side/bottom border b, title bar on top) to the 1920x1080 client
        b = (im.size[0] - SW) // 2; top = im.size[1] - SH - b
        if not _cap_warned[0]:
            _cap_warned[0] = True
            print("[driver] hidden capture %dx%d -> cropped to client %dx%d (border %d, title %d)" % (im.size[0], im.size[1], SW, SH, b, top), flush=True)
        im = im.crop((b, top, b + SW, top + SH))
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
        ok_, _d, txt_ = send_cmd("state", "", timeout)
        m = STATE_RX.search(txt_) if ok_ else None   # the STATE line is logged before the CMD ok line: no extra log polling
        if not m:
            m = wait_log(STATE_RX.pattern, off, 1)
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
    st = None if ENG else get_state()
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
    def say(m): print("[driver] %s %s" % (time.strftime("%H:%M:%S"), m), flush=True)
    fguard = FocusGuard(say) if (ENG and os.environ.get("SN2_FOCUSGUARD", "1") != "0") else None
    if fguard: fguard.start()
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
    def input_state():
        """(game_is_foreground, clip_state, capture_is_game) from Win32: foreground window, GetClipCursor vs virtual screen, hwndCapture of the foreground thread"""
        pids = set(game_pids()); fg = user32.GetForegroundWindow()
        pid = wt.DWORD(); user32.GetWindowThreadProcessId(fg, ctypes.byref(pid)) if fg else None
        fgg = bool(fg) and pid.value in pids
        r = wt.RECT(); user32.GetClipCursor(ctypes.byref(r))
        vx, vy, vw, vh = (user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        clip = "released" if (r.left <= vx and r.top <= vy and r.right >= vx + vw and r.bottom >= vy + vh) else "CLIPPED(%d,%d,%d,%d)" % (r.left, r.top, r.right, r.bottom)
        cap = False
        try:
            class GTI(ctypes.Structure):
                _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND),
                            ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]
            g = GTI(); g.cbSize = ctypes.sizeof(GTI)
            if fg and user32.GetGUIThreadInfo(user32.GetWindowThreadProcessId(fg, None), ctypes.byref(g)) and g.hwndCapture:
                cp = wt.DWORD(); user32.GetWindowThreadProcessId(g.hwndCapture, ctypes.byref(cp)); cap = cp.value in pids
        except Exception: pass
        return fgg, clip, cap
    MOUSEPROBE_ON = ENG and os.environ.get("SN2_MOUSEPROBE", "0") == "1"
    def mouse_probe(at):
        """engine mode, opt-in (SN2_MOUSEPROBE=1; user-approved 2026-11-22 for the focus tests): relative mouse MOVE only (no click, no key, no window to front);
        game must not turn the camera. Cursor position is saved and restored. Logs MOUSEPROBE at= fg_is_game= clip= capture= yaw_before= yaw_after= pass="""
        if not ENG or not game_pids(): return
        fgg, clip, cap = input_state()
        if not MOUSEPROBE_ON:
            say("EVT at=%s fg_is_game=%s clip=%s capture_is_game=%s" % (at, fgg, clip, cap)); return
        pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
        s0 = get_state(); time.sleep(0.2)
        for dx, dy in ((300, 0), (300, 0), (0, 200), (0, 200), (-200, 0)):
            for _ in range(10): mouse_event(dx // 10, dy // 10, MOUSEEVENTF_MOVE); time.sleep(0.01)
            time.sleep(0.05)
        time.sleep(0.5)
        s1 = get_state()
        user32.SetCursorPos(pt.x, pt.y)
        fgg2, clip2, cap2 = input_state()
        if s0 and s1:
            dyaw = abs(wrap(s1["yaw"] - s0["yaw"])); dp = abs(s1["pitch"] - s0["pitch"]); turned = dyaw > 1.0 or dp > 1.0
            yb, ya = "%.2f/p%.2f" % (s0["yaw"], s0["pitch"]), "%.2f/p%.2f" % (s1["yaw"], s1["pitch"])
        else:
            turned = False; yb = ya = "n/a"
        ok = (not turned) and (not fgg) and (not fgg2) and clip == "released" and clip2 == "released" and not cap and not cap2
        say("MOUSEPROBE at=%s fg_is_game=%s clip=%s capture_is_game=%s yaw_before=%s yaw_after=%s pass=%s" % (at, fgg or fgg2, clip2, cap or cap2, yb, ya, ok))
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
    def q2_window(label):
        """hidden-desktop test, IN-WORLD after readiness (pawn live). label 'A' = hands-off + harness mouse wiggle (relative SendInput MOVES only, cursor restored),
        'B' = the user's own input (move/click/W A S D Tab Esc in their own window), harness idle (no wiggle). Env SN2_HIDDEN_WINDOWS=1 enables, SN2_WINDOW_SECS (30),
        SN2_WINDOW_LEAD (35: notice before the window opens). The Lua mod logs 'Q2 <time> world pawn yaw pitch ui' every 500 ms while run/q2.txt exists.
        Status lines go to <Workspace>/autotest/hidden_desktop_status.txt"""
        if os.environ.get("SN2_HIDDEN_WINDOWS") != "1" or not ENG: return
        wiggle = label == "A"
        kind = "hands-off" if wiggle else "USER INPUT"
        dur = float(os.environ.get("SN2_WINDOW_SECS", "30")); lead = float(os.environ.get("SN2_WINDOW_LEAD", "35"))
        st = os.path.join(os.path.dirname(os.environ["SN2_AUTOTEST_OUT"]), "hidden_desktop_status.txt")
        def status(t):
            with open(st, "a") as f: f.write(t + chr(10))
            say(t)
        start = time.time() + lead
        status("WINDOW %s STARTS AT %s (%s)" % (label, time.strftime("%H:%M:%S", time.localtime(start)), kind))
        while time.time() < start: time.sleep(0.2)
        try: shot(os.path.join(shots_dir, "q2_%s_before.png" % label))
        except Exception as ex: say("Q2 shot before failed: %s" % ex)
        open(os.path.join(run_dir(), "q2.txt"), "w").write("1")
        end = time.time() + dur
        status("WINDOW %s OPEN %s (%s)" % (label, time.strftime("%H:%M:%S"), kind))
        pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt)); ox, oy = pt.x, pt.y
        pat = [(15, 0), (0, 15), (-15, 0), (0, -15)]; k = 0
        try:
            while time.time() < end:
                if wiggle:
                    _i = INPUT(type=0); _i.u.mi = MOUSEINPUT(pat[k % 4][0], pat[k % 4][1], 0, 0x0001, 0, 0)   # relative MOVE only (deliberate real-input exception for this test)
                    user32.SendInput(1, ctypes.byref(_i), ctypes.sizeof(INPUT)); k += 1
                time.sleep(0.4)
        finally:
            if wiggle: user32.SetCursorPos(ox, oy)
            try: os.remove(os.path.join(run_dir(), "q2.txt"))
            except OSError: pass
            status("WINDOW %s CLOSED %s" % (label, time.strftime("%H:%M:%S")))
        try: shot(os.path.join(shots_dir, "q2_%s_after.png" % label))
        except Exception as ex: say("Q2 shot after failed: %s" % ex)
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
                time.sleep(0.25); continue
            t_known = time.time(); idle_limit = 60
            s = todo[k]; e = s["engine"]
            if k == last_k:
                if time.time() - t_act < e.get("retry_after", 1.5):
                    time.sleep(0.25); continue
                attempts += 1
                if attempts >= 10:
                    raise MenuFail(s["screen"], "screen unchanged after 10 actions (button %r still live)" % e["label"], kind)
                say("step %s: screen unchanged -> acting again (attempt %d/10)" % (s["screen"], attempts + 1))
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
                say("  step %s done (end condition met)" % s["screen"]); mouse_probe("after_step_" + s["screen"])
                try: menu_shot(s["screen"])
                except (FocusError, RuntimeError):
                    if game_pids(): raise
                if k == len(todo) - 1:
                    return
                last_k = k; t_known = time.time(); idle_limit = 120   # the next screen (main menu after a world exit) can take ~30-90 s
                continue
            # no settle wait: the loop head polls (0.25 s) for the next step's own live button and clicks it at once; the same button
            # still live after retry_after (1.5 s) = ignored click -> click again (cap 10)
            say("  step %s done" % s["screen"]); mouse_probe("after_step_" + s["screen"])
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
        t_wait_end = time.time() + 300
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
                if os.environ.get("SN2_HIDDEN_DESKTOP") == "1" and not (len(d["buttons"]) == 1 and d["buttons"][0]["text"].strip().lower() == "ok"):
                    pick = None   # hidden run: only an OK-only dialog is ever clicked
                if not pick:
                    save_stall(out, "dialog")
                    print("[driver] RESULT FAIL_DIALOG buttons=%r" % labels, flush=True)
                    return 4
                if ENG:
                    post_click(pick["hwnd"])   # BM_CLICK: no focus, no mouse
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
            fg_probe("at_lobby"); mouse_probe("at_lobby")
        else:
            need_focus()
        d = 0.0
        if not ENG:   # engine mode needs no frame-diff gate: do_steps_engine polls the live buttons and re-clicks an ignored click
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
        if plan.get("lobbyCensus"):   # test-only object census in the lobby (GC-watchdog diagnosis): hold the first click until the Lua mod has logged them all
            _lc = max(plan["lobbyCensus"]); say("lobby census: holding the menu clicks until 'CENSUS DONE lobby' (samples at %s s after the lobby WORLD line)" % plan["lobbyCensus"])
            if not wait_log(r"\[SN2AutoTest\] CENSUS DONE lobby", off, _lc + 90):
                say("WARNING 'CENSUS DONE lobby' not seen in time; clicking on")
        mark = log_size()
        do_steps(menus["load_game" if plan.get("start") == "load" else "new_game"])
        # world
        if not wait_log(r"\[SN2AutoTest\] PAWN possessed", mark, 240):
            time.sleep(0.1)
            save_stall(out, "nopawn")
            shot(os.path.join(shots_dir, "00_nopawn.png"))
            print("[driver] RESULT FAIL_NOPAWN"); clean_exit(False); return 1
        pawn_ok[0] = True
        say("pawn possessed; waiting for readiness (min %ss, max %ss)" % (plan.get("settleMin", 2), plan.get("settleSeconds", 15)))
        t_pw = time.time(); prev = None; stable_n = 0
        while time.time() - t_pw < plan.get("settleSeconds", 15):
            st0 = get_state(3)
            if st0 and prev and max(abs(a - b) for a, b in zip(st0["pawn"], prev["pawn"])) < 1.0:
                stable_n += 1
            else:
                stable_n = 0
            prev = st0
            if stable_n >= 3 and time.time() - t_pw >= plan.get("settleMin", 2):
                break
        if plan.get("worldCensus") is not None:
            if not wait_log(r"\[SN2AutoTest\] CENSUS DONE world", mark, plan["worldCensus"] + 120):
                say("WARNING 'CENSUS DONE world' not seen in time")
        say("readiness reached after %.1f s (pawn stable x%d)" % (time.time() - t_pw, stable_n))
        fg_probe("ingame")
        q2_window("A"); q2_window("B")
        _t_ms = time.time(); menu_shot("ingame_first"); say("TIMING menu_shot ingame_first %.1f s" % (time.time() - _t_ms))
        cal = menus["calibration"]
        n = 0
        # ---- death handling (generic, every waypoint / look / shot): signal = Lua verb 'death' (WBP_RespawnScreen_C visible + rooted).
        # The game respawns the pawn at once but the screen stays up (and blocks IA_Look) until CONTINUE (BackButton) is clicked.
        class WaypointDied(Exception): pass
        class RespawnFail(Exception): pass
        gl_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Subnautica2", "Saved", "Logs", "Subnautica2.log")
        gl_off = [os.path.getsize(gl_path) if os.path.exists(gl_path) else 0]
        deaths = []; died_wps = []
        DEATH_RX = re.compile(r"Respawning\. Last damage by (\S+)[^\r\n]*?Death Location: X=(-?[\d.]+) Y=(-?[\d.]+) Z=(-?[\d.]+)")
        def is_dead():
            ok, d, _ = send_cmd("death", "", 10)
            return bool(ok) and d == "dead"
        def death_info():
            try:
                with open(gl_path, "rb") as f:
                    f.seek(gl_off[0]); txt = f.read().decode("utf-8", "replace")
            except OSError:
                return None, None
            ms = DEATH_RX.findall(txt)
            if len(ms) > len(deaths):
                m = ms[len(deaths)]
                return m[0], (float(m[1]), float(m[2]), float(m[3]))
            return None, None
        def handle_death(wi, wp):
            t0 = time.time()
            cause, pos = death_info()
            deaths.append((wp["name"], pos, cause))
            say("DEATH waypoint=%s pos=%s cause=%s" % (wp["name"], ("%.0f,%.0f,%.0f" % pos) if pos else "?", cause or "unknown"))
            clicked = False; t_click = 0.0
            while time.time() - t0 < 60:
                if not clicked or time.time() - t_click > 12:
                    ok, d, _ = send_cmd("click", "fn:HandleButtonClicked name:BackButton@WBP_RespawnScreen", 15)
                    say("  CONTINUE click -> ok=%s %s" % (ok, d))
                    if ok: clicked = True; t_click = time.time()
                if clicked and not is_dead():
                    st = get_state()
                    if st:
                        say("RESPAWN pos=%.0f,%.0f,%.0f after=%.1f" % (*st["pawn"], time.time() - t0))
                        return
                time.sleep(1.0)
            save_stall(out, "respawn")
            raise RespawnFail("no respawn within 60 s after the death at %s (clicked=%s)" % (wp["name"], clicked))
        def chk(wi, wp):
            if is_dead():
                raise WaypointDied()
        def wait_frames(nfr, pawn_still=0.0, label=None):
            """condition wait: the game has rendered >= nfr more frames (fresh image) and, if pawn_still, the pawn has not moved for that long.
            label: log 'FPS <label>' from frames/elapsed (free, no extra blocking probe)"""
            _t_wf = time.time()
            _r = _wait_frames(nfr, pawn_still)
            if label and _r:
                el = max(time.time() - _t_wf, 0.001)
                say("FPS %s: %.1f (%d frames in %.1f s, wait_frames)" % (label, _r / el, _r, el))
        def _wait_frames(nfr, pawn_still=0.0):
            ok0, d0, _ = send_cmd("frame") if ENG else (None, "", "")
            if not ok0:
                time.sleep(1.0); return
            try: f0 = int(d0)
            except ValueError:
                time.sleep(1.0); return
            t0 = time.time(); last_pos = None; still_since = None
            while time.time() - t0 < 10:
                ok1, d1, _ = send_cmd("frame")
                try: adv = int(d1) - f0
                except ValueError: adv = 0
                if pawn_still:
                    st1 = get_state(3)
                    pos = st1["pawn"] if st1 else None
                    if pos and last_pos and max(abs(a - b) for a, b in zip(pos, last_pos)) < 1.0:
                        still_since = still_since or time.time()
                    else:
                        still_since = None
                    last_pos = pos
                    if adv >= nfr and still_since and time.time() - still_since >= pawn_still:
                        return adv
                elif adv >= nfr:
                    return adv
                time.sleep(0.1)
        prev_shot = [None]; views_done = {}; vstate = {}
        def do_waypoint(wi, wp):
            nonlocal n
            if wi < 5:
                if ENG: send_cmd("teleport", str(wi + 1))
                else: combo("ctrl+shift+" + "zxcvb"[wi])
            if ENG and wp.get("cmd"):   # test-only: run one engine-mode verb at this waypoint (e.g. 'tadpole'), then wait cmdWait s
                ok_c, d_c, _ = send_cmd(wp["cmd"]); say("CMD %s -> ok=%s %s" % (wp["cmd"], ok_c, d_c)); time.sleep(float(wp.get("cmdWait", 3)))
            views = wp.get("views")
            wait_frames(10, 0.0 if views else 0.6)   # abs views: no "pawn still" wait (a swimming pawn never is, and every second costs oxygen)
            chk(wi, wp)
            if views == "one":
                # diagnostic waypoint: probe, shot k0, wait `wait` seconds (death-checked every 5 s, probe every `probeEvery` s), probe, shot k1
                def _one_shot(k, tag):
                    wait_frames(6, 0.0)
                    chk(wi, wp)
                    if ENG: send_cmd("camlog", "%s_k%d" % (wp["name"], k))
                    st1 = get_state() or {"pawn": (0, 0, 0), "cam": (0, 0, 0), "yaw": float("nan"), "pitch": float("nan")}
                    fn1 = "%02d_%s_k%d.png" % (wi, wp["name"], k)
                    _im1 = shot(os.path.join(shots_dir, fn1))
                    say("SHOTSIZE %s %dx%d (%s)" % (fn1, _im1.size[0], _im1.size[1], tag))
                    with open(manifest, "a") as f:
                        f.write("%d\t%s\t%d\t%.2f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%s\n" % (wi, wp["name"], k, st1["yaw"], *st1["pawn"], *st1["cam"], int(time.time()), fn1))
                    print("[driver] SHOT %s yaw=%.1f pitch=%.1f pawn=%s" % (fn1, st1["yaw"], st1["pitch"], st1["pawn"]), flush=True)
                if ENG and wp.get("probe"): send_cmd("sn1probe", "%s_%s_start" % (wp["name"], wp["probe"]), 30)
                _one_shot(0, "start")
                _w = float(wp.get("wait", 0)); _t_w = time.time(); _t_p = time.time(); _pe = float(wp.get("probeEvery", 0))
                while time.time() - _t_w < _w:
                    time.sleep(1.0)
                    if int(time.time() - _t_w) % 5 == 0: chk(wi, wp)
                    if _pe and ENG and wp.get("probe") and time.time() - _t_p >= _pe:
                        send_cmd("sn1probe", "%s_%s_t%d" % (wp["name"], wp["probe"], int(time.time() - _t_w)), 30); _t_p = time.time()
                if _w: say("diagnostic wait done: %.0f s" % (time.time() - _t_w))
                if ENG and wp.get("probe"): send_cmd("sn1probe", "%s_%s_end" % (wp["name"], wp["probe"]), 30)
                _one_shot(1, "after wait")
                return
            if views == "vanish":
                # long diagnostic waypoint (2026-11-23, vanish_proof): stay in view of the terrain, re-teleport + re-look before every shot, census every probeEvery s,
                # o2 refill every o2Every s, watch the game log for the story-goal burst, force it at forceGoalAt s if it has not come, run to `wait` s
                # (or `afterBurst` s after the burst, if set). State survives a death/retry (timeline is not restarted).
                vs = vstate.setdefault(wi, {"t0": time.time(), "k": 0, "shot": -1e9, "probe": -1e9, "o2": -1e9, "burst": None, "forced": False, "off": 0, "tailbuf": "", "seen": set(), "n": 0})
                BURST_RX = re.compile(r"Unlocked story goal (DA_Investigation_BioBed_Unlock_CoralGardens_StoryGoal|DA_Player_NoA_FirstRadioMessage_StoryGoal|DA_Player_NoA_FirstRadioMessage_without_BaseNoA_StoryGoal)|Alert_Research1_PDA_1")
                def el(): return time.time() - vs["t0"]
                def v_census(tag):
                    ok_c, d_c, _ = send_cmd("terraincensus", "%s_%s" % (wp["name"], tag), 30)
                    say("TCENSUS t=%.0f %s -> ok=%s %s" % (el(), tag, ok_c, d_c))
                def v_shot(tag):
                    if wi < 5 and ENG: send_cmd("teleport", str(wi + 1))
                    if ENG and wp.get("o2"): send_cmd("o2fill")
                    chk(wi, wp)
                    if wp.get("yaw") is not None: turn_to(wrap(float(wp["yaw"])), float(wp.get("pitch", 0.0)), cal, tol=1.5)
                    chk(wi, wp)
                    wait_frames(6, 0.0)
                    chk(wi, wp)
                    k = vs["k"]; vs["k"] += 1
                    if ENG: send_cmd("camlog", "%s_k%d" % (wp["name"], k))
                    st1 = get_state() or {"pawn": (0, 0, 0), "cam": (0, 0, 0), "yaw": float("nan"), "pitch": float("nan")}
                    fn1 = "%02d_%s_k%d.png" % (wi, wp["name"], k)
                    _im1 = shot(os.path.join(shots_dir, fn1))
                    say("SHOTSIZE %s %dx%d (t=%.0f %s)" % (fn1, _im1.size[0], _im1.size[1], el(), tag))
                    with open(manifest, "a") as f:
                        f.write("%d\t%s\t%d\t%.2f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%s\n" % (wi, wp["name"], k, st1["yaw"], *st1["pawn"], *st1["cam"], int(time.time()), fn1))
                    print("[driver] SHOT %s t=%.0f %s yaw=%.1f pitch=%.1f pawn=%s" % (fn1, el(), tag, st1["yaw"], st1["pitch"], st1["pawn"]), flush=True)
                def v_scanlog():
                    try:
                        with open(gl_path, "rb") as f:
                            f.seek(vs["off"]); chunk = f.read()
                        vs["off"] += len(chunk)
                    except OSError:
                        return None
                    txt = chunk.decode("utf-8", "replace")
                    for line in txt.splitlines():
                        m = BURST_RX.search(line)
                        if m and (m.group(1) or "Alert_Research1") not in vs["seen"]:
                            vs["seen"].add(m.group(1) or "Alert_Research1")
                            say("LOGLINE %s" % line.strip()[:200])
                            if vs["burst"] is None: vs["burst"] = (el(), line.strip()[:60])
                    return vs["burst"]
                def v_burst_note():
                    b = vs["burst"]
                    say("BURST %s t=%.1f (log line %s)" % ("forced" if vs["forced"] else "natural", b[0], b[1]))
                    v_census("burst"); v_shot("burst"); vs["probe"] = vs["shot"] = time.time()
                if not vs["n"]:
                    # the log may already hold the burst from before the waypoint started: that would make it unusable as 'before'
                    vs["off"] = 0; pre = v_scanlog()
                    if pre: say("WARNING burst already in the game log before the waypoint started: %s" % (pre,)); vs["burst"] = None; vs["seen"].clear()
                    vs["off"] = os.path.getsize(gl_path) if os.path.exists(gl_path) else 0
                    if ENG: send_cmd("storygoalstate", "DA_Player_NoA_FirstRadioMessage_StoryGoal")
                    v_census("start"); v_shot("start"); vs["n"] = 1
                    vs["shot"] = vs["probe"] = vs["o2"] = time.time()
                    say("vanish: t0 set, wait=%s forceGoalAt=%s" % (wp.get("wait"), wp.get("forceGoalAt")))
                _w = float(wp.get("wait", 0)); _se = float(wp.get("shotEvery", 30)); _pe = float(wp.get("probeEvery", 30)); _oe = float(wp.get("o2Every", 30))
                _fg = float(wp.get("forceGoalAt", 1e9)); _ab = float(wp.get("afterBurst", 0)); _force_t = None
                while el() < _w:
                    time.sleep(1.0)
                    chk(wi, wp)
                    was = vs["burst"]
                    v_scanlog()
                    if vs["burst"] and not was: v_burst_note()
                    if not vs["burst"] and not vs["forced"] and el() >= _fg:
                        ok_g, d_g, _ = send_cmd("storygoal", "DA_Player_NoA_FirstRadioMessage_StoryGoal", 30)
                        say("FORCEGOAL t=%.0f storygoal -> ok=%s %s" % (el(), ok_g, d_g)); vs["forced"] = True; _force_t = el()
                    if vs["forced"] and not vs["burst"] and _force_t is not None and el() - _force_t > 20:
                        say("BURST forced-sent but no burst line in the game log within 20 s (storygoal ok result above)"); _force_t = None
                    if vs["burst"] and _ab and el() - vs["burst"][0] >= _ab:
                        say("afterBurst %.0f s reached, ending the wait" % _ab); break
                    if _oe and ENG and time.time() - vs["o2"] >= _oe:
                        send_cmd("o2fill"); vs["o2"] = time.time()
                    if _pe and time.time() - vs["probe"] >= _pe:
                        v_census("t%d" % int(el())); vs["probe"] = time.time()
                    if _se and time.time() - vs["shot"] >= _se:
                        v_shot("t%d" % int(el())); vs["shot"] = time.time()
                say("diagnostic wait done: %.0f s, burst=%s forced=%s" % (el(), vs["burst"], vs["forced"]))
                if not vs["burst"]: say("BURST none seen in the game log")
                v_census("end"); v_shot("end")
                return
            def o2():   # test-only oxygen refill (waypoint field "o2": true)
                if ENG and wp.get("o2"):
                    ok_o, d_o, _ = send_cmd("o2fill")
                    if not ok_o: say("O2FILL failed: %s" % d_o)
            if views == "script":
                # scripted engine-verb steps (bug report popup test). Step kinds: {"cmd","args","wait"}, {"state":{k:v}} (bugreport_state detail
                # must match; text is a substring match), {"time":"frozen"|"advancing","over":s}, {"shot":name}. Results: ASSERT PASS/FAIL lines.
                def bstate():
                    ok_s, d_s, _ = send_cmd("bugreport_state", "", 15)
                    kv = {}
                    if ok_s:
                        head, _, txt = d_s.partition(" text=")
                        for tok in head.split():
                            k_, _, v_ = tok.partition("=")
                            kv[k_] = v_
                        kv["text"] = txt
                    return ok_s, kv, d_s
                for si, stp in enumerate(wp.get("steps", [])):
                    if "cmd" in stp:
                        ok_c, d_c, _ = send_cmd(stp["cmd"], stp.get("args", ""), 60)
                        say("STEP %d CMD %s %s -> ok=%s %s" % (si, stp["cmd"], stp.get("args", ""), ok_c, d_c))
                        if not ok_c: say("ASSERT FAIL step %d cmd %s failed: %s" % (si, stp["cmd"], d_c))
                        time.sleep(float(stp.get("wait", 1)))
                    elif "state" in stp:
                        ok_s, kv, raw = bstate()
                        for k_, v_ in stp["state"].items():
                            good = ok_s and ((v_ in kv.get(k_, "")) if k_ == "text" else (kv.get(k_) == v_))
                            say("ASSERT %s step %d state %s=%s (got %s) | %s" % ("PASS" if good else "FAIL", si, k_, v_, kv.get(k_), raw[:200]))
                    elif "time" in stp:
                        ok1, kv1, _r1 = bstate(); time.sleep(float(stp.get("over", 2))); ok2, kv2, _r2 = bstate()
                        try: dt = float(kv2.get("time")) - float(kv1.get("time"))
                        except (TypeError, ValueError): dt = None
                        good = dt is not None and ((abs(dt) < 0.05) if stp["time"] == "frozen" else (dt > 0.5 * float(stp.get("over", 2))))
                        say("ASSERT %s step %d time %s (game time %s -> %s, dt=%s)" % ("PASS" if good else "FAIL", si, stp["time"], kv1.get("time"), kv2.get("time"), dt))
                    elif "shot" in stp:
                        fn = "%02d_%s_%s.png" % (wi, wp["name"], stp["shot"])
                        try:
                            _im = shot(os.path.join(shots_dir, fn)); say("STEP %d SHOT %s %dx%d" % (si, fn, _im.size[0], _im.size[1]))
                        except Exception as e_s:  # noqa: BLE001
                            say("ASSERT FAIL step %d shot %s: %r" % (si, fn, e_s))
                        st = get_state() or {"pawn": (0, 0, 0), "cam": (0, 0, 0), "yaw": float("nan")}
                        with open(manifest, "a") as f:
                            f.write("%d\t%s\t%d\t%.2f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%s\n" % (wi, wp["name"], si, st["yaw"], *st["pawn"], *st["cam"], int(time.time()), fn))
                        n += 1
                return
            if views == "fixed":
                # one view at waypoint yaw/pitch (UE degrees, as in an F1 report), then optional engine verb "cmdAfter" (e.g. bugshot), one shot k0
                o2()
                if ENG and wp.get("fov"):
                    ok_f, d_f, _ = send_cmd("fov", str(wp["fov"]))
                    say("FOV request %s -> ok=%s %s" % (wp["fov"], ok_f, d_f))
                chk(wi, wp)
                st = turn_to(wrap(float(wp["yaw"])), float(wp["pitch"]), cal, tol=1.0)
                o2(); chk(wi, wp)
                wait_frames(6, 0.0, "wp_%s" % wp["name"])
                chk(wi, wp)
                if ENG and wp.get("cmdAfter"):
                    ok_c, d_c, _ = send_cmd(wp["cmdAfter"], "", 60); say("CMDAFTER %s -> ok=%s %s" % (wp["cmdAfter"], ok_c, d_c)); time.sleep(float(wp.get("cmdWait", 3)))
                if ENG: send_cmd("camlog", "%s_k0" % wp["name"])
                st = get_state() or st or {"pawn": (0, 0, 0), "cam": (0, 0, 0), "yaw": float("nan"), "pitch": float("nan")}
                say("VIEWERR fixed target yaw=%.1f pitch=%.1f measured yaw=%.2f pitch=%.2f cam=(%.0f,%.0f,%.0f)" % (float(wp["yaw"]), float(wp["pitch"]), st["yaw"], st["pitch"], *st["cam"]))
                fn = "%02d_%s_k0.png" % (wi, wp["name"])
                _im = shot(os.path.join(shots_dir, fn))
                say("SHOTSIZE %s %dx%d" % (fn, _im.size[0], _im.size[1]))
                with open(manifest, "a") as f:
                    f.write("%d\t%s\t%d\t%.2f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%s\n" % (wi, wp["name"], 0, st["yaw"], *st["pawn"], *st["cam"], int(time.time()), fn))
                n += 1
                print("[driver] SHOT %s yaw=%.1f pitch=%.1f pawn=%s" % (fn, st["yaw"], st["pitch"], st["pawn"]), flush=True)
                return
            if views in ("abs8ud", "down45"):
                o2()
                if ENG and wp.get("fov"):
                    ok_f, d_f, _ = send_cmd("fov", str(wp["fov"]))
                    say("FOV request %s -> ok=%s %s" % (wp["fov"], ok_f, d_f))
                done = views_done.setdefault(wi, set())   # shots survive a death: the retry only takes the missing views
                if ENG and wp.get("probe") and not done: send_cmd("sn1probe" if wp["probe"] != "env" else "envprobe", "%s_%s_before" % (wp["name"], wp["probe"]), 30)
                for k in range(2 if views == "down45" else 10):
                    if k in done: continue
                    o2()
                    chk(wi, wp)
                    if views == "down45": ty, tp = 0.0, (-89.0 if k == 0 else -45.0)
                    else: ty, tp = (45.0 * k, 0.0) if k < 8 else (0.0, 89.0 if k == 8 else -89.0)
                    st = turn_to(wrap(ty), tp, cal, tol=1.5)
                    o2()
                    chk(wi, wp)
                    wait_frames(6, 0.0, ("wp_%s" % wp["name"]) if not done else None)
                    chk(wi, wp)
                    if ENG: send_cmd("camlog", "%s_k%d" % (wp["name"], k))
                    st = get_state() or st or {"pawn": (0, 0, 0), "cam": (0, 0, 0), "yaw": float("nan"), "pitch": float("nan")}
                    eyaw = abs(wrap(ty - st["yaw"])) if (k < 8 or views == "down45") else 0.0; epit = abs(tp - st["pitch"])
                    say("VIEWERR k%d target yaw=%.1f pitch=%.1f measured yaw=%.2f pitch=%.2f err yaw=%.2f pitch=%.2f cam=(%.0f,%.0f,%.0f) %s" % (
                        k, ty, tp, st["yaw"], st["pitch"], eyaw, epit, *st["cam"], "OK" if eyaw <= 2.0 and epit <= 2.0 else "OUT_OF_TOLERANCE"))
                    fn = "%02d_%s_k%d.png" % (wi, wp["name"], k)
                    _im = shot(os.path.join(shots_dir, fn))
                    say("SHOTSIZE %s %dx%d" % (fn, _im.size[0], _im.size[1]))
                    with open(manifest, "a") as f:
                        f.write("%d\t%s\t%d\t%.2f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%s\n" % (wi, wp["name"], k, st["yaw"], *st["pawn"], *st["cam"], int(time.time()), fn))
                    done.add(k); n += 1
                    print("[driver] SHOT %s yaw=%.1f pitch=%.1f pawn=%s" % (fn, st["yaw"], st["pitch"], st["pawn"]), flush=True)
                if ENG and wp.get("probeAfter"): send_cmd("sn1probe", "%s_%s_after" % (wp["name"], wp["probeAfter"]), 30)
                return
            st = get_state()
            if wp.get("offset") and st:
                dx, dy_ = st["lifepod"][0] - st["pawn"][0], st["lifepod"][1] - st["pawn"][1]
                front = math.degrees(math.atan2(dy_, dx))
            else:
                front = st["yaw"] if st else 0.0
            say("waypoint %s front yaw %.1f" % (wp["name"], front)); mouse_probe("waypoint_" + wp["name"])
            for k in range(8):
                chk(wi, wp)
                if wi < 5:
                    if ENG: send_cmd("teleport", str(wi + 1))
                    else: combo("ctrl+shift+" + "zxcvb"[wi])
                st = turn_to(wrap(front + 45 * k), 0.0, cal)
                chk(wi, wp)
                wait_frames(10 if k == 0 else 6, 0.0, ("wp_%s" % wp["name"]) if k == 0 else None)
                chk(wi, wp)
                fn = "%02d_%s_k%d.png" % (wi, wp["name"], k)
                _im = shot(os.path.join(shots_dir, fn))
                try:   # Q1 evidence: per-shot luma + mean abs diff to the previous shot (0 = identical/stale frame)
                    import numpy as _np
                    _a = _np.asarray(_im.convert("L"), dtype=_np.float32)
                    _d = float(_np.abs(_a - prev_shot[0]).mean()) if prev_shot[0] is not None else -1.0
                    prev_shot[0] = _a
                    say("Q1 %s luma=%.1f diff_prev=%s" % (fn, float(_a.mean()), "n/a" if _d < 0 else "%.2f" % _d))
                except Exception as _ex: say("Q1 stats failed: %s" % _ex)
                st = st or get_state() or {"pawn": (0, 0, 0), "cam": (0, 0, 0), "yaw": float("nan"), "pitch": float("nan")}
                with open(manifest, "a") as f:
                    f.write("%d\t%s\t%d\t%.2f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%s\n" % (wi, wp["name"], k, st["yaw"], *st["pawn"], *st["cam"], int(time.time()), fn))
                n += 1
                print("[driver] SHOT %s yaw=%.1f pitch=%.1f pawn=%s" % (fn, st["yaw"], st["pitch"], st["pawn"]), flush=True)
        for wi, wp in enumerate(plan["waypoints"]):
            for attempt in (1, 2):
                try:
                    do_waypoint(wi, wp); break
                except WaypointDied:
                    handle_death(wi, wp)
                    if attempt == 2:
                        died_wps.append(wp["name"])
                        print("[driver] DIED_WAYPOINT %s (died twice, no further shots there)" % wp["name"], flush=True)
                    else:
                        say("retrying waypoint %s once after the respawn" % wp["name"])
        print("[driver] DEATHS %d RESPAWNS %d DIED_WAYPOINTS %s" % (len(deaths), len(deaths), ",".join(died_wps) or "none"), flush=True)
        say("all shots done: %d" % n)
        # quit through the Escape menu (autotest.sh kills the process after 60 s if this did not end it)
        try:
            do_steps(menus["quit_game"])
        except FocusError:
            if game_pids():
                raise
            say("game window closed after the last quit click (expected)")
        _tq = time.time()
        while game_pids() and time.time() - _tq < 30: time.sleep(1.0)
        say("CLEAN QUIT path=main_quit exe_exited=%s after %.1f s (autotest.sh force-kills only if it is still running 60 s after the driver ends)" % (not game_pids(), time.time() - _tq))
        if game_pids():
            save_stall(out, "quit"); say("QUIT_FAILED game process still running after the quit steps")
            print("[driver] RESULT FAIL_QUIT game still running"); clean_exit(False); return 1
        if fguard: fguard.stop()
        print("[driver] RESULT DONE"); return 0
    except MenuFail as e:
        reason = "quit" if e.kind == "quit" else "menu"
        if ENG and game_pids():
            try:   # evidence for the planner: what the engine sees as visible buttons at the stall
                with open(os.path.join(out, "buttons_%s.txt" % reason), "w", encoding="utf-8") as bf:
                    for b in visible_buttons(): bf.write(repr(b) + chr(10))
                    for lab in ("00h 0", "Continue"):   # FUNCS of the save row and the panel Continue button, for choosing a click method
                        ok_, d_, t_ = send_cmd("funcs", lab, 20)
                        bf.write("funcs %r -> ok=%s %s%s" % (lab, ok_, d_, chr(10)))
                        for fm in re.finditer(r"\[SN2AutoTest\] FUNCS (.*)", t_): bf.write("  " + fm.group(1) + chr(10))
            except Exception as ex: say("button dump failed: %s" % ex)
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
        if type(e).__name__ == "RespawnFail":
            print("[driver] RESULT FAIL_RESPAWN %s" % e, flush=True)
            clean_exit(False); return 1
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
    keep = {k: plan.get(k) for k in ("name", "worldLevel", "waypoints", "lobbyCensus", "worldCensus")}
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
        if c == "quit":   # engine mode: best-effort clean quit for autotest.sh timeout/stop: main_quit click via the command channel, WM_CLOSE fallback
            ENG = True
            ok, d, _ = send_cmd("click", "fn:HandleButtonClicked name:QuitButton@WBP_MainLobbyScreen", 8)
            print("quit click ok=%s detail=%s" % (ok, d))
            if not ok:
                def _close():
                    h = game_hwnd()
                    if h: user32.PostMessageW(h, 0x0010, 0, 0)
                    return bool(h)
                r = _on_hidden_desktop(_close) if os.environ.get("SN2_HIDDEN_DESKTOP") == "1" else _close()
                print("WM_CLOSE posted=%s" % r)
            return 0
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
