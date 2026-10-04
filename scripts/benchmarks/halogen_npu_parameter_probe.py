"""Tiny variable-expert-matrix probe; standalone, synthetic, not full Halogen MTP.

All expert matrices are graph inputs. One session alternates A/B matrices, x,
and coefficients. NPU invocation requires a root-reviewed guarded runner.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

TOP_K, WIDTH, INTERMEDIATE = 10, 64, 32
INPUT_BYTES = 246_056
TENSOR_LIMIT = 64 << 20


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            value.update(chunk)
    return value.hexdigest()


def build_graph():
    inputs = [helper.make_tensor_value_info(name, TensorProto.FLOAT, shape) for name, shape in
              [('x', [1, WIDTH]), ('W_gate_up', [TOP_K, WIDTH, 2 * INTERMEDIATE]),
               ('W_down', [TOP_K, INTERMEDIATE, WIDTH]), ('routing_weights', [TOP_K, 1, 1])]]
    nodes = [helper.make_node('MatMul', ['x', 'W_gate_up'], ['gu']),
             helper.make_node('Split', ['gu'], ['gate', 'up'], axis=2, num_outputs=2),
             helper.make_node('Sigmoid', ['gate'], ['gate_sig']),
             helper.make_node('Mul', ['gate', 'gate_sig'], ['silu_gate']),
             helper.make_node('Mul', ['silu_gate', 'up'], ['hidden']),
             helper.make_node('MatMul', ['hidden', 'W_down'], ['expert_output']),
             helper.make_node('Mul', ['expert_output', 'routing_weights'], ['weighted_experts']),
             helper.make_node('ReduceSum', ['weighted_experts', 'expert_axis'], ['y'], keepdims=0)]
    graph = helper.make_graph(nodes, 'tiny_variable_expert_inputs', inputs,
                              [helper.make_tensor_value_info('y', TensorProto.FLOAT, [1, WIDTH])],
                              [numpy_helper.from_array(np.array([0], dtype=np.int64), 'expert_axis')])
    model = helper.make_model(graph, producer_name='strix-alloy-parameter-probe',
                              opset_imports=[helper.make_opsetid('', 21)])
    model.ir_version = 13
    helper.set_model_props(model, {'scope': 'tiny synthetic expert inputs; no live routing or Halogen state',
                                  'expert_weights': 'runtime graph inputs, not initializers'})
    onnx.checker.check_model(model)
    return model


def fixtures():
    rng = np.random.default_rng(2026100402)
    feeds = {}
    for label, scale in [('A', .2), ('B', .35)]:
        coefficients = np.arange(1, TOP_K + 1, dtype=np.float32)
        if label == 'B':
            coefficients = coefficients[::-1].copy()
        feeds[label] = {'x': rng.normal(0, scale, (1, WIDTH)).astype(np.float32),
                        'W_gate_up': rng.normal(0, scale, (TOP_K, WIDTH, 2 * INTERMEDIATE)).astype(np.float32),
                        'W_down': rng.normal(0, scale, (TOP_K, INTERMEDIATE, WIDTH)).astype(np.float32),
                        'routing_weights': (coefficients / 55).reshape(TOP_K, 1, 1)}
    if sum(value.nbytes for feed in feeds.values() for value in feed.values()) >= TENSOR_LIMIT:
        raise ValueError('tiny fixture tensor limit exceeded')
    if any(sum(value.nbytes for value in feed.values()) != INPUT_BYTES for feed in feeds.values()):
        raise ValueError('tiny fixture input geometry differs')
    return feeds


def reference(feed):
    """Independent per-expert FP32 NumPy calculation, not a batched ONNX replay."""
    output = np.zeros((1, WIDTH), dtype=np.float32)
    for expert in range(TOP_K):
        projected = feed['x'] @ feed['W_gate_up'][expert]
        gate, up = projected[:, :INTERMEDIATE], projected[:, INTERMEDIATE:]
        activated = gate / (1 + np.exp(-gate))
        contribution = (activated * up) @ feed['W_down'][expert]
        output += float(feed['routing_weights'][expert, 0, 0]) * contribution
    return output


def run(model_path, provider, repetitions, report_path, ep_dir=None):
    if report_path.exists():
        raise FileExistsError('probe report exists; overwrite refused')
    if provider == 'npu' and ep_dir is None:
        raise ValueError('NPU probe requires the verified provider copy directory')
    if provider == 'cpu' and ep_dir is not None:
        raise ValueError('provider copy applies only to NPU probe')
    result = {'schema': 1, 'scope': 'tiny runtime matrices; one session; synthetic inputs; not Halogen MTP',
              'passed': False, 'provider_requested': provider, 'model_sha256': digest(model_path),
              'cpu_fallback_allowed': provider == 'cpu', 'tensor_limit_bytes': TENSOR_LIMIT,
              'feed_bytes_per_call': INPUT_BYTES, 'session_creations': 0,
              'timing_scope': 'host contiguous input copies + session.run input transfer/execution/output; validation excluded',
              'seed': 2026100402}
    runtime = session = options = devices = dll_directory = ort = None
    registered = False
    profile_finished = False
    cleanup_errors = []
    try:
        model = onnx.load(str(model_path))
        if model.SerializeToString() != build_graph().SerializeToString():
            raise ValueError('model differs from the frozen tiny graph contract')
        feeds = fixtures()
        expected = {label: reference(feed) for label, feed in feeds.items()}
        tolerance = {'rtol': .03, 'atol': .003} if provider == 'npu' else {'rtol': 3e-5, 'atol': 3e-6}
        if np.allclose(expected['A'], expected['B'], **tolerance):
            raise ValueError('A/B outputs insufficiently separated to detect stale data')
        for label, other in [('A', 'B'), ('B', 'A')]:
            for name in ('W_gate_up', 'W_down', 'x', 'routing_weights'):
                stale = reference(dict(feeds[label], **{name: feeds[other][name]}))
                if np.allclose(expected[label], stale, **tolerance):
                    raise ValueError('fixture cannot detect stale input: ' + label + '/' + name)
        result.update(tolerance=tolerance, input_sets={label: {name: hashlib.sha256(value.tobytes()).hexdigest()
                                                              for name, value in feed.items()}
                                                       for label, feed in feeds.items()},
                      reference_sha256={label: hashlib.sha256(value.tobytes()).hexdigest()
                                        for label, value in expected.items()},
                      reference_separation_max_abs=float(np.max(np.abs(expected['A'] - expected['B']))),
                      fixture_tensor_bytes=sum(value.nbytes for feed in feeds.values() for value in feed.values()))
        if provider == 'npu':
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime = initialize()
            ep = next(ep for ep in ExecutionProviderCatalog.get_default().find_all_providers()
                      if ep.name == 'VitisAIExecutionProvider')
            if ep.ready_state == ExecutionProviderReadyState.NOT_PRESENT:
                raise RuntimeError('VitisAI is absent; acquisition is disabled')
            ready = ep.ensure_ready_async().get()
            if int(ready.status) != 1:
                raise RuntimeError('VitisAI readiness failed: ' + ready.diagnostic_text)
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report_path.with_suffix(''))
        if provider == 'npu':
            from halogen_npu_expert_onnx import verified_provider_copy
            catalog_library = Path(ep.library_path).resolve(strict=True)
            chosen_library, verified_files = verified_provider_copy(catalog_library, ep_dir)
            dll_directory = os.add_dll_directory(str(chosen_library.parent))
            result.update(catalog_library=str(catalog_library), provider_library=str(chosen_library),
                          provider_library_sha256=digest(chosen_library), provider_copy_files=verified_files,
                          placement_scope='strict ORT Node EP attribution; provider-internal split needs compiler context')
            ort.register_execution_provider_library(ep.name, str(chosen_library))
            registered = True
            devices = [device for device in ort.get_ep_devices()
                       if device.ep_name == ep.name and str(device.device.type).endswith('.NPU')]
            if len(devices) != 1:
                raise RuntimeError('expected one VitisAI NPU device')
            cache_key = hashlib.sha256((result['model_sha256'] + ':' + result['provider_library_sha256']).encode()).hexdigest()
            options.add_provider_for_devices(devices, {'cache_dir': str(report_path.parent / 'vitisai-cache'),
                                                       'cache_key': cache_key, 'enable_cache_file_io_in_mem': '0'})
            options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
            result['cache_key'] = cache_key
        started = time.perf_counter_ns()
        result['session_creations'] += 1
        if provider == 'npu':
            session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False)
        else:
            session = ort.InferenceSession(str(model_path), sess_options=options, providers=['CPUExecutionProvider'])
        session.disable_fallback()
        result.update(ort_version=ort.__version__, session_providers=session.get_providers(),
                      initialization_ms=(time.perf_counter_ns() - started) / 1e6)
        samples, warmups = [], []
        for index in range(repetitions + 4):
            label = 'A' if index % 2 == 0 else 'B'
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order='C', copy=True)
                    for name, value in feeds[label].items()}
            actual = session.run(None, feed)[0]
            elapsed_ms = (time.perf_counter_ns() - started) / 1e6
            error = float(np.max(np.abs(actual - expected[label])))
            np.testing.assert_allclose(actual, expected[label], **tolerance)
            row = {'input_set': label, 'host_call_ms': elapsed_ms, 'max_abs_error': error,
                   'output_sha256': hashlib.sha256(actual.tobytes()).hexdigest()}
            (warmups if index < 4 else samples).append(row)
        profile = Path(session.end_profiling())
        profile_finished = True
        events = json.loads(profile.read_text(encoding='utf-8'))
        nodes = [event for event in events if event.get('cat') == 'Node']
        providers = sorted({event.get('args', {}).get('provider', '<missing>') for event in nodes})
        result.update(profile=str(profile), profile_sha256=digest(profile), node_events=len(nodes),
                      executed_node_providers=providers, warmup_calls=warmups, measured_calls=samples)
        if provider == 'npu' and (not nodes or providers != ['VitisAIExecutionProvider']):
            raise RuntimeError('profile does not prove all Node events executed by VitisAI')
        timings = [row['host_call_ms'] for row in samples]
        result.update(passed=True, repetitions=repetitions, mean_host_call_ms=statistics.fmean(timings),
                      median_host_call_ms=statistics.median(timings), min_host_call_ms=min(timings),
                      p95_host_call_ms=sorted(timings)[int(np.ceil(.95 * len(timings))) - 1])
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if session is not None and not profile_finished:
            try:
                profile = Path(session.end_profiling())
                result['partial_profile'] = str(profile)
            except Exception as exc:
                result['partial_profile_error'] = type(exc).__name__ + ': ' + str(exc)
        session = options = devices = None
        gc.collect()
        if registered:
            try:
                ort.unregister_execution_provider_library('VitisAIExecutionProvider')
                result['provider_unregistered'] = True
            except Exception as exc:
                cleanup_errors.append('provider unregister: ' + str(exc))
        if dll_directory is not None:
            try:
                dll_directory.close()
                result['dll_directory_closed'] = True
            except Exception as exc:
                cleanup_errors.append('DLL directory close: ' + str(exc))
        if runtime is not None:
            try:
                runtime()
                result['bootstrap_shutdown'] = True
            except Exception as exc:
                cleanup_errors.append('bootstrap shutdown: ' + str(exc))
        if cleanup_errors:
            result.update(passed=False, cleanup_errors=cleanup_errors)
        with report_path.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, help='exclusive new .onnx path; CPU-only graph creation')
    parser.add_argument('--model', type=Path)
    parser.add_argument('--provider', choices=('cpu', 'npu'), default='cpu')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--ep-dir', type=Path)
    parser.add_argument('--reps', type=int, default=100)
    args = parser.parse_args()
    if args.build:
        if args.model or args.report or args.ep_dir or args.provider != 'cpu':
            parser.error('--build cannot be mixed with replay arguments')
        model = build_graph()
        with args.build.open('xb') as output:
            output.write(model.SerializeToString())
        print(json.dumps({'model': str(args.build), 'model_sha256': digest(args.build),
                          'expert_weights_are_runtime_inputs': True, 'bytes': args.build.stat().st_size}))
        return 0
    if not args.model or not args.report or not 2 <= args.reps <= 1000 or args.reps % 2:
        parser.error('replay needs --model, --report and an even 2..1000 --reps')
    result = run(args.model, args.provider, args.reps, args.report, args.ep_dir)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('measured_calls', 'warmup_calls', 'provider_copy_files')}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
