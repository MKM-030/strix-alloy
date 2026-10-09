"""Pinned graph and tokenization preparation; CPU only, no provider discovery."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'packages'))
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
import numpy as np
import onnx
import onnxruntime as ort
from tokenizers import Tokenizer

EXPECTED = '5d3e70fd0c9ff14b9b5169a51e957b7a9c74897afd0a35ce4bd318150c1d4d4a'
original = HERE / 'model/onnx/model.onnx'
assert hashlib.sha256(original.read_bytes()).hexdigest() == EXPECTED
fixed = HERE / 'model/minilm-b1-s256.onnx'

def freeze_graph():
    model = onnx.load(str(original))
    onnx.checker.check_model(model)
    inputs = {v.name: v for v in model.graph.input}
    assert set(inputs) == {'input_ids', 'attention_mask', 'token_type_ids'}
    assert all(v.type.tensor_type.elem_type == onnx.TensorProto.INT64 for v in inputs.values())
    original_shapes = {k: [d.dim_value or d.dim_param for d in v.type.tensor_type.shape.dim] for k, v in inputs.items()}
    for value in inputs.values():
        dims = value.type.tensor_type.shape.dim
        assert len(dims) == 2
        for dim, size in zip(dims, (1, 256)):
            dim.ClearField('dim_param')
            dim.dim_value = size
    output = model.graph.output[0]
    assert len(model.graph.output) == 1 and output.name == 'logits'
    assert len(output.type.tensor_type.shape.dim) == 2
    for dim, size in zip(output.type.tensor_type.shape.dim, (1, 1)):
        dim.ClearField('dim_param')
        dim.dim_value = size
    model = onnx.shape_inference.infer_shapes(model, strict_mode=True, data_prop=True)
    onnx.checker.check_model(model)
    onnx.save(model, str(fixed))
    return original_shapes

def tokenizer():
    value = Tokenizer.from_file(str(HERE / 'model/tokenizer.json'))
    assert value.token_to_id('[PAD]') == 0
    value.enable_truncation(max_length=256, strategy='only_second')
    value.enable_padding(length=256, pad_id=0, pad_type_id=0, pad_token='[PAD]')
    return value

def cpu_session(path):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])

def pair(tokenizer_value, query, passage):
    query_only = tokenizer_value.encode(query, add_special_tokens=False)
    if sum(query_only.attention_mask) > 64:
        raise ValueError('Query exceeds frozen 64-token bound')
    encoded = tokenizer_value.encode(query, passage)
    return {name: np.asarray([values], dtype=np.int64) for name, values in
            [('input_ids', encoded.ids), ('attention_mask', encoded.attention_mask), ('token_type_ids', encoded.type_ids)]}

def main():
    original_shapes = freeze_graph()
    t = tokenizer()
    feed = pair(t, 'Which planet is known as the Red Planet?', 'Mars, known for its reddish appearance, is often referred to as the Red Planet.')
    start = time.perf_counter()
    dynamic = cpu_session(original)
    frozen = cpu_session(fixed)
    load_seconds = time.perf_counter() - start
    a = dynamic.run(None, feed)[0]
    b = frozen.run(None, feed)[0]
    assert np.array_equal(a, b), 'Freezing input shapes changed CPU result'
    files = []
    for path in sorted((HERE / 'model').rglob('*')):
        if path.is_file() and '.cache' not in path.parts:
            files.append(dict(path=path.relative_to(HERE).as_posix(), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    receipt = dict(schema=1, model_id='cross-encoder/ms-marco-MiniLM-L6-v2',
        revision='233902d25c440f23af6f7d6e94d2946bac0bee0a', original_shapes=original_shapes,
        fixed_input_shape=[1,256], output_shape=[1,1], pair_layout='Tokenizer JSON postprocessor, only_second truncation, right pad to256',
        max_query_tokens=64, files=files, CPU_only=True, NPU_executed=False,
        providers=dynamic.get_providers(), original_vs_fixed_cpu_equal=True,
        reference_probe_logit=float(a[0,0]), session_load_seconds=load_seconds,
        versions=dict(onnx=onnx.__version__, ort=ort.__version__, numpy=np.__version__),
        native_prefill_decode_gain_established=False)
    (HERE / 'cpu-preparation.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('files','original_shapes')}))

if __name__ == '__main__':
    main()
