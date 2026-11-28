#!/usr/bin/env bash
# Run Subnautica 1 (BepInEx + SN1Inspector) on the hidden desktop and drive it with a script.
#   bash src/tools/sn1_run.sh --timeout <s> [--check <s>] [--script <file>] [--no-launch]
# Refusals: 8 no --timeout, 3 SN1 already running, 4 lock held by another session, 6 Steam not ready, 2 bad args.
# Needs the heavy lock (kind "sn1"), Steam running, SN1 not running. Run folder: <Workspace>/sn1_runs/<timestamp>/ (result.txt = verdict).
# Details: research/sn1/README.md
. "$(dirname "$0")/sn2_env.sh"
. "$(dirname "$0")/autotest_lib.sh"
TOOLS="$SN2_REPO/src/tools"
TO=""; CHECK=0; SCRIPT="$TOOLS/sn1_scripts/default.sn1s"; EXTRA=""
while [ $# -gt 0 ]; do case "$1" in
  --timeout) TO="$2"; shift 2 ;; --check) CHECK="$2"; shift 2 ;; --script) SCRIPT="$2"; shift 2 ;;
  --no-launch) EXTRA="--no-launch"; shift ;; *) echo "unknown arg $1"; exit 2 ;; esac; done
case "$TO" in ''|*[!0-9]*|0) echo "REFUSED: every test needs --timeout <seconds> (whole run, launch to exit)"; exit 8;; esac
[ -f "$SCRIPT" ] || { echo "REFUSED: script $SCRIPT not found"; exit 2; }
if tasklist 2>/dev/null | grep -qi "^Subnautica.exe"; then echo "REFUSED: Subnautica.exe is already running"; exit 3; fi
[ -f "$SN1_GAME_DIR/BepInEx/plugins/SN1Inspector/SN1Inspector.dll" ] || { [ -n "$EXTRA" ] || { echo "REFUSED: SN1Inspector not installed (bash src/tools/sn1_build_mod.sh SN1Inspector)"; exit 2; }; }
bash "$TOOLS/heavy_lock.sh" acquire sn1 --note "SN1 run" || { echo "REFUSED: heavy lock held by another session"; exit 4; }
trap 'bash "$TOOLS/heavy_lock.sh" release' EXIT
if [ -z "$EXTRA" ]; then ensure_steam "${SN2_STEAM_WAIT:-90}" || exit 6; fi
RUN="$SN2_WORKSPACE/sn1_runs/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN"
echo "run folder: $RUN  timeout ${TO}s check ${CHECK}s script $SCRIPT"
# overall timeout: python enforces the script deadline; this wrapper adds a hard stop margin
python -u "$TOOLS/sn1_run.py" --run-dir "$(cygpath -w "$RUN")" --timeout "$TO" --check "$CHECK" --script "$(cygpath -w "$SCRIPT")" $EXTRA
RC=$?
echo "RESULT: $(head -1 "$RUN/result.txt" 2>/dev/null)"
exit $RC
