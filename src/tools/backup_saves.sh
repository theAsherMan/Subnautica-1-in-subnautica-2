#!/usr/bin/env bash
# Copy the game's save folder to <SN2_WORKSPACE>/save_backups/<timestamp>/ before any risky test.
# Usage: bash src/tools/backup_saves.sh
# Test worlds are not backed up (user rule 2026-11-22): savegame_N.sav / savegame_N_*.bak of slots N marked test-made are skipped. Test-made = class TEST in
# <Workspace>/reports/sn2_save_classification.tsv, or a slot deleted by a run (<Workspace>/autotest/*/deleted_slots.txt, "deleted .../savegame_N...").
# User/UNSURE slots and all non-slot files are backed up as before.
set -euo pipefail
. "$(dirname "$0")/sn2_env.sh"
TS=$(date +%Y%m%d_%H%M%S)
DST="$SN2_WORKSPACE/save_backups/$TS"
mkdir -p "$DST"
cp -r "$SN2_SAVES_DIR/." "$DST/"
TEST_SLOTS=$( { awk -F'\t' '$7=="TEST"{print $1}' "$SN2_WORKSPACE/reports/sn2_save_classification.tsv" 2>/dev/null
                cat "$SN2_WORKSPACE"/autotest/*/deleted_slots.txt 2>/dev/null | sed -n 's#.* deleted .*/\(savegame_[0-9]*\(_[0-9]*\.bak\|\.sav\)\)$#\1#p'
              } | sed -n 's/^savegame_\([0-9]*\)\(_[0-9]*\.bak\|\.sav\)$/\1/p' | sort -u )
SKIPPED=0
for n in $TEST_SLOTS; do
  for f in "$DST/savegame_${n:?}.sav" "$DST"/savegame_"${n:?}"_*.bak; do
    [ -f "$f" ] && { rm -- "${f:?}"; SKIPPED=$((SKIPPED + 1)); }
  done
done
echo "saves backed up to $DST ($(du -sh "$DST" | cut -f1)); test-world files not kept in the backup: $SKIPPED"
