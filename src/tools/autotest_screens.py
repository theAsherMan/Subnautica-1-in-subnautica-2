#!/usr/bin/env python3
"""Menu-screen identity for the autotest driver: numeric fingerprints, no images stored.

A screen is identified by the normalised cross-correlation (NCC) of a high-pass-filtered grayscale crop of a fixed UI box against the screen's
reference (the mean of that crop over many known-good screenshots). High-pass + NCC removes the animated cave/ocean background and brightness
(fades), so only the fixed UI shapes (buttons, panels, text lines) count. distance = 1 - NCC: ~0.00-0.15 for the right screen, >= 0.75 for any other
menu screen, >= 0.87 for in-game views (VERIFIED offline 2026-11-19 on 359 shots from 18 runs, see research/01_runbook.md).

Files (in src/mods/SN2AutoTest/plans/):
  screens.json        fingerprints written by `build` (numbers only): box, reference, thresholds
  screen_labels.json  true screen of every menu shot of the known runs: {run_folder: [label of menu_01, menu_02, ...]}, label "o" = no known menu screen
                      (loading screen / in-game); plus the UI boxes and thresholds used by `build`.
CLI (also reachable through autotest_driver.py as `screens-build` / `screens-check`):
  python -I autotest_screens.py build  [AUTOTEST_DIR]
  python -I autotest_screens.py check  [AUTOTEST_DIR] [--loo]
"""
import glob, json, os, sys

PLANS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mods", "SN2AutoTest", "plans")
SCREENS_JSON = os.path.join(PLANS, "screens.json")
LABELS_JSON = os.path.join(PLANS, "screen_labels.json")
SCALE = 8      # crop is downsampled by this factor
SIGMA = 1.5    # gaussian blur (in downsampled pixels) subtracted for the high-pass


