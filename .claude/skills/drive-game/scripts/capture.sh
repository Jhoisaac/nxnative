#!/bin/zsh
# capture.sh <run folder> <name>: while the host runs with DM_CTL=<run folder>/ctl.txt (run.sh, route.sh, or the user's own run command with DM_CTL added),
# save the evidence of what is on screen now: shots/<name>.png, the render passes of one frame (DM_NVN_PASSDUMP lines, "[pass] F<frame> …", into the host's log)
# and that frame's colour targets as PNGs in tex_<name>/. For a visual defect: one capture where it shows, one where it does not (or from a good build), then compare.
R="${1:A}"; N="$2"; S="${0:A:h}"
[[ -n "$N" ]] || { echo "usage: capture.sh <run folder> <name>" >&2; exit 2; }
mkdir -p "$R/tex_$N"
"$S/ctl.sh" "$R" snap "$N" || exit 1
"$S/ctl.sh" "$R" passdump 1; sleep 1
"$S/ctl.sh" "$R" texdump "$R/tex_$N/t%d.png"; sleep 2
echo "passes: grep '^\[pass\]' in the host's log (the last frame dumped); colour targets: $(ls "$R/tex_$N" | wc -l | tr -d ' ') files in $R/tex_$N"
