#!/usr/bin/env python3
"""Talk to a Subnautica 1 session the USER started (SN1Inspector command files). See research/sn1/README.md.

  python src/tools/sn1_live.py status
  python src/tools/sn1_live.py cmd <verb> [args...]          # any SN1Inspector verb, prints the reply
  python src/tools/sn1_live.py capture [name] [--biome B]   # HUD-less shot + pose + water settings, plus a matching SN2 autotest plan
  python src/tools/sn1_live.py waterbiomes [name]            # dump all biome water settings + loaded atmosphere volumes

Does NOT take the heavy lock and never launches or quits SN1: the user's own SN1 launch is the heavy job.
Refuses (exit 3) when Subnautica.exe is not running. Every reply wait has a timeout (--wait, default 30 s).
Outputs: capture -> repo samples/<biome>/<name>/SN1/{shot.png, info.json} + samples/<biome>/<name>/SN2/plan.json (autotest plan, views "fixed");
<biome> = SN1's biome at the camera unless --biome is given (procedure: samples/README.md). waterbiomes -> <Workspace>/sn1_shots/<name>.json.
SN1 -> SN2 mapping (map offset 0, research/sn1/world_files.md §3): UE.X = 100 z, UE.Y = 100 x, UE.Z = 100 y; UE yaw = Unity yaw (both clockwise from
above, 0 = Unity +z = UE +X); pitch + = up in both. The plan's "at" is the pawn position: the SN1 player position, not the camera.
"""
import datetime, json, os, shutil, subprocess, sys, time

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
IO = os.path.join(C["SN1_GAME_DIR"], "BepInEx", "SN1Inspector")
SHOTS = os.path.join(C["SN2_WORKSPACE"], "sn1_shots")   # waterbiomes dumps only
SAMPLES = os.path.join(REPO, "samples")


def jsave(p, obj):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")


def running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Subnautica.exe", "/NH"], capture_output=True, text=True).stdout
    return "Subnautica.exe" in out


def status():
    d = {}
    try:
        for line in open(os.path.join(IO, "status.txt"), encoding="utf-8"):
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                d[k] = v
    except OSError:
        pass
    return d


def send(text, wait=30):
    # ids must be unique per SN1 session (the mod ignores repeats), so use a time-based id
    cid = "L%d" % int(time.time() * 1000)
    tmp, dst = os.path.join(IO, "cmd.tmp"), os.path.join(IO, "cmd.txt")
    t0 = time.time()
    while os.path.exists(dst):
        if time.time() - t0 > 10:
            return "ERR cmd.txt not consumed within 10 s (is the game in a frozen/minimised state?)"
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


def wait_file(p, secs):
    t0 = time.time()
    last = -1
    while time.time() - t0 < secs:
        if os.path.exists(p):
            s = os.path.getsize(p)
            if s > 0 and s == last:
                return True
            last = s
        time.sleep(0.3)
    return False


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def sn2_plan(name, cam):
    px, py, pz = cam["player"]
    at = [round(100 * pz), round(100 * px), round(100 * py)]
    return {
        "name": "sn1cmp_" + name,
        "worldLevel": None,
        "start": "new",
        "waypoints": [{"name": name, "at": at, "views": "fixed", "yaw": round(wrap(cam["yaw"]), 2), "pitch": round(cam["pitch_up"], 2),
                       "fov": round(cam["fovH"], 2), "o2": True}],
        "settleSeconds": 15,
        "_sn1": {"player": cam["player"], "camera": cam["pos"], "biome": cam.get("biome"), "fovV": cam["fovV"], "screen": cam["screen"]},
    }


def main():
    a = sys.argv[1:]
    wait = 30
    if "--wait" in a:
        i = a.index("--wait"); wait = int(a[i + 1]); del a[i:i + 2]
    biome_arg = None
    if "--biome" in a:
        i = a.index("--biome"); biome_arg = a[i + 1]; del a[i:i + 2]
    if not a:
        print(__doc__); return 2
    if not running():
        print("REFUSED: Subnautica.exe is not running (start SN1 yourself; this tool only talks to a running session)"); return 3
    verb = a[0]
    if verb == "status":
        for k, v in status().items():
            print("%s=%s" % (k, v))
        return 0
    if status().get("state") != "ingame" and verb in ("capture", "waterbiomes"):
        print("REFUSED: SN1 state=%s, need ingame" % status().get("state")); return 4
    if verb == "cmd":
        r = send(" ".join(a[1:]), wait); print(r); return 0 if r.startswith("OK") else 1
    if verb == "waterbiomes":
        name = a[1] if len(a) > 1 else time.strftime("waterbiomes_%Y%m%d_%H%M%S")
        os.makedirs(SHOTS, exist_ok=True)
        out = os.path.join(SHOTS, name + ".json")
        r = send("waterbiomes " + out, wait); print(r); return 0 if r.startswith("OK") else 1
    if verb == "capture":
        name = a[1] if len(a) > 1 else time.strftime("shot_%Y%m%d_%H%M%S")
        tag = "cap_%d" % int(time.time())
        for ext in (".png", ".json"):
            try: os.remove(os.path.join(IO, tag + ext))
            except OSError: pass
        r = send("capture " + tag, wait)
        if not r.startswith("OK"):
            print(r); return 1
        png, js = os.path.join(IO, tag + ".png"), os.path.join(IO, tag + ".json")
        if not wait_file(png, wait):
            print("ERR screenshot not written within %d s: %s" % (wait, png)); return 1
        raw = json.load(open(js, encoding="utf-8"))
        cam = raw["camera"]
        biome = biome_arg or cam.get("biome") or "unknown"
        d = os.path.join(SAMPLES, biome, name)
        if os.path.exists(os.path.join(d, "SN1", "shot.png")):
            print("REFUSED: %s already has an SN1 shot (pick another name; SN1 shots are the fixed reference)" % d); return 5
        os.makedirs(os.path.join(d, "SN1"), exist_ok=True)
        os.makedirs(os.path.join(d, "SN2"), exist_ok=True)
        shutil.move(png, os.path.join(d, "SN1", "shot.png"))
        t = datetime.datetime.fromisoformat(raw["utc"].rstrip("Z")[:26]).replace(tzinfo=datetime.timezone.utc) if raw.get("utc") \
            else datetime.datetime.now(datetime.timezone.utc)
        info = {"game": "SN1", "shot": name, "biome": biome, "image": "shot.png",
                "capture_time_utc": t.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "capture_time_local": t.astimezone().isoformat(timespec="seconds"),
                "source": "src/tools/sn1_live.py capture (SN1Inspector)", "notes": ""}
        info.update({k: v for k, v in raw.items() if k not in info})
        jsave(os.path.join(d, "SN1", "info.json"), info)
        os.remove(js)
        plan = sn2_plan(name, cam)
        jsave(os.path.join(d, "SN2", "plan.json"), plan)
        wp = plan["waypoints"][0]
        print("OK %s  biome=%s depth=%.1f  SN1 player=(%.1f, %.1f, %.1f) yaw=%.1f pitch=%.1f fovH=%.1f" % (
            d, cam.get("biome"), cam.get("depth") or 0, *cam["player"], cam["yaw"], cam["pitch_up"], cam["fovH"]))
        print("   SN2 at=%s yaw=%s pitch=%s fov=%s" % (wp["at"], wp["yaw"], wp["pitch"], wp["fov"]))
        return 0
    print("unknown verb %s" % verb); return 2


if __name__ == "__main__":
    sys.exit(main())
