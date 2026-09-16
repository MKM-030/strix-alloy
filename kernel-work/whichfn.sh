#!/usr/bin/env bash
# whichfn.sh — which function contains a given line number?
cd /home/revn/strix-llama || exit 1
LINE="$1"
awk -v target="$LINE" '
  /^[A-Za-z_].*::.*\(/ || /^[A-Za-z_].*\(.*\)[ ]*\{?$/ { fn = NR ": " $0 }
  NR == target { print "enclosing: " fn; exit }
' src/models/qwen4exp.cpp
echo "--- function starts near ---"
grep -n 'graph_mtp' src/models/qwen4exp.cpp | head -6
