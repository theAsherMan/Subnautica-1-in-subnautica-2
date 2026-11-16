#!/usr/bin/env bash
# Source this from the other tools:  . "$(dirname "$0")/sn2_env.sh"
# Loads <repo>/local.config (see local.config.example) and derives the common paths. Environment variables override the file.
SN2_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CFG="$SN2_REPO/local.config"
if [ -f "$CFG" ]; then
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue ;; esac
    v="${v%$'\r'}"; v="${v#\"}"; v="${v%\"}"
    [ -z "${!k:-}" ] && export "$k=$v"
  done < "$CFG"
else
  echo "sn2_env: $CFG not found - copy local.config.example to local.config and edit it" >&2
fi
: "${SN2_GAME_DIR:?set SN2_GAME_DIR in local.config}"
: "${SN2_WORKSPACE:?set SN2_WORKSPACE in local.config}"
export SN2_REPO
export SN2_UE4SS_DIR="$SN2_GAME_DIR/Subnautica2/Binaries/Win64/ue4ss"
export SN2_SAVES_DIR="${LOCALAPPDATA:-$HOME/AppData/Local}/Subnautica2/Saved/SaveGames"
