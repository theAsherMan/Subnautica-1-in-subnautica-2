#!/usr/bin/env python3
"""SN1 biome -> SN2 biome-region plan (offline, no game, no lock). See research/10 §6 and research/04 "Water colour / fog per area".

  python -I src/tools/sn1_biome_transfer.py safeShallows [--cell 32] [--overlap 10] [--min-px 100] [--y-top 5] [--y-bottom -200]
                                            [--settings <waterbiomes dump json>] [--out <Workspace>/sn1_biomes/<biome>.json]

1. Shape: biomeMap.bin (1024 x 1024, 4 m/px, value = index into biomes.csv) -> mask of the biome -> drop 4-connected components smaller than
   --min-px pixels -> coarsen to --cell metres (a coarse cell is "in" when at least half its pixels are) -> greedy rectangle cover
   (row runs grown downward) -> one box per rectangle, grown by --overlap metres on every horizontal side (so neighbouring boxes overlap
   and a box-edge blend never shows inside the biome; the outer edge moves out by the same amount). Vertical span --y-bottom .. --y-top (Unity metres; 0 = sea level).
2. Look: the SN1 WaterscapeVolume.Settings of the biome (from `sn1_live.py waterbiomes`, file <Workspace>/sn1_shots/<name>.json) ->
   SN2 FUWEWaterLightSettings via sn2_light() below (formula v1, UNTESTED: calibrate with sn1_live.py capture + the SN2 twin shot).
   Without --settings the plan has boxes only and "water_light_t3d": null (the editor script then refuses).
Output JSON (read by src/modkit/scripts/sn1biome_regions.py inside the editor): boxes in UE cm (UE.X = 100 z, UE.Y = 100 x, UE.Z = 100 y).
"""
import argparse, json, math, os, sys
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# L_Main ocean region WaterLightSettings (cooked L_Main, research/09): SN2's own "clear blue ocean" = the calibration anchor.
LMAIN_EXT_DIR = (0.9072499871253967, 0.9451580047607422, 0.9549999833106995)
LMAIN_EXT_SKY = (0.6000000238418579, 0.7607219815254211, 0.800000011920929)
LMAIN_FOG_CM = 7500.0

# Formula v1 tunables (UNTESTED 2026-11-24). K_M: metres of SN1 water whose transmittance becomes SN2 BiomeExtinction (directional light).
K_M = 1.0
FOG_FULL = 3.0     # WaterFogDistance = FOG_FULL / mean(sigma_t) metres (exp(-3) = 5 % left = "can't see through")
FOG_MIN_CM, FOG_MAX_CM = 1000.0, 20000.0


