#!/usr/bin/env python3
"""Fix the in-graph timer: op_selected() matches case-sensitively, but ggml_op_name()
returns UPPERCASE ("MUL_MAT_ID") while the filter tokens are lowercase ("mul_mat_id").
=> nothing ever matched, record_calls was always 0, and the timer reported 0.0 ms/replay.

Proven by the diagnostic: "OP_TIMING_IG DIAG: record_calls=0 collect_calls=3 segs=0".

Fix: lowercase both sides before comparing.
"""
P = '/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu'
src = open(P, encoding='utf-8').read()

old = """static bool op_selected(const ggml_tensor * node) {
    const char * f = getenv("LLAMA_OP_TIMING_OPS");
    std::string filters = f ? f : "mul_mat_id,ssm,gated_delta,flash_attn,get_rows,top_k,moe,softmax,rope";
    const std::string nm = std::string(ggml_op_name(node->op)) + " " + node->name;
    size_t start = 0;
    while (start <= filters.size()) {
        size_t comma = filters.find(',', start);
        std::string tok = filters.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
        if (!tok.empty() && nm.find(tok) != std::string::npos) {
            return true;
        }"""

new = """static bool op_selected(const ggml_tensor * node) {
    const char * f = getenv("LLAMA_OP_TIMING_OPS");
    // NOTE: ggml_op_name() returns UPPERCASE names ("MUL_MAT_ID") while the default
    // filter tokens are lowercase. Compare case-insensitively, or nothing ever matches
    // and the timer silently reports 0.0 ms/replay.
    std::string filters = f ? f : "mul_mat_id,ssm,gated_delta,flash_attn,get_rows,top_k,moe,softmax,rope";
    std::string nm = std::string(ggml_op_name(node->op)) + " " + node->name;
    auto lower = [](std::string & s) {
        std::transform(s.begin(), s.end(), s.begin(),
                       [](unsigned char c) { return (char) std::tolower(c); });
    };
    lower(nm);
    lower(filters);
    size_t start = 0;
    while (start <= filters.size()) {
        size_t comma = filters.find(',', start);
        std::string tok = filters.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
        if (!tok.empty() && nm.find(tok) != std::string::npos) {
            return true;
        }"""

assert src.count(old) == 1, f'anchor count={src.count(old)}'
src = src.replace(old, new)

# make sure the headers we now rely on are present
need = []
if '#include <algorithm>' not in src:
    need.append('#include <algorithm>')
if '#include <cctype>' not in src:
    need.append('#include <cctype>')
if need:
    anchor = '#include "ggml-common.h"\n'
    if anchor in src:
        src = src.replace(anchor, anchor + '\n'.join(need) + '\n', 1)
    else:
        # fall back: after the first include block
        idx = src.index('\n', src.index('#include'))
        src = src[:idx+1] + '\n'.join(need) + '\n' + src[idx+1:]

open(P, 'w', encoding='utf-8').write(src)
print('patched OK')
print('  "lower(nm)" present   :', src.count('lower(nm)'))
print('  case-insensitive note :', src.count('case-insensitively'))
print('  headers added         :', need if need else '(already present)')
