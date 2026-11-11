"""Root-only CPU lookup comparison; import/default CLI is inert.

Run only in the sealed 0.20.3 image with the real serving tokenizer mounted
readonly, network disabled and no accelerator/model-weight mounts.
"""
import argparse
import ast
import collections
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import platform
import statistics
import struct
import sys
import time
import types

API_SHA = '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'
ADAPTER_SHA = '00172cbc3f245e3ea7c0130064712b7d6c9860275b2983ed98a8c1f04748546e'
TOKENIZER_SOURCE_SHA = '4ad1b3ac05211d1852fe00a69eece59cdac26373024e84137bb8a1b6d00ae3b3'
ENV = ('HF_HUB_OFFLINE', 'TOKENIZERS_PARALLELISM', 'OMP_NUM_THREADS',
       'RAYON_NUM_THREADS', 'HALOGEN_CHAT_TEMPLATE', 'HF_HOME',
       'HUGGINGFACE_HUB_CACHE', 'HF_HUB_CACHE', 'TRANSFORMERS_CACHE')


def pin(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def ids_sha(ids):
    return hashlib.sha256(struct.pack('<' + 'i' * len(ids), *ids)).hexdigest()


def load_adapter(path):
    if pin(path)['sha256'] != ADAPTER_SHA:
        raise ValueError('Exact frozen direct-backend adapter required')
    spec = importlib.util.spec_from_file_location('sealed_lookup_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serving_loader(source, where):
    """Execute exactly the two actual serving-loader functions, no API startup."""
    if hashlib.sha256(source).hexdigest() != API_SHA:
        raise ValueError('Exact API required')
    names = {'chat_template_override', 'load_serving_tokenizer'}
    body = [node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in body} != names:
        raise ValueError('Actual serving loader missing')
    namespace = {'os': os}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
                 'actual-serving-tokenizer-loader.py', 'exec'), namespace)
    return namespace['load_serving_tokenizer'](where)


def make_templates(adapter, source):
    result = {'stock': adapter.lookup_namespace(source),
              'direct_backend_scalar': adapter.lookup_namespace(adapter.patch_source(source))}
    result['direct_backend_scalar']['_LOOKUP_DIRECT_ENABLED'] = True
    for namespace in result.values():
        # The API compiles this regex once, not once per request. Prime it untimed.
        namespace['view_segments']('1\tx\n2\ty\n3\tz')
    return result


def fresh_namespace(template):
    result = dict(template)
    result['_VIEW_CACHE'], result['_VIEW_CACHE_IDS'] = collections.OrderedDict(), [0]
    for name in ('view_segments', 'lookup_view', '_lookup_encode_segments'):
        if name in template:
            fn = template[name]
            result[name] = types.FunctionType(fn.__code__, result, fn.__name__, fn.__defaults__, fn.__closure__)
    return result


def numbered(groups):
    return '\n-- another tool excerpt --\n'.join('\n'.join((
        f'{10 * group + 1}\tconst row{group} = new GlideRecord("incident");',
        f'{10 * group + 2}\trow{group}.addQuery("short_description", "é 今日は 👩🏽‍💻");',
        f'{10 * group + 3}\trow{group}.query();')) for group in range(groups))


def prepare_fixtures(tokenizer):
    original = [('no-tool-block', 'plain prompt', 1, False),
        ('unrecognized-tool-text', 'plain tool text without line numbers', 1, True),
        ('one-json-output', json.dumps({'output': 'é 今日は 👩🏽‍💻\nreturn 1;'}), 1, True),
        ('four-numbered-segments', numbered(4), 1, True),
        ('twelve-numbered-segments', numbered(12), 1, True),
        ('fortyeight-numbered-segments', numbered(48), 1, True),
        ('warm-view-cache', numbered(12), 3, True),
        ('json-numbered-segments', json.dumps({'output': numbered(8)}, ensure_ascii=False), 1, True)]
    opening, closing = [tokenizer.convert_tokens_to_ids(text) for text in ('<tool_response>', '</tool_response>')]
    if any(type(value) is not int or value < 0 for value in (opening, closing)):
        raise ValueError('Actual tool boundary IDs unavailable')
    result = []
    for name, body, repetitions, tool in original:
        ids = tokenizer(body, add_special_tokens=False)['input_ids']
        ids = [opening, *ids, closing] if tool else list(ids)
        result.append(dict(name=name, body_utf8_sha256=hashlib.sha256(body.encode()).hexdigest(),
            ids=ids, opening=opening, closing=closing, repetitions=repetitions,
            cache_mode='warm' if name == 'warm-view-cache' else 'cold'))
    return result


