#!/usr/bin/env python3
"""Lua-free OS-input driver for the GC-watchdog UE4SS on/off A/B (src/tools/gc_ab_test.sh). Does NOT touch autotest_driver.py: it imports it
as a module and reuses its OS-input helpers (click, press, combo, focus, find_game_dialogs, game_pids) and the screen-identity classifier.

Needs from the game: ONLY the game log (<LOCALAPPDATA>/Subnautica2/Saved/Logs/Subnautica2.log) and the screen (full-screen grabs, screens.json
fingerprints), never UE4SS.log / SN2AutoTest run files. So it works with and without UE4SS (dwmapi.dll).

Usage: python gc_ab_driver.py run --launch-epoch N [--stay 20] [--lobby-timeout 300] [--world-timeout 240] [--world-map L_SN2World]
Prints (flush) lines '[gcab] HH:MM:SS ...' and finally one 'RESULT <DONE|GC_CRASH|EXITED|FAIL_LOBBY|FAIL_MENU|FAIL_WORLD|FAIL_DIALOG|FAIL_QUIT>'.
Epoch markers: LOBBY_LOG_AT, MENU_READY_AT, FIRST_CLICK_AT, WORLD_LOG_AT (all unix seconds, from this process' clock)."""
import json
import os
import re
import sys
import time

os.environ["SN2_INPUT"] = "os"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autotest_driver as ad  # noqa: E402

ad.INPUT_MODE = "os"
ad.ENG = False

PLANS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mods", "SN2AutoTest", "plans")
GAMELOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Subnautica2", "Saved", "Logs", "Subnautica2.log")
CRASH_RX = re.compile(r"Spent too much time waiting for FinishDestroy|AbortInsideMemberFunction|Fatal error|LowLevelFatalError")


