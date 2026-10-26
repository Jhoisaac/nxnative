#!/bin/zsh
# route.sh <run folder> <tag> <step…>: a fresh copy of the run state, the host started (DMHOST=<path> for another build, WINDOW=1 / AUDIO=1 as run.sh), the steps, then the host stopped.
# Steps:  f<N>      wait until the log reaches "frame N:" (the game is drawing)
#         w<sec>    wait
#         s<name>   screenshot to shots/<tag>_<name>.png
#         anything else is a DM_CTL line ("A~0.3", "LUp+A~0.7", "passdump 1"); after a press it waits for its hold (~) or 0.15 s
# Log: <run folder>/<tag>.log. Example: route.sh run b f1200 w20 A~0.3 w5 A~0.3 w20 s0 LUp~8 s1
R="${1:A}"; T="$2"; shift 2
S="${0:A:h}"; B="$(cat "$R/.build")"
"$S/fresh.sh" "$R"
"$R/run.sh" "${DMHOST:-$B/tools/dmhost}" "$R/$T.log" & P=$!
trap 'kill $P 2>/dev/null; wait $P 2>/dev/null' EXIT INT TERM
for k in "$@"; do
  kill -0 $P 2>/dev/null || { echo "the host exited (see $R/$T.log)" >&2; exit 1; }
  case "$k" in
    f<->) until grep -q "frame ${k#f}:" "$R/$T.log" 2>/dev/null; do kill -0 $P 2>/dev/null || { echo "the host exited (see $R/$T.log)" >&2; exit 1; }; sleep 0.5; done;;
    w*) sleep "${k#w}";;
    s*) "$S/ctl.sh" "$R" snap "${T}_${k#s}" >/dev/null;;
    *) "$S/ctl.sh" "$R" "$k"; [[ "$k" == *"~"* ]] && sleep "${k##*~}" || sleep 0.15;;
  esac
done
