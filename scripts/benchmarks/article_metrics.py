"""Pure benchmark accounting; no inference or model state."""
import json,math,re

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
    if any(type(v) is not int or v not in (512,2048,8192,32768) or v+128>capacity for v in values):
        raise ValueError('Unsupported benchmark length or insufficient output room')
    if len(set(values))!=len(values): raise ValueError('Repeated benchmark sizes')
    return tuple(values)
