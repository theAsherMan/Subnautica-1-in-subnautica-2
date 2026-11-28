"""Static analysis conversations: the investigator talks with the static-analyst agent (Opus, xhigh, read-only)
through a headless Claude CLI. Call through static_analysis.sh (it loads local.config). Details: research/01_runbook.md
"Static analysis".

  new    --game sn1|sn2|both [--slug S]   create a conversation folder, print its path (quick)
  send   <conv> --message-file F          queue a message; if no turn is running, run turns until the inbox is empty
                                          (blocks: start it with run_in_background). While a turn runs, the message is
                                          delivered at the analyst's next tool step by the hook.
  watch  <conv> [--from N]                print each analyst message as it lands; exits when the analyst is idle
  cancel <conv>                           kill the running turn (the conversation can go on with another send)
  end    <conv>                           close the conversation (refused while a turn runs)
  status <conv>                           state, turns, cost, pending messages

Conversation folder (<Workspace>/static_analysis/<stamp>_<slug>/):
  meta.json, running.json (while a turn runs), inbox/*.md (+ delivered/), updates/NN_<TAG>.md, updates.log,
  turns/turn_NN_in.md + turn_NN.stream.jsonl + turn_NN.stderr.txt, commands.log (every Bash command), work/ (WORKDIR).
Env: SN2_SA_MODEL (default claude-opus-5-5), SN2_SA_EFFORT (default xhigh; empty = omit), CLAUDE_BIN.
"""
import argparse
import ctypes
import glob
import json
import os
import re
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TOOLS))
STALL_S = 20 * 60
TAGS = ("PARTIAL", "QUESTION", "ANSWER")
TAG_RE = re.compile(r"^\s*[*_#>\s]*(PARTIAL|QUESTION|ANSWER)\b[*_]*\s*:?", re.IGNORECASE)


def env(k, default=""):
    return os.environ.get(k, default) or default


def fwd(p):
    return p.replace("\\", "/")


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ---------- small file helpers ----------
def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2)
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.1)
    os.replace(tmp, path)


def append(path, line):
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


def pid_alive(pid):
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


# ---------- conversation state ----------
class Conv:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        if not os.path.isfile(os.path.join(self.path, "meta.json")):
            sys.exit("static_analysis: not a conversation folder: " + path)

    def p(self, *a):
        return os.path.join(self.path, *a)

    @property
    def meta(self):
        return read_json(self.p("meta.json"), {})

    def save_meta(self, m):
        write_json(self.p("meta.json"), m)

    def running(self):
        r = read_json(self.p("running.json"))
        if r and pid_alive(r.get("runner_pid")):
            return r
        return None

    def inbox(self):
        try:
            return sorted(n for n in os.listdir(self.p("inbox")) if n.endswith(".md"))
        except OSError:
            return []

    def events(self):
        try:
            return sorted(n for n in os.listdir(self.p("updates")) if n.endswith(".md"))
        except OSError:
            return []

    def claim(self):
        """Become the runner. Atomic create of running.json; a stale file (dead runner) is removed first."""
        path = self.p("running.json")
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"runner_pid": os.getpid(), "claude_pid": None, "turn": None, "since": now()}, f)
                return True
            except FileExistsError:
                r = read_json(path, {})
                if r.get("runner_pid") and pid_alive(r["runner_pid"]):
                    return False
                if not r and time.time() - os.path.getmtime(path) < 5:
                    return False  # being written right now
                try:
                    os.remove(path)
                except OSError:
                    return False
        return False

    def release(self):
        try:
            os.remove(self.p("running.json"))
        except OSError:
            pass


# ---------- claude CLI ----------
def find_claude():
    c = env("CLAUDE_BIN")
    if c and os.path.isfile(c):
        return c
    for name in ("claude", "claude.exe"):
        for d in os.environ.get("PATH", "").split(os.pathsep):
            f = os.path.join(d, name)
            if os.path.isfile(f):
                return f
    home = os.path.expanduser("~")
    cands = glob.glob(os.path.join(home, ".vscode", "extensions", "anthropic.claude-code-*", "resources",
                                   "native-binary", "claude.exe"))
    if cands:
        return max(cands, key=os.path.getmtime)
    sys.exit("static_analysis: claude CLI not found; set CLAUDE_BIN in local.config")


