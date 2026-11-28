#!/usr/bin/env python3
"""SN1 terrain extractor: .optoctrees -> UE-ready OBJ tiles (UE axes, cm, absolute). See research/sn1/README.md sections 4 and 7.

  sn1_extract_terrain.py --center X Y Z [--size 500] [--tile 125] [--out DIR]

Unity metres in; OBJ out in UE cm: UE.X = 100*unity.z, UE.Y = 100*unity.x, UE.Z = 100*unity.y.
Mesher: surface nets on SN1's own density semantics (not a port of Voxeland's face mesher, see research/sn1/world_files.md §4).
Triangle winding: numeric cross product (b-a)x(c-a) points out of the solid (into the water), in Unity space and, because
the axis map is a cyclic permutation, also in UE space. In UE's left-handed space that is clockwise-from-the-front = front face.
Read-only on the SN1 install. Peak RAM about 1 GB for a 500 m cube. Single process.
"""
import argparse, json, os, struct, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ORIGIN = np.array([-2048, -3040, -2048], dtype=np.int64)  # Unity metres of voxel index (0,0,0) corner
BATCH = 160
TREE = 32


def cfg():
    d = {}
    for line in open(os.path.join(REPO, "local.config"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"')
    return d


def batch_path(sn1, bx, by, bz):
    return os.path.join(sn1, "Subnautica_Data", "StreamingAssets", "SNUnmanagedData", "Build18",
                        "CompiledOctreesCache", "compiled-batch-%d-%d-%d.optoctrees" % (bx, by, bz))


def read_trees(path):
    """Returns list of 125 trees, each a uint8 array (n,4) view: type, density, firstChild lo, hi."""
    d = open(path, "rb").read()
    ver = struct.unpack_from("<i", d, 0)[0]
    if ver < 4:
        return None
    p = 4
    trees = []
    for _ in range(125):
        n = struct.unpack_from("<H", d, p)[0]
        p += 2
        trees.append(np.frombuffer(d, dtype=np.uint8, count=4 * n, offset=p).reshape(n, 4))
        p += 4 * n
    return trees


def decode_tree(nodes, out_t, out_d):
    """Fill 32^3 arrays [x,y,z]. Child index = firstChild + 4*(x>=half) + 2*(y>=half) + (z>=half)."""
    stack = [(0, 0, 0, 0, TREE)]
    while stack:
        nid, x, y, z, s = stack.pop()
        t, dn, lo, hi = nodes[nid]
        fc = int(lo) + (int(hi) << 8)
        if fc == 0:
            out_t[x:x + s, y:y + s, z:z + s] = t
            out_d[x:x + s, y:y + s, z:z + s] = dn
        else:
            h = s >> 1
            for c in range(8):
                stack.append((fc + c, x + (h if c & 4 else 0), y + (h if c & 2 else 0), z + (h if c & 1 else 0), h))


def build_grid(sn1, vmin, vmax):
    """Global voxel index box [vmin, vmax) -> T, D uint8 arrays. Missing batch/octree = type 0, density 0 (outside)."""
    size = vmax - vmin
    T = np.zeros(tuple(size), np.uint8)
    D = np.zeros(tuple(size), np.uint8)
    b0 = vmin // BATCH
    b1 = (vmax - 1) // BATCH
    read = []
    lt = np.zeros((TREE,) * 3, np.uint8)
    ld = np.zeros((TREE,) * 3, np.uint8)
    for bx in range(b0[0], b1[0] + 1):
        for by in range(b0[1], b1[1] + 1):
            for bz in range(b0[2], b1[2] + 1):
                path = batch_path(sn1, bx, by, bz)
                if not os.path.exists(path):
                    read.append(((bx, by, bz), "missing"))
                    continue
                trees = read_trees(path)
                read.append(((bx, by, bz), "ok" if trees else "badversion"))
                if not trees:
                    continue
                for tx in range(5):
                    for ty in range(5):
                        for tz in range(5):
                            o = np.array([bx * BATCH + tx * TREE, by * BATCH + ty * TREE, bz * BATCH + tz * TREE])
                            lo = np.maximum(o, vmin)
                            hi = np.minimum(o + TREE, vmax)
                            if np.any(lo >= hi):
                                continue
                            nodes = trees[tx * 25 + ty * 5 + tz]  # Int3.Range order: z fastest, then y, then x
                            if len(nodes) == 1 and nodes[0][0] == 0:
                                continue
                            decode_tree(nodes, lt, ld)
                            sl_l = tuple(slice(lo[i] - o[i], hi[i] - o[i]) for i in range(3))
                            sl_g = tuple(slice(lo[i] - vmin[i], hi[i] - vmin[i]) for i in range(3))
                            T[sl_g] = lt[sl_l]
                            D[sl_g] = ld[sl_l]
    return T, D, read


def inside_mask(T, D):
    # VoxelandData.OctNode.IsBelowSurface: density==0 -> type>0 ; else density>=126
    return np.where(D == 0, T > 0, D >= 126)


def dec(d):
    return (d.astype(np.float32) - 126.0) / 126.0


def crossing_s(tin, din, tout, dout):
    """Fraction of the edge from the inside voxel centre to the outside one (VoxelandChunk.ComputeSurfaceIntersection)."""
    s = np.full(din.shape, 0.5, np.float32)
    a = dec(din)
    b = dec(dout)
    nin = din != 0
    nout = dout != 0
    both = nin & nout
    s[both] = a[both] / (a[both] - b[both])
    only_in = nin & ~nout
    s[only_in] = a[only_in]
    only_out = ~nin & nout
    s[only_out] = 1.0 + b[only_out]
    return np.clip(s, 0.0, 1.0)


def surface_nets(T, D):
    """Returns (verts float32 (n,3) in voxel-index space (centres at +0.5 applied later), tris int32 (m,3), tri_type uint8)."""
    ins = inside_mask(T, D)
    sx, sy, sz = ins.shape
    cs = (sx - 1, sy - 1, sz - 1)  # cells
    cell_flat = lambda i, j, k: (i * cs[1] + j) * cs[2] + k
    Tf = T.reshape(-1)
    Df = D.reshape(-1)
    strides = (sy * sz, sz, 1)
    edges = []  # per axis: (pos(n,3) of voxel A, A_inside bool, s_from_A, type_of_inside)
    for ax in range(3):
        sl_a = [slice(None)] * 3
        sl_b = [slice(None)] * 3
        sl_a[ax] = slice(0, -1)
        sl_b[ax] = slice(1, None)
        x = ins[tuple(sl_a)] ^ ins[tuple(sl_b)]
        idx = np.argwhere(x).astype(np.int64)
        del x
        fa = idx @ np.array(strides, np.int64)
        fb = fa + strides[ax]
        a_in = ins.reshape(-1)[fa]
        fin = np.where(a_in, fa, fb)
        fout = np.where(a_in, fb, fa)
        s_in = crossing_s(Tf[fin], Df[fin], Tf[fout], Df[fout])
        s_a = np.where(a_in, s_in, 1.0 - s_in).astype(np.float32)
        edges.append((idx, a_in, s_a, Tf[fin]))
    # accumulate per cell
    keys, pts = [], []
    for ax, (idx, a_in, s_a, _) in enumerate(edges):
        p = idx.astype(np.float32)
        p[:, ax] += s_a  # crossing point in voxel-centre index space
        u, v = [(1, 2), (2, 0), (0, 1)][ax]
        for du in (0, 1):
            for dv in (0, 1):
                c = idx.copy()
                c[:, u] -= du
                c[:, v] -= dv
                ok = np.all((c >= 0) & (c < np.array(cs)), axis=1)
                keys.append(cell_flat(c[ok, 0], c[ok, 1], c[ok, 2]))
                pts.append(p[ok])
    keys = np.concatenate(keys)
    pts = np.concatenate(pts)
    uk, inv = np.unique(keys, return_inverse=True)
    cnt = np.bincount(inv, minlength=len(uk)).astype(np.float32)
    verts = np.empty((len(uk), 3), np.float32)
    for i in range(3):
        verts[:, i] = np.bincount(inv, weights=pts[:, i], minlength=len(uk)) / cnt
    del keys, pts, inv
    # quads
    tris, ttype = [], []
    for ax, (idx, a_in, _, tin) in enumerate(edges):
        u, v = [(1, 2), (2, 0), (0, 1)][ax]
        order = [(1, 1), (0, 1), (0, 0), (1, 0)]  # cell-min offsets: (u-1,v-1),(u,v-1),(u,v),(u-1,v)
        cid = []
        okall = np.ones(len(idx), bool)
        for du, dv in order:
            c = idx.copy()
            c[:, u] -= du
            c[:, v] -= dv
            okall &= np.all((c >= 0) & (c < np.array(cs)), axis=1)
            cid.append(cell_flat(c[:, 0].clip(0), c[:, 1].clip(0), c[:, 2].clip(0)))
        q = np.stack([np.searchsorted(uk, k) for k in cid], axis=1)
        q = np.where(okall[:, None], q, 0)
        # order (u-1,v-1),(u,v-1),(u,v),(u-1,v) is CCW in (u,v) (normal +axis) -> faces +axis; A inside => outward = +axis
        flip = ~a_in
        q = np.where(flip[:, None], q[:, ::-1], q)
        q = q[okall]
        tin = tin[okall]
        # split along the shorter diagonal
        d02 = np.linalg.norm(verts[q[:, 0]] - verts[q[:, 2]], axis=1)
        d13 = np.linalg.norm(verts[q[:, 1]] - verts[q[:, 3]], axis=1)
        use02 = d02 <= d13
        t_a = np.where(use02[:, None], q[:, [0, 1, 2]], q[:, [1, 2, 3]])
        t_b = np.where(use02[:, None], q[:, [0, 2, 3]], q[:, [1, 3, 0]])
        tris += [t_a, t_b]
        ttype += [tin, tin]
    return verts, np.concatenate(tris).astype(np.int64), np.concatenate(ttype)


def edge_table(tris, nv):
    """Per undirected edge: (lo, hi, use count, signed sum of directions). Closed oriented manifold edge: count 2, sum 0."""
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]).astype(np.int64)
    lo = np.minimum(e[:, 0], e[:, 1])
    hi = np.maximum(e[:, 0], e[:, 1])
    dr = np.where(e[:, 0] < e[:, 1], 1, -1)
    key = lo * nv + hi
    uk, inv = np.unique(key, return_inverse=True)
    inv = inv.reshape(-1)
    cnt = np.bincount(inv)
    tot = np.bincount(inv, weights=dr).astype(np.int64)
    return uk // nv, uk % nv, cnt, tot


