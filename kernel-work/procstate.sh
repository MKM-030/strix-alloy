#!/usr/bin/env bash
# procstate.sh — is the loader alive or stuck?
r=$(pgrep -x llama-server | head -1)
if [ -z "$r" ]; then echo "no llama-server"; exit 0; fi
echo "pid=$r"
grep -E 'VmRSS|State' /proc/"$r"/status 2>/dev/null
echo "wchan: $(cat /proc/$r/wchan 2>/dev/null)"
echo "open fds: $(ls /proc/$r/fd 2>/dev/null | wc -l)"
echo "cpu ticks: $(awk '{print $14+$15}' /proc/$r/stat 2>/dev/null)"
sleep 20
echo "--- after 20s ---"
echo "cpu ticks: $(awk '{print $14+$15}' /proc/$r/stat 2>/dev/null)"
grep -E 'VmRSS' /proc/"$r"/status 2>/dev/null
free -g | head -2
