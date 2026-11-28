#!/usr/bin/env python
"""Claude Code PostToolUse hook: lint research/ after any Write/Edit inside it.

Wired in .claude/settings.json (PostToolUse, matcher Write|Edit|MultiEdit). Reads the hook JSON on stdin.
If the written file is not under <repo>/research/, exits 0 silently. Otherwise runs research_lint.py:
- no errors: exit 0 (silent);
- errors: exit 2 with a summary on stderr, which Claude Code feeds back to the agent that made the edit.
  Errors in the edited file (or pointing at it) are listed in full; others are counted, since another
  session or agent may be mid-edit there.
"""
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normcase(os.path.abspath(os.path.join(HERE, "..", "..")))
RESEARCH = os.path.join(REPO, "research")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    ti = data.get("tool_input") or {}
    tr = data.get("tool_response") or {}
    path = ti.get("file_path") or (tr.get("filePath") if isinstance(tr, dict) else None)
    if not path:
        return 0
    m = re.match(r"^/([a-zA-Z])/(.*)$", path)  # Git Bash form /c/Users/... -> C:/Users/...
    if m and os.name == "nt":
        path = m.group(1) + ":/" + m.group(2)
    full = os.path.abspath(path)
    if not os.path.normcase(full).startswith(RESEARCH + os.sep):
        return 0
    rel = full[len(RESEARCH) + 1:].replace(os.sep, "/")
    p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "research_lint.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode == 0:
        return 0
    errs = [l for l in p.stdout.splitlines() if l.startswith("ERROR ")]
    if not errs:
        sys.stderr.write("research_lint failed to run:\n" + p.stdout[-2000:] + p.stderr[-2000:])
        return 2
    mine = [e for e in errs if rel.lower() in e.lower()]
    other = len(errs) - len(mine)
    out = ["research_lint after editing research/%s:" % rel]
    if mine:
        out += mine
    else:
        out.append("(no errors in or pointing at this file)")
    if other:
        out.append("%d other error(s) elsewhere in research/; run `python -I src/tools/research_lint.py` to list them "
                   "(they may be another agent's work in progress)." % other)
    sys.stderr.write("\n".join(out) + "\n")
    return 2 if mine else 0


if __name__ == "__main__":
    sys.exit(main())