def build_header(conv, m):
    paths = [("<GameDir>", env("SN2_GAME_DIR")), ("<SN1Dir>", env("SN1_GAME_DIR")),
             ("<ModkitDir>", env("SN2_MODKIT_DIR")), ("<Workspace>", env("SN2_WORKSPACE")), ("<RepoDir>", REPO)]
    lines = ["# Static analysis conversation", "",
             "Game(s): " + m["game"],
             "Date: " + time.strftime("%Y-%m-%d"),
             "WORKDIR (the only place you may write): " + fwd(conv.p("work")),
             "", "Placeholders used in research/ on this machine:"]
    lines += ["- %s = %s" % (k, fwd(v) if v else "(not set in local.config)") for k, v in paths]
    return "\n".join(lines) + "\n\n"


def git_status():
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, timeout=60)
        return set(out.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return set()


def run_turn(conv, messages):
    m = conv.meta
    n = len(m["turns"]) + 1
    first_event = len(conv.events()) + 1
    body = "\n\n".join("[Message from the investigator]\n" + t for t in messages)
    prompt = (build_header(conv, m) if n == 1 else "") + body
    with open(conv.p("turns", "turn_%02d_in.md" % n), "w", encoding="utf-8", newline="\n") as f:
        f.write(prompt)

    claude = find_claude()
    cmd = [claude, "-p", "--agent", "static-analyst", "--model", env("SN2_SA_MODEL", "claude-opus-5-5"),
           "--output-format", "stream-json", "--verbose",
           "--settings", conv.p("hook_settings.json"),
           "--allowedTools", "Read", "Grep", "Glob", "Bash",
           "--disallowedTools", "Edit", "Write", "NotebookEdit", "Agent", "Task", "WebFetch", "WebSearch"]
    effort = os.environ.get("SN2_SA_EFFORT", "xhigh")
    if effort:
        cmd += ["--effort", effort]
    dirs = [env("SN2_GAME_DIR"), env("SN1_GAME_DIR"), env("SN2_MODKIT_DIR"), env("SN2_WORKSPACE")]
    dirs = [d for d in dirs if d and os.path.isdir(d)]
    if dirs:
        cmd += ["--add-dir"] + dirs
    if m.get("session_id"):
        cmd += ["--resume", m["session_id"]]

    child_env = dict(os.environ)
    child_env.pop("CLAUDECODE", None)
    child_env["SN2_SA_CONV"] = conv.path
    before = git_status()
    started = time.time()
    rec = {"n": n, "started": now(), "first_event": first_event, "messages": len(messages)}
    m["turns"].append(rec)
    conv.save_meta(m)
    append(conv.p("updates.log"), "%s TURN %d START (%d message(s))" % (now(), n, len(messages)))

    stream = open(conv.p("turns", "turn_%02d.stream.jsonl" % n), "w", encoding="utf-8", newline="\n")
    errf = open(conv.p("turns", "turn_%02d.stderr.txt" % n), "w", encoding="utf-8", newline="\n")
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, cwd=REPO, env=child_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=errf, creationflags=flags)
    r = read_json(conv.p("running.json"), {})
    r.update({"claude_pid": proc.pid, "turn": n})
    write_json(conv.p("running.json"), r)
    proc.stdin.write(prompt.encode("utf-8"))
    proc.stdin.close()

    last_tag, result, session = None, None, m.get("session_id")
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        stream.write(line + "\n")
        stream.flush()
        touch(conv.p("last_activity"))
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("session_id"):
            session = ev["session_id"]
        t = ev.get("type")
        if t == "assistant":
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "text" and c.get("text", "").strip():
                    last_tag = write_event(conv, n, c["text"])
        elif t == "result":
            result = ev
    proc.wait()
    stream.close()
    errf.close()

    cancelled = os.path.exists(conv.p("cancel_requested"))
    changed = sorted(git_status() - before)
    m = conv.meta
    rec = m["turns"][-1]
    rec.update({
        "ended": now(), "seconds": round(time.time() - started, 1), "exit_code": proc.returncode,
        "end": "cancelled" if cancelled else (last_tag or "no_message") if proc.returncode == 0 else "error",
        "cost_usd": (result or {}).get("total_cost_usd"), "num_api_turns": (result or {}).get("num_turns"),
        "result_subtype": (result or {}).get("subtype"), "repo_changed_during_turn": changed})
    if session:
        m["session_id"] = session
    m["total_cost_usd"] = round(sum(t.get("cost_usd") or 0 for t in m["turns"]), 4)
    conv.save_meta(m)
    append(conv.p("updates.log"), "%s TURN %d END %s (%.0f s, $%s)" % (
        now(), n, rec["end"], rec["seconds"], rec["cost_usd"]))
    if changed:
        append(conv.p("updates.log"), "%s WARNING repo changed during turn %d (may be another session): %s" % (
            now(), n, "; ".join(changed)[:2000]))
        print("WARNING: repo changed during turn %d (may be another session): %s" % (n, "; ".join(changed)))
    return cancelled