def signature(namespace, outputs):
    return (tuple(tuple(value) for value in outputs),
            tuple((key, tuple(value)) for key, value in namespace['_VIEW_CACHE'].items()),
            tuple(namespace['_VIEW_CACHE_IDS']))


class CountHF:
    """Untimed only. Every encode/decode delegates to the actual HF object."""
    def __init__(self, tokenizer):
        self.tokenizer, self.encode_calls = tokenizer, 0
    def __call__(self, value, **kwargs):
        self.encode_calls += 1
        return self.tokenizer(value, **kwargs)
    def decode(self, *args, **kwargs):
        return self.tokenizer.decode(*args, **kwargs)


def profile_HF_dispatch(namespace, tokenizer, fixture):
    """Untimed only; observe the actual HF object, never a counter facade."""
    code = getattr(type(tokenizer).__call__, '__code__', None)
    if code is None:
        raise ValueError('Actual HF Python dispatch code is required for direct-usage proof')
    count = 0
    previous = sys.getprofile()
    def observe(frame, event, arg):
        nonlocal count
        if event == 'call' and frame.f_code is code and frame.f_locals.get('self') is tokenizer:
            count += 1
    try:
        sys.setprofile(observe)
        outputs = [namespace['lookup_view'](tokenizer, fixture['ids'], fixture['opening'], fixture['closing'])
                   for _ in range(fixture['repetitions'])]
    finally:
        sys.setprofile(previous)
    return outputs, count


def untimed_parity(templates, tokenizer, fixtures):
    rows, totals = [], dict(stock=0, direct_backend_scalar=0)
    for fixture in fixtures:
        results = {}
        for arm in ('stock', 'direct_backend_scalar'):
            ns = fresh_namespace(templates[arm])
            outputs, dispatches = profile_HF_dispatch(ns, tokenizer, fixture)
            results[arm] = signature(ns, outputs)
            totals[arm] += dispatches
        if results['stock'] != results['direct_backend_scalar']:
            raise ValueError('Untimed LOOK/cache parity failed: ' + fixture['name'])
        rows.append(dict(name=fixture['name'], outputs=[list(value) for value in results['stock'][0]],
                         cache_ids=list(results['stock'][2]), parity=True))
    return dict(passed=True, cases=rows, HF_wrapper_encode_calls=totals, timed=False,
                actual_HF_object_used=True, profiler_restored=True,
                native_encoding_call_reduction_claimed=False)


def contract_checks(templates, tokenizer):
    fixture = prepare_fixtures(tokenizer)[3]
    class RejectBatch:
        def __call__(self, value, **kwargs):
            if isinstance(value, list):
                raise TypeError('injected unsupported batch')
            return tokenizer(value, **kwargs)
        def decode(self, *args, **kwargs):
            return tokenizer.decode(*args, **kwargs)
    cases = []
    for name, ids, subject in (
            ('unqualified-wrapper-fallback', fixture['ids'], RejectBatch()),
            ('unclosed-tool-response', fixture['ids'][:-1], tokenizer),
            ('cache-and-LOOK-limits', fixture['ids'] + fixture['ids'], tokenizer)):
        saved = {}
        for arm in ('stock', 'direct_backend_scalar'):
            ns = fresh_namespace(templates[arm])
            if name == 'cache-and-LOOK-limits':
                ns['VIEW_CACHE_MAX_IDS'], ns['VIEW_LOOK_MAX_IDS'] = 16, 28
            outputs = [ns['lookup_view'](subject, ids, fixture['opening'], fixture['closing'])]
            saved[arm] = signature(ns, outputs)
        if saved['stock'] != saved['direct_backend_scalar']:
            raise ValueError('Contract parity failed: ' + name)
        cases.append(dict(name=name, passed=True, timed=False))
    return dict(passed=True, cases=cases)


def time_arm(template, tokenizer, fixture, clock=time.perf_counter_ns):
    if isinstance(tokenizer, CountHF):
        raise ValueError('Counter wrappers must never enter timed calls')
    if sys.getprofile() is not None:
        raise ValueError('Untimed dispatch profiling must not enter timed calls')
    ns = fresh_namespace(template)  # Creation/cache reset is outside all timing.
    if fixture['cache_mode'] == 'warm':
        ns['lookup_view'](tokenizer, fixture['ids'], fixture['opening'], fixture['closing'])
    outputs, durations = [], []
    for _ in range(fixture['repetitions']):
        before = clock()
        value = ns['lookup_view'](tokenizer, fixture['ids'], fixture['opening'], fixture['closing'])
        after = clock()
        durations.append(after - before)
        outputs.append(value)
    result = dict(call_ns=durations, total_lookup_ns=sum(durations), cache_mode=fixture['cache_mode'],
        primed_outside_timing=fixture['cache_mode'] == 'warm', counter_wrapper_used=False,
        output_counts=[len(value) for value in outputs], output_sha256=[ids_sha(value) for value in outputs])
    return result, signature(ns, outputs)


