#!/usr/bin/env bash
# huntlauncher.sh — find any script/config in the fork (or nearby) exporting several LLAMA_ gates.
for root in /home/revn/strix-llama /home/revn /home/revn/projects /home/revn/src; do
  [ -d "$root" ] || continue
  echo "### $root"
  grep -rlE 'LLAMA_(MMB|QSA|HC_|NORM|GDN|PLE)' \
      --include='*.sh' --include='*.ps1' --include='*.md' --include='*.env' --include='*.txt' \
      --include='*.json' --include='*.yaml' --include='*.yml' \
      "$root" 2>/dev/null | grep -vE '/\.git/|/build-hip/|node_modules' | head -20
done
echo
echo "### any file with >=5 LLAMA_ gate exports under /home/revn"
grep -rlE 'LLAMA_(MMB|QSA|HC_BLK16|HC_GATEMIX|NORM_GATED|GDN_CONV|PLE_CONV)' /home/revn 2>/dev/null \
  | grep -vE '/\.git/|/build|node_modules' | while read -r f; do
    n=$(grep -cE 'LLAMA_[A-Z0-9_]+=' "$f" 2>/dev/null)
    [ "$n" -ge 5 ] && echo "$n  $f"
  done | sort -rn | head -10
