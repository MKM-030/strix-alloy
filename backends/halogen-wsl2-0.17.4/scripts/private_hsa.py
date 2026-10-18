"""Opt-in startup admission for the two frozen private ROCr component variants.

This reads bounded local receipts and library bytes only. It never loads a DSO,
changes the installed SDK, or changes the ordinary service environment.
"""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOTS = (ROOT / '.local', ROOT.parents[1] / 'server/.local')
IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a'
SONAME_PATH = '/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libhsa-runtime64.so.1'
LIBRARY_SHAS = {
    'stock': '1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5',
    'source_stock': '2ba2eafa07cfcedb3754a7708858f2c054bc07c9e4e24fe4820b5340cda95af5',
    'candidate': 'cf1f4447cd92330c6a551042eff1ad95de2df4e276c09dfbfe7a252b5fa89434',
}
GATE_SHA = '95b58bbee9b413a3e081d65b737f782054405f22556036516a0821a16637e5a7'
COMPONENT_SHA = '7e1a0f5b1dcfd122d65f88db6d6dda43d0bbd2634adaf3cd7b4f21bb69e1e3b8'
LAUNCHER_SHA = 'bd2945ae634248e63ce2b008c2cbbdc17ac1af7f47a3a97082c8d36a41955c4f'
PROBE_SHA = '9b2f6dd62162cbed8ea51f767e018c787a69ebf03fa6e4cc8b6ef153fdf83f52'
COMPARISON_SHAS = {
    'installed-comparison.json': '53fa6d249c1bbe223e83b57e1123074ea08991a141405e5c48f1753860e39f2b',
    'patch-comparison.json': '2ba692800c835e7179ff32fb35299b50a577e251856c9be3dca713fa6506ce55',
}


def require(condition, message):
    if not condition:
        raise ValueError('Private HSA admission: ' + message)


def local_path(name):
    require(isinstance(name, str) and PureWindowsPath(name).is_absolute() and
            re.match(r'^[A-Za-z]:[\\/]', name) and
            not any(c in name[2:] for c in ':,*?"<>|') and
            '..' not in PureWindowsPath(name).parts and not any(ord(c) < 32 for c in name),
            'use an unambiguous absolute Windows drive path')
    path = Path(name)
    reject_links(path)
    path = path.resolve()
    require(any(path != root.resolve() and path.is_relative_to(root.resolve()) for root in LOCAL_ROOTS),
            'artifacts must stay under backend .local or server .local')
    return path


def reject_links(path):
    for node in (path, *path.parents):
        info = node.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'symlinks and reparse points are forbidden')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def identity(info):
    return {key: getattr(info, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def capture(name, expected, limit=4 * 1024**2):
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'invalid SHA-256')
    path = local_path(str(name))
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'bounded regular file required')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    reject_links(path)
    # Python 3.12 on Windows reports different st_ctime_ns values through
    # fstat and Path.stat. Reopen the same unlinked regular path and compare
    # fstat with fstat; retain every identity field without a time tolerance.
    with path.open('rb') as current:
        reopened = os.fstat(current.fileno())
        require(stat.S_ISREG(reopened.st_mode), 'reopened regular file required')
    reject_links(path)
    require(identity(before) == identity(after) == identity(reopened) and len(raw) == after.st_size,
            'file identity changed while reading')
    require(hashlib.sha256(raw).hexdigest() == expected, 'frozen bytes changed: ' + str(path))
    return raw, {'path': str(path), 'sha256': expected, 'identity': identity(after)}


def json_capture(name, expected):
    raw, binding = capture(name, expected)
    value = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(value, dict), 'JSON object required')
    return value, binding


def validate_configuration(value):
    require(isinstance(value, dict) and set(value) == {'receipt', 'receipt_sha256'},
            'profile requires exactly receipt and receipt_sha256')
    require(isinstance(value['receipt_sha256'], str) and re.fullmatch('[0-9a-f]{64}', value['receipt_sha256']),
            'independently reviewed receipt SHA-256 required')
    return {'receipt': str(local_path(value['receipt'])), 'receipt_sha256': value['receipt_sha256']}


def validate_scope(checkpoint, context, prompt_cache, draft_tokens, speculation_policy):
    require(checkpoint == 'v2' and type(context) is int and context == 262144 and
            prompt_cache == 'Off' and type(draft_tokens) is int and draft_tokens == 2 and
            speculation_policy == {'HALOGEN_PLD': '3,3'},
            'experiment requires v2, context 262144, cache Off, MTP 2 and PLD 3,3')


