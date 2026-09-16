#!/usr/bin/env bash
# launcherblock.sh — print the author's flash-next wrapper + gate block verbatim.
F=/home/revn/pwilkin/install.sh
echo "=== lines 436-540 (generic wrapper + gates + flash-next exec) ==="
sed -n '436,540p' "$F"
