"""Compare the pure freestanding CPU function with already frozen proposals.

No evaluator, future-label scoring, timing, retune, model or native hook runs.
The DLL has no entry point, imports, runtime setup, or device dependencies.
"""
from pathlib import Path
import ctypes
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PREDICTIONS_SHA = 'be54505c785271d76f1808b27f72618df9f2a0b82e6730c0a7b2d37488157c62'
DECODED_SHA = '6e4036db6dc008c206badac7101c28fcf46cda90033f5a44723a00668751bd67'
TOKENIZER_SHA = '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'


def pin(path, expected=None):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert expected is None or digest == expected, str(path)
    return data, dict(path=str(path), bytes=len(data), sha256=digest)


def main():
    output_path = HERE / 'cpp-match.json'
    assert not output_path.exists(), 'Fresh-only result already exists'
    before = {}
    for name in ('longmatch64.h', 'longmatch64_cpu.cpp', 'longmatch64_cpu.obj', 'longmatch64_cpu.dll'):
        _, before[name] = pin(HERE / name)
    predictions, prediction_pin = pin(HERE / 'predictions.json', PREDICTIONS_SHA)
    decoded, decoded_pin = pin(ROOT / 'docs/research/halogen0173-selector-pilot-20261009/native-capture/decoded.json', DECODED_SHA)
    tokenizer, tokenizer_pin = pin(Path('C:/AI/models/halogen-flashnext/tokenizer/tokenizer.json'), TOKENIZER_SHA)
    rows, tokenizer = json.loads(decoded)['rows'], json.loads(tokenizer)
    allowed = set(tokenizer['model']['vocab'].values())
    special = set()
    for token in tokenizer.get('added_tokens', []):
        allowed.add(token['id'])
        if token.get('special'):
            special.add(token['id'])
    allowed -= special
    assert min(allowed) >= 0 and max(allowed) < 262144
    bitmap = (ctypes.c_uint8 * 32768)()
    for token in allowed:
        bitmap[token // 8] |= 1 << (token % 8)
    library = ctypes.CDLL(str(HERE / 'longmatch64_cpu.dll'))
    function = library.causal_pld64_predict
    function.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint32)]
    function.restype = ctypes.c_int
    cases = json.loads(predictions)
    for prediction in cases:
        row = rows[prediction['at']]
        assert row['wire_request_id'] == prediction['wire_request_id'] and row['round'] == prediction['round']
        suffix = (ctypes.c_int32 * len(row['context_suffix']))(*row['context_suffix'])
        stock = (ctypes.c_int32 * 3)(*prediction['stock'])
        ids, metadata = (ctypes.c_int32 * 3)(), (ctypes.c_uint32 * 4)()
        assert function(suffix, len(suffix), stock, bitmap, 262144, ids, metadata) == 0
        assert list(ids) == prediction['proposal'] and ids[0] == stock[0]
        expected = prediction['meta']
        assert list(metadata) == [int(expected['reason'] == 'longer_compatible_match'),
            expected.get('match', 0), expected.get('index', 0), expected['checks']]
    assert len(cases) == 96
    for name, original in before.items():
        _, current = pin(HERE / name)
        assert original == current
    result = dict(schema='causal-pld-longmatch64.cpp-prediction-match.v1', passed=True,
        frozen_cases=96, mismatches=0, unchanged_openings=96, width=3,
        matches_prediction_bytes_sha256=PREDICTIONS_SHA, artifacts=before,
        prediction_input=prediction_pin, decoded_input=decoded_pin, tokenizer_input=tokenizer_pin,
        future_evaluator_executions=0, timing_measured=False, sweeps_or_fit=0,
        pure_CPU_only=True, native_hook_installed=False, GPU_executed=False, NPU_executed=False,
        model_executed=False, serving_gain_claim=False)
    with output_path.open('x', encoding='utf-8', newline='\n') as target:
        target.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in
        ('artifacts', 'prediction_input', 'decoded_input', 'tokenizer_input')}, sort_keys=True))


if __name__ == '__main__':
    main()
