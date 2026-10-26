#!/bin/zsh
# ctl.sh <run folder> <DM_CTL line…>   one line for the running host ("A~0.3", "LUp+A~0.7", "passdump 1", "texdump <path with %d>", …)
# ctl.sh <run folder> snap <name>      screenshot of the next presented frame to shots/<name>.png; waits up to 20 s for it and prints the path
# The host reads the file every 100 ms and runs the lines in order; a press holds the reader for its hold time, so a later line waits for it.
R="${1:A}"; shift
[[ -f "$R/ctl.txt" ]] || { echo "not a run folder: $R" >&2; exit 2; }
if [[ "$1" == snap ]]; then
  f="$R/shots/$2.png"; rm -f "$f"; echo "shot $f" >> "$R/ctl.txt"
  for i in {1..100}; do [[ -s "$f" ]] && { sleep 0.2; echo "$f"; exit 0; }; sleep 0.2; done
  echo "no frame presented in 20 s ($f): the host stopped, is loading, or the game suspended itself out of focus" >&2; exit 1
fi
echo "$*" >> "$R/ctl.txt"
