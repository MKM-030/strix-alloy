#!/usr/bin/env python3
"""Add round/width/yield accounting to the server's timing block (Codex priority 1).

From counters that already exist, per request, at INFO level (no trace needed):
  rounds                 = stats.n_draft_verif_steps
  width  (proposed/round) = stats.n_draft_tokens / rounds
  yield  (emitted/round)  = stats.n_gen / rounds
  target ms/round         = phase tgt_decode total / rounds
  target ms/emitted token = phase tgt_decode total / n_gen
  prefix survival         = n_accepted_per_pos[i] / rounds   (which draft positions survive)

This separates "round cost grows with depth" from "yield per round falls",
which is the distinction Codex asked for.
"""
P = '/home/revn/strix-llama/tools/server/server-context.cpp'
src = open(P, encoding='utf-8').read()

old = """            if (n_decode > 0) {
                SLT_INF(*this,
                        "phase: tgt_decode = %8.2f ms x%5d (%.1f%% of gen) | spec_catchup = %8.2f ms x%5d (%.1f%%)\\n",
                        (double) d_decode / 1000.0 / (double) n_decode, (int) n_decode,
                        100.0 * (double) d_decode / 1000.0 / t_gen_total,
                        (double) d_catchup / 1000.0 / (double) (n_catchup ? n_catchup : 1), (int) n_catchup,
                        100.0 * (double) d_catchup / 1000.0 / t_gen_total);
            }"""

new = """            if (n_decode > 0) {
                SLT_INF(*this,
                        "phase: tgt_decode = %8.2f ms x%5d (%.1f%% of gen) | spec_catchup = %8.2f ms x%5d (%.1f%%)\\n",
                        (double) d_decode / 1000.0 / (double) n_decode, (int) n_decode,
                        100.0 * (double) d_decode / 1000.0 / t_gen_total,
                        (double) d_catchup / 1000.0 / (double) (n_catchup ? n_catchup : 1), (int) n_catchup,
                        100.0 * (double) d_catchup / 1000.0 / t_gen_total);
            }

            // round / width / yield accounting: separates "round cost grew" from "yield fell".
            const int32_t rnd = (int32_t) stats.n_draft_verif_steps;
            if (rnd > 0) {
                const int32_t prop = (int32_t) stats.n_draft_tokens;
                const int32_t gen  = (int32_t) stats.n_gen;
                SLT_INF(*this,
                        "rounds: %5d | width(proposed/round) = %5.2f | yield(emitted/round) = %5.2f | "
                        "target_ms/round = %7.2f | target_ms/emitted_token = %7.3f\\n",
                        (int) rnd,
                        (double) prop / (double) rnd,
                        (double) gen  / (double) rnd,
                        (double) d_decode / 1000.0 / (double) rnd,
                        (double) d_decode / 1000.0 / (double) (gen > 0 ? gen : 1));

                std::string surv;
                for (size_t i = 0; i < n_accepted_per_pos.size(); ++i) {
                    if (i > 0) { surv += ", "; }
                    surv += string_format("%.3f", (double) n_accepted_per_pos[i] / (double) rnd);
                }
                if (!surv.empty()) {
                    SLT_INF(*this, "prefix survival per draft position: (%s)\\n", surv.c_str());
                }
            }"""
assert src.count(old) == 1, f'anchor count={src.count(old)}'
src = src.replace(old, new, 1)

open(P, 'w', encoding='utf-8').write(src)
print('patched OK')
print('  rounds line:', src.count('rounds: %5d | width'))
print('  prefix survival:', src.count('prefix survival per draft position'))
