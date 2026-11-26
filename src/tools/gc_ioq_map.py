#!/usr/bin/env python3
"""Map the IoStore read requests captured by gc_ioq_scan.py to chunks / packages and report the queue around the lobby -> world travel
(hypothesis H8, 2026-11-26). Python stdlib + numpy; fine with -I.
Usage: python -I gc_ioq_map.py <run dir> [--utoc <Subnautica2-Windows.utoc>] [--list <retoc list text>] [--top 12] [--out FILE]
Inputs in the run dir: ioq_parts.json (paths list: a request's partition field is an index into it), ioq_life.json, ioq_scan.jsonl (from gc_ioq_scan.py), Subnautica2.log (UTC markers).
Needs the .utoc (default <GameDir>/Subnautica2/Content/Paks/Subnautica2-Windows.utoc from local.config) and the text of
  retoc list --all --package --size --path <utoc>   (run automatically with src/tools/bin/retoc.exe and cached as <run dir>/utoc_list.txt).
TOC layout (UE 5.6, TOC version 8, header 144 B): ChunkIds 12 B, OffsetAndLength 10 B (5 B big-endian offset + 5 B length, virtual space),
perfect-hash seeds 4 B, chunks-without-perfect-hash 4 B, compression blocks 12 B (40-bit raw offset, 24-bit compressed size, 24-bit
uncompressed size, 8-bit method), method names 32 B. A raw .ucas offset -> block (searchsorted over block raw offsets) -> virtual offset
= block * CompressionBlockSize -> chunk. Chunk id = 8-byte id, 2-byte index, 1 pad, 1 type (1 ExportBundleData, 2 BulkData, 3 OptionalBulkData,
4 MemoryMappedBulkData, 5 ScriptObjects, 6 ContainerHeader, 7 ExternalFile, 8 ShaderCodeLibrary, 9 ShaderCode, 10 PackageStoreEntry).
IoDispatcher priorities: Min INT_MIN, Low -2^30, Medium 0, High 2^30, Max INT_MAX (a higher value is served first)."""
import argparse, calendar, collections, json, os, re, struct, subprocess, sys, time
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TYPES = {1: "ExportBundleData", 2: "BulkData", 3: "OptionalBulkData", 4: "MemoryMappedBulkData", 5: "ScriptObjects", 6: "ContainerHeader",
         7: "ExternalFile", 8: "ShaderCodeLibrary", 9: "ShaderCode", 10: "PackageStoreEntry"}


