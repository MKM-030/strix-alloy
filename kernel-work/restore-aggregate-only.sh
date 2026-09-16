#!/usr/bin/env bash
# restore-aggregate-only.sh — bring back the aggregate op timer, remove the in-graph path.
#
# WHY: the aggregate recorder fires when !use_cuda_graph, which includes the EAGER WARMUP evals
# that happen with graphs ENABLED. Those evals run the production kernels, and cudaEventRecord
# works there (no capture active). That gives per-op GPU time in the production configuration.
# The in-graph (capture-time) path is the one that crashed / returned err=400, so it goes.
set -euo pipefail
cd /home/revn/strix-llama

echo "=== restore the diagnosed op-timing work from the stash ==="
git stash pop 2>&1 | tail -3
echo "op_timing refs: $(grep -c 'op_timing' ggml/src/ggml-cuda/ggml-cuda.cu)"

echo
echo "=== strip the in-graph record call (the dangerous path) ==="
python3 - <<'PY'
P = '/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu'
src = open(P, encoding='utf-8').read()

old = """                if (use_cuda_graph && cuda_graph_update_required && op_timing_ig::enabled()
                        && op_timing_ig::op_selected(node)) {
                    op_timing_ig::record(cuda_ctx->stream(), node);
                }"""
if src.count(old) == 1:
    src = src.replace(old, "                // in-graph (capture-time) op timing removed: hipEventElapsedTime returns 400 for\n"
                           "                // captured events on this ROCm/DXG build. Aggregate path only.\n")
    print('  in-graph record call: REMOVED')
else:
    # the diagnostic variant may still be present
    old2 = """                if (use_cuda_graph && cuda_graph_update_required) {
                    ++op_timing_ig::cap_nodes_seen;
                    if (op_timing_ig::cap_sample.size() < 200) {
                        op_timing_ig::cap_sample += std::string(ggml_op_name(node->op)) + ",";
                    }
                    if (op_timing_ig::enabled() && op_timing_ig::op_selected(node)) {
                        ++op_timing_ig::cap_matches;
                        op_timing_ig::record(cuda_ctx->stream(), node);
                    }
                }"""
    assert src.count(old2) == 1, f'neither variant found ({src.count(old2)})'
    src = src.replace(old2, "                // in-graph (capture-time) op timing removed: hipEventElapsedTime returns 400 for\n"
                            "                // captured events on this ROCm/DXG build. Aggregate path only.\n")
    print('  in-graph diagnostic block: REMOVED')

# disable the in-graph collect() so it cannot run at all
old3 = "    if (op_timing_ig::enabled() && !cuda_graph_update_required) {"
if src.count(old3) == 1:
    src = src.replace(old3, "    if (false && op_timing_ig::enabled() && !cuda_graph_update_required) {")
    print('  in-graph collect gate: DISABLED')
old4 = "        op_timing_ig::begin_capture_hook();"
if src.count(old4) == 1:
    src = src.replace(old4, "        if (false) op_timing_ig::begin_capture_hook();")
    print('  in-graph capture hook: DISABLED')

open(P, 'w', encoding='utf-8').write(src)
print('  remaining op_timing_ig call sites:',
      sum(src.count(s) for s in ('op_timing_ig::record(', 'op_timing_ig::collect()')))
PY

echo
echo "=== how the aggregate timer will be driven ==="
grep -n 'op_timing::record\|op_timing::flush' ggml/src/ggml-cuda/ggml-cuda.cu
