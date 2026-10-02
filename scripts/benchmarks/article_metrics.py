"""Pure benchmark accounting; no inference or model state."""
import hashlib,json,math,re
from pathlib import Path

def checked_profile_hash(state, profile_path):
    actual = hashlib.sha256(Path(profile_path).read_bytes()).hexdigest()
    if state.get('profile_sha256') != actual:
        raise ValueError('Managed run does not match the selected profile bytes')
    return actual

def normalized_seconds(ttft,decode_tps):
    if not all(math.isfinite(x) for x in (ttft,decode_tps)) or ttft<0 or decode_tps<=0:
        raise ValueError('Valid first-token time and positive decode rate required')
    return ttft+1000/decode_tps

def acceptance(rows):
    if any(r.get('drafted') is None or r.get('accepted') is None for r in rows):return None
    total=sum(r['drafted'] for r in rows); kept=sum(r['accepted'] for r in rows)
    if total<=0:return None
    if not 0<=kept<=total:raise ValueError('Invalid draft accounting')
    return kept/total

def score_retrieval(text,expected):
    # Parse a JSON object, never search reasoning text or merely substrings.
    obj={}; decoder=json.JSONDecoder()
    for match in re.finditer(r'\{',text):
        try:
            value,_=decoder.raw_decode(text[match.start():])
            if isinstance(value,dict):obj=value;break
        except ValueError:pass
    missing=[key for key,value in expected.items() if obj.get(key)!=value]
    return {'correct':len(expected)-len(missing),'total':len(expected),'missing':missing}

def phase_rates(timings,ratio=1.0):
    if not math.isfinite(ratio) or ratio<=0:raise ValueError('Invalid clock ratio')
    return {'pp':float(timings['prompt_per_second'])*ratio,'decode':float(timings['predicted_per_second'])*ratio}

def validate_backend(label,actual_model):
    models={'gufo':'gufo-flash-next','projfix':'projfix-flash-next',
            'halogen-v2':'halogen-v2','halogen-w4b':'halogen-w4b'}
    if label not in models or actual_model!=models[label]:
        raise ValueError('Active engine does not match the benchmark label')
    return actual_model

def validate_geometry(context,fill,reps,output_limit):
    if not 4096<=context<=262144 or not 512<=fill<context:
        raise ValueError('Context/input sizes are outside the supported benchmark range')
    if not 1<=reps<=5 or not 16<=output_limit<=4096:
        raise ValueError('Use 1..5 repetitions and an output cap of 16..4096')
    if fill+3*output_limit+256>context:
        raise ValueError('Leave room for three outputs and follow-up instructions')


def backend_validation_finished(label,context,state):
    """The engine API may listen before its owning Halogen guard finishes tests."""
    if label in ('gufo','projfix'):return True
    if label not in ('halogen-v2','halogen-w4b'):
        raise ValueError('Unknown benchmark backend')
    if not isinstance(state,dict):return False
    if state.get('checkpoint')!=label.removeprefix('halogen-') or state.get('context')!=context:
        raise ValueError('Backend validation state belongs to a different configuration')
    if state.get('phase') in ('failed','stopped'):
        raise ValueError('Halogen validation terminated before measurement')
    return state.get('phase')=='ready'


def cell_name(backend,context,fill,tag=''):
    if tag and not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',tag):
        raise ValueError('Use a short alphanumeric run tag, not a path')
    return f'{backend}-c{context}-p{fill}'+('-'+tag if tag else '')


def benchmark_input_sizes(values, capacity):
    """Cold benchmark lengths; reserve space for 128 actual generated tokens."""
    if type(capacity) is not int or not values:
        raise ValueError('Invalid benchmark capacity or empty size list')
    if any(type(v) is not int or v not in (512,2048,8192,16384,32768) or v+128>capacity for v in values):
        raise ValueError('Unsupported benchmark length or insufficient output room')
    if len(set(values))!=len(values): raise ValueError('Repeated benchmark sizes')
    return tuple(values)


