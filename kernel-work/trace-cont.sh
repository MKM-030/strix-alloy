#!/usr/bin/env bash
# Trace the sources of CONT and CPY in our model graph.
cd /home/revn/strix-llama
echo "=== ggml_cont / ggml_cont_2d / ggml_cont_3d call sites in the model ==="
grep -n 'ggml_cont' src/models/qwen4exp.cpp | head -40
echo
echo "=== count by file (src/) ==="
grep -rn 'ggml_cont' src/*.cpp src/models/*.cpp 2>/dev/null | awk -F: '{print $1}' | sort | uniq -c | sort -rn | head
echo
echo "=== ggml_transpose sites ==="
grep -n 'ggml_transpose' src/models/qwen4exp.cpp | head -20
echo
echo "=== explicit cpy sites ==="
grep -n 'ggml_cpy' src/models/qwen4exp.cpp | head -20
echo
echo "=== the MTP/nextn build (where contiguous happens for eh_proj) ==="
grep -n 'concat_flat\|reshape\|cont' src/models/qwen4exp.cpp | sed -n '1,40p'
