#!/usr/bin/env python3
"""Bug-report collector (see research/01 "Bug reports from the user"). Run through bugshot_watch.sh under the Monitor tool.

Polls <ue4ss>/Mods/SN2BugShot/reports/*.json (written by the in-game F1 key). For each report: captures the game window (PrintWindow, normal
or hidden desktop; falls back to a screen grab if the capture is black), copies json + png + log excerpts into <Workspace>/bugshots/<id>/,
removes the report from the Mods folder and prints ONE line:
    BUGSHOT <id> [late] map=.. ue=(x,y,z) sn1=(x,y,z) depth=<m> hit=<actor|none> shot=<method> desc=<submitted|cancelled|nopopup|none> text="<first 150 chars, newlines as \n>" dir=<path>
The report folder also gets description.txt. <id>.json.pending files (popup still open) are ignored by the glob and never touched.
Also prints GAME started / GAME exited lines. Read-only toward the game: no input, no kill, no save access (only removes its own report files).
Usage: python -u bugshot_watch.py [--reports DIR] [--once]
"""
import ctypes, ctypes.wintypes as wt, glob, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
EXE = "Subnautica2-Win64-Shipping.exe"
UE4SS = os.environ["SN2_UE4SS_DIR"]
WORK = os.environ["SN2_WORKSPACE"]
REPORTS = os.path.join(UE4SS, "Mods", "SN2BugShot", "reports")
OUT = os.path.join(WORK, "bugshots")
UE4SS_LOG = os.path.join(UE4SS, "UE4SS.log")
GAME_LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Subnautica2", "Saved", "Logs", "Subnautica2.log")
SHOT_ROOT = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Subnautica2", "Saved", "Screenshots")
SW, SH = 1920, 1080   # client size the harness uses (hidden-desktop capture is cropped to it)
user32 = ctypes.windll.user32
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

def say(s):
    print(s, flush=True)

def game_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + EXE, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return {int(l.split('","')[1]) for l in out.splitlines() if EXE.lower() in l.lower()}

def game_hwnd(pids):
    """returns (hwnd, desktop) with desktop 'normal' or 'hidden'; largest visible window of the game process"""
    found = []
    def collect(h, desk):
        if user32.IsWindowVisible(h):
            pid = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value in pids:
                r = wt.RECT(); user32.GetWindowRect(h, ctypes.byref(r))
                area = (r.right - r.left) * (r.bottom - r.top)
                if area > 0:   # ignore 0-area helper windows of the same process
                    found.append((area, h, desk))
        return True
    cbN = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(lambda h, _: collect(h, "normal"))
    cbH = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(lambda h, _: collect(h, "hidden"))
    user32.EnumWindows(cbN, 0)
    user32.OpenDesktopW.restype = wt.HANDLE
    hd = user32.OpenDesktopW("SN2Test", 0, False, 0x01FF | 0x000F0000)
    if hd:
        user32.EnumDesktopWindows(hd, cbH, 0)
        user32.CloseDesktop(hd)
    if found:
        found.sort(key=lambda t: t[0], reverse=True)
        return found[0][1], found[0][2]
    return None, None

def capture(pids):
    """-> (PIL image or None, method string)"""
    import numpy as np
    import winshot
    h, desk = game_hwnd(pids)
    if not h:
        return None, "none(no game window)"
    if user32.IsIconic(h):
        return None, "none(minimized)"
    im, ok = winshot.capture(h)
    if desk == "hidden" and im.size != (SW, SH) and im.size[0] >= SW and im.size[1] >= SH:
        b = (im.size[0] - SW) // 2; top = im.size[1] - SH - b
        im = im.crop((b, top, b + SW, top + SH))
    mean = float(np.asarray(im).mean())
    if mean >= 2.0:
        return im, "printwindow-%s(mean=%.0f)" % (desk, mean)
    if desk == "normal":   # black PrintWindow (e.g. flip-model swapchain): screen grab of the window rect, only valid while the game is on top
        try:
            from PIL import ImageGrab
            r = wt.RECT(); user32.GetClientRect(h, ctypes.byref(r))
            pt = wt.POINT(0, 0); user32.ClientToScreen(h, ctypes.byref(pt))
            g = ImageGrab.grab(bbox=(pt.x, pt.y, pt.x + r.right, pt.y + r.bottom), all_screens=True)
            fg = user32.GetForegroundWindow() == h
            return g, "screengrab%s(printwindow mean=%.1f)" % ("" if fg else "-NOT-FOREGROUND", mean)
        except Exception as e:
            return im, "printwindow-black(%s)" % e
    return im, "printwindow-%s-black(mean=%.1f)" % (desk, mean)