def say(m):
    print("[gcab] %s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


OUT_DIR = os.environ.get("SN2_GCAB_OUT") or os.getcwd()   # run folder (gc_ab_test.sh exports it); evidence PNGs go here
_last_focus = [0.0]


def focus_game():
    """2026-11-24: bring the game window to the front before every screen grab / click (a console or the UE4SS 'Debugging Tools' window can
    cover it and break the screen fingerprints). Best effort, at most one attempt per 1.5 s; ad.focus() returns at once when the game already is
    the foreground window."""
    if time.time() - _last_focus[0] < 1.5:
        return
    _last_focus[0] = time.time()
    try:
        ad.focus()
    except Exception as e:  # noqa: BLE001
        say("focus_game: %s" % e)


def overlap_titles():
    """titles of visible top-level windows of other processes that overlap the game window rect (evidence for 'a window covers the game')"""
    import ctypes
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    res = []
    try:
        g = ad.game_hwnd()
        gr = wt.RECT(); u.GetWindowRect(g, ctypes.byref(gr))

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(h, _):
            if h != g and u.IsWindowVisible(h) and not u.IsIconic(h):
                r = wt.RECT(); u.GetWindowRect(h, ctypes.byref(r))
                n = u.GetWindowTextLengthW(h)
                if n and r.left < gr.right and r.right > gr.left and r.top < gr.bottom and r.bottom > gr.top:
                    b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
                    res.append("%r (%d,%d)-(%d,%d)%s" % (b.value, r.left, r.top, r.right, r.bottom, " FOREGROUND" if u.GetForegroundWindow() == h else ""))
            return True
        u.EnumWindows(cb, 0)
    except Exception as e:  # noqa: BLE001
        res.append("overlap_titles failed: %s" % e)
    return res


def save_desktop(name):
    try:
        from PIL import ImageGrab
        p = os.path.join(OUT_DIR, name)
        ImageGrab.grab().save(p)
        say("saved %s" % p)
    except Exception as e:  # noqa: BLE001
        say("save_desktop failed: %s" % e)


class GameLog:
    """incremental reader of the game log; ignores a log older than the launch (the game rotates the old one away at start)"""
    def __init__(self, launch_epoch):
        self.t0 = launch_epoch; self.off = 0; self.buf = ""

    def poll(self):
        try:
            if os.path.getmtime(GAMELOG) < self.t0:
                return self.buf
            size = os.path.getsize(GAMELOG)
            if size < self.off:
                self.off = 0; self.buf = ""
            if size > self.off:
                with open(GAMELOG, "rb") as f:
                    f.seek(self.off); self.buf += f.read().decode("utf-8", "replace"); self.off = size
        except OSError:
            pass
        return self.buf


def main(argv):
    a = {"--stay": "20", "--lobby-timeout": "300", "--world-timeout": "240", "--world-map": "L_SN2World", "--launch-epoch": "0"}
    i = 2
    while i < len(argv):
        a[argv[i]] = argv[i + 1]; i += 2
    stay = float(a["--stay"]); world_rx = re.compile(r"Took [\d.]+ seconds to LoadMap\(\S*%s" % re.escape(a["--world-map"]))
    lobby_rx = re.compile(r"LogLoad: LoadMap: \S*L_ClientLobby")
    log = GameLog(float(a["--launch-epoch"]))
    menus = json.load(open(os.path.join(PLANS, "menus.json")))
    # screen identity -> (x, y), taken from menus.json new_game / quit_game so the coordinates stay in one place
    nav = {s["expect"]: (s["x"], s["y"]) for s in menus["new_game"] if "x" in s}
    q = {s["screen"]: (s["x"], s["y"]) for s in menus["quit_game"] if "x" in s}
    from PIL import ImageGrab
    from autotest_screens import Screens
    scr = Screens()
    hist = []

    def ident():
        focus_game()
        r = scr.identify(ImageGrab.grab())
        hist.append((time.time(), r[0], r[5])); del hist[:-3]
        stable = len(hist) == 3 and len({h[1] for h in hist}) == 1 and hist[-1][0] - hist[0][0] >= 0.8 and abs(hist[-1][2] - hist[0][2]) < 1.5
        return r[0], stable

    def alive():
        return bool(ad.game_pids())

    def check_end(where):
        """-> RESULT string if the run is over (crash marker in the game log, or the process is gone), else None"""
        if CRASH_RX.search(log.poll()):
            say("GC/fatal marker in the game log (%s)" % where); return "GC_CRASH"
        if not alive():
            say("game process gone (%s)" % where); return "EXITED"
        return None

    def dialogs(state):
        ds = ad.find_game_dialogs()
        if not ds or state["n"] >= 3:
            return None
        d = ds[0]; labels = [b["text"] for b in d["buttons"]]
        say("DIALOG title=%r text=%r buttons=%r" % (d["title"], " | ".join(d["texts"]), labels)); state["n"] += 1
        pick = next((b for b in d["buttons"] if b["text"].strip().lower() in ("ok", "continue", "close")), None)
        if not pick:
            return "FAIL_DIALOG"
        ad.focus(d["hwnd"]); ad.click_window_button(pick); say("DIALOG_DISMISSED %s" % pick["text"]); time.sleep(1)
        return None

    def finish(res):
        print("RESULT %s" % res, flush=True); return 0 if res == "DONE" else 1

    try:
        # ---- game process up
        t_end = time.time() + 90
        while not alive() and time.time() < t_end:
            time.sleep(1)
        if not alive():
            return finish("EXITED")
        # ---- lobby: the game log shows the lobby LoadMap; start-up dialogs handled on the way
        t_end = time.time() + float(a["--lobby-timeout"]); dstate = {"n": 0}
        while True:
            buf = log.poll()
            m = lobby_rx.search(buf)
            if m:
                print("LOBBY_LOG_AT %.3f" % time.time(), flush=True); break
            r = check_end("waiting for the lobby")
            if r:
                return finish(r)
            r = dialogs(dstate)
            if r:
                return finish(r)
            if time.time() > t_end:
                say("lobby LoadMap not in the game log within %s s" % a["--lobby-timeout"]); return finish("FAIL_LOBBY")
            time.sleep(0.5)
        # ---- menus by screen identity: act at once on a stably identified screen, no fixed waits
        t_menu0 = time.time(); last = None; t_act = 0.0; attempts = 0; clicked_create = False
        t_end = time.time() + float(a["--world-timeout"]) + 120; first = True; unid0 = None; unid_saved = False
        while not world_rx.search(log.poll()):
            r = check_end("menus / world load")
            if r:
                return finish(r)
            r = dialogs(dstate)
            if r:
                return finish(r)
            if time.time() > t_end:
                say("world LoadMap not seen in time (last screen %s, create clicked %s); windows overlapping the game: %s" % (last, clicked_create, overlap_titles()))
                save_desktop("menu_fail_screen.png")
                return finish("FAIL_WORLD" if clicked_create else "FAIL_MENU")
            name, stable = ident()
            if name is None:
                unid0 = unid0 or time.time()
                if time.time() - unid0 > 20 and not unid_saved:   # one evidence PNG per run
                    unid_saved = True
                    say("screen unidentified for >20 s; windows overlapping the game: %s" % overlap_titles()); save_desktop("unidentified_screen.png")
            else:
                unid0 = None
            if stable and name in nav:
                if first:
                    print("MENU_READY_AT %.3f" % time.time(), flush=True)
                if name == last and time.time() - t_act < 15:   # 2026-11-24: was 8 s; a cold, shader-loading game answers a click late
                    time.sleep(0.3); continue
                attempts = attempts + 1 if name == last else 0
                if attempts >= 6:   # was 3
                    return finish("FAIL_MENU")
                if first:
                    first = False; print("FIRST_CLICK_AT %.3f" % time.time(), flush=True)
                say("screen %s stable -> click %s" % (name, nav[name])); _last_focus[0] = 0.0; focus_game(); ad.click(*nav[name])
                last = name; t_act = time.time(); clicked_create = clicked_create or name == "create_game"
            time.sleep(0.3)
        print("WORLD_LOG_AT %.3f" % time.time(), flush=True)
        say("world LoadMap done (%s); staying %.0f s" % (a["--world-map"], stay))
        t_stay = time.time() + stay
        while time.time() < t_stay:
            r = check_end("in the world")
            if r:
                return finish(r)
            time.sleep(1)
        # ---- clean quit: Escape -> pause menu EXIT -> EXIT WITHOUT SAVING -> (lobby again) main menu QUIT
        stage = 0; t_esc = 0.0; t_act = 0.0; n_esc = 0; t_end = time.time() + 300
        while alive() and time.time() < t_end:
            name, stable = ident()
            if stage == 0 and stable and name == "pause_menu":
                say("quit: pause menu -> exit"); ad.click(*q["pause_exit_game"]); stage = 1; t_act = time.time()
            elif stage == 0 and name is None and time.time() - t_esc > 6 and n_esc < 5:
                say("quit: Escape"); ad.press("esc"); t_esc = time.time(); n_esc += 1
            elif stage == 1 and stable and name == "exit_confirm":
                say("quit: confirm exit without saving"); ad.click(*q["exit_without_saving"]); stage = 2; t_act = time.time()
            elif stage == 2 and stable and name == "main_menu":
                say("quit: main menu QUIT"); ad.click(*q["main_quit"]); stage = 3; t_act = time.time()
            elif stage == 3 and time.time() - t_act > 25:
                break
            elif stage in (1, 2) and time.time() - t_act > 90:
                break
            elif stage == 0 and n_esc >= 5 and time.time() - t_esc > 8:
                break
            time.sleep(0.4)
        if alive():
            say("clean quit did not end the game (stage %d) -> Alt+F4" % stage)
            ad.combo("alt+f4")
            t_end = time.time() + 20
            while alive() and time.time() < t_end:
                time.sleep(1)
        if alive():
            return finish("FAIL_QUIT")
        return finish("DONE")
    except ad.FocusError:
        return finish("FAIL_FOCUS")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv))
