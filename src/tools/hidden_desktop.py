#!/usr/bin/env python3
"""Hidden Win32 desktop prototype (Part B investigation, 2026-11-22).

A second desktop ("SN2Test") in the interactive window station. Processes started on it are
invisible to the user and do not receive the user's real mouse / keyboard (those go to the
input desktop only). This tool NEVER calls SwitchDesktop unless --show is given by hand.

Usage:
  python hidden_desktop.py selftest [--exe PATH]  create desktop, launch a GDI app (default notepad.exe),
                                                  find its window, capture it with PrintWindow, kill it, close desktop
  python hidden_desktop.py launch EXE [ARGS...]   create desktop, launch EXE on it (prints pid), leave desktop open
                                                  (the desktop closes when its last process exits and this tool exits)
  python hidden_desktop.py windows                list windows on the desktop (needs the desktop to exist)
  python hidden_desktop.py shot FILE [PID]        PrintWindow capture of the biggest window on the desktop (or of PID)
  python hidden_desktop.py --show / --back        manual only: SwitchDesktop to SN2Test / back to the input desktop
"""
import ctypes, ctypes.wintypes as wt, os, subprocess, sys, time

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
DESK = "SN2Test"
GENERIC_ALL = 0x10000000
DESKTOP_ALL = 0x01FF | 0x000F0000  # DESKTOP_* rights + STANDARD_RIGHTS_REQUIRED

u32.CreateDesktopW.restype = wt.HANDLE
u32.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
u32.OpenDesktopW.restype = wt.HANDLE
u32.OpenDesktopW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.BOOL, wt.DWORD]
u32.CloseDesktop.argtypes = [wt.HANDLE]
u32.SwitchDesktop.argtypes = [wt.HANDLE]
u32.OpenInputDesktop.restype = wt.HANDLE
u32.OpenInputDesktop.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
WNDENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
u32.EnumDesktopWindows.argtypes = [wt.HANDLE, WNDENUM, wt.LPARAM]
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u32.IsWindowVisible.argtypes = [wt.HWND]
u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.GetWindowDC.restype = wt.HDC
u32.GetWindowDC.argtypes = [wt.HWND]
u32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
u32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
g32.CreateCompatibleDC.restype = wt.HDC
g32.CreateCompatibleDC.argtypes = [wt.HDC]
g32.CreateCompatibleBitmap.restype = wt.HBITMAP
g32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
g32.SelectObject.restype = wt.HGDIOBJ
g32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
g32.DeleteObject.argtypes = [wt.HGDIOBJ]
g32.DeleteDC.argtypes = [wt.HDC]


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


g32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.POINTER(BMIH), wt.UINT]


def create_desktop(name=DESK):
    """create (or open if it exists) the hidden desktop; returns the handle. Never switches to it."""
    h = u32.CreateDesktopW(name, None, None, 0, DESKTOP_ALL, None)
    if not h:
        raise OSError("CreateDesktopW failed, error %d" % ctypes.get_last_error())
    return h


def close_desktop(h):
    if h and not u32.CloseDesktop(h):
        return False
    return True


def launch_on_desktop(argv, name=DESK, cwd=None):
    """CreateProcess with STARTUPINFO.lpDesktop = 'WinSta0\\<name>'. Returns (pid, process handle)."""
    class SI(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
                    ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                    ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                    ("lpReserved2", ctypes.c_void_p), ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE),
                    ("hStdError", wt.HANDLE)]

    class PI(ctypes.Structure):
        _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]
    si = SI(); si.cb = ctypes.sizeof(si)
    si.lpDesktop = "WinSta0" + chr(92) + name
    pi = PI()
    cmd = subprocess.list2cmdline(argv)
    k32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD,
                                   ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(SI), ctypes.POINTER(PI)]
    buf = ctypes.create_unicode_buffer(cmd)
    ok = k32.CreateProcessW(None, buf, None, None, False, 0, None, cwd or os.path.dirname(os.path.abspath(argv[0])) or None,
                            ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        raise OSError("CreateProcessW failed, error %d" % ctypes.get_last_error())
    k32.CloseHandle(pi.hThread)
    return pi.dwProcessId, pi.hProcess


def list_windows(h):
    """[(hwnd, pid, class, title, (l,t,r,b), visible)] for the top-level windows of desktop handle h"""
    out = []

    def cb(hwnd, _):
        pid = wt.DWORD(); u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        c = ctypes.create_unicode_buffer(256); t = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, c, 256); u32.GetWindowTextW(hwnd, t, 256)
        r = wt.RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
        out.append((hwnd, pid.value, c.value, t.value, (r.left, r.top, r.right, r.bottom), bool(u32.IsWindowVisible(hwnd))))
        return True
    f = WNDENUM(cb)
    u32.EnumDesktopWindows(h, f, 0)
    return out


