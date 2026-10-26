#!/bin/zsh
# fresh.sh <run folder>: replace the folder's run state with a new copy of the user's (<id>_build/run, without temp), so every run starts from the same saves
set -e
R="${1:A}"; B="$(cat "$R/.build")"
for f in "$B"/run/*(N); do [[ "${f:t}" == temp ]] && continue; rm -rf "$R/${f:t}"; cp -R "$f" "$R/"; done
rm -rf "$R/temp"; mkdir -p "$R/temp"; : > "$R/ctl.txt"
