#!/usr/bin/env bash
# reset-port.sh — kill all llama-server, wait, verify port 8114 free.
for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
for p in $(pgrep -f 'final-suite[.]sh'); do kill -9 "$p" 2>/dev/null; done
for p in $(pgrep -f 'projfix-opt[.]sh'); do kill -9 "$p" 2>/dev/null; done
for p in $(pgrep -f 'sweep-ub[.]sh'); do kill -9 "$p" 2>/dev/null; done
sleep 6
echo "servers running: $(pgrep -x llama-server | wc -l)"
if ss -tln 2>/dev/null | grep -q ':8114'; then
  echo "PORT 8114 STILL BOUND:"; ss -tlnp 2>/dev/null | grep ':8114'
else
  echo "port 8114 free"
fi
free -g | head -2
