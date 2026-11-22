#!/usr/bin/env python3
"""Window capture that works while the window is covered by other windows or not focused (engine input mode of the autotest harness).
No input events, no focus change. PrintWindow(hwnd, hdc, PW_CLIENTONLY | PW_RENDERFULLCONTENT) -> PIL image of the CLIENT area.
Usage: python winshot.py HWND_OR_PROCESS OUT.png      (HWND decimal, or the string 'game')
"""
import ctypes, ctypes.wintypes as wt, sys

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

PW_CLIENTONLY, PW_RENDERFULLCONTENT = 1, 2
DIB_RGB_COLORS, BI_RGB, SRCCOPY = 0, 0, 0x00CC0020

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

def client_size(hwnd):
    r = wt.RECT(); user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top

def capture(hwnd, flags=PW_CLIENTONLY | PW_RENDERFULLCONTENT):
    """returns (PIL.Image RGB, ok_flag_from_PrintWindow). Raises RuntimeError for an empty client area."""
    from PIL import Image
    w, h = client_size(hwnd)
    if w <= 0 or h <= 0:
        raise RuntimeError("window client area is empty (%dx%d) - minimized?" % (w, h))
    hdc_win = user32.GetDC(hwnd)
    hdc = gdi32.CreateCompatibleDC(hdc_win)
    bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    old = gdi32.SelectObject(hdc, bmp)
    try:
        ok = user32.PrintWindow(hwnd, hdc, flags)
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, BI_RGB, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bi), DIB_RGB_COLORS)
        im = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        gdi32.SelectObject(hdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc)
        user32.ReleaseDC(hwnd, hdc_win)
    return im, bool(ok)

if __name__ == "__main__":
    h = sys.argv[1]
    if h == "game":
        import autotest_driver as d
        h = d.game_hwnd()
    else:
        h = int(h)
    im, ok = capture(h)
    im.save(sys.argv[2])
    import numpy as np
    print("saved", sys.argv[2], im.size, "PrintWindow ok=%s mean=%.1f" % (ok, float(np.asarray(im).mean())))