def make_manifold(verts, tris, ttype, max_pass=4):
    """Split vertices so no edge is shared by 3+ triangles or by 2 triangles of the same direction.

    Surface nets (one vertex per cell) makes such edges where a cell face is ambiguous (checkerboard: two
    diagonal corners inside) or where two sheets touch: 4 quads then share one edge. A DynamicMesh /
    GeometryScript mesh refuses the 3rd+ triangle of an edge and the 2nd same-direction triangle, so the
    importer lost them (single-triangle holes). Fix: every (triangle, corner) is a node; nodes of one
    vertex are joined across good edges (fans); at a bad edge the triangles are paired (opposite direction,
    preferring the pairing that agrees with the fans at BOTH endpoints) and the pairs are joined at both
    endpoints. Each remaining class of a vertex gets its own copy of the vertex (same position), so the
    geometry is unchanged and the sheets just stop sharing the vertex. Returns verts, tris, info.
    """
    nv0 = len(verts)
    verts = verts.copy()
    tris = tris.copy()
    info = {"bad_edges_per_pass": []}
    for _ in range(max_pass):
        nv = len(verts)
        lo, hi, cnt, tot = edge_table(tris, nv)
        bad = (cnt > 2) | ((cnt == 2) & (tot != 0))
        nbad = int(bad.sum())
        info["bad_edges_per_pass"].append(nbad)
        if nbad == 0:
            break
        badkey = set((lo[bad] * nv + hi[bad]).tolist())
        bv = np.unique(np.concatenate([lo[bad], hi[bad]]))
        flat = tris.reshape(-1)
        order = np.argsort(flat, kind="stable")
        sv = flat[order]
        par = {}

        def find(x):
            par.setdefault(x, x)
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x

        def union(x, y):
            par[find(x)] = find(y)
        tl_of = {}
        bad_tris = {}  # edge key -> [(tri, dir)]
        for v in bv.tolist():
            a = np.searchsorted(sv, v, "left")
            b = np.searchsorted(sv, v, "right")
            tl = (order[a:b] // 3).tolist()
            tl_of[v] = tl
            by_u = {}
            for t in tl:
                tv = tris[t].tolist()
                i = tv.index(v)
                nxt = tv[(i + 1) % 3]
                prv = tv[(i + 2) % 3]
                by_u.setdefault(nxt, []).append((t, 1))   # edge v->nxt
                by_u.setdefault(prv, []).append((t, -1))  # edge prv->v
            for u, ts in by_u.items():
                k = min(u, v) * nv + max(u, v)
                if k in badkey:
                    if v < u:
                        bad_tris[k] = [(t, d if v < u else -d) for t, d in ts]
                elif len(ts) == 2:
                    union((ts[0][0], v), (ts[1][0], v))
            for t in tl:
                find((t, v))
        fan = {x: find(x) for x in list(par)}  # snapshot: fans through good edges only
        for k, lst in bad_tris.items():
            v, u = divmod(k, nv)
            plus = [t for t, d in lst if d > 0]
            minus = [t for t, d in lst if d < 0]
            pairs = []
            for key_ in ("v", "u", "any"):
                for tp in list(plus):
                    for tm in list(minus):
                        if (key_ == "v" and fan.get((tp, v)) == fan.get((tm, v))) or                            (key_ == "u" and fan.get((tp, u)) == fan.get((tm, u))) or key_ == "any":
                            pairs.append((tp, tm))
                            plus.remove(tp)
                            minus.remove(tm)
                            break
            # same-direction leftovers (2 same-dir tris, no opposite): keep apart, nothing to join
            for tp, tm in pairs:
                union((tp, v), (tm, v))
                union((tp, u), (tm, u))
        newv = []
        for v in bv.tolist():
            seen = {}
            for t in tl_of[v]:
                r = find((t, v))
                if r not in seen:
                    seen[r] = v if not seen else nv + len(newv)
                    if seen[r] != v:
                        newv.append(verts[v])
                if seen[r] != v:
                    tris[t][tris[t] == v] = seen[r]
        if not newv:
            break
        verts = np.concatenate([verts, np.array(newv, verts.dtype)])
    info["vertices_added"] = int(len(verts) - nv0)
    lo, hi, cnt, tot = edge_table(tris, len(verts))
    info["final_bad_edges"] = int(((cnt > 2) | ((cnt == 2) & (tot != 0))).sum())
    info["final_open_edges_total"] = int((cnt == 1).sum())
    return verts, tris, info


def topo_check(vu, tris, lo_ue, hi_ue, tol_cm=300.0):
    """Index-based (not position-based) check over ALL kept triangles, equivalent to a cross-tile check.
    nonmanifold = edges with 3+ triangles or 2 same-direction triangles (anywhere);
    interior_open = single-use edges whose midpoint is farther than tol_cm from the cube faces
    (the centroid cull leaves open edges within ~1-2 voxels of the border)."""
    lo, hi, cnt, tot = edge_table(tris, len(vu))
    nonman = (cnt > 2) | ((cnt == 2) & (tot != 0))
    op = cnt == 1
    m = to_ue(((vu[lo] + vu[hi]) / 2).astype(np.float64))
    near = np.any((m < lo_ue + tol_cm) | (m > hi_ue - tol_cm), axis=1)
    return {"edges": int(len(lo)), "nonmanifold_edges": int(nonman.sum()), "open_edges": int(op.sum()),
            "open_near_cube_border": int((op & near).sum()), "interior_open_edges": int((op & ~near).sum()),
            "interior_open_plus_nonmanifold": int((op & ~near).sum() + nonman.sum())}


def to_ue(v_unity):
    o = np.empty_like(v_unity, dtype=np.float64)
    o[:, 0] = 100.0 * v_unity[:, 2]
    o[:, 1] = 100.0 * v_unity[:, 0]
    o[:, 2] = 100.0 * v_unity[:, 1]
    return o


def write_obj(path, vu, tris, ttype):
    """vu: Unity-metre verts (n,3) used by tris. Writes UE cm."""
    used = np.unique(tris)
    remap = np.zeros(len(vu), np.int64)
    remap[used] = np.arange(len(used))
    ue = to_ue(vu[used].astype(np.float64))
    order = np.argsort(ttype, kind="stable")
    with open(path, "w", newline="\n") as f:
        f.write("# SN1 terrain tile, UE axes, cm, absolute\n")
        f.write("\n".join("v %.2f %.2f %.2f" % (a, b, c) for a, b, c in ue))
        f.write("\n")
        cur = None
        buf = []
        tt = ttype[order]
        tr = remap[tris[order]] + 1
        for t, (a, b, c) in zip(tt, tr):
            if t != cur:
                buf.append("usemtl type_%d" % t)
                cur = t
            buf.append("f %d %d %d" % (a, b, c))
        f.write("\n".join(buf))
        f.write("\n")
    return len(used)


def ray_down(vu, tris, x, z, y_from):
    """Highest triangle hit below y_from on the vertical line (x,z), Unity space. Returns y or None."""
    a = vu[tris[:, 0]]
    b = vu[tris[:, 1]]
    c = vu[tris[:, 2]]
    m = ((np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0]) <= x) & (np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0]) >= x) &
         (np.minimum(np.minimum(a[:, 2], b[:, 2]), c[:, 2]) <= z) & (np.maximum(np.maximum(a[:, 2], b[:, 2]), c[:, 2]) >= z))
    a, b, c = a[m].astype(np.float64), b[m].astype(np.float64), c[m].astype(np.float64)
    d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
    ok = np.abs(d) > 1e-12
    a, b, c, d = a[ok], b[ok], c[ok], d[ok]
    w0 = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
    w1 = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
    w2 = 1 - w0 - w1
    hit = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
    y = (w0 * a[:, 1] + w1 * b[:, 1] + w2 * c[:, 1])[hit]
    y = y[y <= y_from]
    return float(y.max()) if len(y) else None


