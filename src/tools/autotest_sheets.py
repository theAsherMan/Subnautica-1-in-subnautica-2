#!/usr/bin/env python3
"""Contact sheets + per-shot statistics for an autotest run folder.
Usage: python autotest_sheets.py <run_folder> <plan_name>
Writes <run>/sheets/<idx>_<waypoint>.png (4x2 tiles 480x270) and <run>/shot_stats.txt.
"""
import csv, os, sys
import numpy as np
from PIL import Image, ImageDraw

run, plan = sys.argv[1], sys.argv[2]
shots = os.path.join(run, "shots")
rows = list(csv.DictReader(open(os.path.join(run, "manifest.tsv")), delimiter="\t"))
os.makedirs(os.path.join(run, "sheets"), exist_ok=True)
TW, TH, CAP, HDR = 480, 270, 18, 24

stats, prev, found = [], None, 0
for r in rows:
    p = os.path.join(shots, r["file"])
    if not os.path.exists(p):
        stats.append("%s  MISSING" % r["file"]); prev = None; continue
    found += 1
    im = Image.open(p).convert("RGB")
    small = np.asarray(im.resize((480, 270)), dtype=np.float32)
    lum = float(np.mean(small @ np.array([0.299, 0.587, 0.114], dtype=np.float32)))
    diff = float(np.mean(np.abs(small - prev))) if prev is not None else float("nan")
    flags = ("BLACK " if lum <= 3 else "") + ("UNCHANGED " if prev is not None and diff <= 0.5 else "")
    stats.append("%s  size=%dx%d lum=%.1f diff_prev=%s %s" % (r["file"], im.size[0], im.size[1], lum,
                 "-" if prev is None else "%.2f" % diff, flags.strip()))
    prev = small
with open(os.path.join(run, "shot_stats.txt"), "w") as f:
    f.write("shots found with image: %d / manifest rows %d\n" % (found, len(rows)))
    f.write("\n".join(stats) + "\n")

by = {}
for r in rows:
    by.setdefault((int(r["idx"]), r["waypoint"]), []).append(r)
for (idx, wp), rs in sorted(by.items()):
    nrows = 3 if max(int(x["k"]) for x in rs) >= 8 else 2   # abs8ud waypoints have k0..k9
    sheet = Image.new("RGB", (4 * TW, HDR + nrows * (TH + CAP)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    r0 = rs[0]
    d.text((6, 6), "%s pawn=(%.0f,%.0f,%.0f) plan=%s" % (wp, float(r0["pawnX"]), float(r0["pawnY"]), float(r0["pawnZ"]), plan), fill=(255, 255, 0))
    for r in rs:
        k = int(r["k"]); cx, cy = (k % 4) * TW, HDR + (k // 4) * (TH + CAP)
        d.text((cx + 4, cy + 3), "k=%d yaw=%.0f" % (k, float(r["yaw"])), fill=(255, 255, 255))
        p = os.path.join(shots, r["file"])
        if os.path.exists(p):
            sheet.paste(Image.open(p).convert("RGB").resize((TW, TH)), (cx, cy + CAP))
    sheet.save(os.path.join(run, "sheets", "%02d_%s.png" % (idx, wp)))
print("sheets done; found %d/%d" % (found, len(rows)))
