#!/usr/bin/env python3
"""Compare two SN2AutoTest pod dumps (poddump_<world>_<ts>.txt) in the lifepod's local frame.
Usage: python pod_diff.py <dumpA> <dumpB> <out.md>
Rows are matched by (actor class, component name, occurrence). Each component's world transform is converted into the frame of the
BP_StaticLifepod_Surface_C actor root (inverse of the pod root world transform, UE rotator convention). Reports: rows only in A / only in B,
differences > 1 cm / > 0.5 deg in the pod-local transform, differences in visible / hiddenInGame / collision / mesh / attach parent / data layers,
and differences between the BP_LifepodManager_C property sections."""
import math, sys, collections

POD_CLASS = "BP_StaticLifepod_Surface_C"
LOC_TOL, ROT_TOL = 1.0, 0.5

def parse_vec(s):
    try:
        return [float(x) for x in s.split(",")]
    except ValueError:
        return None

def rot_matrix(p, y, r):
    """UE FRotationMatrix rows = X (forward), Y (right), Z (up) axes in world space"""
    sp, cp = math.sin(math.radians(p)), math.cos(math.radians(p))
    sy, cy = math.sin(math.radians(y)), math.cos(math.radians(y))
    sr, cr = math.sin(math.radians(r)), math.cos(math.radians(r))
    return [[cp * cy, cp * sy, sp],
            [sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp],
            [-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp]]

def dot(a, b):
    return sum(x * y for x, y in zip(a, b))

def to_rotator(m):
    x, y, z = m
    pitch = math.degrees(math.atan2(x[2], math.hypot(x[0], x[1])))
    yaw = math.degrees(math.atan2(x[1], x[0]))
    sy = (-math.sin(math.radians(yaw)), math.cos(math.radians(yaw)), 0.0)
    roll = math.degrees(math.atan2(dot(z, sy), dot(y, sy)))
    return pitch, yaw, roll

def load(path):
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    hdr = lines[0].split("\t")
    rows, mgr, section = [], [], 0
    for ln in lines[1:]:
        if ln.startswith("## MANAGER_PROPERTIES"):
            section = 1; continue
        if not ln.strip():
            continue
        parts = ln.split("\t")
        if section == 0:
            rows.append(dict(zip(hdr, parts)))
        else:
            mgr.append(parts)
    pod = next((r for r in rows if r["actorClass"] == POD_CLASS and r.get("isRoot") == "1"), None)
    frame = None
    if pod:
        loc, rot = parse_vec(pod["worldLoc"]), parse_vec(pod["worldRot"])
        if loc and rot:
            frame = (loc, rot_matrix(*rot))
    seen = collections.Counter()
    out = {}
    for r in rows:
        k = (r["actorClass"], r["comp"])
        seen[k] += 1
        r["_key"] = k + (seen[k],)
        r["_local"] = local(r, frame)
        out[r["_key"]] = r
    return rows, out, mgr, frame

def local(r, frame):
    if not frame:
        return None
    wl, wr = parse_vec(r["worldLoc"]), parse_vec(r["worldRot"])
    if not wl or not wr:
        return None
    loc, m = frame
    d = [wl[i] - loc[i] for i in range(3)]
    ll = [dot(d, m[j]) for j in range(3)]
    mc = rot_matrix(*wr)
    lm = [[dot(mc[i], m[j]) for j in range(3)] for i in range(3)]
    return ll, lm

def rot_diff_deg(a, b):
    tr = sum(dot(a[i], b[i]) for i in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))

def f3(v):
    return "(%.1f, %.1f, %.1f)" % tuple(v)

def main(a_path, b_path, out_path):
    ra, da, ma, fa = load(a_path)
    rb, db, mb, fb = load(b_path)
    L = ["# Pod component diff", "", "A = `%s`" % a_path.replace("\\", "/").split("/")[-1], "B = `%s`" % b_path.replace("\\", "/").split("/")[-1], "",
         "Rows: A %d, B %d. Pod root frame found: A %s, B %s." % (len(ra), len(rb), bool(fa), bool(fb)),
         "Pod root world: A %s, B %s." % (fa[0] if fa else "?", fb[0] if fb else "?"), ""]
    only_a = [k for k in da if k not in db]
    only_b = [k for k in db if k not in da]
    L += ["## Present in A only (%d)" % len(only_a), "", "| actor class | component | pod-local loc | visible | collision |", "|---|---|---|---|---|"]
    for k in only_a:
        r = da[k]; l = r["_local"]
        L.append("| %s | %s | %s | %s | %s |" % (k[0], k[1], f3(l[0]) if l else "?", r["visible"], r["collisionEnabled"]))
    L += ["", "## Present in B only (%d)" % len(only_b), "", "| actor class | component | pod-local loc | visible | collision |", "|---|---|---|---|---|"]
    for k in only_b:
        r = db[k]; l = r["_local"]
        L.append("| %s | %s | %s | %s | %s |" % (k[0], k[1], f3(l[0]) if l else "?", r["visible"], r["collisionEnabled"]))
    diffs = []
    for k in da:
        if k not in db:
            continue
        x, y = da[k], db[k]
        why = []
        lx, ly = x["_local"], y["_local"]
        if lx and ly:
            dl = math.dist(lx[0], ly[0])
            if dl > LOC_TOL:
                why.append("loc A %s B %s (d=%.1f cm)" % (f3(lx[0]), f3(ly[0]), dl))
            dr = rot_diff_deg(lx[1], ly[1])
            if dr > ROT_TOL:
                why.append("rot A (%.1f,%.1f,%.1f) B (%.1f,%.1f,%.1f) (d=%.1f deg)" % (*to_rotator(lx[1]), *to_rotator(ly[1]), dr))
        for f in ("visible", "hiddenInGame", "collisionEnabled", "collisionProfile", "actorCollision", "actorHidden", "mesh", "parent", "dataLayers"):
            if x.get(f) != y.get(f):
                why.append("%s A=%s B=%s" % (f, x.get(f), y.get(f)))
        if why:
            diffs.append((k, why))
    L += ["", "## Differences in matched rows (%d of %d matched)" % (len(diffs), len(da) - len(only_a)), "", "| actor class | component | differences |", "|---|---|---|"]
    for k, why in diffs:
        L.append("| %s | %s | %s |" % (k[0], k[1], "; ".join(w.replace("|", "/") for w in why)))
    pa = {(p[0], p[1]): p for p in ma if len(p) >= 4}
    pb = {(p[0], p[1]): p for p in mb if len(p) >= 4}
    L += ["", "## BP_LifepodManager_C property differences", "", "| class | property | type | A | B |", "|---|---|---|---|---|"]
    n = 0
    for k in sorted(set(pa) | set(pb)):
        va = pa[k][3] if k in pa else "(absent)"
        vb = pb[k][3] if k in pb else "(absent)"
        if va != vb:
            n += 1
            L.append("| %s | %s | %s | %s | %s |" % (k[0], k[1], (pa.get(k) or pb.get(k))[2], va.replace("|", "/"), vb.replace("|", "/")))
    L += ["", "(%d of %d manager properties differ)" % (n, len(set(pa) | set(pb)))]
    open(out_path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("rows A=%d B=%d onlyA=%d onlyB=%d diffs=%d mgrdiffs=%d -> %s" % (len(ra), len(rb), len(only_a), len(only_b), len(diffs), n, out_path))

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__); sys.exit(2)
    main(*sys.argv[1:])