def previews(out, ins, vmin, center, spot, water):
    from PIL import Image, ImageDraw
    sx, sy, sz = ins.shape
    # top surface height map: highest inside voxel per (x,z)
    rev = ins[:, ::-1, :]
    anyin = ins.any(axis=1)
    top = sy - 1 - np.argmax(rev, axis=1)
    h = np.where(anyin, top, -1).astype(np.float32)
    valid = h >= 0
    lo, hi = (h[valid].min(), h[valid].max()) if valid.any() else (0, 1)
    g = np.where(valid, (h - lo) / max(hi - lo, 1e-6), 0)
    rgb = np.zeros((sx, sz, 3), np.uint8)
    rgb[..., 0] = (255 * g).astype(np.uint8)
    rgb[..., 1] = (255 * (1 - abs(g - 0.5) * 2)).astype(np.uint8)
    rgb[..., 2] = (255 * (1 - g)).astype(np.uint8)
    rgb[~valid] = 20
    # image: x horizontal (Unity x), z vertical up (flip rows)
    img = Image.fromarray(np.transpose(rgb, (1, 0, 2))[::-1].copy()).resize((sx * 2, sz * 2), Image.NEAREST)
    dr = ImageDraw.Draw(img)

    def mark(p, col, name):
        px = (p[0] + 2048 - vmin[0]) * 2
        py = (sz - (p[2] + 2048 - vmin[2])) * 2
        dr.ellipse([px - 6, py - 6, px + 6, py + 6], outline=col, width=2)
        dr.text((px + 8, py - 6), name, fill=col)
    mark(spot, (255, 255, 255), "spot")
    mark(water, (255, 255, 0), "water")
    dr.text((4, 4), "top surface height y %.0f (blue) .. %.0f (red) m, x right, z up" % (lo + vmin[1] - 3040, hi + vmin[1] - 3040), fill=(255, 255, 255))
    img.save(os.path.join(out, "preview_topdown.png"))
    # cross-section at z = spot z (x horizontal, y up)
    kz = int(np.floor(center[2] + 2048)) - vmin[2]
    kz = min(max(kz, 0), sz - 1)
    sec = ins[:, :, kz]
    im = np.where(sec, 90, 235).astype(np.uint8)
    img2 = Image.fromarray(np.stack([im] * 3, -1).transpose(1, 0, 2)[::-1].copy()).resize((sx * 2, sy * 2), Image.NEAREST)
    d2 = ImageDraw.Draw(img2)

    def mark2(p, col, name):
        px = (p[0] + 2048 - vmin[0]) * 2
        py = (sy - (p[1] + 3040 - vmin[1])) * 2
        d2.ellipse([px - 6, py - 6, px + 6, py + 6], outline=col, width=2)
        d2.text((px + 8, py - 6), name, fill=col)
    mark2(spot, (255, 0, 0), "spot")
    mark2(water, (0, 0, 255), "water")
    d2.text((4, 4), "section at z=%.1f: dark=solid, light=water, x right, y up" % (kz + vmin[2] - 2048 + 0.5), fill=(255, 0, 0))
    img2.save(os.path.join(out, "preview_section.png"))


