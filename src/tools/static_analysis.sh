#!/usr/bin/env bash
# Static analysis conversation with the static-analyst agent (investigator only; not a heavy job, no lock).
#   static_analysis.sh new --game sn1|sn2|both [--slug S]     -> prints the conversation folder
#   static_analysis.sh send <conv> --message-file F           (run_in_background: blocks while turns run)
#   static_analysis.sh watch <conv> [--from N]                (use with Monitor)
#   static_analysis.sh cancel|end|status <conv>
# Details: research/01_runbook.md "Static analysis".
. "$(dirname "$0")/sn2_env.sh"
args=()
for a in "$@"; do
  case "$a" in /*) command -v cygpath >/dev/null 2>&1 && a="$(cygpath -m "$a")" ;; esac
  args+=("$a")
done
exec python -u "$(dirname "$0")/static_analysis.py" "${args[@]}"
