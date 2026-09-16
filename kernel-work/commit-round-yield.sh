#!/usr/bin/env bash
set -e
cd /home/revn/strix-llama
git add tools/server/server-context.cpp
git -c user.name='kernel-work' -c user.email='kernel@local' commit -q -m "server: add round / width / yield accounting to the timing block

Separates 'round cost grew with depth' from 'yield per round fell', which is the
distinction needed to decide where a decode optimisation would pay. All from counters
that already exist, printed at INFO level so no trace build is required:
rounds, width(proposed/round), yield(emitted/round), target_ms/round,
target_ms/emitted_token, and per-position prefix survival."
git log --oneline -1
git status --short | head -3
echo "(clean if empty)"