async def calibrated_prompt(prompt, target, measure):
    """Pad an immutable input by observation; never assume a tokenizer's split."""
    observed = await measure(prompt)
    if observed == target:
        return prompt
    if type(observed) is not int or observed > target or observed < 0:
        raise ValueError('Source prompt exceeds the target or returned invalid usage')
    def padded(count):
        return ' a'*count + prompt
    lower, upper = 0, max(1, target-observed)
    for _ in range(8):
        count = await measure(padded(upper))
        if type(count) is not int or count < observed:
            raise ValueError('Invalid calibration token count')
        if count >= target:
            break
        lower, upper = upper, upper*2
    else:
        raise ValueError('Cannot bracket exact input length')
    if count == target:
        return padded(upper)
    while upper-lower > 1:
        middle = (lower+upper)//2
        count = await measure(padded(middle))
        if count == target:
            return padded(middle)
        if count < target:
            lower = middle
        else:
            upper = middle
    raise ValueError('Cannot calibrate exact input length; no observed token count matches')


def memory_snapshot(state):
    """Controller-reported host RAM and commit headroom, not GPU allocations."""
    snapshot = state.get('memory') or {}
    result = {key: snapshot[key] for key in ('available_bytes','commit_headroom_bytes') if key in snapshot}
    if any(type(value) is not int or value < 0 for value in result.values()):
        raise ValueError('Invalid controller memory telemetry')
    return result


def verified_prompt(path, size, manifest=None):
    path=Path(path)
    data=path.read_bytes()
    if manifest is not None:
        entry=manifest['prompts'][str(size)]
        if entry['file']!=path.name or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('Cold prompt differs from its immutable input manifest')
    return data.decode('utf-8')


def response_timings(value):
    usage = value['usage']
    timings = dict(value.get('timings') or {})
    if not timings and usage.get('gufo'):
        timings = {'prompt_per_second':usage.get('prompt_tokens_per_second'),
                   'predicted_per_second':usage.get('completion_tokens_per_second'),
                   'prompt_ms':usage['gufo'].get('prefill_ms'),
                   'predicted_ms':usage['gufo'].get('decode_ms')}
    return timings


def cold_sample(value, size, output):
    usage = value['usage']; timings = response_timings(value)
    native = usage.get('gufo') or {}
    if usage.get('prompt_tokens') != size or usage.get('completion_tokens') != output:
        raise ValueError('Unexpected actual input/output token count')
    if (timings.get('prompt_n',size) != size or timings.get('predicted_n',output) != output
            or timings.get('cache_n',0) != 0 or usage.get('cached_tokens',0) != 0
            or usage.get('prompt_tokens_details',{}).get('cached_tokens',0) != 0
            or native.get('cache_hit') or native.get('cache_disk_hit')
            or 'max_tokens_clamped_from' in timings):
        raise ValueError('Cached, clamped or inconsistent cold sample')
    for field in ('prompt_per_second',) if output == 1 else ('prompt_per_second','predicted_per_second'):
        rate = timings.get(field)
        if not isinstance(rate,(float,int)) or not math.isfinite(rate) or rate<=0:
            raise ValueError('Missing or invalid phase rate: '+field)
    message = value['choices'][0]['message']
    text = (message.get('reasoning_content') or '')+(message.get('content') or '')
    drafted = timings.get('draft_n',usage.get('draft_tokens'))
    kept = timings.get('draft_n_accepted',timings.get('draft_accepted',usage.get('draft_tokens_accepted')))
    if drafted is not None or kept is not None:
        if type(drafted) is not int or type(kept) is not int or not 0<=kept<=drafted:
            raise ValueError('Invalid speculative acceptance accounting')
    return {'timings':timings,'usage':usage,'finish_reason':value['choices'][0].get('finish_reason'),
            'output_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'drafted':drafted,'accepted':kept,
            'acceptance':kept/drafted if drafted else None}
