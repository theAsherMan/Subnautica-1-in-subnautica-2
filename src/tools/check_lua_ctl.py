"""Exit 1 (and print file:line) if a Lua file contains a raw control character other than TAB and LF (CR included).
Why: a literal CR/LF/TAB inside a Lua string pattern breaks the string ('unfinished string'), and UE4SS then does not load the mod (2026-11-19 incident).
Write escapes as backslash + r/n/t in the source, never the raw characters.   Usage: python check_lua_ctl.py <file.lua> [...]"""
import sys

bad = 0
for path in sys.argv[1:]:
    for n, line in enumerate(open(path, "rb").read().split(b"\n"), 1):
        c = [x for x in line if x < 32 and x != 9]
        if c:
            print("%s:%d: raw control character 0x%02x" % (path, n, c[0]))
            bad = 1
sys.exit(bad)
