"""Claude Code hook for static-analyst sessions (started by static_analysis.py; never active in other sessions).

Usage (from the generated <conv>/hook_settings.json):  python -I static_analysis_hook.py pre|post
  pre  (PreToolUse, Bash): logs the command to <conv>/commands.log and refuses writes into sn1_decompiled
       by anything other than a plain ilspycmd call.
  post (PostToolUse, all tools): delivers investigator messages waiting in <conv>/inbox/ as additionalContext,
       then moves them to <conv>/inbox/delivered/.
The conversation folder comes from the env var SN2_SA_CONV (set by static_analysis.py for its claude process).
"""
import json
import os
import re
import sys
import time

CONV = os.environ.get("SN2_SA_CONV", "")

WRITE_PAT = re.compile(
    r"(>|\btee\b|\bcp\b|\bmv\b|\brm\b|\bmkdir\b|\btouch\b|\bsed\s+-i|\bopen\s*\([^)]*['\"][wax]|write_text|write_bytes"
    r"|\bshutil\b|\bos\.(remove|rename|replace|makedirs|mkdir|unlink)|Set-Content|Out-File|New-Item|Remove-Item"
    r"|Copy-Item|Move-Item|\bdel\b|\bunzip\b|\btar\b|\b7z\b|\bretoc\b|\buaa\b|\blvl(bp)?\b|\brepak\b)",
    re.IGNORECASE)
HARMLESS_REDIR = re.compile(r"\d*>\s*/dev/null|\d*>&\d|&>\s*/dev/null|\d*>\s*\$null", re.IGNORECASE)
PLAIN_ILSPY = re.compile(r"^\s*(\S*[/\\])?ilspycmd(\.exe)?\s[^;&|<>`$]*$", re.IGNORECASE)


CD_INTO = re.compile(r"\b(cd|pushd|Set-Location)\s+['\"]?[^;&|]*sn1_decompiled", re.IGNORECASE)


def writes_into_cache(cmd):
    """Heuristic: a write operation with sn1_decompiled AFTER it (its target), or any write after cd-ing into it.
    Reading from the cache and redirecting into WORKDIR (grep <cache file> > <WORKDIR>/x) is allowed."""
    low = cmd.lower()
    if CD_INTO.search(cmd) and WRITE_PAT.search(cmd):
        return True
    return any("sn1_decompiled" in low[m.start():] for m in WRITE_PAT.finditer(cmd))


def log(name, line):
    if not CONV:
        return
    try:
        with open(os.path.join(CONV, name), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
    except OSError:
        pass


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def pre(data):
    cmd = (data.get("tool_input") or {}).get("command") or ""
    log("commands.log", cmd.replace("\r", " ").replace("\n", " \\n "))
    if "sn1_decompiled" not in cmd.lower():
        return
    if PLAIN_ILSPY.match(cmd):
        return
    if writes_into_cache(HARMLESS_REDIR.sub(" ", cmd)):
        log("commands.log", "  -> REFUSED by hook (write into sn1_decompiled)")
        emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Refused: this command looks like it writes into sn1_decompiled. Only a plain ilspycmd call may "
                "write there (ilspycmd ... -o <Workspace>/sn1_decompiled/<Type>). Put your own files in WORKDIR.")}})


def post(_data):
    if not CONV:
        return
    inbox = os.path.join(CONV, "inbox")
    try:
        names = sorted(n for n in os.listdir(inbox) if n.endswith(".md"))
    except OSError:
        return
    if not names:
        return
    done = os.path.join(inbox, "delivered")
    os.makedirs(done, exist_ok=True)
    parts = []
    for n in names:
        src = os.path.join(inbox, n)
        try:
            with open(src, encoding="utf-8") as f:
                text = f.read().strip()
            os.replace(src, os.path.join(done, n))
        except OSError:
            continue
        parts.append("[Message from the investigator]\n" + text)
        log("updates.log", "-- DELIVERED mid-turn inbox/delivered/" + n)
    if parts:
        emit({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n\n".join(parts)}})


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "pre":
        pre(data)
    elif mode == "post":
        post(data)


if __name__ == "__main__":
    main()
