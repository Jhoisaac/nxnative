#!/bin/zsh
# mkrun.sh <NSP folder>/<id>_build <run folder>
# Makes a test run folder for the Mac host: a copy of the user's run state (<id>_build/run: saves, pipeline archive, prewarm list; never the original)
# and run.sh, which starts the host on it with DM_CTL=<run folder>/ctl.txt. VER=v<n> picks the game version (default: the newest one with both patched_<ver> and extract/<ver>/RomFS).
set -e
[[ $# -eq 2 ]] || { echo "usage: mkrun.sh <NSP folder>/<id>_build <run folder>" >&2; exit 2; }
B="${1:A}"; R="${2:A}"; REPO="${0:A:h:h:h:h:h}"
ID="${B:t}"; ID="${ID%_build}"
[[ -d "$B/run" ]] || { echo "no run state in $B/run (start the game once with the NSP script's run command first)" >&2; exit 1; }
if [[ -z "$VER" ]]; then   # several versions: the one with the highest number
  VER=$(for p in "$B"/patched_v*(N); do v="${p:t}"; v="${v#patched_}"; [[ "$p" != *.key && -d "$B/extract/$v/RomFS" ]] && echo "${v#v} $v"; done | sort -n | tail -1 | cut -d' ' -f2)
fi
[[ -n "$VER" && -d "$B/patched_$VER" ]] || { echo "no patched_<ver> with extract/<ver>/RomFS in $B (set VER=v<n>)" >&2; exit 1; }
# The shader map the build was packed with: the build's own profile copy (a provisional or derived profile) when it has one, otherwise the repository's
SHMAP="$B/profile/$ID/shader_map.tsv"; [[ -f "$SHMAP" ]] || SHMAP="$REPO/dm/games/$ID/shader_map.tsv"
mkdir -p "$R/shots"
echo "$B" > "$R/.build"
"${0:A:h}/fresh.sh" "$R"
cat > "$R/run.sh" <<EOF
#!/bin/zsh
# run.sh [host] [log]: the Mac host on this folder's copy of the run state, driven by ctl.txt. WINDOW=1 opens a window (the game may suspend itself while the
# window is not focused), AUDIO=1 plays sound; both are off by default. exec: the host takes this script's PID, so kill reaches it.
cd "\${0:A:h}"
B="$B"
H="\${1:-\$B/tools/dmhost}"; L="\${2:-run.log}"
exec env DM_ROOT="\$B" DM_ROMFS="\$B/extract/$VER/RomFS" DM_SAVE="\$PWD/save" DM_TEMP="\$PWD/temp" DM_MSL_DIR="\$B/shader/cache" DM_FONT_DIR="\$B/font" \\
  DM_NVN_SHMAP="$SHMAP" DM_LANG="\${DM_LANG:-en-US}" DM_CTL="\$PWD/ctl.txt" \\
  \${WINDOW:+DM_WINDOW=1} \${AUDIO:+DM_AUDIO=1} "\$H" "\$B/patched_$VER" > "\$L" 2>&1
EOF
chmod +x "$R/run.sh"
[[ -n "$(ls "$B"/aoc(N) 2>/dev/null)" ]] && sed -i '' "s|DM_CTL=|DM_AOC_DIR=\"$B/aoc\" DM_CTL=|" "$R/run.sh"   # add-on content beside the game
echo "run folder $R: game $ID, version $VER, host $B/tools/dmhost, shader map $SHMAP"