class LogTail:
    """new lines of a log since the previous call (offset kept; a smaller file = rotated -> start at 0); first call starts at the current end"""
    def __init__(self, path):
        self.path = path
        self.off = os.path.getsize(path) if os.path.exists(path) else 0
    def take(self, cap=200):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return ""
        if size < self.off:
            self.off = 0
        with open(self.path, "rb") as f:
            f.seek(self.off); data = f.read()
        self.off = size
        lines = data.decode("utf-8", "replace").splitlines()
        if len(lines) > cap:
            lines = ["... (%d earlier lines cut)" % (len(lines) - cap)] + lines[-cap:]
        return "\n".join(lines) + "\n"

def engine_shot(rep_mtime, wait=3.0):
    """earliest image under Saved/Screenshots written at/after the capture time (HighResShot is asynchronous; the popup may stay open for a long time after it)"""
    end = time.time() + wait
    while True:
        best = None
        for ext in ("png", "jpg", "bmp"):
            for p in glob.glob(os.path.join(SHOT_ROOT, "**", "*." + ext), recursive=True):
                try:
                    m = os.path.getmtime(p)
                except OSError:
                    continue
                if m >= rep_mtime - 1 and (best is None or m < best[0]):
                    best = (m, p)
        if best or time.time() > end:
            return best[1] if best else None
        time.sleep(0.25)

def fnum(d, *path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d

def line_for(rep, id_, late, method, dest):
    ue, un = rep.get("ue"), rep.get("unity")
    f = lambda v: "%.0f" % v if isinstance(v, (int, float)) else "?"
    g = lambda v: "%.1f" % v if isinstance(v, (int, float)) else "?"
    ch = rep.get("crosshair") or {}
    hit = ch.get("actor") or ("?" if ch.get("hit") else "none")
    text = (rep.get("description") or "")[:150].replace("\r", "").replace("\n", "\\n").replace('"', "'")
    return 'BUGSHOT %s%s map=%s ue=(%s,%s,%s) sn1=(%s,%s,%s) depth=%s hit=%s shot=%s desc=%s text="%s" dir=%s' % (
        id_, " late" if late else "", rep.get("map", "?"),
        f(fnum(rep, "ue", "x")), f(fnum(rep, "ue", "y")), f(fnum(rep, "ue", "z")),
        g(fnum(rep, "unity", "x")), g(fnum(rep, "unity", "y")), g(fnum(rep, "unity", "z")),
        g(rep.get("depth")), hit, method, rep.get("descriptionState") or "none", text, dest.replace("\\", "/"))

def handle(path, started, ulog, glog, pids):
    id_ = os.path.splitext(os.path.basename(path))[0]
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8") as f:
            rep = json.load(f)
    except Exception:
        return False   # half-written or locked: retry next poll
    late = (mtime < started) or (time.time() - mtime > 5.0)
    method = "none"; im = None
    try:
        im, method = capture(pids) if pids else (None, "none(game not running)")
    except Exception as e:
        method = "none(%s)" % str(e)[:60]
    dest = os.path.join(OUT, id_)
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(path, os.path.join(dest, "report.json"))
    if im is not None:
        im.save(os.path.join(dest, "screen.png"))
    es = fnum(rep, "engineShot", "called") and engine_shot(rep.get("captureEpoch") or mtime) or None
    if es:
        shutil.copy2(es, os.path.join(dest, "engine_shot" + os.path.splitext(es)[1]))
    with open(os.path.join(dest, "ue4ss_log_since_last.txt"), "w", encoding="utf-8") as f:
        f.write(ulog.take())
    with open(os.path.join(dest, "game_log_since_last.txt"), "w", encoding="utf-8") as f:
        f.write(glog.take())
    with open(os.path.join(dest, "description.txt"), "w", encoding="utf-8") as f:
        f.write(rep.get("description") or "")
    with open(os.path.join(dest, "meta.txt"), "w", encoding="utf-8") as f:
        f.write("late=%s\nshot=%s\nengine_shot=%s\n" % (late, method, es or "none"))
    os.remove(path)
    say(line_for(rep, id_, late, method + ("+engine" if es else ""), dest))
    return True

def main():
    once = "--once" in sys.argv
    global REPORTS
    if "--reports" in sys.argv:
        REPORTS = sys.argv[sys.argv.index("--reports") + 1]
    os.makedirs(REPORTS, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    started = time.time()
    ulog, glog = LogTail(UE4SS_LOG), LogTail(GAME_LOG)
    say("WATCHING %s -> %s" % (REPORTS.replace("\\", "/"), OUT.replace("\\", "/")))
    pids = set(); last_proc = 0.0; state = None
    while True:
        now = time.time()
        if now - last_proc > 2.0:
            last_proc = now
            pids = game_pids()
            if pids and state != "up":
                state = "up"; say("GAME started pid=%s" % ",".join(map(str, sorted(pids))))
            elif not pids and state == "up":
                state = "down"; say("GAME exited")
            elif not pids and state is None:
                state = "down"
        for p in sorted(glob.glob(os.path.join(REPORTS, "*.json"))):
            handle(p, started, ulog, glog, game_pids() if not pids else pids)
        if once:
            return
        time.sleep(0.25)

if __name__ == "__main__":
    main()
