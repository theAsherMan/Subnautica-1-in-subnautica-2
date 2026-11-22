#!/usr/bin/env bash
# Launch Subnautica 2 with the project's start options. Steam must be running.
# Default option: -OverridePlayerStart=Shallows  = new games skip the intro and start with an empty hotbar (VERIFIED 2026-11-18, see research/09).
# Usage: bash src/tools/launch_game.sh [extra game args...]      e.g. SN2_START=Deep bash src/tools/launch_game.sh   (SN2_START=none -> no override)
# Why not steam://run/<id>//<args>/: Steam did not start the game from that URL (2026-11-18); starting the exe directly with SteamAppId set works.
. "$(dirname "$0")/sn2_env.sh"
# RAM: only one heavy job (game/editor/cook) at a time across parallel sessions -> src/tools/heavy_lock.sh. SN2_LOCK_WAIT=<s> waits for it (default: try once).
bash "$(dirname "$0")/heavy_lock.sh" acquire game --wait "${SN2_LOCK_WAIT:-0}" || { echo "NOT LAUNCHED: heavy lock busy (bash src/tools/heavy_lock.sh status)"; exit 4; }
# Steam client must be running: without it the game logs "Steam API failed to initialize" (Client API initialized 0), shows the
# "wasn't launched through the launcher" error and exits (FAILED 2026-11-22, research/01). Refuse instead of burning a launch.
if ! tasklist 2>/dev/null | grep -qi "^steam.exe"; then echo "NOT LAUNCHED: steam.exe is not running (start Steam and log in first)"; bash "$(dirname "$0")/heavy_lock.sh" release >/dev/null 2>&1; exit 6; fi
START="${SN2_START:-Shallows}"
ARGS="$*"
[ "$START" != "none" ] && ARGS="-OverridePlayerStart=$START $ARGS"
DIR="$SN2_GAME_DIR/Subnautica2/Binaries/Win64"
powershell -NoProfile -c "\$d=(Resolve-Path '$DIR').Path; \$env:SteamAppId='1962700'; \$env:SteamGameId='1962700'; Start-Process -FilePath \"\$d\Subnautica2-Win64-Shipping.exe\" -WorkingDirectory \$d $(if [ -n "$ARGS" ]; then printf %s "-ArgumentList '$ARGS'"; fi)"
echo "launched with: $ARGS"
