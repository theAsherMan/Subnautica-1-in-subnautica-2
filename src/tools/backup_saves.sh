#!/usr/bin/env bash
# Copy the game's save folder to <SN2_WORKSPACE>/save_backups/<timestamp>/ before any risky test.
# Usage: bash src/tools/backup_saves.sh
set -euo pipefail
. "$(dirname "$0")/sn2_env.sh"
TS=$(date +%Y%m%d_%H%M%S)
DST="$SN2_WORKSPACE/save_backups/$TS"
mkdir -p "$DST"
cp -r "$SN2_SAVES_DIR/." "$DST/"
echo "saves backed up to $DST ($(du -sh "$DST" | cut -f1))"
