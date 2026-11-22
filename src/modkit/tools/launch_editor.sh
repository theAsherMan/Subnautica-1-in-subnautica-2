#!/usr/bin/env bash
# Open the modkit editor (via Launch-Editor.cmd) after taking the heavy lock (src/tools/heavy_lock.sh), so parallel sessions never run
# the editor next to the game or a cook. Sessions use this; the .cmd stays for double-clicking by hand (the lock still sees that editor
# as a running heavy process and makes other sessions wait).
# Usage: bash src/modkit/tools/launch_editor.sh [editor args...]      SN2_LOCK_WAIT=<s> waits for the lock (default: try once)
# When done: close the editor (python -I src/modkit/tools/ue_run.py -c "unreal.SystemLibrary.quit_editor()", UNTESTED), then
#            bash src/tools/heavy_lock.sh release
. "$(dirname "$0")/../../tools/sn2_env.sh"
bash "$SN2_REPO/src/tools/heavy_lock.sh" acquire editor --wait "${SN2_LOCK_WAIT:-0}" || { echo "NOT LAUNCHED: heavy lock busy (bash src/tools/heavy_lock.sh status)"; exit 4; }
if tasklist 2>/dev/null | grep -qi "^UnrealEditor.exe"; then echo "editor already open - not starting a second one"; exit 0; fi
CMDFILE="$(cygpath -w "$SN2_REPO/src/modkit/Launch-Editor.cmd")"
powershell -NoProfile -c "& '$CMDFILE' $*"
echo "editor starting (first load takes minutes); ue_run.py answers once it is up"
