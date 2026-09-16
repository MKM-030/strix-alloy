#!/usr/bin/env bash
set -e
cd /home/revn/strix-llama
git add tools/hidden-dump tools/CMakeLists.txt
git -c user.name='kernel-work' -c user.email='kernel@local' commit -q -F - <<'MSG'
tools: add hidden-dump harness for MTP draft-head training data

Dumps the trunk nextn hidden (h_nextn) per token through the existing
llama_get_embeddings_nextn_ith staging API, so the training pairs use exactly
the tensor the draft head consumes at inference:
  input  = (h[k-1], tokens[k])
  target = tokens[k+1]
Read-only: no graph changes, no weights written, no product contact.
Windows-safe: heap corpus buffer (1 MiB stack array overflowed the 1 MiB
default stack reserve), output buffers sized to the window.
MSG
git log --oneline -3
