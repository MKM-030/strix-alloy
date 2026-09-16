#!/usr/bin/env bash
# rss.sh — print llama-server RSS (GiB) and time, 8 samples 20s apart.
for i in $(seq 1 8); do
  r=$(pgrep -x llama-server | head -1)
  if [ -z "$r" ]; then echo "$(date +%T) no server"; else
    echo "$(date +%T) rss=$(awk '/VmRSS/{printf "%.2f", $2/1048576}' /proc/$r/status 2>/dev/null) GiB"
  fi
  sleep 20
done
