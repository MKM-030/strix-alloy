#!/usr/bin/env bash
# commit-fork.sh — commit the current fork work on win-native (script avoids cwd/quoting issues).
cd /home/revn/strix-llama || exit 1
echo "pwd=$(pwd) branch=$(git rev-parse --abbrev-ref HEAD)"
git add src/models/qwen4exp.cpp tools/server/server-context.cpp src/llama-lazy-reader.h
git -c user.name=revn -c user.email=revn@local commit -F - <<'MSG'
win-native: d2t draft-vocab trim + on-device speculative checkpoints

Two ports needed to make FR-Spec and MTP work on this branch:

- d2t/t2d draft-vocab trim in qwen4exp (loader + MTP graph): lets an MTP sidecar
  carry its head over a subset of the vocabulary (65k of 248320) and expand the
  logits back for verification. No-op when the tensor is absent.
- LLAMA_STATE_SEQ_FLAGS_ON_DEVICE on the six speculative checkpoint sites, so
  recurrent state snapshots stay on device instead of a host round-trip (PR 28118).

Measured: the on-device checkpoints are a no-op here (this branch already sets
n_rs_seq and QWEN4EXP supports rs_rollback, so it used the rollback path already);
the d2t path loads the converted FR-Spec head but faults in the logit expansion.
MSG
echo "--- result ---"
git log --oneline -2
git status --short | head -5
