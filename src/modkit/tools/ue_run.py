"""Run Python inside the open Unreal editor via the Python plugin's Remote Execution (localhost only).
Editor side (once): Project Settings > Plugins > Python > "Enable Remote Execution?" = on.
Usage (from the repo root):
  python -I src/modkit/tools/ue_run.py <script.py>        runs the file in the editor
  python -I src/modkit/tools/ue_run.py -c "<statement>"   runs one statement, prints its result
Prints the editor's output (print / unreal.log lines); exit 1 on failure, 2 if no editor answers.
The client module (remote_execution.py) is Epic's and is loaded from the engine named in local.config (SN2_MODKIT_DIR), not shipped here.
"""
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


def load_config():
    cfg = {}
    path = os.path.join(REPO, "local.config")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"')
    cfg.update({k: v for k, v in os.environ.items() if k.startswith("SN2_")})
    return cfg


def engine_python_dir(cfg):
    modkit = cfg.get("SN2_MODKIT_DIR")
    if not modkit:
        sys.exit("SN2_MODKIT_DIR not set - copy local.config.example to local.config")
    engine = cfg.get("SN2_ENGINE_DIR", os.path.join(modkit, "UE_5.6_SN2"))
    return os.path.join(engine, "Engine", "Plugins", "Experimental", "PythonScriptPlugin", "Content", "Python")


def main():
    sys.path.insert(0, engine_python_dir(load_config()))
    import remote_execution as rx  # noqa: E402  (Epic's client, from the engine)

    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "-c":
        cmd, mode = sys.argv[2], rx.MODE_EXEC_STATEMENT
    else:
        cmd, mode = os.path.abspath(sys.argv[1]).replace("\\", "/"), rx.MODE_EXEC_FILE
    r = rx.RemoteExecution()
    r.start()
    try:
        t0 = time.time()
        while not r.remote_nodes and time.time() - t0 < 8:
            time.sleep(0.2)
        if not r.remote_nodes:
            print("NO EDITOR FOUND (is the editor open with Remote Execution enabled?)")
            return 2
        node = r.remote_nodes[0]
        print("editor node:", node.get("project_name"), node.get("engine_version"))
        r.open_command_connection(node["node_id"])
        res = r.run_command(cmd, unattended=True, exec_mode=mode)
        for o in res.get("output", []):
            print(f"[{o.get('type')}] {o.get('output')}".rstrip())
        print("result:", res.get("result"), "| success:", res.get("success"))
        return 0 if res.get("success") else 1
    finally:
        r.stop()


if __name__ == "__main__":
    sys.exit(main())
