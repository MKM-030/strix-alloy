"""Build single or selected-top10 Flash-Next MTP expert ONNX prototypes.

Selected expert IDs are fixed per graph; router coefficients are dynamic.
This sparse expert subgraph does not replace the complete MTP head or supply
the absent Halogen target-state export/import interface.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import stat
import statistics
import struct
import time
import numpy as np
import onnx
from onnx import helper, TensorProto, numpy_helper
from hgn_q4c_slice import decode_rows


def validate_selected(values):
    try:
        if len(values) != 10:
            raise ValueError('requires exactly ten expert IDs')
    except TypeError as exc:
        raise ValueError('requires a bounded sequence of ten expert IDs') from exc
    if any(type(index) is not int or not 0 <= index < 512 for index in values) or len(set(values)) != 10:
        raise ValueError('requires ten unique integer expert IDs from 0 through 511')
    return tuple(values)


def expert_ids(value):
    try:
        values = tuple(int(part) for part in value.split(','))
    except (TypeError, ValueError) as exc:
        raise ValueError('expected ten comma-separated expert IDs') from exc
    return validate_selected(values)


def build_graph(gate_up, down, selected=None):
    if selected is not None:
        selected = validate_selected(selected)
    gu, down = np.asarray(gate_up, dtype=np.float32), np.asarray(down, dtype=np.float32)
    batched = selected is not None
    rank = 3 if batched else 2
    if gu.ndim != rank or down.ndim != rank or not np.isfinite(gu).all() or not np.isfinite(down).all():
        raise ValueError('invalid or non-finite expert matrices')
    width, intermediate = gu.shape[-1], down.shape[-1]
    if width <= 0 or intermediate <= 0 or gu.shape[-2] != 2 * intermediate or down.shape[-2] != width:
        raise ValueError('incompatible expert matrix geometry')
    if batched and (gu.shape[0] != 10 or down.shape[0] != 10):
        raise ValueError('requires exactly ten selected experts')
    gate_weights = gu.transpose(0, 2, 1) if batched else gu.T
    down_weights = down.transpose(0, 2, 1) if batched else down.T
    initializers = [numpy_helper.from_array(gate_weights.copy(), 'W_gate_up'),
                    numpy_helper.from_array(down_weights.copy(), 'W_down')]
    nodes = [helper.make_node('MatMul', ['x', 'W_gate_up'], ['gu']),
             helper.make_node('Split', ['gu'], ['gate', 'up'], axis=2 if batched else 1, num_outputs=2),
             helper.make_node('Sigmoid', ['gate'], ['gate_sig']),
             helper.make_node('Mul', ['gate', 'gate_sig'], ['silu_gate']),
             helper.make_node('Mul', ['silu_gate', 'up'], ['hidden']),
             helper.make_node('MatMul', ['hidden', 'W_down'], ['expert_output' if batched else 'y'])]
    inputs = [helper.make_tensor_value_info('x', TensorProto.FLOAT, [1, width])]
    if batched:
        # Prepare this shape on the host: VitisAI does not support dynamic Unsqueeze.
        inputs.append(helper.make_tensor_value_info('routing_weights', TensorProto.FLOAT, [10, 1, 1]))
        initializers.append(numpy_helper.from_array(np.array([0], dtype=np.int64), 'expert_axis'))
        nodes += [helper.make_node('Mul', ['expert_output', 'routing_weights'], ['weighted_experts']),
                  helper.make_node('ReduceSum', ['weighted_experts', 'expert_axis'], ['y'], keepdims=0)]
    graph = helper.make_graph(nodes, 'flash_next_mtp_selected_top10' if batched else 'flash_next_mtp_expert0',
                              inputs, [helper.make_tensor_value_info('y', TensorProto.FLOAT, [1, width])], initializers)
    model = helper.make_model(graph, producer_name='strix-alloy-halogen-npu',
                              opset_imports=[helper.make_opsetid('', 21)])
    model.ir_version = 13  # The installed Windows ML ORT 1.25 accepts IR <= 13.
    if batched:
        helper.set_model_props(model, {'selected_experts': ','.join(map(str, selected)),
                                      'scope': 'expert-subgraph-only; fixed IDs; dynamic router weights'})
    onnx.checker.check_model(model)
    return model


def read_top10(hgn, manifest_path, selected):
    selected = validate_selected(selected)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('identity') != 'qwen3.8-flash-next' or hgn.stat().st_size != manifest.get('file_size'):
        raise ValueError('HGN identity or file size differs from manifest')
    entries = {value['name']: value for value in manifest['entries']}
    gate_entry = entries['mtp.layers.0.mlp.experts.gate_up_proj.weight']
    down_entry = entries['mtp.layers.0.mlp.experts.down_proj.weight']
    if gate_entry['dims'] != [512, 1280, 2560] or down_entry['dims'] != [512, 2560, 640]:
        raise ValueError('unexpected Flash-Next expert geometry')
    before = hgn.stat()
    gu, down = [], []
    with hgn.open('rb') as stream:
        header = stream.read(104)
        if len(header) != 104 or struct.unpack_from('<II', header) != (0x314E4748, manifest['version']):
            raise ValueError('HGN header differs from manifest')
        count, table, _, size = struct.unpack_from('<QQQQ', header, 8)
        if size != before.st_size or count != manifest['tensor_count'] or table + count * 160 > size:
            raise ValueError('HGN header bounds differ from manifest')
        if header[40:104].split(b'\0', 1)[0].decode('ascii') != manifest['identity']:
            raise ValueError('HGN model identity differs from manifest')
        stream.seek(table)
        matched = set()
        for _ in range(count):
            record = stream.read(160)
            if len(record) != 160:
                raise ValueError('truncated HGN tensor table')
            name = record[:96].split(b'\0', 1)[0].decode('ascii')
            if name not in (gate_entry['name'], down_entry['name']):
                continue
            entry = entries[name]
            store, rank = struct.unpack_from('<II', record, 96)
            dims = list(struct.unpack_from('<qqqq', record, 104))[:rank]
            offset, length = struct.unpack_from('<QQ', record, 136)
            checksum, variant = struct.unpack_from('<II', record, 152)
            if (store, dims, offset, length, checksum, variant) != (entry['store'], entry['dims'], entry['offset'], entry['size'], entry['xor32'], entry['variant']):
                raise ValueError('expert tensor table differs from manifest: ' + name)
            matched.add(name)
        if len(matched) != 2:
            raise ValueError('HGN expert tensor table is incomplete')
        for index in selected:
            gu.append(decode_rows(stream, gate_entry, index * 1280, 1280))
            down.append(decode_rows(stream, down_entry, index * 2560, 2560))
    after = hgn.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('HGN changed during sparse decoding')
    return np.stack(gu), np.stack(down)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def save_graph(model, output, gate_up, down, selected, source=None):
    output.parent.mkdir(parents=True, exist_ok=True)
    data = output.with_name(output.name + '.data')
    receipt = output.with_name(output.name + '.json')
    lock = output.with_name(output.name + '.lock')
    # Exclusive creation also refuses two concurrent writers to the same graph.
    handle = lock.open('x', encoding='utf-8')
    try:
        if any(path.exists() for path in (output, data, receipt)):
            raise FileExistsError('graph, data or receipt already exists; nothing overwritten')
        onnx.save_model(model, str(output), save_as_external_data=True, all_tensors_to_one_file=True,
                        location=data.name, size_threshold=1024)
        result = {'schema': 1, 'scope': 'selected-expert subgraph; no Halogen state transfer or complete MTP head',
                  'model': str(output.resolve()), 'model_sha256': digest(output), 'data_sha256': digest(data),
                  'graph_operators': [node.op_type for node in model.graph.node],
                  'graph_input_shapes': {value.name: [dim.dim_value for dim in value.type.tensor_type.shape.dim]
                                         for value in model.graph.input},
                  'selected_experts': list(selected) if selected else None,
                  'gate_up': list(gate_up.shape), 'down': list(down.shape),
                  'weights_bytes': gate_up.nbytes + down.nbytes,
                  'decoded_gate_up_sha256': hashlib.sha256(gate_up.tobytes()).hexdigest(),
                  'decoded_down_sha256': hashlib.sha256(down.tobytes()).hexdigest(), 'source': source}
        receipt.write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result
    finally:
        handle.close()
        lock.unlink(missing_ok=True)


def verified_provider_copy(catalog_library, copied_directory):
    """Verify the complete copy against the active installed provider directory."""
    catalog_library = Path(catalog_library).resolve(strict=True)
    original = catalog_library.parent
    copied = Path(copied_directory).resolve(strict=True)
    if not catalog_library.is_file() or not copied.is_dir() or original == copied:
        raise ValueError('provider copy must be a separate directory')

    def inventory(directory):
        files = {}
        for entry in (directory, *directory.rglob('*')):
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('provider directory cannot contain reparse entries')
            if entry.is_file():
                files[entry.relative_to(directory).as_posix()] = entry
            elif not entry.is_dir():
                raise ValueError('provider directory contains a non-file entry')
        return files

    originals, copies = inventory(original), inventory(copied)
    if originals.keys() != copies.keys():
        raise ValueError('provider copy file set differs from the installed directory')
    verified = []
    for name, source in sorted(originals.items()):
        destination = copies[name]
        source_size, copied_size = source.stat().st_size, destination.stat().st_size
        source_hash, copied_hash = digest(source), digest(destination)
        if source_size != copied_size or source_hash != copied_hash:
            raise ValueError('provider copy differs from installed bytes: ' + name)
        verified.append({'relative_path': name, 'bytes': source_size,
                         'catalog_sha256': source_hash, 'copied_sha256': copied_hash})
    return copied / catalog_library.name, verified


def replay(model_path, provider, repetitions, report_path, ep_dir=None):
    """Replay a fixed graph with CPU or strict ORT VitisAI attribution."""
    if ep_dir is not None and provider != 'npu':
        raise ValueError('provider directory override is only valid for NPU replay')
    if report_path.exists():
        raise FileExistsError('report already exists')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result = {'schema': 1, 'provider_requested': provider, 'model_sha256': digest(model_path),
              'data_sha256': digest(model_path.with_name(model_path.name + '.data')),
              'scope': 'expert-subgraph replay; synthetic input; not Halogen PP/TG or live target state',
              'passed': False, 'cpu_fallback_allowed': provider == 'cpu', 'profiling_enabled': True}
    runtime, session, options, devices, dll_directory = None, None, None, None, None
    registered = False
    try:
        if provider == 'npu':
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime = initialize()
            ep = next(p for p in ExecutionProviderCatalog.get_default().find_all_providers()
                      if p.name == 'VitisAIExecutionProvider')
            if ep.ready_state == ExecutionProviderReadyState.NOT_PRESENT:
                raise RuntimeError('VitisAI is not installed; automatic acquisition is disabled')
            ready = ep.ensure_ready_async().get()
            if int(ready.status) != 1:
                raise RuntimeError('VitisAI readiness failed: ' + ready.diagnostic_text)
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report_path.with_suffix(''))
        if provider == 'npu':
            catalog_library = Path(ep.library_path).resolve(strict=True)
            chosen_library = catalog_library
            result.update(catalog_provider_library=str(catalog_library),
                          catalog_provider_library_sha256=digest(catalog_library),
                          provider_copy_requested=ep_dir is not None)
            if ep_dir is not None:
                chosen_library, verified_files = verified_provider_copy(catalog_library, ep_dir)
                result['provider_copy_files'] = verified_files
                dll_directory = os.add_dll_directory(str(chosen_library.parent))
            result.update(provider_library=str(chosen_library), provider_library_sha256=digest(chosen_library),
                          placement_scope='ORT EP attribution; internal provider CPU/AIE split requires compiler evidence')
            ort.register_execution_provider_library(ep.name, str(chosen_library))
            registered = True
            devices = [d for d in ort.get_ep_devices() if d.ep_name == ep.name and str(d.device.type).endswith('.NPU')]
            if len(devices) != 1:
                raise RuntimeError('expected exactly one VitisAI NPU device')
            cache_key = hashlib.sha256(':'.join(result[key] for key in
                                      ('model_sha256', 'data_sha256', 'provider_library_sha256')).encode()).hexdigest()
            options.add_provider_for_devices(devices, {
                'cache_dir': str(report_path.parent / 'vitisai-cache'),
                'cache_key': cache_key, 'enable_cache_file_io_in_mem': '0'})
            options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
            result['cache_key'] = cache_key
            initialize_started = time.perf_counter_ns()
            session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False)
        else:
            initialize_started = time.perf_counter_ns()
            session = ort.InferenceSession(str(model_path), sess_options=options, providers=['CPUExecutionProvider'])
        session.disable_fallback()
        result.update(ort_version=ort.__version__, session_providers=session.get_providers(),
                      session_initialization_ms=(time.perf_counter_ns() - initialize_started) / 1e6)
        model = onnx.load(str(model_path), load_external_data=True)
        weights = {value.name: numpy_helper.to_array(value) for value in model.graph.initializer}
        gu, down = weights['W_gate_up'].swapaxes(-1, -2), weights['W_down'].swapaxes(-1, -2)
        x = np.random.default_rng(20261004).normal(0, .2, (1, gu.shape[-1])).astype(np.float32)
        coefficients = np.arange(1, 11, dtype=np.float32) / 55 if gu.ndim == 3 else np.ones(1, dtype=np.float32)
        feed = {'x': x}
        if gu.ndim == 3:
            routing_input = next(value for value in model.graph.input if value.name == 'routing_weights')
            routing_shape = [dim.dim_value for dim in routing_input.type.tensor_type.shape.dim]
            if routing_shape not in ([10], [10, 1, 1]):
                raise ValueError('unsupported router input shape')
            feed['routing_weights'] = coefficients.reshape(routing_shape)
            result.update(routing_input_shape=routing_shape,
                          host_router_reshape=routing_shape == [10, 1, 1])
        else:
            gu, down = gu[None], down[None]
        expected = np.zeros_like(x)
        intermediate = down.shape[-1]
        for index in range(len(gu)):
            projected = x @ gu[index].T
            gate, up = projected[:, :intermediate], projected[:, intermediate:]
            expected += coefficients[index] * ((gate / (1 + np.exp(-gate)) * up) @ down[index].T)
        warmup_started = time.perf_counter_ns()
        actual = session.run(None, feed)[0]
        result.update(input_sha256=hashlib.sha256(x.tobytes()).hexdigest(),
                      routing_sha256=hashlib.sha256(coefficients.tobytes()).hexdigest(),
                      max_abs_error=float(np.max(np.abs(actual - expected))), warmup_runs=1,
                      warmup_ms=(time.perf_counter_ns() - warmup_started) / 1e6)
        # Separately declared prototype approximation tolerance; precision is not inferred.
        tolerance = {'rtol': .03, 'atol': .003} if provider == 'npu' else {'rtol': 3e-5, 'atol': 3e-6}
        result['tolerance'] = tolerance
        np.testing.assert_allclose(actual, expected, **tolerance)
        samples = []
        for _ in range(repetitions):
            start = time.perf_counter_ns()
            session.run(None, feed)
            samples.append((time.perf_counter_ns() - start) / 1e6)
        profile = Path(session.end_profiling())
        events = json.loads(profile.read_text(encoding='utf-8'))
        attribution = sorted({event.get('args', {}).get('provider') for event in events
                              if event.get('args', {}).get('provider')})
        result.update(profile=str(profile), executed_providers=attribution)
        if provider == 'npu' and (not attribution or any(name != 'VitisAIExecutionProvider' for name in attribution)):
            raise RuntimeError('profile does not prove exclusive VitisAI execution')
        result.update(passed=True, repetitions=repetitions, mean_ms=statistics.fmean(samples),
                      median_ms=statistics.median(samples), min_ms=min(samples),
                      p95_ms=sorted(samples)[max(0, int(np.ceil(.95 * len(samples))) - 1)], samples_ms=samples)
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        session = None
        options, devices = None, None
        gc.collect()
        cleanup_errors = []
        if registered:
            try:
                ort.unregister_execution_provider_library('VitisAIExecutionProvider')
                result['provider_unregistered'] = True
            except Exception as exc:
                cleanup_errors.append('Provider unregister: ' + type(exc).__name__ + ': ' + str(exc))
        if dll_directory is not None:
            try:
                dll_directory.close()
                result['dll_directory_closed'] = True
            except Exception as exc:
                cleanup_errors.append('DLL directory close: ' + type(exc).__name__ + ': ' + str(exc))
        if runtime is not None:
            try:
                runtime()
                result['bootstrap_shutdown'] = True
            except Exception as exc:
                cleanup_errors.append('Bootstrap shutdown: ' + type(exc).__name__ + ': ' + str(exc))
        if cleanup_errors:
            result.update(passed=False, cleanup_errors=cleanup_errors)
            result.setdefault('error', 'Runtime cleanup failed')
        report_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate-up', type=Path)
    parser.add_argument('--down', type=Path)
    parser.add_argument('--hgn', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--expert-ids', type=expert_ids)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--check-model', type=Path)
    parser.add_argument('--provider', choices=('cpu', 'npu'), default='cpu')
    parser.add_argument('--reps', type=int, default=100)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--ep-dir', type=Path, help='NPU replay only: byte-identical copy of the installed provider directory')
    args = parser.parse_args()
    if args.check_model:
        if not args.report or not 1 <= args.reps <= 1000 or any((args.gate_up, args.down, args.hgn, args.manifest, args.expert_ids, args.out)):
            parser.error('replay needs --report and 1..1000 repetitions, without conversion options')
        if args.ep_dir and args.provider != 'npu':
            parser.error('--ep-dir requires --check-model --provider npu')
        result = replay(args.check_model, args.provider, args.reps, args.report, args.ep_dir)
        print(json.dumps({key: value for key, value in result.items() if key != 'samples_ms'}, indent=2))
        return 0 if result['passed'] else 1
    if not args.out or args.report or args.ep_dir or args.provider != 'cpu' or args.reps != 100:
        parser.error('conversion requires --out; --report belongs to --check-model')
    if args.hgn:
        if not args.manifest or not args.expert_ids or args.gate_up or args.down:
            parser.error('top10 conversion requires --hgn, --manifest and --expert-ids only')
        gu, down = read_top10(args.hgn, args.manifest, args.expert_ids)
        source = {'hgn': str(args.hgn.resolve()), 'manifest_sha256': digest(args.manifest)}
    else:
        if not args.gate_up or not args.down or args.manifest or args.expert_ids:
            parser.error('single expert conversion requires --gate-up and --down only')
        gu = np.load(args.gate_up, allow_pickle=False).astype(np.float32)
        down = np.load(args.down, allow_pickle=False).astype(np.float32)
        if gu.shape != (1280, 2560) or down.shape != (2560, 640):
            raise ValueError('unexpected single expert geometry')
        source = {'gate_up_sha256': digest(args.gate_up), 'down_sha256': digest(args.down)}
    result = save_graph(build_graph(gu, down, args.expert_ids), args.out, gu, down, args.expert_ids, source)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
