"""Recover the first screen's proposals, without executing its evaluator.

Sources were saved retrospectively. The initial 96 proposals were frozen in
memory before evaluation. This run executes only the exact recovered predictor
and verifies its bytes against that original pre-evaluator hash. It creates
fresh files exclusively; there is no hardware, native runtime, or model import.
"""
from pathlib import Path
import ast
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
DECODED = ROOT / 'docs/research/halogen0173-selector-pilot-20261009/native-capture/decoded.json'
TOKENIZER = Path('C:/AI/models/halogen-flashnext/tokenizer/tokenizer.json')
DECODED_SHA = '6e4036db6dc008c206badac7101c28fcf46cda90033f5a44723a00668751bd67'
TOKENIZER_SHA = '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
PREDICTIONS_SHA = 'be54505c785271d76f1808b27f72618df9f2a0b82e6730c0a7b2d37488157c62'


def main():
    for name in ('predictions.json', 'proposal-recovery.json'):
        assert not (HERE / name).exists(), 'Fresh-only output exists: ' + name
    decoded_bytes, tokenizer_bytes = DECODED.read_bytes(), TOKENIZER.read_bytes()
    assert hashlib.sha256(decoded_bytes).hexdigest() == DECODED_SHA
    assert hashlib.sha256(tokenizer_bytes).hexdigest() == TOKENIZER_SHA
    decoded, tokenizer = json.loads(decoded_bytes), json.loads(tokenizer_bytes)
    defined = set(tokenizer['model']['vocab'].values())
    special = set()
    for token in tokenizer.get('added_tokens', []):
        defined.add(token['id'])
        if token.get('special'):
            special.add(token['id'])
    allowed = defined - special
    source_path = HERE / 'executed-inline-screen.py'
    source_bytes = source_path.read_bytes()
    tree = ast.parse(source_bytes)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'propose']
    assert len(functions) == 1
    # Execute only this function definition. No future-label function, top-level
    # screen loop, accepted-prefix comparison or evaluator runs in recovery.
    namespace = {'allowed': frozenset(allowed)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source_path), 'exec'), namespace)
    propose = namespace['propose']
    rows = decoded['rows']
    proposals = []
    for at, row in enumerate(rows):
        if row['source'] != 'pld':
            continue
        assert row['offer_total'] == row['stock_width'] == 3
        assert row['context_available'] and len(row['context_suffix']) == 64
        assert row['context_suffix'][-1] == row['current_id'] and row['native_allowance'] >= 3
        draft, metadata = propose(row['context_suffix'], row['offer_ids'])
        assert len(draft) == 3 and draft[0] == row['offer_ids'][0]
        proposals.append(dict(at=at, wire_request_id=row['wire_request_id'], round=row['round'],
            proposal=draft, stock=row['offer_ids'][:], changed=draft != row['offer_ids'], meta=metadata))
    assert len(proposals) == 96
    data = json.dumps(proposals, sort_keys=True, separators=(',', ':')).encode()
    assert len(data) == 16220 and hashlib.sha256(data).hexdigest() == PREDICTIONS_SHA
    receipt = dict(schema='causal-pld-longmatch64.proposal-recovery.v1', predictor_only=True,
        future_evaluator_executions=0, predictions=96, prediction_bytes=len(data),
        predictions_sha256=PREDICTIONS_SHA, decoded_sha256=DECODED_SHA,
        tokenizer_sha256=TOKENIZER_SHA, executed_source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        original_predictions_frozen_in_memory_before_evaluation=True,
        durable_archival_after_original_evaluation=True, source_saved_retrospectively=True,
        no_retune=True, hardware_executed=False, files_written_only_in_fresh_directory=True)
    with (HERE / 'predictions.json').open('xb') as target:
        target.write(data)
    with (HERE / 'proposal-recovery.json').open('x', encoding='utf-8', newline='\n') as target:
        target.write(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
