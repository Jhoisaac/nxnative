#!/bin/zsh
# sheet.sh <out.png> <shot…>: a contact sheet (2 columns of 640x360 tiles) so that one image read shows a whole route
S="${0:A:h}"; X="${TMPDIR:-/tmp}/dm_sheet"
[[ -x "$X" && "$X" -nt "$S/sheet.swift" ]] || swiftc -O -o "$X" "$S/sheet.swift" || exit 1
"$X" "$@" && echo "$1"
