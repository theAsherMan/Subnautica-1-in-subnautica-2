#!/usr/bin/env python3
"""Side-by-side contact sheet of SN1 and SN2 views (SN1 left, SN2 right, one labelled row per view).
Usage: python compare_shots.py <sn1_dir> <sn2_shots_dir> <out.png>
SN1 files: spot1_yaw000.png .. spot1_yaw315.png, spot1_up.png, spot1_down.png
SN2 files: <idx>_<wp>_k0.png .. _k9.png (k0..k7 = yaw 0,45..315; k8 = up; k9 = down)
Write <out.png> into the run folder, never into research/.
"""
import glob, os, re, sys
from PIL import Image, ImageDraw

sn1_dir, sn2_dir, out = sys.argv[1:4]
TW, TH, CAP = 640, 360, 18
views = [("yaw%03d" % (45 * k), "spot1_yaw%03d.png" % (45 * k), k) for k in range(8)] + [("up", "spot1_up.png", 8), ("down", "spot1_down.png", 9)]

def sn2_file(k):
    m = sorted(glob.glob(os.path.join(sn2_dir, "*_k%d.png" % k)))
    m = [p for p in m if re.search(r"/\d\d_[^/]*_k%d\.png$" % k, p.replace(chr(92), "/"))]
    return m[0] if m else None

def tile(sheet, d, path, x, y, label):
    d.text((x + 4, y + 3), label, fill=(255, 255, 255))
    if path and os.path.exists(path):
        sheet.paste(Image.open(path).convert("RGB").resize((TW, TH)), (x, y + CAP))
    else:
        d.text((x + 8, y + CAP + 8), "MISSING", fill=(255, 80, 80))

sheet = Image.new("RGB", (2 * TW, len(views) * (TH + CAP)), (20, 20, 20))
d = ImageDraw.Draw(sheet)
for i, (name, f1, k) in enumerate(views):
    y = i * (TH + CAP)
    tile(sheet, d, os.path.join(sn1_dir, f1), 0, y, "SN1 " + name)
    tile(sheet, d, sn2_file(k), TW, y, "SN2 " + name + " (k%d)" % k)
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
sheet.save(out)
print("wrote", out, sheet.size)
