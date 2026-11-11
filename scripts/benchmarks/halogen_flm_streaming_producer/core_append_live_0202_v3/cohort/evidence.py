"""Current-request HDO2 evidence only; no recorded future IDs or oracle input."""
import hashlib
import json
from pathlib import Path
import re
import struct

STATS = ('queries','lock_busy','datagrams','rejected_datagrams','recv_errors','begins',
    'authorities','readies','retirements','sequence_failures','stale_readies','prefix_misses',
    'current_misses','already_consumed','hits','proposed_ids','native_fallbacks')
PREFIX = 'db50995e2fb9f8eff514405041f9f9b2511acd09b013591d30971d0b14f1242b'


def need(ok, why):
    if not ok: raise ValueError(why)


def read(path): return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(); data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def save_new(path, value, raw=False):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    data = value if raw else (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()
    with path.open('xb') as stream: stream.write(data)


def stats(runtime, active):
    # Only the already-owned container is read. No model/API request is sent.
    code = "import json,struct;f=open('/tmp/hgn0202-stream-stats.bin','rb');b=f.read(136);f.close();assert len(b)==136;print(json.dumps(list(struct.unpack('<17Q',b))))"
    values = json.loads(runtime.ops.docker('exec', active['inner']['container_id'], 'python3', '-c', code))
    need(type(values) is list and len(values) == 17 and all(type(x) is int and x >= 0 for x in values),
         'Complete unsigned136-byte HDO2 statistics required')
    return dict(zip(STATS, values))


def delta(before, after):
    need(set(before) == set(after) == set(STATS), 'HDO2 statistics fields differ')
    result = {key:after[key]-before[key] for key in STATS}
    need(all(type(x) is int and x >= 0 for x in result.values()), 'HDO2 counters regressed')
    return result


def capture(raw_dir, folder, ordinal, sample, *, candidate):
    request = sample['native_request_id']
    paths = list((Path(raw_dir)/'token-ids').glob('request-'+str(request)+'-*.json'))
    need(len(paths) == 1, 'Current native-T completion record missing or ambiguous')
    path = paths[0]
    need(not any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)), 'Linked native-T capture')
    value = read(path); begin = value.get('begin',{}); terminal = value.get('terminal',{})
    epoch = value.get('request_epoch'); ids = value.get('token_ids')
    need(value.get('schema') == 'halogen0202.streaming-native-ID-observer.v1'
         and value.get('api_sha256') == '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'
         and value.get('native_request_id') == begin.get('request_id') == terminal.get('request_id') == request
         and type(epoch) is str and re.fullmatch('[0-9a-f]{32}',epoch)
         and begin.get('request_epoch') == terminal.get('request_epoch') == epoch
         and begin.get('source') == terminal.get('source') == 'native_T'
         and begin.get('engine_sha256') == 'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c'
         and begin.get('tokenizer_sha256') == '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
         and begin.get('prefix_count') == sample['actual_input_tokens'] == 8192
         and begin.get('prefix_sha256') == PREFIX and begin.get('generated_count') == 0
         and terminal.get('kind') == 'done' and terminal.get('complete_native_stream') is True
         and terminal.get('generated_count') == sample['actual_output_tokens'] == 128
         and terminal.get('prefix_count') == 8320 and terminal.get('reason') == sample['finish_reason']
         and value.get('observer_error') is None and (not candidate or value.get('sidecar_retired') is False)
         and type(ids) is list and len(ids) == 128
         and all(type(t) is int and 0 <= t < 248077 for t in ids), 'Actual native-T authority does not reconcile')
    response = read(Path(folder)/('response-'+str(ordinal)+'.json')); choice = response['choices'][0]
    need(response['timings']['raw_native_request_id'] == request
         and response['usage']['prompt_tokens'] == 8192 and response['usage']['completion_tokens'] == 128
         and hashlib.sha256(choice['text'].encode()).hexdigest() == sample['output_sha256']
         and choice['finish_reason'] == sample['finish_reason'], 'Exact output/RAW/native-T response identity differs')
    target = Path(folder)/'token-ids'/path.name; save_new(target,path.read_bytes(),raw=True)
    result = dict(native_request_id=request, request_epoch=epoch, token_ids=ids,
        token_ID_sha256=hashlib.sha256(struct.pack('<128i',*ids)).hexdigest(),
        output_sha256=sample['output_sha256'], finish_reason=sample['finish_reason'],
        actual_input_tokens=8192, actual_output_tokens=128, capture=pin(target))
    save_new(Path(folder)/('token-sample-'+str(ordinal)+'.json'),result)
    return result


def require_parity(reference, current):
    need(all(reference[key] == current[key] for key in ('token_ids','token_ID_sha256',
         'output_sha256','finish_reason','actual_input_tokens','actual_output_tokens')),
         'Current exact native-T/output parity differs from BEFORE warmup')


def require_warmup(delta_values):
    need(all(delta_values[key] > 0 for key in ('queries','readies','hits','proposed_ids')),
         'Excluded candidate warmup has zero actual NPU READY/native hits/proposals; stop without headline')
