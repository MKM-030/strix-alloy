#!/usr/bin/env python3
src = open('ggml/src/ggml-cuda/ggml-cuda.cu').read()
a1 = 'static void ggml_cuda_graph_evaluate_and_capture(ggml_backend_cuda_context & cuda_ctx'
print('a1 in src:', a1 in src)
import re
m = re.search(r'static void ggml_cuda_graph_evaluate_and_capture\(', src)
print('re found at', m.start() if m else None)
if m:
    print(repr(src[m.start():m.start() + 130]))
a2 = '                bool ok = ggml_cuda_compute_forward(*cuda_ctx, node);'
print('a2 in src:', a2 in src)
if a2 not in src:
    m2 = re.search(r'bool ok = ggml_cuda_compute_forward', src)
    print('a2 partial at', m2.start() if m2 else None)
    if m2:
        print(repr(src[m2.start() - 40:m2.start() + 60]))
a3 = '''        } else {
            graph_evaluated_or_captured = true; // ggml graph has been directly evaluated
        }
    }'''
print('a3 in src:', a3 in src)