def time_case(templates, tokenizer, fixture, iterations, case_index, clock=time.perf_counter_ns, progress=None):
    warmups, pairs = [], []
    order = ('stock', 'direct_backend_scalar') if case_index % 2 == 0 else ('direct_backend_scalar', 'stock')
    signatures = {}
    for arm in order:
        row, signatures[arm] = time_arm(templates[arm], tokenizer, fixture, clock)
        row.update(case=fixture['name'], arm=arm, excluded_warmup=True)
        warmups.append(row)
        if progress: progress('warmup', row)
    if signatures['stock'] != signatures['direct_backend_scalar']:
        raise ValueError('Warmup parity failed')
    for iteration in range(iterations):
        order = ['stock', 'direct_backend_scalar'] if (iteration + case_index) % 2 == 0 else ['direct_backend_scalar', 'stock']
        pair = dict(case=fixture['name'], iteration=iteration, order=order, arms={}, parity=False)
        pairs.append(pair)
        signatures = {}
        for arm in order:
            pair['arms'][arm], signatures[arm] = time_arm(templates[arm], tokenizer, fixture, clock)
            if progress: progress('pair', pair)
        if signatures['stock'] != signatures['direct_backend_scalar']:
            raise ValueError('Measured LOOK/cache parity failed')
        pair['parity'] = True
        if progress: progress('pair', pair)
    return warmups, pairs


def aggregate_pairs(pairs):
    if not pairs or not all(pair['parity'] and set(pair['arms']) == {'stock', 'direct_backend_scalar'} for pair in pairs):
        raise ValueError('Complete paired observations required')
    result = dict(measured_pairs=len(pairs))
    for arm in ('stock', 'direct_backend_scalar'):
        values = [row['arms'][arm]['total_lookup_ns'] for row in pairs]
        result[arm] = dict(mean_ns=statistics.fmean(values), median_ns=statistics.median(values),
            min_ns=min(values), max_ns=max(values), stdev_ns=statistics.stdev(values) if len(values) > 1 else 0)
    result['paired_difference_ns'] = [row['arms']['direct_backend_scalar']['total_lookup_ns'] - row['arms']['stock']['total_lookup_ns'] for row in pairs]
    result['direct_backend_scalar_vs_stock_mean_percent'] = (result['direct_backend_scalar']['mean_ns'] / result['stock']['mean_ns'] - 1) * 100
    return result


