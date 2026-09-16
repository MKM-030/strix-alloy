#!/usr/bin/env bash
# diag.sh — inspect the no-draft test log and process state.
echo "=== no-draft log (grep) ==="
grep -aiE 'listening|d2t|t2d|vocab_out|ABORT|assert|error|failed' /tmp/nodraft.log 2>/dev/null | tail -8
echo "=== log lines: $(wc -l < /tmp/nodraft.log 2>/dev/null) ==="
echo "=== tail ==="
tail -4 /tmp/nodraft.log 2>/dev/null
echo "=== servers: $(pgrep -x llama-server | wc -l) ==="
