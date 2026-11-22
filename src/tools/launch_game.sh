#!/usr/bin/env bash
# Launch Subnautica 2 the way the Steam "Play" button does: steam.exe -applaunch 1962700 <args>. Steam must be running.
# No gameplay args by default (new games start through the map's own start rules, research/09). Only display args are passed by autotest.sh
# (-windowed -ResX=1920 -ResY=1080 -WinX=0 -WinY=0).
# Usage: bash src/tools/launch_game.sh [extra game args...]
#   Opt-in start override for manual use only: SN2_START=<Tag> bash src/tools/launch_game.sh   (adds -OverridePlayerStart=<Tag>; unset/none = nothing added)
# History: steam://run/<id>//<args>/ did not start the game (2026-11-18); until 2026-11-22 the Shipping exe was started directly with SteamAppId set.
. "$(dirname "$0")/sn2_env.sh"
# RAM: only one heavy job (game/editor/cook) at a time across parallel sessions -> src/tools/heavy_lock.sh. SN2_LOCK_WAIT=<s> waits for it (default: try once).
bash "$(dirname "$0")/heavy_lock.sh" acquire game --wait "${SN2_LOCK_WAIT:-0}" || { echo "NOT LAUNCHED: heavy lock busy (bash src/tools/heavy_lock.sh status)"; exit 4; }
# Steam client must be running: without it the game logs "Steam API failed to initialize" (Client API initialized 0), shows the
# "wasn't launched through the launcher" error and exits (FAILED 2026-11-22, research/01). Refuse instead of burning a launch.
if ! tasklist 2>/dev/null | grep -qi "^steam.exe"; then echo "NOT LAUNCHED: steam.exe is not running (start Steam and log in first)"; bash "$(dirname "$0")/heavy_lock.sh" release >/dev/null 2>&1; exit 6; fi
# steam.exe path: registry HKCU\Software\Valve\Steam\SteamExe, else the path of the running steam.exe process
STEAMEXE=$(reg query 'HKCU\Software\Valve\Steam' //v SteamExe 2>/dev/null | tr -d '\r' | sed -n 's/^ *SteamExe *REG_SZ *//p')
if [ -z "$STEAMEXE" ] || ! [ -f "$(cygpath -u "$STEAMEXE" 2>/dev/null)" ]; then
  STEAMEXE=$(powershell -NoProfile -c "(Get-Process steam -ErrorAction SilentlyContinue | Select-Object -First 1).Path" | tr -d '\r')
fi
STEAMEXE_U=$(cygpath -u "$STEAMEXE" 2>/dev/null)
if [ -z "$STEAMEXE" ] || [ ! -f "$STEAMEXE_U" ]; then echo "NOT LAUNCHED: steam.exe path not found"; bash "$(dirname "$0")/heavy_lock.sh" release >/dev/null 2>&1; exit 6; fi
ARGS="$*"
case "${SN2_START:-none}" in none|"") ;; *) ARGS="-OverridePlayerStart=$SN2_START $ARGS";; esac
# shellcheck disable=SC2086
"$STEAMEXE_U" -applaunch 1962700 $ARGS
echo "launched via Steam (-applaunch 1962700) with: $ARGS"