def feature(im, box, scale=SCALE, sigma=SIGMA, mask=None):
    """normalised high-pass vector (numpy 2D) of the crop `box` (x0,y0,x1,y1 in 1920x1080 coordinates) of PIL image `im`.
    mask = list of rects (same coordinates) whose cells are zeroed after the high-pass: content that changes between launches (save rows, counters)."""
    import numpy as np
    from PIL import ImageFilter
    c = im.convert("L").crop(tuple(box))
    w, h = c.size
    sm = c.resize((max(1, w // scale), max(1, h // scale)), 2)   # 2 = BOX
    a = np.asarray(sm, dtype="float32")
    bl = np.asarray(sm.filter(ImageFilter.GaussianBlur(sigma)), dtype="float32")
    hp = a - bl
    for (mx0, my0, mx1, my1) in (mask or []):
        hp[max(0, (my0 - box[1]) // scale):max(0, -(-(my1 - box[1]) // scale)), max(0, (mx0 - box[0]) // scale):max(0, -(-(mx1 - box[0]) // scale))] = 0.0
    hp -= hp.mean()
    return hp / (float(np.linalg.norm(hp)) + 1e-6), float(a.mean())


class Screens:
    def __init__(self, path=SCREENS_JSON):
        import numpy as np
        d = json.load(open(path))
        self.cfg = d
        self.accept = d["thresholds"]["accept"]
        self.margin = d["thresholds"]["margin"]
        self.refs = {}
        for k, v in d["screens"].items():
            w, h = v["wh"]
            self.refs[k] = (v["box"], np.array(v["ref"], dtype="float32").reshape(h, w) / 1000.0, v.get("mask"))

    def distances(self, im):
        out = {}
        lum = {}
        for k, (box, ref, mask) in self.refs.items():
            f, m = feature(im, box, self.cfg["scale"], self.cfg["sigma"], mask)
            if f.shape != ref.shape:
                out[k] = 2.0
            else:
                out[k] = 1.0 - float((f * ref).sum() / (float((ref * ref).sum()) ** 0.5 + 1e-9))
            lum[k] = m
        return out, lum

    def identify(self, im):
        """-> (name or None, best_name, best_dist, second_name, second_dist, lum_of_best_box). name None = unknown / no known menu screen"""
        d, lum = self.distances(im)
        order = sorted(d, key=d.get)
        b, s = order[0], order[1]
        ok = d[b] <= self.accept and (d[s] - d[b]) >= self.margin
        return (b if ok else None), b, d[b], s, d[s], lum[b]


# ---------------------------------------------------------------- offline tools
def _samples(auto_dir):
    """[(run, file, label)] from screen_labels.json: menu shots by index + all in-game waypoint shots as 'o'"""
    lab = json.load(open(LABELS_JSON))
    S = []
    for run, labs in lab["runs"].items():
        for i, l in enumerate(labs, 1):
            fs = sorted(glob.glob(os.path.join(auto_dir, run, "shots", "menu_%02d_*.png" % i)))
            if fs:
                S.append((run, fs[0], l))
        for f in sorted(glob.glob(os.path.join(auto_dir, run, "shots", "[0-9][0-9]_*_k[0-9].png"))):
            if run + "/shots/" + os.path.basename(f) in lab.get("not_o", []):   # a waypoint shot that really shows a menu (labelled in "extra")
                continue
            S.append((run, f, "o"))
        if run in lab.get("nopawn_is", {}):
            f = os.path.join(auto_dir, run, "shots", "00_nopawn.png")
            if os.path.exists(f):
                S.append((run, f, lab["nopawn_is"][run]))
    for e in lab.get("extra", []):   # single files outside the menu_NN naming (stall shots): {"file": "<run>/shots/x.png", "label": ".."}
        f = os.path.join(auto_dir, e["file"])
        if os.path.exists(f):
            S.append((e["file"].split("/")[0], f, e["label"]))
    return lab, S


def build(auto_dir):
    import numpy as np
    from PIL import Image
    lab, S = _samples(auto_dir)
    boxes = lab["boxes"]
    feats = {k: [] for k in boxes}
    for run, f, l in S:
        if l in boxes:
            feats[l].append(feature(Image.open(f), boxes[l], mask=lab.get("masks", {}).get(l))[0])
    out = {"version": 1, "scale": SCALE, "sigma": SIGMA, "thresholds": lab["thresholds"], "screens": {}}
    for k, fl in feats.items():
        m = np.mean(fl, axis=0)
        m = m / (np.linalg.norm(m) + 1e-9)
        out["screens"][k] = {"box": boxes[k], "wh": [m.shape[1], m.shape[0]], "samples": len(fl),
                             "ref": [int(round(x * 1000)) for x in m.flatten()]}
        if lab.get("masks", {}).get(k):
            out["screens"][k]["mask"] = lab["masks"][k]
        print("%-10s box=%s %dx%d from %d shots" % (k, boxes[k], m.shape[1], m.shape[0], len(fl)))
    json.dump(out, open(SCREENS_JSON, "w"), separators=(",", ":"))
    print("wrote", os.path.abspath(SCREENS_JSON), os.path.getsize(SCREENS_JSON), "bytes")


def check(auto_dir, loo=False):
    """confusion table: every labelled shot against every reference. loo = references rebuilt without the shot's own run (honest generalisation)"""
    import numpy as np
    from PIL import Image
    lab, S = _samples(auto_dir)
    boxes = lab["boxes"]
    F = {k: [] for k in boxes}
    for _, f, _ in S:
        im = Image.open(f); im.load()
        for k in boxes:
            F[k].append(feature(im, boxes[k], mask=lab.get("masks", {}).get(k))[0])
    labs = np.array([s[2] for s in S]); runs = np.array([s[0] for s in S])
    def refs(mask):
        r = {}
        for k in boxes:
            idx = np.where((labs == k) & mask)[0]
            m = np.mean([F[k][i] for i in idx], axis=0)
            r[k] = m / (np.linalg.norm(m) + 1e-9)
        return r
    full = refs(np.ones(len(S), bool))
    cache = {}
    D = []
    for i in range(len(S)):
        if loo:
            if S[i][0] not in cache:
                cache[S[i][0]] = refs(runs != S[i][0])
            R = cache[S[i][0]]
        else:
            R = full
        D.append({k: 1.0 - float((F[k][i] * R[k]).sum() / ((R[k] * R[k]).sum() ** 0.5 + 1e-9)) for k in boxes})
    acc, mar = lab["thresholds"]["accept"], lab["thresholds"]["margin"]
    names = list(boxes) + ["unknown"]
    conf = {t: {n: 0 for n in names} for t in list(boxes) + ["o"]}
    own = {k: [] for k in boxes}; other_min = {k: [] for k in boxes}; ingame_min = {k: [] for k in boxes}; bad = []
    for i, (run, f, l) in enumerate(S):
        d = D[i]; o = sorted(d, key=d.get); b, s = o[0], o[1]
        ident = b if (d[b] <= acc and d[s] - d[b] >= mar) else "unknown"
        conf[l][ident] += 1
        if l == "o":
            if ident != "unknown": bad.append((run, os.path.basename(f), l, ident, d[b], d[s]))
            for k in boxes: ingame_min[k].append(d[k])
        else:
            own[l].append(d[l]); other_min[l].append(min(v for k, v in d.items() if k != l))
            if ident != l: bad.append((run, os.path.basename(f), l, ident, d[b], d[s]))
    print("mode: %s   shots: %d   accept<=%.2f margin>=%.2f" % ("leave-one-run-out" if loo else "references from all shots", len(S), acc, mar))
    print("\nconfusion (rows = true screen, columns = identified; 'o' = no menu screen, e.g. loading / in-game):")
    print("%-10s" % "" + "".join("%9s" % n[:8] for n in names))
    for t, row in conf.items():
        print("%-10s" % t + "".join("%9d" % row[n] for n in names))
    print("\ndistance (1-NCC): own-screen max | nearest OTHER screen min (any shot of that screen) | in-game shots vs this ref min")
    for k in boxes:
        print("%-10s own max %.3f | other-screen min %.3f | in-game min %.3f | n=%d" % (k, max(own[k]), min(other_min[k]), min(ingame_min[k]), len(own[k])))
    print("\nmisidentified: %d" % len(bad))
    for b in bad: print("  %s %s true=%s got=%s best=%.3f second=%.3f" % b)
    return len(bad)


def main(argv):
    if len(argv) < 2 or argv[1] not in ("build", "check"):
        print(__doc__); return 2
    from_ws = None
    for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "local.config")):
        if l.startswith("SN2_WORKSPACE="):
            from_ws = l.split("=", 1)[1].strip().strip('"')
    pos = [a for a in argv[2:] if not a.startswith("--")]
    auto = pos[0] if pos else os.path.join(from_ws, "autotest")
    if argv[1] == "build": build(auto); return 0
    return 1 if check(auto, "--loo" in argv) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
