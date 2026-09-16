#!/usr/bin/env bash
# killjobs.sh — stop sweep/server processes without matching this script's own name.
for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
for p in $(pgrep -f 'sweep-ub[.]sh'); do kill -9 "$p" 2>/dev/null; done
sleep 3
echo "remaining: $(pgrep -x llama-server | wc -l) server, $(pgrep -f 'sweep-ub[.]sh' | wc -l) sweep"
free -g | head -2