def touch(path):
    with open(path, "w") as f:
        f.write(now())


def write_event(conv, turn, text):
    mt = TAG_RE.match(text)
    tag = mt.group(1).upper() if mt else "TEXT"
    k = len(conv.events()) + 1
    name = "%02d_%s.md" % (k, tag)
    with open(conv.p("updates", name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text.strip() + "\n")
    append(conv.p("updates.log"), "%s %02d %s turn=%d updates/%s" % (now(), k, tag, turn, name))
    return tag


# ---------- commands ----------
def cmd_new(a):
    if a.game not in ("sn1", "sn2", "both"):
        sys.exit("--game must be sn1, sn2 or both")
    ws = env("SN2_WORKSPACE")
    if not ws:
        sys.exit("SN2_WORKSPACE not set (run through static_analysis.sh)")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", a.slug or "conv")[:40]
    path = os.path.join(ws, "static_analysis", time.strftime("%Y%m%d_%H%M%S") + "_" + slug)
    for d in ("inbox", "updates", "turns", "work"):
        os.makedirs(os.path.join(path, d), exist_ok=True)
    hook = fwd(os.path.join(TOOLS, "static_analysis_hook.py"))
    settings = {"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": 'python -I "%s" pre' % hook}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": 'python -I "%s" post' % hook}]}]}}
    write_json(os.path.join(path, "hook_settings.json"), settings)
    write_json(os.path.join(path, "meta.json"), {"game": a.game, "created": now(), "session_id": None,
                                                 "ended": False, "turns": [], "total_cost_usd": 0})
    open(os.path.join(path, "updates.log"), "a").close()
    print(fwd(path))


def cmd_send(a):
    conv = Conv(a.conv)
    if conv.meta.get("ended"):
        sys.exit("static_analysis: conversation has ended")
    with open(a.message_file, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        sys.exit("static_analysis: empty message")
    name = "%s_%06d.md" % (time.strftime("%Y%m%d_%H%M%S"), int(time.time() * 1e6) % 1000000)
    tmp = conv.p("inbox", name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
    os.replace(tmp, conv.p("inbox", name))
    if not conv.claim():
        print("queued inbox/%s: a turn is running; the analyst gets it after its next tool call" % name)
        return
    print("running turn(s); watch with: static_analysis.sh watch " + fwd(conv.path))
    sys.stdout.flush()
    try:
        while True:
            names = conv.inbox()
            if not names:
                conv.release()
                if not conv.inbox() or not conv.claim():  # re-check: a send may have queued after our check
                    break
                continue
            texts = []
            os.makedirs(conv.p("inbox", "delivered"), exist_ok=True)
            for nm in names:
                with open(conv.p("inbox", nm), encoding="utf-8") as f:
                    texts.append(f.read().strip())
                os.replace(conv.p("inbox", nm), conv.p("inbox", "delivered", nm))
            if run_turn(conv, texts):
                try:
                    os.remove(conv.p("cancel_requested"))
                except OSError:
                    pass
                conv.release()
                print("turn cancelled; %d message(s) left in the inbox for the next send" % len(conv.inbox()))
                break
    finally:
        r = read_json(conv.p("running.json"), {})
        if r.get("runner_pid") == os.getpid():
            conv.release()
    m = conv.meta
    t = m["turns"][-1] if m["turns"] else {}
    print("idle: last turn %s ended %s; total cost $%s" % (t.get("n"), t.get("end"), m.get("total_cost_usd")))


def show_event(conv, name):
    with open(conv.p("updates", name), encoding="utf-8") as f:
        text = f.read().strip()
    print("== %s  (%s)" % (name[:-3], fwd(conv.p("updates", name))))
    if len(text) > 1500:
        text = text[:1500] + "\n[... truncated; read the file for the rest]"
    print(text)
    sys.stdout.flush()


def cmd_watch(a):
    conv = Conv(a.conv)
    m = conv.meta
    if a.from_ is not None:
        seen = a.from_ - 1
    else:
        seen = (m["turns"][-1]["first_event"] - 1) if m["turns"] and conv.running() else len(conv.events())
    t0, idle_polls, stalled = time.time(), 0, False
    while True:
        evs = conv.events()
        for nm in evs[seen:]:
            show_event(conv, nm)
        seen = max(seen, len(evs))
        r = conv.running()
        if r:
            idle_polls = 0
            try:
                quiet = time.time() - os.path.getmtime(conv.p("last_activity"))
            except OSError:
                quiet = 0
            if quiet > STALL_S and not stalled:
                print("STALLED: no output from the analyst for %d min (turn %s, claude pid %s). "
                      "Cancel with: static_analysis.sh cancel %s" % (quiet // 60, r.get("turn"), r.get("claude_pid"),
                                                                    fwd(conv.path)))
                sys.stdout.flush()
                stalled = True
            elif quiet <= STALL_S:
                stalled = False
        elif not conv.inbox() and time.time() - t0 > 20:
            idle_polls += 1
            if idle_polls >= 2:
                m = conv.meta
                t = m["turns"][-1] if m["turns"] else {}
                print("IDLE: turn %s ended %s; total cost $%s" % (t.get("n"), t.get("end"), m.get("total_cost_usd")))
                return
        time.sleep(3)


def cmd_cancel(a):
    conv = Conv(a.conv)
    r = conv.running()
    if not r or not r.get("claude_pid"):
        print("no turn running")
        return
    touch(conv.p("cancel_requested"))
    pid = r["claude_pid"]
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        os.kill(pid, 9)
    append(conv.p("updates.log"), "%s CANCEL turn %s (claude pid %s killed)" % (now(), r.get("turn"), pid))
    print("cancelled turn %s (claude pid %s)" % (r.get("turn"), pid))


def cmd_end(a):
    conv = Conv(a.conv)
    if conv.running():
        sys.exit("static_analysis: a turn is running; cancel it first")
    m = conv.meta
    m["ended"] = True
    m["ended_at"] = now()
    conv.save_meta(m)
    append(conv.p("updates.log"), "%s END of conversation" % now())
    print("ended; %d turn(s), total cost $%s" % (len(m["turns"]), m.get("total_cost_usd")))


def cmd_status(a):
    conv = Conv(a.conv)
    m = conv.meta
    r = conv.running()
    print("conversation: " + fwd(conv.path))
    print("state: %s" % ("ENDED" if m.get("ended") else "RUNNING turn %s (claude pid %s)" % (
        r.get("turn"), r.get("claude_pid")) if r else "IDLE"))
    try:
        print("last activity: " + open(conv.p("last_activity")).read().strip())
    except OSError:
        pass
    print("game: %s  session: %s  turns: %d  total cost: $%s" % (
        m.get("game"), m.get("session_id"), len(m["turns"]), m.get("total_cost_usd")))
    for t in m["turns"]:
        print("  turn %d: %s, %s s, $%s%s" % (t["n"], t.get("end", "running"), t.get("seconds"), t.get("cost_usd"),
                                             ", REPO CHANGED" if t.get("repo_changed_during_turn") else ""))
    print("messages from the analyst: %d   pending in inbox: %d" % (len(conv.events()), len(conv.inbox())))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new")
    p.add_argument("--game", required=True)
    p.add_argument("--slug")
    p.set_defaults(fn=cmd_new)
    p = sp.add_parser("send")
    p.add_argument("conv")
    p.add_argument("--message-file", required=True)
    p.set_defaults(fn=cmd_send)
    p = sp.add_parser("watch")
    p.add_argument("conv")
    p.add_argument("--from", dest="from_", type=int)
    p.set_defaults(fn=cmd_watch)
    for name, fn in (("cancel", cmd_cancel), ("end", cmd_end), ("status", cmd_status)):
        p = sp.add_parser(name)
        p.add_argument("conv")
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
