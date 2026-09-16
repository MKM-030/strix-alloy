#!/usr/bin/env bash
set -e
cd /home/revn/strix-llama
git add tools/server/server-context.cpp
git -c user.name='kernel-work' -c user.email='kernel@local' commit -q -F - <<'MSG'
server: add generation-gated decode phase timing

Measures two wall-clock phases around boundaries that already synchronize, so no
new GPU sync is introduced:
  tgt_decode   = llama_decode(ctx_tgt) + llama_synchronize at the sampling boundary
  spec_catchup = common_speculative_process

Both are gated on slot state == SLOT_STATE_GENERATING so the once-per-request
prefill decode does not pollute the per-request decode ledger. Printed alongside
the existing timings.

Measured result (PROJFIX, ub 2048, 8k, n-max 2): target verify ~80% of the
decode wall, draft ~16%, accept ~0.01%. Verification amortizes 45% across 3 rows
vs independent passes, but the marginal extra row costs 36.3 ms/token versus a
35.0 ms serial token -- which is why wider MTP does not pay here.
MSG
git log --oneline -3