def cfg():
    d = {}
    for line in open(os.path.join(REPO, "local.config"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"')
    return d


class Toc:
    def __init__(self, path):
        b = open(path, "rb").read()
        assert b[:16] == b"-==--==--==--==-", "not a utoc"
        (self.ver, _r0, _r1, hs, ne, nb, bes, nm, nml, self.bsz, dis, pc) = struct.unpack_from("<BBHIIIIIIIII", b, 16)
        assert hs == 144 and bes == 12, (hs, bes)
        seeds, = struct.unpack_from("<I", b, 84)
        nonph, = struct.unpack_from("<I", b, 96)
        o = hs
        self.ids = [b[o + 12 * i:o + 12 * i + 12] for i in range(ne)]
        o += 12 * ne
        ol = np.frombuffer(b, dtype=np.uint8, count=10 * ne, offset=o).reshape(ne, 10).astype(np.uint64)
        o += 10 * ne

        def be(a):
            r = a[:, 0]
            for i in range(1, 5):
                r = (r << np.uint64(8)) | a[:, i]
            return r
        self.c_off, self.c_len = be(ol[:, 0:5]), be(ol[:, 5:10])
        o += 4 * seeds + 4 * nonph
        blk = np.frombuffer(b, dtype=np.uint8, count=12 * nb, offset=o).reshape(nb, 12).astype(np.uint64)
        self.b_raw = blk[:, 0] | blk[:, 1] << np.uint64(8) | blk[:, 2] << np.uint64(16) | blk[:, 3] << np.uint64(24) | blk[:, 4] << np.uint64(32)
        self.b_csize = blk[:, 5] | blk[:, 6] << np.uint64(8) | blk[:, 7] << np.uint64(16)
        self.order = np.argsort(self.c_off, kind="stable")
        self.c_off_sorted = self.c_off[self.order]
        self.ne, self.nb = ne, nb

    def attrib(self, offset, size):
        """{chunk index: compressed bytes} for the raw range [offset, offset+size)."""
        first = max(int(np.searchsorted(self.b_raw, np.uint64(offset), side="right")) - 1, 0)
        last = min(max(int(np.searchsorted(self.b_raw, np.uint64(offset + size - 1), side="right")) - 1, first), self.nb - 1)
        out = {}
        for blk in range(first, last + 1):
            v = np.uint64(blk * self.bsz)
            ci = int(np.searchsorted(self.c_off_sorted, v, side="right")) - 1
            if ci >= 0:
                c = int(self.order[ci])
                if v < self.c_off[c] + self.c_len[c]:
                    out[c] = out.get(c, 0) + int(self.b_csize[blk])
        return out


def load_names(list_path):
    names = {}
    for line in open(list_path, encoding="utf-8", errors="replace"):
        t = line.split(None, 5)
        if len(t) >= 5:
            names[t[1].lower()] = t[5].strip() if len(t) > 5 else "-"
    return names


def log_markers(path):
    """UTC epoch of the interesting game-log lines."""
    m = {}
    if not os.path.exists(path):
        return m
    rx = re.compile(r"^\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]")
    for line in open(path, encoding="utf-8", errors="replace"):
        r = rx.match(line)
        if not r:
            continue
        y, mo, d, h, mi, s, ms = map(int, r.groups())
        t = calendar.timegm((y, mo, d, h, mi, s)) + ms / 1000.0
        if "LoadMap: /Game/Maps/L_ClientLobby" in line and "lobby_loadmap" not in m:
            m["lobby_loadmap"] = t
        elif "LogLoad: LoadMap:" in line and "L_SN2World" in line and "travel" not in m:
            m["travel"] = t
        elif "Audio Device unregistered from world 'None'" in line and "travel" in m and "purge_start" not in m:
            m["purge_start"] = t
        elif "SkyLight change" in line and "travel" in m and "purge_end" not in m:
            m["purge_end"] = t
        elif ("Spent more than" in line and "FinishDestroy" in line) and "crash" not in m:
            m["crash"] = t
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--utoc")
    ap.add_argument("--list")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--out")
    a = ap.parse_args()
    run = a.run
    c = cfg()
    utoc = a.utoc or os.path.join(c["SN2_GAME_DIR"], "Subnautica2", "Content", "Paks", "Subnautica2-Windows.utoc")
    lst = a.list or os.path.join(run, "utoc_list.txt")
    if not os.path.exists(lst):
        with open(lst, "w", encoding="utf-8") as f:
            subprocess.run([os.path.join(REPO, "src", "tools", "bin", "retoc.exe"), "list", "--all", "--package", "--size", "--path", utoc], stdout=f, check=True)
    toc, names = Toc(utoc), load_names(lst)
    pj = json.load(open(os.path.join(run, "ioq_parts.json")))
    main_idx = [i for i, p in enumerate(pj["paths"]) if p.endswith("Subnautica2-Windows.ucas")][0]
    freq = pj["qpc_freq"]
    life = {int(k): v for k, v in json.load(open(os.path.join(run, "ioq_life.json"))).items()}
    scans = [json.loads(l) for l in open(os.path.join(run, "ioq_scan.jsonl"))]
    mk = log_markers(os.path.join(run, "Subnautica2.log"))
    out = open(a.out or os.path.join(run, "ioq_report.txt"), "w", encoding="utf-8")

    def P(*x):
        s = " ".join(str(i) for i in x)
        print(s)
        out.write(s + "\n")

    t0 = scans[0]["t"]
    P("markers (UTC epoch): " + ", ".join("%s=%.1f" % (k, v) for k, v in mk.items()))
    tr = mk.get("travel")
    rel = (lambda t: t - tr) if tr else (lambda t: t - t0)
    P("rel. time base: %s" % ("LoadMap L_SN2World (travel)" if tr else "first scan"))
    P("== timeline (every ~2 s): rel_s, queued requests, queued MB, started, seqmax, queued per priority")
    last = -9
    for s in scans:
        r = rel(s["t"])
        if r - last >= 2.0 or abs(r) < 0.3:
            last = r
            P("  %+7.1f  inq=%5d  mb=%7.1f  started=%d  seqmax=%d  prio=%s" % (r, s["inq"], s["mb_inq"], len(s["started"]), s["seqmax"], s["prio"]))
    cache = {}

    def describe(off, size):
        key = (off, size)
        if key not in cache:
            cache[key] = {ci: b for ci, b in toc.attrib(off, size).items()}
        return cache[key]

    def label(ci):
        idb = toc.ids[ci]
        ty = TYPES.get(idb[11], str(idb[11]))
        return ty, names.get(idb.hex(), "-")

    P("== life table: %d requests seen" % len(life))
    groups = collections.defaultdict(list)
    for seq, e in life.items():
        off, size, prio, part, created, t_inq, t_st, t_done, t_last = e
        if part != main_idx:
            continue
        created_t = None
        if tr and t_inq is not None:
            created_t = t_inq
        if t_inq is None:
            g = "never seen queued (completed between scans)"
        elif tr is None:
            g = "all"
        elif t_inq < (mk.get("purge_start", tr)):
            g = "queued before travel"
        else:
            g = "first queued during/after purge"
        groups[g].append((seq, e))
    for g, items in sorted(groups.items()):
        mb = sum(e[1] for _, e in items) / 1e6
        pr = collections.Counter(e[2] for _, e in items)
        P("  [%s] %d requests, %.0f MB, priorities %s" % (g, len(items), mb, dict(pr)))
        tcount, pcount = collections.Counter(), collections.Counter()
        for _, e in items:
            for ci, b in describe(e[0], e[1]).items():
                ty, path = label(ci)
                tcount[ty] += b
                pcount[(ty, path if ty != "ShaderCode" else "(shader code)")] += b
        P("      raw MB by chunk type: " + ", ".join("%s %.0f" % (k, v / 1e6) for k, v in tcount.most_common()))
        for (ty, path), v in pcount.most_common(a.top):
            P("      %7.1f MB  %-16s %s" % (v / 1e6, ty, path))
        waits = [(e[7] - e[5]) for _, e in items if e[5] is not None and e[7] is not None]
        if waits:
            waits.sort()
            P("      queue wait (first seen queued -> first seen done, s): n=%d median=%.1f p90=%.1f max=%.1f" % (len(waits), waits[len(waits) // 2], waits[int(len(waits) * .9)], waits[-1]))
        still = [e for _, e in items if e[7] is None and e[5] is not None]
        if still:
            P("      never seen completed: %d requests, %.0f MB" % (len(still), sum(e[1] for e in still) / 1e6))
    if tr and "purge_start" in mk:
        ps, pe = mk["purge_start"], mk.get("purge_end", mk.get("crash", scans[-1]["t"]))
        P("== requests completed inside the purge window (first seen done in [%+.1f, %+.1f] s)" % (rel(ps), rel(pe)))
        inside = [(seq, e) for seq, e in life.items() if e[7] and ps <= e[7] <= pe and e[3] == main_idx]
        P("  %d requests, %.0f MB" % (len(inside), sum(e[1] for _, e in inside) / 1e6))
        by = collections.Counter()
        for _, e in inside:
            for ci, b in describe(e[0], e[1]).items():
                by[label(ci)[0]] += b
        P("  by type: " + ", ".join("%s %.0f MB" % (k, v / 1e6) for k, v in by.most_common()))
    if tr and "purge_start" in mk:
        # stall model: is the end of the purge the moment the BelowNormal (-1) queue empties?
        pe = mk.get("purge_end")
        pre = [x for x in scans if x["t"] <= tr + 0.5]
        post = [x for x in scans if x["t"] > tr]
        P("== stall model (BelowNormal = priority -1, Low = -2^30; each request ~0.262 MB)")
        if pre:
            x = pre[-1]
            P("  last scan before travel (%+.1f s): -1 queued %d (~%.0f MB), Low queued %d, medium %d" % (rel(x["t"]), x["prio"].get("-1", 0), x["prio"].get("-1", 0) * 0.262, x["prio"].get("-1073741824", 0), x["prio"].get("0", 0)))
        if post:
            x = post[0]
            P("  first scan after travel (%+.1f s): -1 queued %d (~%.0f MB), Low queued %d (cancelled by the travel if it dropped)" % (rel(x["t"]), x["prio"].get("-1", 0), x["prio"].get("-1", 0) * 0.262, x["prio"].get("-1073741824", 0)))
        seen_bn = False
        t_empty = None
        for x in post:
            if x["prio"].get("-1", 0) > 0:
                seen_bn = True
            elif seen_bn:
                t_empty = x["t"]
                break
        if t_empty:
            P("  -1 queue first seen empty at %+.2f s; purge end (SkyLight change) at %+.2f s; difference %+.2f s" % (rel(t_empty), rel(pe) if pe else float("nan"), (rel(t_empty) - rel(pe)) if pe else float("nan")))
        else:
            P("  -1 queue never seen going from non-empty to empty after the travel scan window")
    out.close()


if __name__ == "__main__":
    main()
