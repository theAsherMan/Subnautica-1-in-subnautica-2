#!/usr/bin/env python3
"""Subnautica 1 run driver (called by sn1_run.sh after lock + Steam checks). See research/11_sn1_modding.md.

  sn1_run.py --run-dir DIR --timeout S [--check S] [--script FILE] [--no-launch]

--no-launch: offline test of the backup / hashing / registry export / slot-cleanup logic with no game (a fake 'new slot' can be made
with SN1_FAKE_NEWSLOT=1 to exercise the delete path; it is only ever created and deleted by this tool).
Never uses the visible desktop; never edits SN1 saves or the registry.
"""
import argparse, hashlib, os, shutil, subprocess, sys, time, glob

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def cfg():
    d = {}
    for line in open(os.path.join(REPO, "local.config"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"')
    return d


C = cfg()
SN1 = C["SN1_GAME_DIR"]
WS = C["SN2_WORKSPACE"]
SAVES = os.path.join(SN1, "SNAppData", "SavedGames")
IO = os.path.join(SN1, "BepInEx", "SN1Inspector")
EXE = os.path.join(SN1, "Subnautica.exe")
REG_KEY = r"HKCU\Software\Unknown Worlds"
RUN = None
T0 = time.time()


def log(msg):
    line = "[sn1_run] %6.1f %s" % (time.time() - T0, msg)
    print(line, flush=True)
    if RUN:
        with open(os.path.join(RUN, "run.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def snapshot(root):
    """{relpath: (sha256, mtime, size)} for every file under root"""
    out = {}
    for dp, dn, fn in os.walk(root):
        for n in fn:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, root).replace("\\", "/")
            try:
                out[rel] = (sha(p), int(os.path.getmtime(p)), os.path.getsize(p))
            except OSError as e:
                out[rel] = ("ERR " + str(e), 0, 0)
    return out


def write_snapshot(snap, path):
    with open(path, "w", encoding="utf-8") as f:
        for k in sorted(snap):
            f.write("%s\t%s\t%d\t%d\n" % (k, snap[k][0], snap[k][1], snap[k][2]))


def slot_dirs():
    return sorted(n for n in os.listdir(SAVES) if os.path.isdir(os.path.join(SAVES, n))) if os.path.isdir(SAVES) else []


def proc_running(name="Subnautica.exe"):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return name.lower() in out.lower()


def reg_export(path):
    subprocess.run(["reg", "export", REG_KEY, path, "/y"], capture_output=True)


def reg_text(path):
    if not os.path.exists(path):
        return []
    raw = open(path, "rb").read()
    txt = raw.decode("utf-16", errors="replace") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", errors="replace")
    return [l for l in txt.replace("\r", "").split("\n")]


SM_PREFIXES = ("Screenmanager Resolution Width_h", "Screenmanager Resolution Height_h", "Screenmanager Fullscreen mode_h", "Screenmanager Resolution Use Native_h")
REG_GAME_KEY = REG_KEY + r"\Subnautica"


def reg_dwords(path):
    """{value name: int} of the 4 user display values in a .reg export (prefix match; the '... Default_h' values do not match)"""
    out = {}
    for l in reg_text(path):
        if l.startswith('"') and '"=dword:' in l:
            name, val = l[1:].split('"=dword:')
            if name.startswith(SM_PREFIXES):
                out[name] = int(val.strip(), 16)
    return out


def reg_restore_display(pre_reg, notes):
    """Write back changed Screenmanager display values (only those 4 names) from the pre-run export. Caller guarantees the game has exited."""
    want = reg_dwords(pre_reg)
    tmp = os.path.join(RUN, "reg_now.reg")
    reg_export(tmp)
    now = reg_dwords(tmp)
    lines = []
    for name, val in sorted(want.items()):
        if now.get(name) != val:
            r = subprocess.run(["reg", "add", REG_GAME_KEY, "/v", name, "/t", "REG_DWORD", "/d", str(val), "/f"], capture_output=True, text=True)
            lines.append("restored %s: %s -> %d (rc %d)" % (name, now.get(name), val, r.returncode))
    with open(os.path.join(RUN, "reg_restored.txt"), "w") as f:
        f.write("\n".join(lines) + "\n" if lines else "nothing to restore\n")
    for l in lines:
        log(l)
    notes.append("reg display values restored: %d (pre-run values tracked: %d)" % (len(lines), len(want)))
    for l in lines:
        notes.append("  " + l)


def hd(*args, timeout=60):
    return subprocess.run([sys.executable, "-u", os.path.join(HERE, "hidden_desktop.py")] + list(args), capture_output=True, text=True, timeout=timeout)


class Inspector:
    def __init__(self):
        self.n = 0

    def status(self):
        d = {}
        try:
            for line in open(os.path.join(IO, "status.txt"), encoding="utf-8"):
                if "=" in line:
                    k, v = line.rstrip("\n").split("=", 1)
                    d[k] = v
        except OSError:
            pass
        return d

    def send(self, text, wait=60):
        self.n += 1
        cid = "c%03d" % self.n
        tmp = os.path.join(IO, "cmd.tmp")
        dst = os.path.join(IO, "cmd.txt")
        t0 = time.time()
        while os.path.exists(dst) and time.time() - t0 < 10:
            time.sleep(0.1)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write("%s %s\n" % (cid, text))
        os.replace(tmp, dst)
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                for line in open(os.path.join(IO, "out.txt"), encoding="utf-8", errors="replace"):
                    if line.startswith(cid + " "):
                        return line.rstrip("\n")[len(cid) + 1:]
            except OSError:
                pass
            time.sleep(0.2)
        return "ERR no reply within %d s" % wait


def collect(tag=""):
    """copy BepInEx log, out.txt, status, Unity Player.log into the run folder"""
    for src, dst in ((os.path.join(SN1, "BepInEx", "LogOutput.log"), "LogOutput.log"), (os.path.join(IO, "out.txt"), "out.txt"),
                     (os.path.join(IO, "status.txt"), "status_last.txt"),
                     (os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "LocalLow", "Unknown Worlds", "Subnautica", "Player.log"), "Player.log")):
        try:
            shutil.copyfile(src, os.path.join(RUN, dst))
        except OSError:
            pass


def main():
    global RUN
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--timeout", type=int, required=True)
    ap.add_argument("--check", type=int, default=0)
    ap.add_argument("--script", default=os.path.join(HERE, "sn1_scripts", "default.sn1s"))
    ap.add_argument("--no-launch", action="store_true")
    a = ap.parse_args()
    RUN = a.run_dir
    os.makedirs(os.path.join(RUN, "shots"), exist_ok=True)
    result_path = os.path.join(RUN, "result.txt")
    verdict, notes = "FAIL_INTERNAL", []
    proc = None
    pid = None
    forced = False
    deleted = []
    try:
        # ---- backups ----------------------------------------------------------
        stamp = time.strftime("%Y%m%d_%H%M%S")
        bdir = os.path.join(WS, "save_backups", "sn1_" + stamp)
        if os.path.isdir(SAVES):
            shutil.copytree(SAVES, bdir)
        log("save backup -> %s" % bdir)
        pre = snapshot(SAVES) if os.path.isdir(SAVES) else {}
        write_snapshot(pre, os.path.join(RUN, "saves_pre.tsv"))
        pre_slots = slot_dirs()
        open(os.path.join(RUN, "slots_pre.txt"), "w").write("\n".join(pre_slots) + "\n")
        log("pre-launch slot dirs: %s" % pre_slots)
        reg_export(os.path.join(RUN, "reg_pre.reg"))
        run_start = time.time()
        # clean io folder of stale files so results are this run's
        os.makedirs(IO, exist_ok=True)
        for n in ("status.txt", "cmd.txt", "cmd.tmp", "out.txt"):
            try:
                os.remove(os.path.join(IO, n))
            except OSError:
                pass

        # ---- launch -----------------------------------------------------------
        if a.no_launch:
            log("--no-launch: skipping game launch")
            if os.environ.get("SN1_FAKE_NEWSLOT") == "1":
                time.sleep(1.2)
                fake = os.path.join(SAVES, "slot9999_faketest")
                os.makedirs(fake, exist_ok=True)
                open(os.path.join(fake, "x.bin"), "wb").write(b"fake")
                log("created fake slot %s (offline test only)" % fake)
            verdict = "DONE_OFFLINE"
        else:
            env = dict(os.environ, HD_APPID="264710")
            args = [sys.executable, "-u", os.path.join(HERE, "hidden_desktop.py"), "launch", EXE,
                    "-screen-fullscreen", "0", "-screen-width", "1280", "-screen-height", "720"]
            holder_log = open(os.path.join(RUN, "hidden_holder.log"), "w")
            proc = subprocess.Popen(args, stdout=holder_log, stderr=subprocess.STDOUT, env=env)
            for _ in range(120):
                time.sleep(0.5)
                try:
                    t = open(os.path.join(RUN, "hidden_holder.log")).read()
                except OSError:
                    t = ""
                if "pid " in t:
                    pid = int(t.split("pid ")[1].split()[0]); break
            if not pid:
                verdict = "FAIL_LAUNCH"; raise RuntimeError("holder never printed a pid")
            log("launched Subnautica.exe pid %d on hidden desktop SN2Test" % pid)
            verdict = run_script(a, pid, proc)
    except Exception as e:
        log("EXCEPTION %r" % (e,))
        notes.append("exception %r" % (e,))
        if verdict in ("FAIL_INTERNAL",):
            pass
    finally:
        # ---- stop -------------------------------------------------------------
        if pid:
            if not wait_exit(pid, 5):
                log("game still running at end of run: trying quit command, then WM_CLOSE, then FORCED_KILL of pid %d" % pid)
                try:
                    Inspector().send("quit", wait=5)
                except Exception:
                    pass
                if not wait_exit(pid, 30):
                    hd("close", str(pid)); log("WM_CLOSE posted")
                    if not wait_exit(pid, 30):
                        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
                        forced = True; log("FORCED_KILL pid %d" % pid)
                        wait_exit(pid, 15)
        if proc:
            try:
                proc.wait(timeout=20)
            except Exception:
                proc.kill()
        collect()
        # ---- post: hashes, registry, slot cleanup ------------------------------------
        post_ok = True
        try:
            gone = not proc_running()
            log("Subnautica.exe fully exited: %s" % gone)
            cleanup_slots(pre_slots, run_start, gone, deleted, notes)
            post = snapshot(SAVES) if os.path.isdir(SAVES) else {}
            write_snapshot(post, os.path.join(RUN, "saves_post.tsv"))
            bad = []
            for k, v in pre.items():
                if k not in post:
                    bad.append("MISSING " + k)
                elif post[k][0] != v[0]:
                    bad.append("CHANGED " + k)
            new = sorted(set(post) - set(pre))
            log("pre-existing save files: %d, changed/missing: %d, new files left: %d" % (len(pre), len(bad), len(new)))
            open(os.path.join(RUN, "save_compare.txt"), "w").write("pre-existing files changed or missing:\n" + "\n".join(bad) + "\nnew files after run:\n" + "\n".join(new) + "\n")
            if bad:
                post_ok = False
                notes.append("SAVE HASH MISMATCH: %s" % bad)
            if gone:
                reg_restore_display(os.path.join(RUN, "reg_pre.reg"), notes)
            else:
                notes.append("REG RESTORE SKIPPED: game still running")
            reg_export(os.path.join(RUN, "reg_post.reg"))
            ra, rb = reg_text(os.path.join(RUN, "reg_pre.reg")), reg_text(os.path.join(RUN, "reg_post.reg"))
            import difflib
            d = [l for l in difflib.unified_diff(ra, rb, "pre", "post", lineterm="", n=0)]
            open(os.path.join(RUN, "reg_diff.txt"), "w", encoding="utf-8").write("\n".join(d) + "\n")
            log("registry diff lines: %d (see reg_diff.txt)" % len(d))
            notes.append("registry diff lines: %d" % len(d))
            dd = [l for l in d if "Screenmanager" in l and l[:1] in "+-" and l[:3] not in ("+++", "---")]
            notes.append("reg diff after restore (Screenmanager lines): %d" % len(dd))
            # Steam Cloud: does a deleted slot come back?
            if deleted:
                time.sleep(30)
                back = [x for x in slot_dirs() if x not in pre_slots]
                log("30 s after deletion, new slot dirs present again: %s" % back)
                notes.append("slots back 30 s after deletion: %s" % back)
        except Exception as e:
            log("post-run exception %r" % (e,)); notes.append("post exception %r" % (e,)); post_ok = False
        if not post_ok and verdict.startswith("DONE"):
            verdict = "FAIL_SAVES"
        if forced:
            notes.append("FORCED_KILL")
        with open(result_path, "w") as f:
            f.write("%s\nrun time %d s\n%s\n" % (verdict, time.time() - T0, "\n".join(notes)))
        log("RESULT %s" % verdict)


def wait_exit(pid, secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
        if '"%d"' % pid not in out:
            return True
        time.sleep(1)
    return False


def cleanup_slots(pre_slots, run_start, exited, deleted, notes):
    cur = slot_dirs()
    new = [n for n in cur if n not in pre_slots]
    cand = []
    for n in new:
        p = os.path.join(SAVES, n)
        if os.path.getctime(p) >= run_start - 2:
            cand.append(n)
    log("slot cleanup: new dirs %s, created after run start %s" % (new, cand))
    if new and not exited:
        notes.append("CLEANUP SKIPPED: game still running; new slots left: %s" % new); log(notes[-1]); return
    if new != cand or len(cand) > 1:
        if new:
            notes.append("CLEANUP SKIPPED: ambiguous (new=%s created_after_start=%s); nothing deleted" % (new, cand)); log(notes[-1])
        return
    for n in cand:
        if n in pre_slots or n in ("slot0000", "slot0001", "options") or not n.startswith("slot"):
            notes.append("CLEANUP REFUSED for %s" % n); continue
        p = os.path.realpath(os.path.join(SAVES, n))
        if os.path.dirname(p) != os.path.realpath(SAVES):
            notes.append("CLEANUP REFUSED (path outside saves): %s" % p); continue
        shutil.rmtree(p)
        deleted.append(p)
        open(os.path.join(RUN, "deleted_slots.txt"), "a").write(p + "\n")
        log("DELETED test slot %s" % p)
        notes.append("deleted test slot: %s" % n)


def run_script(a, pid, proc):
    ins = Inspector()
    deadline = T0 + a.timeout
    next_check = T0 + a.check if a.check else None
    shots = os.path.join(RUN, "shots")
    shot_n = [0]

    def tick():
        nonlocal next_check
        if proc.poll() is not None or not wait_exit_nonblock(pid):
            return "EXITED"
        if time.time() > deadline:
            return "TIMEOUT"
        if next_check and time.time() >= next_check:
            next_check += a.check
            s = ins.status()
            shot_n[0] += 1
            r = hd("shot", os.path.join(shots, "check_%02d.png" % shot_n[0]), str(pid))
            log("CHECK state=%s scene=%s frame=%s fps=%s pos=%s hshot=%s" % (s.get("state"), s.get("scene"), s.get("frame"), s.get("fps"), s.get("pos"), (r.stdout.strip() or r.stderr.strip())[:80]))
            collect()
        return None

    def sleep_tick(sec):
        t0 = time.time()
        while time.time() - t0 < sec:
            r = tick()
            if r:
                return r
            time.sleep(0.5)
        return None

    # plugin up?
    t0 = time.time()
    while not os.path.exists(os.path.join(IO, "status.txt")):
        r = tick()
        if r:
            return "CRASH" if r == "EXITED" else r
        if time.time() - t0 > 180:
            log("status.txt never appeared within 180 s of launch"); return "FAIL_NOSTATUS"
        time.sleep(1)
    log("status.txt appeared after %d s" % (time.time() - t0))
    for line in open(a.script, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        verb, rest = parts[0], (parts[1] if len(parts) > 1 else "")
        if verb == "wait":
            w = rest.split(); state = w[0]; lim = int(w[1]) if len(w) > 1 else 300
            t0 = time.time()
            while ins.status().get("state") != state:
                r = tick()
                if r:
                    return "CRASH" if r == "EXITED" else r
                if time.time() - t0 > lim:
                    log("wait %s exceeded %d s (state=%s)" % (state, lim, ins.status().get("state")))
                    return {"menu": "FAIL_MENU", "ingame": "FAIL_NOPAWN"}.get(state, "FAIL_WAIT")
                time.sleep(0.5)
            log("wait %s satisfied after %d s" % (state, time.time() - t0))
        elif verb == "sleep":
            r = sleep_tick(float(rest))
            if r:
                return "CRASH" if r == "EXITED" else r
        elif verb == "nearpoll":
            # nearpoll <cap_s> <radius> [max]: repeat 'near' every 3 s until more than the player is found, or the cap passes
            w = rest.split(); lim = int(w[0]); t0 = time.time()
            while True:
                reply = ins.send("near " + " ".join(w[1:]))
                p = reply.split()
                n = int(p[1]) if len(p) > 1 and p[0] == "OK" and p[1].isdigit() else 0
                if n > 1 or time.time() - t0 > lim:
                    break
                r = sleep_tick(3)
                if r:
                    return "CRASH" if r == "EXITED" else r
            log("nearpoll after %d s -> %s" % (time.time() - t0, reply[:600]))
            with open(os.path.join(RUN, "cmd_replies.txt"), "a", encoding="utf-8") as f:
                f.write("near (poll) %s\n    %s\n" % (rest, reply))
        elif verb == "snap":
            shutil.copyfile(os.path.join(IO, "status.txt"), os.path.join(RUN, "status_%d.txt" % int(time.time() - T0)))
        elif verb == "hshot":
            r = hd("shot", os.path.join(shots, rest.strip()), str(pid)); log("hshot %s: %s" % (rest, (r.stdout.strip() or r.stderr.strip())[:100]))
        elif verb == "cmd":
            reply = ins.send(rest)
            log("cmd '%s' -> %s" % (rest, reply[:400]))
            with open(os.path.join(RUN, "cmd_replies.txt"), "a", encoding="utf-8") as f:
                f.write("%s\n    %s\n" % (rest, reply))
            if rest.startswith("shot"):
                fn = os.path.basename(rest.split()[1]) if len(rest.split()) > 1 else None
                if fn:
                    fn = fn if fn.lower().endswith(".png") else fn + ".png"
                    for _ in range(40):
                        if os.path.exists(os.path.join(IO, fn)):
                            time.sleep(0.5); shutil.copyfile(os.path.join(IO, fn), os.path.join(shots, fn)); log("copied shot " + fn); break
                        time.sleep(0.25)
            if rest.startswith("quit"):
                t0 = time.time()
                while wait_exit_nonblock(pid) and time.time() - t0 < 60:
                    time.sleep(1)
                if wait_exit_nonblock(pid):
                    log("process still alive 60 s after quit"); return "FAIL_QUIT"
                log("process exited %d s after quit" % (time.time() - t0))
                return "DONE"
            if reply.startswith("ERR"):
                log("command error, continuing")
        else:
            log("unknown script verb %s" % verb)
        r = tick()
        if r:
            return "CRASH" if r == "EXITED" else r
    return "DONE_NOQUIT"


def wait_exit_nonblock(pid):
    """True while the pid is alive"""
    out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return '"%d"' % pid in out


if __name__ == "__main__":
    sys.exit(main())
