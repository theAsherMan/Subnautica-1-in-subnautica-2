#!/usr/bin/env python3
"""Purge-window timeline from a Subnautica2.log (2026-11-24): every log line between the L_SN2World LoadMap line and the SkyLight line (or the end).
Usage: python -I gc_window.py <Subnautica2.log> [out.txt]
Prints: window bounds, LogGarbage line count (verbose evidence), per-category line counts, then all window lines except LogGarbage queue entries ('[n]:' beyond 10)."""
import re, sys, collections
log = sys.argv[1]
out = open(sys.argv[2], "w", encoding="utf-8") if len(sys.argv) > 2 else sys.stdout
lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
start = end = None
for i, l in enumerate(lines):
    if start is None and "LogLoad: LoadMap:" in l and "L_SN2World" in l:
        start = i
    elif start is not None and "SkyLight change" in l:
        end = i; break
if start is None:
    print("no L_SN2World LoadMap line", file=out); sys.exit(0)
if end is None: end = len(lines) - 1
ts = lambda l: l[1:24] if l.startswith("[") else "?"
print(f"window lines {start+1}..{end+1}  from {ts(lines[start])} to {ts(lines[end])}", file=out)
gar = [l for l in lines if "LogGarbage" in l]
verb = [l for l in gar if "Warning" not in l]
print(f"LogGarbage lines in whole log: {len(gar)} ; non-warning (verbose/log) ones: {len(verb)}", file=out)
for l in verb[:15]: print("  " + l[:200], file=out)
cat = collections.Counter(); qn = 0
body = []
for l in lines[start:end + 1]:
    m = re.match(r"\[[^\]]*\]\[\s*(\d+)\](\w+):", l)
    c = m.group(2) if m else "other"; cat[c] += 1
    if "LogGarbage: Warning:   [" in l:
        qn += 1
        if qn > 10: continue
    body.append(l)
print("window lines per category: " + ", ".join(f"{k}={v}" for k, v in cat.most_common()), file=out)
print("--- window lines (queue entries beyond 10 omitted) ---", file=out)
for l in body: print(l[:260], file=out)
