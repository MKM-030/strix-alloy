#!/usr/bin/env bash
# nuke.sh — kill every bench-related process; verify GPU idle.
set +e
for pat in 'final-suite[.]sh' 'projfix-opt[.]sh' 'sweep-ub[.]sh' 'ub16-suite[.]sh' 'lever-test[.]sh' 'hip-bench2[.]sh'; do
  for p in $(pgrep -f "$pat"); do kill -9 "$p" 2>/dev/null; done
done
for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 6
# second pass (a suite may have relaunched a server between passes)
for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 3
echo "servers=$(pgrep -x llama-server | wc -l) suites=$(pgrep -f 'suite[.]sh|test[.]sh|opt[.]sh' | wc -l)"
free -g | head -2