def cfg():
    d = {}
    for line in open(os.path.join(REPO, "local.config"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"')
    return d


def load_map(sn1dir):
    b = os.path.join(sn1dir, "Subnautica_Data", "StreamingAssets", "SNUnmanagedData", "Build18")
    m = np.frombuffer(open(os.path.join(b, "biomeMap.bin"), "rb").read()[2:], dtype=np.uint8).reshape(1024, 1024)  # m[row=z, col=x]
    names = [l.strip() for l in open(os.path.join(b, "biomes.csv"), encoding="utf-8").read().splitlines()[1:] if l.strip()]
    return m, names


def components(mask):
    """4-connected components: list of (pixel count, [(r, c), ...])."""
    seen = np.zeros(mask.shape, dtype=bool)
    out = []
    rows, cols = np.nonzero(mask)
    for r0, c0 in zip(rows.tolist(), cols.tolist()):
        if seen[r0, c0]:
            continue
        seen[r0, c0] = True
        q, px = deque([(r0, c0)]), []
        while q:
            r, c = q.popleft()
            px.append((r, c))
            for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if 0 <= rr < 1024 and 0 <= cc < 1024 and mask[rr, cc] and not seen[rr, cc]:
                    seen[rr, cc] = True
                    q.append((rr, cc))
        out.append((len(px), px))
    out.sort(key=lambda t: -t[0])
    return out


def rect_cover(g):
    """Greedy cover of boolean grid g by axis-aligned rectangles (r0, c0, r1, c1 inclusive): take the leftmost run of the topmost free row,
    grow it downward while the whole run is in g and still free. Exact cover (union == g, no overlaps)."""
    free = g.copy()
    rects = []
    H, W = g.shape
    for r in range(H):
        c = 0
        while c < W:
            if not free[r, c]:
                c += 1
                continue
            c1 = c
            while c1 + 1 < W and free[r, c1 + 1]:
                c1 += 1
            r1 = r
            while r1 + 1 < H and free[r1 + 1, c:c1 + 1].all():
                r1 += 1
            free[r:r1 + 1, c:c1 + 1] = False
            rects.append((r, c, r1, c1))
            c = c1 + 1
    return rects


def lin(v):
    return [float(x) for x in v]


def sn2_light(s):
    """SN1 WaterscapeVolume.Settings (SN1Inspector SettingsJson) -> dict of FUWEWaterLightSettings fields. Formula v1 (UNTESTED):
      sigma_c  = SN1 extinction per metre (derived_extinction_per_m = (absorption + scattering) * murkiness / 100)
      BiomeExtinction_c         = exp(-sigma_c * K_M)                         (transmittance over K_M metres)
      BiomeExtinctionSkylight_c = LMAIN_SKY_c ** (sigma_c * K_M / -ln LMAIN_DIR_c)   (same per-channel ratio to the L_Main anchor)
      BiomeAlbedo_c   = single-scattering albedo (scattering_rgb_c / sigma_c), normalised to max 1 (L_Main's albedo also peaks at 1.0)
      WaterFogDistance = 100 * FOG_FULL / mean(sigma)  cm, clamped [FOG_MIN_CM, FOG_MAX_CM]
      Advanced.BiomeEmissive = SN1 derived_emissive (only when non-zero)
    Kept from L_Main: extinction scales 12.5 / 17.5, fog thickness 10 / base 4, blend XYSeperateZ (2000, 100), caustics DepthFadeMax 45000."""
    sig = [max(1e-6, x) for x in s["derived_extinction_per_m"]]
    sc = s["derived_scattering_rgb_per_m"]
    ext = [math.exp(-x * K_M) for x in sig]
    sky = []
    for c in range(3):
        ratio = sig[c] * K_M / -math.log(LMAIN_EXT_DIR[c])
        sky.append(LMAIN_EXT_SKY[c] ** ratio)
    alb = [sc[c] / sig[c] for c in range(3)]
    mx = max(alb) or 1.0
    alb = [a / mx for a in alb]
    fog = min(FOG_MAX_CM, max(FOG_MIN_CM, 100.0 * FOG_FULL / (sum(sig) / 3.0)))
    em = s.get("derived_emissive") or [0, 0, 0]
    d = {
        "BiomeExtinction": ext + [1.0], "BiomeExtinctionSkylight": sky + [1.0],
        "BiomeExtinctionScaleDirectionalLight": 12.5, "BiomeExtinctionScaleSkylight": 17.5,
        "BiomeAlbedo": alb + [1.0], "WaterFogDistance": fog, "WaterFogThickness": 10.0, "WaterFogBaseThickness": 4.0,
        "BiomeBlendType": "XYSeperateZ", "BiomeBlendDistanceXYAndZ": [2000.0, 100.0], "CausticsSettings": {"DepthFadeMax": 45000.0},
    }
    if max(abs(x) for x in em[:3]) > 1e-6:
        d["Advanced"] = {"BiomeEmissive": lin(em[:3]) + [1.0]}
    return d


def t3d(v):
    """dict / list -> UE ImportText (struct fields not named keep their defaults)."""
    if isinstance(v, dict):
        return "(" + ",".join("%s=%s" % (k, t3d(x)) for k, x in v.items()) + ")"
    if isinstance(v, list):
        if len(v) == 4:
            return "(R=%r,G=%r,B=%r,A=%r)" % tuple(float(x) for x in v)
        if len(v) == 2:
            return "(X=%r,Y=%r)" % tuple(float(x) for x in v)
    if isinstance(v, float):
        return repr(v)
    return str(v)


def find_settings(dump, biome):
    for b in dump.get("biomeSettings", []):
        if b["name"] == biome:
            return b["settings"]
    names = [b["name"] for b in dump.get("biomeSettings", [])]
    sys.exit("biome %r not in the dump's biomeSettings %s" % (biome, names))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("biome")
    ap.add_argument("--cell", type=int, default=32, help="coarse cell, metres (multiple of 4)")
    ap.add_argument("--overlap", type=float, default=10.0, help="grow every box by this many metres per horizontal side")
    ap.add_argument("--min-px", type=int, default=100, help="drop components smaller than this many 4 m pixels")
    ap.add_argument("--y-top", type=float, default=5.0)
    ap.add_argument("--y-bottom", type=float, default=-200.0)
    ap.add_argument("--settings", help="waterbiomes dump (sn1_live.py waterbiomes)")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.cell % 4:
        sys.exit("--cell must be a multiple of 4")
    C = cfg()
    m, names = load_map(C["SN1_GAME_DIR"])
    if a.biome not in names:
        sys.exit("unknown biome %r; known: %s" % (a.biome, names))
    idx = names.index(a.biome)
    mask = m == idx
    comps = components(mask)
    keep = np.zeros_like(mask)
    kept = []
    for n, px in comps:
        if n >= a.min_px:
            rr, cc = zip(*px)
            keep[list(rr), list(cc)] = True
            kept.append({"pixels": n, "x": [min(cc) * 4 - 2048, max(cc) * 4 - 2044], "z": [min(rr) * 4 - 2048, max(rr) * 4 - 2044]})
    k = a.cell // 4
    coarse = keep.reshape(1024 // k, k, 1024 // k, k).mean(axis=(1, 3)) >= 0.5
    rects = rect_cover(coarse)
    # fidelity vs the 4 m mask
    back = np.repeat(np.repeat(coarse, k, axis=0), k, axis=1)
    miss, extra = int((keep & ~back).sum()), int((back & ~keep).sum())
    boxes = []
    yc, hy = (a.y_top + a.y_bottom) / 2.0, (a.y_top - a.y_bottom) / 2.0
    for (r0, c0, r1, c1) in rects:
        x0, x1 = c0 * a.cell - 2048 - a.overlap, (c1 + 1) * a.cell - 2048 + a.overlap
        z0, z1 = r0 * a.cell - 2048 - a.overlap, (r1 + 1) * a.cell - 2048 + a.overlap
        boxes.append({"unity_x": [x0, x1], "unity_z": [z0, z1], "unity_y": [a.y_bottom, a.y_top],
                      "center_ue": [50.0 * (z0 + z1), 50.0 * (x0 + x1), 100.0 * yc],
                      "half_ue": [50.0 * (z1 - z0), 50.0 * (x1 - x0), 100.0 * hy]})
    plan = {"biome": a.biome, "biome_index": idx, "cell_m": a.cell, "overlap_m": a.overlap, "min_px": a.min_px, "components": kept,
            "mask_px": int(keep.sum()), "miss_px": miss, "extra_px": extra, "boxes": boxes,
            "formula": "v1 (UNTESTED 2026-11-24): see sn2_light() in src/tools/sn1_biome_transfer.py", "K_M": K_M, "FOG_FULL": FOG_FULL,
            "sn1_settings": None, "water_light": None, "water_light_t3d": None}
    if a.settings:
        s = find_settings(json.load(open(a.settings, encoding="utf-8")), a.biome)
        wl = sn2_light(s)
        plan.update(sn1_settings=s, settings_file=os.path.basename(a.settings), water_light=wl, water_light_t3d=t3d(wl))
    out = a.out or os.path.join(C["SN2_WORKSPACE"], "sn1_biomes", a.biome + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(plan, open(out, "w", encoding="utf-8"), indent=1)
    print("%s: %d components kept (%s px), %d boxes at %d m cells, mask %d px, missed %d px (%.1f %%), extra %d px (%.1f %%)" % (
        a.biome, len(kept), [c["pixels"] for c in kept], len(boxes), a.cell, plan["mask_px"], miss, 100.0 * miss / max(1, plan["mask_px"]),
        extra, 100.0 * extra / max(1, plan["mask_px"])))
    print("water light:", plan["water_light_t3d"] or "none (no --settings yet)")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