def qualify(configuration):
    configuration = validate_configuration(configuration)
    receipt, receipt_binding = json_capture(configuration['receipt'], configuration['receipt_sha256'])
    require(set(receipt) == {'schema', 'image', 'variant', 'library', 'abi_gate', 'component'} and
            receipt['schema'] == 'halogen.rocr-engine-admission.v1' and receipt['image'] == IMAGE and
            receipt['variant'] in ('source_stock', 'candidate'), 'unsupported private engine receipt')
    for key in ('library', 'abi_gate', 'component'):
        require(isinstance(receipt[key], dict) and set(receipt[key]) == {'path', 'sha256'}, 'invalid ' + key + ' binding')
    variant = receipt['variant']
    require(receipt['library']['sha256'] == LIBRARY_SHAS[variant] and
            receipt['abi_gate']['sha256'] == GATE_SHA and receipt['component']['sha256'] == COMPONENT_SHA,
            'receipt does not bind the frozen successful release')
    library_path = local_path(receipt['library']['path'])
    require(library_path.name == 'libhsa-runtime64.so.1', 'private library must be a regular SONAME file')
    _, library_binding = capture(library_path, LIBRARY_SHAS[variant], 16 * 1024**2)
    gate, gate_binding = json_capture(receipt['abi_gate']['path'], GATE_SHA)
    require(gate['schema'] == 'halogen.rocr-private-static-abi-gate.v1' and gate['passed'] is True and
            gate['static_only'] is True and gate['elf_execution_performed'] is False and
            gate['errors'] == [] and gate['unresolved_dependency_availability'] == [] and
            gate['checks']['stock_patched_interface_equal'] is True, 'complete passing static ABI gate required')
    for key, selected in (('original', 'stock'), ('source_stock', 'source_stock'), ('patched', 'candidate')):
        require(gate[key]['sha256'] == LIBRARY_SHAS[selected], 'static gate runtime binding differs')
        if key != 'original':
            check = gate['checks'][key]
            require(all(check[name] is True for name in ('soname_one', 'rocr_version_preserved',
                    'renamed_sysdeps_present', 'static_thunk_graph')) and
                    all(check[name] == [] for name in ('missing_original_exports', 'added_exports',
                    'added_needed', 'forbidden_generic_needed', 'direct_hsakmt_imports')) and
                    check['strong_unversioned_import_closure']['unresolved'] == [], 'incomplete ABI/import closure')
    component, component_binding = json_capture(receipt['component']['path'], COMPONENT_SHA)
    require(component['schema'] == 'halogen.rocr-component-owned.v1' and component['image'] == IMAGE and
            component['passed'] is True and component['contaminated'] is False and component['errors'] == [] and
            component['cleanup_pending'] is False and component['root_runtime_reviewed'] is True and
            component['colleague_preserved'] is True and component['monitor_stopped'] is True and
            component['controller_handle_closed'] is True and component['source_sha256'] == LAUNCHER_SHA and
            component['probe_sha256'] == PROBE_SHA and component['abi_gate_sha256'] == GATE_SHA and
            component['minimum_physical_gib'] >= 18 and component['minimum_commit_gib'] >= 18,
            'complete successful owned component receipt required')
    windows = component['windows']
    require([row['variant'] for row in windows] == ['stock', 'source_stock', 'candidate'], 'three exact component windows required')
    component_root = Path(component_binding['path']).parent
    evidence = []
    probes = []
    for row in windows:
        selected = row['variant']
        require(row['hsa_sha256'] == LIBRARY_SHAS[selected] and row['passed'] is True and
                row['errors'] == [] and row['container_removed'] is True and row['job_closed'] is True and
                row['cleanup_pending'] is False and row['exit_code'] == 0, 'component window failed or cleanup unresolved')
        probe, binding = json_capture(component_root / selected / 'result/probe.json', row['probe_receipt_sha256'])
        require(probe['schema'] == 'halogen.rocr-poll-backoff-component.v1' and probe['image'] == IMAGE and
                probe['passed'] is True and probe['variant'] == selected and probe['cleanup_errors'] == [] and
                probe['bindings']['source']['sha256'] == PROBE_SHA and
                probe['bindings']['hsa']['sha256'] == LIBRARY_SHAS[selected] and
                probe['registered_callback_drain_confirmed'] is True and
                probe['unsafe_object_teardown_skipped'] is False and
                [item['label'] for item in probe['timings']] == ['A', 'B'], 'bound component probe differs')
        probes.append(probe)
        evidence.append(binding)
    require(all([item['output_sha256'] for item in probe['timings']] ==
                [item['output_sha256'] for item in probes[0]['timings']] for probe in probes), 'exact BF16 parity differs')
    for filename, expected in COMPARISON_SHAS.items():
        comparison, binding = json_capture(component_root / filename, expected)
        require(comparison['schema'] == 'halogen.rocr-poll-backoff-component-comparison.v1' and
                comparison['exact_bf16_parity'] is True and comparison['component_only'] is True and
                comparison['token_rate_claim'] is False and comparison['acceptance_claim'] is False,
                'bound component parity comparison differs')
        evidence.append(binding)
    return {'configuration': configuration, 'receipt': receipt_binding, 'image': IMAGE, 'variant': variant,
            'library': library_binding, 'abi_gate': gate_binding, 'component': component_binding, 'evidence': evidence}


def revalidate(qualified):
    if qualified is not None:
        require(qualify(qualified['configuration']) == qualified, 'qualified artifact identity changed before startup')
