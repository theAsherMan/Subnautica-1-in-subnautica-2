#!/usr/bin/env python3
"""GC-watchdog statistics: one row per lobby -> world LoadMap found in Subnautica 2 game logs.

Usage: python -I gc_purge_stats.py [--tsv OUT.tsv] <game logs, run folders or folders...>
  Folders are searched recursively for *.log (UE4SS*/driver* logs skipped). Logs are de-duplicated by their first timestamp
  (the same game log is copied into several run / crash folders). All times are UTC, as in the game log.

Columns (tab separated, header line starts with '#'):
  logstart         first timestamp of the log
  lobby_loadmap    `LogLoad: LoadMap: .../L_ClientLobby` line
  world_loadmap    the lobby -> world `LogLoad: LoadMap:` line (non-lobby map) and the map name + game mode
  lobby_to_lm_s    seconds lobby LoadMap start -> world LoadMap
  boot_to_lobby_s  seconds log start -> lobby LoadMap start
  purge_s          the GC purge of the lobby: the silent gap from `LogAudio: Display: Audio Device unregistered from world 'None'.`
                   to the next timestamped log line (normally `LogRenderer: Forcing update ... SkyLight change`)
  result           OK (`Took .. seconds to LoadMap(<world>)` seen), GC_CRASH (`Spent too much time waiting for FinishDestroy` or
                   `AbortInsideMemberFunction`), NO_END (log ends before either)
  gc_queue         `objects in queue: N` of the LogGarbage watchdog line (GC_CRASH rows)
Prints a summary (purge distribution, crash count) at the end. Test-only diagnosis tool (research/01 "GC-watchdog analysis")."""
import glob
import os
import re
import sys
from collections import Counter
from datetime import datetime

TS = re.compile(r'^\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]')


def ts(line):
    m = TS.match(line)
    if not m:
        return None
    y, mo, d, h, mi, s, ms = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi, s, ms * 1000)


def fmt(t):
    return t.strftime('%Y-%m-%d %H:%M:%S.') + '%03d' % (t.microsecond // 1000) if t else ''


def scan(path):
    """-> (first timestamp, [row dict, ...])"""
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return None, []
    first = next((ts(l) for l in lines if ts(l)), None)
    if first is None:
        return None, []
    rows = []
    lobby_start = None
    cur = None
    last = first
    for i, l in enumerate(lines):
        t = ts(l)
        if t:
            last = t
        else:
            t = last
        m = re.search(r'LogLoad: LoadMap: (\S+)', l)
        if m:
            if 'L_ClientLobby' in m.group(1):
                lobby_start = t
                continue
            game = re.search(r'game=(\w+)', m.group(1))
            cur = dict(logstart=first, lobby=lobby_start, world=t, map=m.group(1).split('?')[0].split('/')[-1],
                       mode=game.group(1) if game else '', purge=None, result='NO_END', queue='')
            rows.append(cur)
            # purge gap: unregistered line -> next timestamped line
            for j in range(i, min(i + 400, len(lines))):
                if "unregistered from world 'None'" in lines[j]:
                    t0 = ts(lines[j])
                    for k in range(j + 1, min(j + 60, len(lines))):
                        t1 = ts(lines[k])
                        if t1:
                            cur['purge'] = (t1 - t0).total_seconds()
                            break
                    break
            continue
        if cur is None or cur['result'] != 'NO_END':
            continue
        q = re.search(r'objects in queue: (\d+)', l)
        if q:
            cur['queue'] = q.group(1)
        if 'Spent too much time waiting for FinishDestroy' in l or 'AbortInsideMemberFunction' in l:
            cur['result'] = 'GC_CRASH'
        elif re.search(r'Took [\d.]+ seconds to LoadMap\(', l) and 'L_ClientLobby' not in l:
            cur['result'] = 'OK'
    return first, rows


def main(argv):
    tsv = None
    args = list(argv)
    if '--tsv' in args:
        i = args.index('--tsv')
        tsv = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 2
    files = []
    for a in args:
        if os.path.isdir(a):
            files += glob.glob(os.path.join(a, '**', '*.log'), recursive=True)
        else:
            files += glob.glob(a)
    seen = {}
    for f in sorted(set(files)):
        b = os.path.basename(f)
        if 'UE4SS' in b or 'driver' in b:
            continue
        first, rows = scan(f)
        if first is not None and first not in seen:
            seen[first] = (f, rows)
    head = ['#logstart', 'lobby_loadmap', 'world_loadmap', 'map', 'mode', 'lobby_to_lm_s', 'boot_to_lobby_s', 'purge_s', 'result', 'gc_queue', 'file']
    out = ['\t'.join(head)]
    allrows = []
    for key in sorted(seen):
        f, rows = seen[key]
        for r in rows:
            lm = (r['world'] - r['lobby']).total_seconds() if r['lobby'] else None
            boot = (r['lobby'] - r['logstart']).total_seconds() if r['lobby'] else None
            allrows.append((r, lm))
            out.append('\t'.join([fmt(r['logstart']), fmt(r['lobby']), fmt(r['world']), r['map'], r['mode'],
                                  '%.1f' % lm if lm is not None else '', '%.1f' % boot if boot is not None else '',
                                  '%.3f' % r['purge'] if r['purge'] is not None else '', r['result'], r['queue'], f]))
    text = '\n'.join(out) + '\n'
    if tsv:
        open(tsv, 'w', encoding='utf-8', newline='\n').write(text)
    else:
        sys.stdout.write(text)
    p = sorted(r['purge'] for r, _ in allrows if r['purge'] is not None)
    print('logs %d loads %d  %s' % (len(seen), len(allrows), dict(Counter((r['map'], r['result']) for r, _ in allrows))))
    if p:
        print('purge_s n=%d min=%.3f median=%.3f p75=%.3f max=%.3f  >=10s: %d  >=15s: %d  GC_CRASH: %d' % (
            len(p), p[0], p[len(p) // 2], p[3 * len(p) // 4], p[-1], sum(x >= 10 for x in p), sum(x >= 15 for x in p),
            sum(r['result'] == 'GC_CRASH' for r, _ in allrows)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
