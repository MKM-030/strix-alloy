"""Check the selected real finite device-snapshot mode and charge its commands.

An optional independent scalar-only control proves exact post-resolution rows.
This checks runtime evidence, never executes a model or mutates its state.
"""
import argparse
import json
import math
from pathlib import Path


def finite_ms(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise AssertionError('Elapsed costs must be finite nonnegative numbers')
    return float(value)


def command_cost_ms(row: dict) -> float:
    elapsed = finite_ms(row['elapsed_ms'])
    components = 0.0
    for call in row['native_calls']:
        if 'input_tokens' in call:
            components += sum(finite_ms(call[key]) for key in
                              ('decode_dispatch_ms', 'synchronize_ms', 'logits_readiness_ms',
                               'logits_copy_ms', 'greedy_ms'))
        else:
            components += finite_ms(call['elapsed_ms'])
    if components > elapsed + 0.000001:
        raise AssertionError('Command wall time does not cover all recorded native component costs')
    return elapsed


def check(candidate_path: Path, control_path: Path | None = None, mode: str = 'partial') -> dict:
    if mode not in ('partial', 'full'):
        raise AssertionError('Snapshot mode must be explicitly partial or full')
    full = mode == 'full'
    flags = 2 if full else 3
    mode_name = 'full_device_clear' if full else 'partial_device'
    save_kind = 'save_full_device_snapshot' if full else 'save_partial_device_snapshot'
    restore_kind = 'restore_full_device_snapshot' if full else 'restore_partial_device_snapshot'
    other_save = 'save_partial_device_snapshot' if full else 'save_full_device_snapshot'
    other_restore = 'restore_partial_device_snapshot' if full else 'restore_full_device_snapshot'
    candidate = json.loads(candidate_path.read_bytes())
    if candidate.get('device_rejection_snapshot', False) is not (not full) or candidate.get('full_device_rejection_snapshot', False) is not full:
        raise AssertionError('Candidate does not select exactly the requested snapshot mode')
    # Retained partial receipts predate these fields; full mode requires both explicit pins.
    if candidate.get('device_snapshot_mode', None if full else mode_name) != mode_name or candidate.get('device_snapshot_flags', None if full else flags) != flags:
        raise AssertionError('Candidate snapshot mode/flags differ from the selected mechanism')
    rows = candidate['results']
    measured = rows[4:]
    resolutions = [row for row in measured if row['op'] == 'resolve_replay']
    proposals = [row for row in measured if row['op'] == 'propose']
    if len(resolutions) != 15 or len(proposals) != 15 or len(measured) != 30 or any(
            row['op'] != ('propose' if index % 2 == 0 else 'resolve_replay') for index, row in enumerate(measured)):
        raise AssertionError('Expected all15 consecutive complete measured proposal/resolution pairs')
    for row in measured:
        if any(call['kind'] in ('clear_both_caches', 'prefill', 'snapshot_save_failed', 'snapshot_restore_fallback')
               for call in row['native_calls']):
            raise AssertionError('Measured snapshot path failed or rebuilt the full prefix')
        if any(call['kind'] in (other_save, other_restore) for call in row['native_calls']):
            raise AssertionError('Measured calls use a different snapshot mechanism')
        if any(call.get('input_tokens') != 1 for call in row['native_calls']
               if call['kind'] in ('speculative_forward', 'authoritative_replay', 'authoritative_forward')):
            raise AssertionError('Measured speculative and authoritative updates must remain scalar')
    restores = 0
    private_clears = 0
    for index, (proposal, resolution) in enumerate(zip(proposals, resolutions)):
        saves = [call for call in proposal['native_calls'] if call['kind'] == save_kind]
        if len(saves) != 1 or proposal['native_calls'][0]['kind'] != save_kind:
            raise AssertionError(f'Round{index}: expected one real snapshot before speculative inputs')
        saved = saves[0]
        if not isinstance(saved['metadata_bytes'], int) or not 0 < saved['metadata_bytes'] <= 64 * 1024 * 1024:
            raise AssertionError(f'Round{index}: snapshot metadata exceeds the finite bound')
        restored = [call for call in resolution['native_calls'] if call['kind'] == restore_kind]
        clears = [call for call in resolution['native_calls'] if call['kind'] == 'clear_private_context_for_full_snapshot']
        if len(restored) > 1 or len(clears) != (len(restored) if full else 0):
            raise AssertionError(f'Round{index}: full restoration must have exactly one private context clear')
        if full:
            if saved.get('flags') != flags or saved.get('sequence_id') != 0 or saved.get('committed_length') != proposal['committed_length'] or saved.get('context_epoch') != proposal['context_epoch']:
                raise AssertionError(f'Round{index}: full save is not bound to flags2/seq0/current committed boundary')
            if restored:
                actual = restored[0]
                calls = resolution['native_calls']
                if len(calls) < 2 or calls[0]['kind'] != 'clear_private_context_for_full_snapshot' or calls[1]['kind'] != restore_kind:
                    raise AssertionError(f'Round{index}: full private clear/restore must precede authoritative replay')
                if clears[0].get('data') is not True or clears[0].get('sequence_count') != 1:
                    raise AssertionError(f'Round{index}: full rollback must clear data in the private one-sequence context')
                if actual.get('flags') != flags or actual.get('sequence_id') != 0 or actual.get('metadata_bytes') != saved['metadata_bytes'] or actual.get('committed_length') != proposal['committed_length'] or actual.get('restored_position') != proposal['committed_length'] - 1 or actual.get('snapshot_context_epoch') != proposal['context_epoch']:
                    raise AssertionError(f'Round{index}: full restore byte count/flags/boundary differs from its save')
                if resolution['update_path'] != 'full_device_snapshot_restore':
                    raise AssertionError(f'Round{index}: full restore path was not recorded')
        restores += len(restored)
        private_clears += len(clears)
    if not restores:
        raise AssertionError('No rejected-input device restoration was exercised')
    if rows[3]['op'] != 'prefill':
        raise AssertionError('Expected the measured initial seed prefill')
    seed_ms = command_cost_ms(rows[3])
    proposal_ms = sum(command_cost_ms(row) for row in proposals)
    resolution_ms = sum(command_cost_ms(row) for row in resolutions)
    component_ms = seed_ms + proposal_ms + resolution_ms
    snapshot_write_ms = sum(finite_ms(row['snapshot_write_ms']) for row in [rows[3], *measured])
    verified = 0
    if control_path is not None:
        control = json.loads(control_path.read_bytes())
        for key in ('format', 'source_revision', 'model_file', 'dll_bundle_directory',
                    'backend', 'device_index', 'device_id', 'f32_row_count', 'actual_n_ctx', 'actual_n_ctx_seq',
                    'actual_n_batch', 'actual_n_ubatch', 'n_threads', 'n_threads_batch',
                    'requested_n_gpu_layers', 'offload_kqv', 'op_offload'):
            if candidate[key] != control[key]:
                raise AssertionError(f'Candidate/control binding differs: {key}')
        if control.get('device_rejection_snapshot', False) is not False or control.get('full_device_rejection_snapshot', False) is not False or control.get('device_snapshot_mode', 'off') != 'off' or control.get('device_snapshot_flags', 0) != 0:
            raise AssertionError('Expected an independent snapshot-off scalar control')
        control_updates = control['results'][4:]
        if len(control_updates) != 37 or any(row['op'] != 'forward' for row in control_updates):
            raise AssertionError('Control must apply all37 authoritative IDs without measured speculative calls')
        if any(len(row['native_calls']) != 1 or row['native_calls'][0].get('input_tokens') != 1 or
               row['native_calls'][0]['kind'] != 'authoritative_forward' for row in control_updates):
            raise AssertionError('Control updates must use only consecutive scalar authoritative forwards')
        by_length = {row['committed_length']: row for row in control['results']}
        candidate_rows = Path(str(candidate_path) + '.rows')
        control_rows = Path(str(control_path) + '.rows')
        initial, initial_control = rows[3], control['results'][3]
        if initial['op'] != 'prefill' or initial_control['op'] != 'prefill' or initial['committed_ids'] != initial_control['committed_ids']:
            raise AssertionError('Measured initial prefixes differ')
        initial_bytes = (candidate_rows / initial['committed_f32_file']).read_bytes()
        if len(initial_bytes) != 993280 or initial_bytes != (control_rows / initial_control['committed_f32_file']).read_bytes():
            raise AssertionError('Initial full F32 rows differ before speculation')
        for index, row in enumerate(resolutions):
            expected = by_length[row['committed_length']]
            if row['committed_ids'] != expected['committed_ids']:
                raise AssertionError(f'Round{index}: committed token histories differ')
            actual_bytes = (candidate_rows / row['committed_f32_file']).read_bytes()
            expected_bytes = (control_rows / expected['committed_f32_file']).read_bytes()
            if len(actual_bytes) != 993280 or actual_bytes != expected_bytes:
                raise AssertionError(f'Round{index}: full F32 row differs from authoritative scalar control')
            verified += 1
    return {'complete_resolutions': len(resolutions), 'full_prefix_rebuilds': 0,
            'snapshot_mode': mode_name, 'snapshot_flags': flags,
            'exact_scalar_control_rows': verified,
            'initial_row_exact': control_path is not None,
            'measured_device_snapshots': len(proposals), 'measured_device_restores': restores,
            'measured_private_context_clears': private_clears,
            'initial_prefill_ms': seed_ms, 'all_proposals_ms': proposal_ms, 'all_resolutions_ms': resolution_ms,
            'charged_component_ms': component_ms, 'seed_amortized_ms_per_round': component_ms / len(resolutions),
            'diagnostic_f32_write_ms': snapshot_write_ms,
            'state_parity_qualified': control_path is not None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--control', type=Path)
    parser.add_argument('--mode', choices=('partial', 'full'), default='partial')
    args = parser.parse_args()
    print(json.dumps(check(args.candidate, args.control, mode=args.mode)))
