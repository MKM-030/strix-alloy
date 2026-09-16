#!/usr/bin/env bash
# stop-all.sh
for pat in 'main-run[.]sh' 'final-suite[.]sh' 'projfix-opt[.]sh' 'sweep-ub[.]sh' 'ub16-suite[.]sh' 'lever-test[.]sh' 'hip-bench2[.]sh' 'rss[.]sh'; do
  for p in $(pgrep -f "$pat" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
done
for p in $(pgrep -x llama-server 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
sleep 5
for p in $(pgrep -x llama-server 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
sleep 2
echo "servers=$(pgrep -x llama-server 2>/dev/null | wc -l)"
free -g | head -2
