#!/usr/bin/env python3
"""Full-desktop screenshot + visible top-level window list for the GC-watchdog runs (gc_ab_test.sh).
Usage: python gc_ab_shot.py <png_path>   (writes <png_path> and <png_path>.windows.txt). Never raises: prints SHOT_OK / SHOT_FAILED <why>."""
import ctypes
import ctypes.wintypes as wt
import sys

user32 = ctypes.windll.user32


def windows():
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h) and not user32.IsIconic(h):
            n = user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cls, 256)
            r = wt.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if buf.value:
                out.append("hwnd=%d pid=%d class=%r title=%r rect=(%d,%d)-(%d,%d)%s" % (
                    h, pid.value, cls.value, buf.value, r.left, r.top, r.right, r.bottom,
                    " FOREGROUND" if user32.GetForegroundWindow() == h else ""))
        return True
    user32.EnumWindows(cb, 0)
    return out


def main():
    p = sys.argv[1]
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(p)
        with open(p + ".windows.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(windows()) + "\n")
        print("SHOT_OK", p)
    except Exception as e:  # noqa: BLE001
        print("SHOT_FAILED", e)


if __name__ == "__main__":
    main()
