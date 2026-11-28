#!/usr/bin/env python3
"""Diff the component/actor property dumps of the SN2AutoTest verb uwa8 (diagnostic, investigator-water3 2026-11-27).

Usage: python -I src/tools/uwa_propdiff.py <UE4SS.log> [<UE4SS.log2>]
Reads lines `UWA uwaN <TAG> (COMP|ACTOR) PROP <Class>.<prop>=<value>` and the summary lines `UWA uwaN <TAG> <key>=...`.
One log: prints, for every pair of tags (STANDALONE / BOX / CAT0 / NEWCUBE / SPAWNEDBP), the properties whose values differ.
Two logs: compares the tags of the first log against the same tags of the second (e.g. ours vs L_Main CAT0).
"""
import re
import sys
from collections import defaultdict

PAT = re.compile(r"UWA uwa\d+ (\w+) (COMP|ACTOR) PROP (\S+?)=(.*)$")
SUM = re.compile(r"UWA uwa\d+ (\w+) (mesh|compScale|bounds|mobility|attachParent|ownerHidden|propsDumped|fullname)\b(.*)$")


def load(path):
    props = defaultdict(dict)   # tag -> {COMP:Class.prop -> value}
    summ = defaultdict(list)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = PAT.search(line)
            if m:
                tag, kind, key, val = m.groups()
                props[tag][kind + ":" + key] = val.strip()
                continue
            m = SUM.search(line)
            if m:
                summ[m.group(1)].append((m.group(2) + m.group(3)).strip())
    return props, summ


def diff(a, b, name_a, name_b):
    keys = sorted(set(a) | set(b))
    n = 0
    for k in keys:
        va, vb = a.get(k, "<absent>"), b.get(k, "<absent>")
        if va != vb:
            print(f"  {k:70s} {name_a}={va}  {name_b}={vb}")
            n += 1
    print(f"  ({n} differing of {len(keys)})")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    pa, sa = load(sys.argv[1])
    if len(sys.argv) == 2:
        tags = sorted(pa)
        for t in tags:
            print(f"== {t}: {len(pa[t])} props")
            for s in sa[t]:
                print("   " + s)
        for i, x in enumerate(tags):
            for y in tags[i + 1:]:
                print(f"== {x} vs {y}")
                diff(pa[x], pa[y], x, y)
    else:
        pb, sb = load(sys.argv[2])
        for t in sorted(set(pa) | set(pb)):
            print(f"== {t}: log1 vs log2")
            diff(pa.get(t, {}), pb.get(t, {}), "log1", "log2")
            print("  log1 summary:", *sa.get(t, []), sep="\n    ")
            print("  log2 summary:", *sb.get(t, []), sep="\n    ")
    return 0


sys.exit(main())