def capture(hwnd, path):
    """PrintWindow(PW_RENDERFULLCONTENT=2) into a 32-bit bitmap; saves PNG (Pillow) and returns (w, h, mean luminance)"""
    r = wt.RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise OSError("window has no size")
    wdc = u32.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(wdc)
    bmp = g32.CreateCompatibleBitmap(wdc, w, h)
    old = g32.SelectObject(mdc, bmp)
    ok = u32.PrintWindow(hwnd, mdc, 2)
    bi = BMIH(); bi.biSize = ctypes.sizeof(bi); bi.biWidth = w; bi.biHeight = -h; bi.biPlanes = 1; bi.biBitCount = 32
    buf = (ctypes.c_ubyte * (w * h * 4))()
    g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    g32.SelectObject(mdc, old); g32.DeleteObject(bmp); g32.DeleteDC(mdc); u32.ReleaseDC(hwnd, wdc)
    from PIL import Image
    import numpy as np
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)[:, :, :3][:, :, ::-1]
    Image.fromarray(arr).save(path)
    return w, h, float(arr.mean()), bool(ok)


def selftest(exe):
    shots = os.path.join(os.environ.get("SN2_AUTOTEST_OUT", os.getcwd()), "hidden_desktop_selftest.png")
    h = create_desktop()
    print("desktop created:", DESK, "handle", h)
    pid = hp = None
    try:
        pid, hp = launch_on_desktop([exe])
        print("launched pid", pid, "on", DESK)
        t0 = time.time(); win = None
        while time.time() - t0 < 15 and not win:
            for w in list_windows(h):
                if w[1] == pid and w[5] and w[4][2] - w[4][0] > 50:
                    win = w; break
            time.sleep(0.3)
        print("windows on desktop:", [(hex(w[0]), w[1], w[2], w[3][:30], w[5]) for w in list_windows(h)])
        if not win:
            print("RESULT selftest FAIL: no visible window for pid %d within 15 s" % pid); return 1
        # sanity: the window must NOT exist on the user's desktop (EnumWindows on the input desktop)
        found_on_user = []
        EW = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def ecb(hwnd, _):
            p = wt.DWORD(); u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid: found_on_user.append(hwnd)
            return True
        u32.EnumWindows(EW(ecb), 0)
        print("windows of that pid on the user's desktop:", len(found_on_user))
        wd, ht, lum, ok = capture(win[0], shots)
        print("capture %dx%d lum=%.1f printwindow_ok=%s -> %s" % (wd, ht, lum, ok, shots))
        res = "PASS" if (not found_on_user and wd > 50 and ht > 50) else "FAIL"
        print("RESULT selftest %s" % res)
        return 0 if res == "PASS" else 1
    finally:
        if pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            if hp: k32.CloseHandle(hp)
        time.sleep(0.5)
        print("desktop closed:", close_desktop(h))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 2
    if a[0] == "selftest":
        exe = a[a.index("--exe") + 1] if "--exe" in a else os.path.join(os.environ.get("SystemRoot", "C:" + chr(92) + "Windows"), "System32", "notepad.exe")
        return selftest(exe)
    if a[0] == "launch":
        os.environ["SteamAppId"] = "1962700"; os.environ["SteamGameId"] = "1962700"   # needed for a direct launch (git b949409)
        # HOLDER: this process owns the desktop handle and must stay alive until the game exits. Exiting right after CreateProcess
        # destroyed the desktop before the game's user32 attached (run 20261122_132101: game never ran). (see research/01).
        h = create_desktop(); pid, hp = launch_on_desktop(a[1:])
        print("pid", pid, flush=True)
        k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        k32.WaitForSingleObject(hp, 0xFFFFFFFF if "--nowait" not in os.environ else 0)
        close_desktop(h); print("game exited; desktop closed", flush=True); return 0
    if a[0] == "windows":
        h = u32.OpenDesktopW(DESK, 0, False, DESKTOP_ALL)
        for w in list_windows(h): print(w)
        return 0
    if a[0] == "shot":
        h = u32.OpenDesktopW(DESK, 0, False, DESKTOP_ALL)
        ws = [w for w in list_windows(h) if w[5] and (len(a) < 3 or w[1] == int(a[2]))]
        ws.sort(key=lambda w: -(w[4][2] - w[4][0]) * (w[4][3] - w[4][1]))
        print(capture(ws[0][0], a[1])); return 0
    if a[0] in ("--show", "--back"):
        h = u32.OpenDesktopW(DESK, 0, False, DESKTOP_ALL) if a[0] == "--show" else u32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        print("SwitchDesktop:", bool(u32.SwitchDesktop(h))); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