def read_obj_verts_tris(path):
    vs, fs = [], []
    for line in open(path):
        if line.startswith("v "):
            vs.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("f "):
            fs.append([int(t) - 1 for t in line.split()[1:4]])
    return np.array(vs, np.float64).reshape(-1, 3), np.array(fs, np.int64).reshape(-1, 3)


def tile_gap_check(out, tile_files, bmin_ue, bmax_ue, tol_cm=100.0):
    """Open edges (used once within one tile) must be matched by a single-use edge in another tile, except near the cube border."""
    allk = {}
    for ti, fpath in enumerate(tile_files):
        v, f = read_obj_verts_tris(fpath)
        vi = np.round(v * 100).astype(np.int64)  # 0.01 cm key
        e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        ka = vi[e[:, 0]]
        kb = vi[e[:, 1]]
        for a, b in zip(map(tuple, ka.tolist()), map(tuple, kb.tolist())):
            key = (a, b) if a < b else (b, a)
            dirn = 1 if a < b else -1
            allk.setdefault(key, []).append((ti, dirn))
    open_cnt = unmatched = 0
    near_border = 0
    for key, lst in allk.items():
        tot = sum(d for _, d in lst)  # a closed manifold has +1 and -1 -> 0
        if tot != 0 or len(lst) % 2:
            open_cnt += 1
            p = np.array(key[0], np.float64) / 100.0
            if (p[0] < bmin_ue[0] + tol_cm or p[0] > bmax_ue[0] - tol_cm or p[1] < bmin_ue[1] + tol_cm or p[1] > bmax_ue[1] - tol_cm or
                    p[2] < bmin_ue[2] + tol_cm or p[2] > bmax_ue[2] - tol_cm):
                near_border += 1
            else:
                unmatched += 1
    return {"edges": len(allk), "open_edges": open_cnt, "open_near_cube_xy_border": near_border, "open_interior": unmatched}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--center", nargs=3, type=float, required=True)
    ap.add_argument("--size", type=float, default=500.0)
    ap.add_argument("--tile", type=float, default=125.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--water", nargs=3, type=float, default=[-1245.13, -251.99, 209.50])
    a = ap.parse_args()
    C = cfg()
    sn1 = C["SN1_GAME_DIR"]
    out = a.out or os.path.join(C["SN2_WORKSPACE"], "sn1_extract", "spot1")
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    c = np.array(a.center, np.float64)
    half = a.size / 2
    umin = c - half
    umax = c + half
    vmin = np.floor(umin - ORIGIN).astype(np.int64) - 2  # +margin voxels
    vmax = np.ceil(umax - ORIGIN).astype(np.int64) + 2
    print("grid voxels", vmax - vmin, flush=True)
    T, D, read = build_grid(sn1, vmin, vmax)
    t_dec = time.time() - t0
    print("decoded %.1fs" % t_dec, flush=True)
    hist = np.bincount(T.reshape(-1), minlength=256)
    ins = inside_mask(T, D)
    verts, tris, ttype = surface_nets(T, D)
    verts, tris, mfinfo = make_manifold(verts, tris, ttype)
    print("make_manifold", mfinfo, flush=True)
    t_mesh = time.time() - t0
    print("meshed %.1fs verts %d tris %d" % (t_mesh, len(verts), len(tris)), flush=True)
    # unity-metre world coords (voxel centres at +0.5)
    vu = verts + (vmin + ORIGIN + 0.5).astype(np.float32)
    nan = int(np.isnan(vu).sum())
    # keep triangles whose centroid is within the cube
    cen = (vu[tris[:, 0]] + vu[tris[:, 1]] + vu[tris[:, 2]]) / 3
    keep = np.all((cen >= umin) & (cen < umax), axis=1)
    tris, ttype, cen = tris[keep], ttype[keep], cen[keep]
    ntile = int(np.ceil(a.size / a.tile))
    ti = np.clip(((cen[:, 0] - umin[0]) // a.tile).astype(int), 0, ntile - 1)
    tk = np.clip(((cen[:, 2] - umin[2]) // a.tile).astype(int), 0, ntile - 1)
    tiles = {}
    files = []
    for i in range(ntile):
        for k in range(ntile):
            m = (ti == i) & (tk == k)
            if not m.any():
                continue
            fp = os.path.join(out, "tile_%d_%d.obj" % (i, k))
            nv = write_obj(fp, vu, tris[m], ttype[m])
            files.append(fp)
            tiles["tile_%d_%d" % (i, k)] = {"vertices": nv, "triangles": int(m.sum()),
                                            "unity_min_xz": [float(umin[0] + i * a.tile), float(umin[2] + k * a.tile)]}
    # self-checks
    spot = np.array(a.center)
    water = np.array(a.water)
    hs = ray_down(vu, tris, spot[0], spot[2], spot[1] + 50)
    hw = ray_down(vu, tris, water[0], water[2], water[1])
    wv = np.floor(water - ORIGIN).astype(int) - vmin
    sv = np.floor(spot - ORIGIN).astype(int) - vmin
    ue_bmin = to_ue(umin[None])[0]
    ue_bmax = to_ue(umax[None])[0]
    lo_ue = np.minimum(ue_bmin, ue_bmax)
    hi_ue = np.maximum(ue_bmin, ue_bmax)
    gaps = tile_gap_check(out, files, lo_ue, hi_ue)  # position-keyed legacy check: cannot tell split vertex copies apart
    gaps["topology_index_based"] = topo_check(vu, tris, lo_ue, hi_ue)
    gaps["make_manifold"] = mfinfo
    # seabed normal check: triangles within 20 m of spot (xz), upward-facing sign
    seab = {}
    near = np.all(np.abs(cen[:, [0, 2]] - spot[[0, 2]]) < 20, axis=1)
    if near.any():
        tr = tris[near]
        A, B, Cc = (to_ue(vu[tr[:, i]].astype(np.float64)) for i in range(3))
        n = np.cross(B - A, Cc - A)
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        seab = {"tris": int(near.sum()), "mean_nz_ue": float(n[:, 2].mean()), "frac_nz_gt_0.5": float((n[:, 2] > 0.5).mean())}
    summary = {
        "cube_unity_min": umin.tolist(), "cube_unity_max": umax.tolist(),
        "cube_ue_cm_min": lo_ue.tolist(), "cube_ue_cm_max": hi_ue.tolist(),
        "grid_voxels": (vmax - vmin).tolist(), "grid_origin_voxel_index": vmin.tolist(),
        "batches": [{"id": list(b), "state": s} for b, s in read],
        "voxel_type_histogram": {int(i): int(n) for i, n in enumerate(hist) if n},
        "tiles": tiles, "total_vertices_before_split": int(len(verts)), "total_triangles": int(len(tris)),
        "nan_vertices": nan,
        "selfcheck": {
            "spot_ray_hit_y": hs, "spot_height_above_surface_m": None if hs is None else float(spot[1] - hs),
            "spot_voxel_inside_solid": bool(ins[tuple(sv)]),
            "water_voxel_inside_solid": bool(ins[tuple(wv)]),
            "water_ray_hit_y": hw, "water_height_above_surface_m": None if hw is None else float(water[1] - hw),
            "seabed_normals_ue": seab, "tile_gap_check": gaps,
        },
        "timing_s": {"decode": round(t_dec, 1), "decode_and_mesh": round(t_mesh, 1), "total": round(time.time() - t0, 1)},
        "mesher": "surface nets on SN1 density semantics (inside = density>=126 or far-inside type>0; crossing via ComputeSurfaceIntersection)",
        "winding": "cross(b-a,c-a) points out of solid, in Unity and UE axes",
    }
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1)
    previews(out, ins, vmin, c, spot, water)
    print(json.dumps(summary["selfcheck"], indent=1))
    print("total triangles", len(tris), "time %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