def run(args):
    output = Path(args.output)
    if output.exists():
        raise ValueError('Retain prior result; never overwrite or retry')
    ledger = dict(schema='halogen0203.cpu-lookup-direct-backend.v1', started_utc=datetime.now(timezone.utc).isoformat(),
        terminal=False, completed=False, parity_passed=False, warmups=[], raw_pairs=[], aggregates=None,
        timing_scope='CPU lookup_view only: decode, view extraction, encode and cache operations; no counter facade.',
        engine_HTTP_GPU_NPU_calls=False, model_weights_accessed=False, tok_s_or_acceptance_gain_qualified=False)
    def save():
        temporary = output.with_suffix(output.suffix + '.tmp')
        temporary.write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf-8')
        temporary.replace(output)
    def progress(kind, row):
        target = ledger['warmups' if kind == 'warmup' else 'raw_pairs']
        if not any(existing is row for existing in target): target.append(row)
        save()
    try:
        adapter = load_adapter(args.adapter)
        source = Path(args.api).read_bytes()
        if hashlib.sha256(source).hexdigest() != API_SHA:
            raise ValueError('API source changed')
        if pin(args.tokenizer_source)['sha256'] != TOKENIZER_SOURCE_SHA:
            raise ValueError('Root tokenizer receipt changed')
        manifest = json.loads(Path(args.tokenizer_source).read_bytes())
        before_env = {name: os.environ.get(name) for name in ENV}
        if before_env['HF_HUB_OFFLINE'] != '1' or any(before_env[key] != value for key, value in manifest['selected_environment'].items()):
            raise ValueError('Actual serving tokenizer environment changed')
        tokenizer_root = Path(args.tokenizer)
        def tokenizer_pins():
            names = sorted(path.relative_to(tokenizer_root).as_posix() for path in tokenizer_root.rglob('*') if path.is_file())
            if names != sorted(row['name'] for row in manifest['files']): raise ValueError('Tokenizer file membership changed')
            rows = []
            for expected in manifest['files']:
                path = tokenizer_root / expected['name']
                actual = pin(path)
                if actual['bytes'] != expected['bytes'] or actual['sha256'] != expected['sha256']:
                    raise ValueError('Tokenizer file changed: ' + expected['name'])
                rows.append(actual)
            return rows
        ledger.update(api=pin(args.api), adapter=pin(args.adapter), harness=pin(__file__),
            tokenizer_source=pin(args.tokenizer_source), tokenizer_files_before=tokenizer_pins(),
            environment_before=before_env, iterations=args.iterations)
        tokenizer = serving_loader(source, str(tokenizer_root))
        import transformers, tokenizers
        native = sys.modules.get('tokenizers.tokenizers')
        ledger['software'] = dict(python=sys.version, platform=platform.platform(),
            transformers_version=transformers.__version__, tokenizers_version=tokenizers.__version__,
            tokenizer_class=type(tokenizer).__module__ + '.' + type(tokenizer).__name__,
            transformers_file=pin(transformers.__file__), tokenizers_file=pin(tokenizers.__file__),
            native_file=pin(native.__file__) if native is not None else None,
            actual_call_source=pin(inspect.getsourcefile(type(tokenizer).__call__)),
            actual_decode_source=pin(inspect.getsourcefile(type(tokenizer).decode)))
        templates = make_templates(adapter, source)
        fixtures = prepare_fixtures(tokenizer)
        ledger['fixtures'] = [{key: value for key, value in fixture.items() if key != 'ids'} | dict(input_count=len(fixture['ids']), input_ids_sha256=ids_sha(fixture['ids'])) for fixture in fixtures]
        ledger['untimed_parity'] = untimed_parity(templates, tokenizer, fixtures)
        calls = ledger['untimed_parity']['HF_wrapper_encode_calls']
        binding = templates['direct_backend_scalar']['_LOOKUP_DIRECT_TYPES'][0]
        actual_type_binding = (type(binding) is tuple and len(binding) == 3 and type(tokenizer) is binding[0]
            and type(tokenizer.backend_tokenizer) is binding[1]
            and type(tokenizer.backend_tokenizer.model) is binding[2])
        ledger['direct_backend_usage'] = dict(proven=actual_type_binding and calls['stock'] > 0 and calls['direct_backend_scalar'] == 0,
            actual_HF_wrapper_calls=calls, untimed_only=True, timing_profiler_used=False,
            candidate_namespace_enabled=templates['direct_backend_scalar']['_LOOKUP_DIRECT_ENABLED'] is True,
            actual_type_binding=actual_type_binding,
            bound_classes=[cls.__module__ + '.' + cls.__qualname__ for cls in binding] if actual_type_binding else None,
            meaning='The same scalar native encodes bypass HF dispatch/attention-mask production; no reduction in native encoding calls is claimed')
        if not ledger['direct_backend_usage']['proven'] or not actual_type_binding:
            raise ValueError('Actual direct-backend usage was not proved; no timing qualification')
        ledger['contracts'] = contract_checks(templates, tokenizer)
        ledger['parity_passed'] = True
        save()
        all_pairs = {}
        for index, fixture in enumerate(fixtures):
            _, pairs = time_case(templates, tokenizer, fixture, args.iterations, index, progress=progress)
            all_pairs[fixture['name']] = pairs
        ledger['tokenizer_files_after'] = tokenizer_pins()
        ledger['environment_after'] = {name: os.environ.get(name) for name in ENV}
        if ledger['environment_after'] != before_env: raise ValueError('Tokenizer environment mutated')
        ledger['aggregates'] = {name: aggregate_pairs(pairs) for name, pairs in all_pairs.items()}
        ledger['completed'] = True
    except BaseException as error:
        ledger['error'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        ledger['terminal'] = True
        ledger['ended_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    return ledger


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    for name in ('api', 'adapter', 'tokenizer', 'tokenizer-source', 'output'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--iterations', type=int, default=21)
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(dict(source_only=True, executed=False)))
        return 0
    if any(getattr(args, name) is None for name in ('api', 'adapter', 'tokenizer', 'tokenizer_source', 'output')) or args.iterations < 1:
        parser.error('--run requires all explicit input/output paths and positive iterations')
    result = run(args)
    print(json.dumps(dict(completed=result['completed'], output=pin(args.output))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
