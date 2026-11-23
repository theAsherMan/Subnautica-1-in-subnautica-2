#!/usr/bin/env python3
"""Compare an extracted terrain mesh with SN1 in-game collider vertices.

  sn1_compare_terrain.py <extract_dir> <collider.obj> [--unity]

<extract_dir> = output of sn1_extract_terrain.py (tile_*.obj, UE cm). <collider.obj> vertices are Unity world metres
(default) and are converted to UE cm. Reports distance (m) from each collider vertex to the nearest extracted triangle
(point-to-triangle via a coarse 5 m grid over triangle bounding boxes). Collider vertices outside the extracted tiles are skipped.
Prints mean / median / 95th percentile / max and writes compare.json into <extract_dir>.
"""
import sys, os, glob, json
import numpy as np


def load_obj(path):
    vs, fs = [], []
    for line in open(path):
        if line.startswith("v "):
            vs.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("f "):
            fs.append([int(t.split("/")[0]) - 1 for t in line.split()[1:4]])
    return np.array(vs, np.float64).reshape(-1, 3), np.array(fs, np.int64).reshape(-1, 3)


def pt_tri_dist(p, a, b, c):
    """Vectorised point (n,3) to triangle (n,3 each) distance (Ericson, closest point on triangle)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-18, 1e-18, den)
    v = vb / den
    w = vc / den
    q = a + ab * v[:, None] + ac * w[:, None]  # interior case
    # fall back to clamped edge/vertex candidates (min over 3 edges handles all outside cases)
    best = np.linalg.norm(p - q, axis=1)
    inside = (v >= 0) & (w >= 0) & (v + w <= 1)
    res = np.where(inside, best, np.inf)
    for s, e in ((a, b), (b, c), (c, a)):
        d = e - s
        t = np.clip(((p - s) * d).sum(1) / np.maximum((d * d).sum(1), 1e-18), 0, 1)
        res = np.minimum(res, np.linalg.norm(p - (s + d * t[:, None]), axis=1))
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    ext, col = args
    V, F = [], []
    off = 0
    for f in sorted(glob.glob(os.path.join(ext, "tile_*.obj"))):
        v, fc = load_obj(f)
        V.append(v)
        F.append(fc + off)
        off += len(v)
    V = np.concatenate(V) / 100.0  # metres, UE axes
    F = np.concatenate(F)
    cv, _ = load_obj(col)
    ue = np.stack([cv[:, 2], cv[:, 0], cv[:, 1]], 1)  # Unity m -> UE m
    lo, hi = V.min(0), V.max(0)
    m = np.all((ue >= lo + 5) & (ue <= hi - 5), axis=1)
    ue = ue[m]
    cell = 5.0
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    tmin = np.minimum(np.minimum(A, B), C)
    tmax = np.maximum(np.maximum(A, B), C)
    grid = {}
    for i in range(len(F)):
        lo_c = np.floor(tmin[i] / cell).astype(int)
        hi_c = np.floor(tmax[i] / cell).astype(int)
        for x in range(lo_c[0], hi_c[0] + 1):
            for y in range(lo_c[1], hi_c[1] + 1):
                for z in range(lo_c[2], hi_c[2] + 1):
                    grid.setdefault((x, y, z), []).append(i)
    dist = np.full(len(ue), np.inf)
    for n, p in enumerate(ue):
        c = np.floor(p / cell).astype(int)
        for r in (1, 2, 3):
            ids = set()
            for x in range(c[0] - r, c[0] + r + 1):
                for y in range(c[1] - r, c[1] + r + 1):
                    for z in range(c[2] - r, c[2] + r + 1):
                        ids.update(grid.get((x, y, z), ()))
            if ids:
                t = np.fromiter(ids, np.int64)
                d = pt_tri_dist(np.broadcast_to(p, (len(t), 3)), A[t], B[t], C[t]).min()
                dist[n] = d
                if d <= r * cell * 0.8:
                    break
    ok = np.isfinite(dist)
    d = dist[ok]
    r = {"collider_vertices": int(len(cv)), "compared": int(ok.sum()), "mean_m": float(d.mean()), "median_m": float(np.median(d)),
         "p95_m": float(np.percentile(d, 95)), "max_m": float(d.max())}
    json.dump(r, open(os.path.join(ext, "compare.json"), "w"), indent=1)
    print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
