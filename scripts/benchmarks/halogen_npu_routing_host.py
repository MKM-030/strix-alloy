"""Bounded, CPU-only routing and dispatch preparation for the NPU prototype.

This does not initialize an EP, decode expert weights, compile a graph, or alter
Halogen state. The measured graph accepts changing coefficients, not changing
expert IDs. A graph miss is an explicit failure, never an implicit compilation.
Routing follows the public Qwen4Exp router; Halogen parity needs live traces.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

EXPERTS = 512
TOP_K = 10
HIDDEN = 2560
GIB = 1 << 30
DECODED_TOP10_BYTES = 196_608_000
ROUTER_BYTES = EXPERTS * HIDDEN * 2


@dataclass(frozen=True)
class Route:
    selected_experts: tuple
    ranked_experts: tuple
    coefficients: np.ndarray
    selected_probability_mass: float
    boundary_probability_margin: float
    coefficient_dtype: str
    normalized: bool


def _ids(values):
    if (not isinstance(values, (tuple, list)) or len(values) != TOP_K
            or any(type(index) is not int or not 0 <= index < EXPERTS for index in values)
            or len(set(values)) != TOP_K):
        raise ValueError('requires ten unique integer expert IDs from 0 through 511')
    return tuple(values)


def _bf16_round(values):
    # Finite FP32 -> BF16 round-to-nearest-even -> exactly representable FP32.
    bits = np.asarray(values, dtype=np.float32).view(np.uint32)
    rounded = (bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) & np.uint32(0xffff0000)
    return rounded.view(np.float32)


def route_top10(logits, *, normalize=True, coefficient_dtype='bfloat16'):
    """Select one token's scores; reject a tie across the 10th/11th boundary.

    Coefficients are stored in sorted expert-ID order, with their association
    preserved. BF16 is the model-config dtype; FP32 is a comparison mode.
    NumPy's softmax/reduction is a CPU reference, not Halogen arithmetic parity.
    """
    values = np.asarray(logits)
    if values.shape != (EXPERTS,) or values.dtype.kind not in 'fiu':
        raise ValueError('requires one numeric vector of 512 router logits')
    if type(normalize) is not bool or coefficient_dtype not in ('float32', 'bfloat16'):
        raise ValueError('invalid router normalization or coefficient dtype')
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        values = values.astype(np.float32)
        if not np.isfinite(values).all():
            raise ValueError('router logits must be finite float32 values')
        exponentials = np.exp(values - values.max())
        probabilities = exponentials / np.sum(exponentials, dtype=np.float32)
    ranked = np.argsort(-probabilities, kind='stable')
    margin = float(probabilities[ranked[TOP_K - 1]] - probabilities[ranked[TOP_K]])
    if margin == 0:
        raise ValueError('top10 boundary tie: exact target selection must be supplied')
    top_ids = ranked[:TOP_K]
    selected = tuple(sorted(map(int, top_ids)))
    mass = float(np.sum(probabilities[top_ids], dtype=np.float32))
    weights = probabilities[top_ids].copy()
    if normalize:
        weights /= np.float32(mass)
    if coefficient_dtype == 'bfloat16':
        weights = _bf16_round(weights)
    by_id = dict(zip(map(int, top_ids), weights))
    packed = np.asarray([by_id[index] for index in selected], dtype=np.float32)
    packed.setflags(write=False)
    return Route(selected, tuple(map(int, top_ids)), packed, mass, margin,
                 coefficient_dtype, normalize)


def pack_for_graph(route, graph_experts):
    """Return FP32[10,1,1] in the existing graph's exact expert order."""
    graph_experts = _ids(graph_experts)
    selected = _ids(route.selected_experts)
    if set(graph_experts) != set(selected):
        raise ValueError('graph miss: selected IDs differ; dispatch refused')
    coefficients = np.asarray(route.coefficients, dtype=np.float32)
    if coefficients.shape != (TOP_K,) or not np.isfinite(coefficients).all() or (coefficients < 0).any():
        raise ValueError('invalid route coefficients')
    by_id = dict(zip(selected, coefficients))
    return np.asarray([by_id[index] for index in graph_experts], dtype=np.float32).reshape(TOP_K, 1, 1)


def graph_cache_key(selected_experts, *, checkpoint_manifest_sha256, builder_sha256,
                    provider_manifest_sha256, runtime_config_sha256):
    """Identity for a new canonical-ID graph; does not establish cache validity.

    The caller must verify the graph/weight receipt and compiled-context hashes
    on a cache hit. Runtime configuration includes ORT, IR/opset, provider
    options, device/driver identity, input ABI, and fallback policy.
    """
    identity = {'selected_experts': sorted(_ids(selected_experts)),
                'checkpoint_manifest_sha256': checkpoint_manifest_sha256,
                'builder_sha256': builder_sha256, 'provider_manifest_sha256': provider_manifest_sha256,
                'runtime_config_sha256': runtime_config_sha256,
                'graph_contract': 'fixed-top10; x=float32[1,2560]; routing=float32[10,1,1]'}
    for field in ('checkpoint_manifest_sha256', 'builder_sha256', 'provider_manifest_sha256',
                  'runtime_config_sha256'):
        value = identity[field]
        if not isinstance(value, str) or len(value) != 64 or any(char not in '0123456789abcdef' for char in value):
            raise ValueError('requires lowercase SHA-256 for ' + field)
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def memory_admission(physical_available_bytes, commit_headroom_bytes, runtime_incremental_bytes,
                     transient_bytes):
    """Plan an additional fixed-top10 session, preserving 18 GiB in both pools.

    Available memory already excludes existing sessions; avoid double-counting
    them. Incremental and peak transient estimates must include provider-owned
    buffers, compilation/context copies and retained weights. Unknown estimates
    refuse admission. This is a snapshot calculation, not a live process guard.
    """
    for value in (physical_available_bytes, commit_headroom_bytes):
        if type(value) is not int or value < 0:
            raise ValueError('memory availability must be nonnegative integer bytes')
    for value in (runtime_incremental_bytes, transient_bytes):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError('memory estimates must be nonnegative integer bytes or unknown')
    if runtime_incremental_bytes is None or transient_bytes is None:
        return {'admitted': False, 'reason': 'runtime or transient estimate is unknown',
                'reserve_bytes': 18 * GIB, 'physical_remaining_bytes': None,
                'commit_remaining_bytes': None}
    if runtime_incremental_bytes < DECODED_TOP10_BYTES:
        raise ValueError('runtime estimate is smaller than the known decoded top10 weights')
    required = runtime_incremental_bytes + transient_bytes
    physical_remaining = physical_available_bytes - required
    commit_remaining = commit_headroom_bytes - required
    admitted = min(physical_remaining, commit_remaining) >= 18 * GIB
    return {'admitted': admitted, 'reason': 'reserve satisfied' if admitted else '18 GiB reserve would be violated',
            'reserve_bytes': 18 * GIB, 'candidate_peak_bytes': required,
            'physical_remaining_bytes': physical_remaining, 'commit_remaining_bytes': commit_remaining}


def load_router_bf16(manifest_path, payload_path, *, expected_manifest_sha256):
    """Read only the already-extracted 2.5 MiB BF16 router, with trusted hashes.

    This consumes a caller-supplied trusted manifest SHA, never the full HGN.
    HGN store0 is BF16 as established by the retained Halogen inspector report.
    Bounded reads reject growth/truncation and avoid unbounded read_bytes().
    """
    with Path(manifest_path).open('rb') as stream:
        manifest_raw = stream.read(256 * 1024 + 1)
    if len(manifest_raw) > 256 * 1024:
        raise ValueError('manifest exceeds bounded 256 KiB limit')
    if hashlib.sha256(manifest_raw).hexdigest() != expected_manifest_sha256:
        raise ValueError('manifest SHA differs from the trusted identity')
    manifest = json.loads(manifest_raw)
    if manifest.get('identity') != 'qwen3.8-flash-next' or manifest.get('version') != 2:
        raise ValueError('unexpected router checkpoint manifest identity')
    entries = [entry for entry in manifest['entries'] if entry['name'] == 'mtp.layers.0.mlp.gate.weight']
    if len(entries) != 1:
        raise ValueError('manifest requires exactly one MTP router entry')
    entry = entries[0]
    if ((entry['store'], entry['variant'], entry['rank'], entry['dims'], entry['size'])
            != (0, 0, 2, [EXPERTS, HIDDEN], ROUTER_BYTES)):
        raise ValueError('unexpected BF16 router geometry or storage')
    with Path(payload_path).open('rb') as stream:
        payload = stream.read(ROUTER_BYTES + 1)
    if len(payload) != ROUTER_BYTES:
        raise ValueError('router payload size differs from manifest')
    if hashlib.sha256(payload).hexdigest() != entry['sha256']:
        raise ValueError('router payload SHA differs from manifest')
    checksum = int(np.bitwise_xor.reduce(np.frombuffer(payload, dtype='<u4'), initial=np.uint32(0)))
    if checksum != entry['xor32']:
        raise ValueError('router payload XOR differs from manifest')
    bits = np.frombuffer(payload, dtype='<u2').astype(np.uint32) << 16
    weights = bits.view(np.float32).reshape(EXPERTS, HIDDEN)
    if not np.isfinite(weights).all():
        raise ValueError('router weights are not finite')
    return weights


def router_logits_fp32(hidden, router_weights):
    """Reference matvec on supplied MLP input; does not reproduce Halogen BF16.

    The MLP input is 2560-wide after its hyperconnection mixer. A raw target
    10240-wide residual is insufficient. Returned logits are FP32, including
    accumulation/output; call-site BF16 behavior requires separate validation.
    """
    hidden = np.asarray(hidden, dtype=np.float32)
    router_weights = np.asarray(router_weights, dtype=np.float32)
    if (hidden.shape != (HIDDEN,) or router_weights.shape != (EXPERTS, HIDDEN)
            or not np.isfinite(hidden).all() or not np.isfinite(router_weights).all()):
        raise ValueError('requires finite hidden[2560] and router_weights[512,2560]')
    with np.errstate(over='ignore', invalid='ignore'):
        logits = router_weights @ hidden
    if not np.isfinite(logits).all():
        raise ValueError('router FP32 reference matvec overflowed')
    return logits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--logits', required=True, type=Path, help='JSON vector of 512 supplied scores')
    parser.add_argument('--coefficient-dtype', choices=('bfloat16', 'float32'), default='bfloat16')
    parser.add_argument('--graph-experts', help='exact ten comma-separated IDs in existing graph order')
    args = parser.parse_args()
    try:
        with args.logits.open('rb') as stream:
            raw = stream.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            raise ValueError('logits input exceeds bounded 64 KiB JSON limit')
        route = route_top10(json.loads(raw.decode('utf-8')),
                            coefficient_dtype=args.coefficient_dtype)
        graph_experts = (tuple(int(part) for part in args.graph_experts.split(','))
                         if args.graph_experts is not None else route.selected_experts)
        packed = pack_for_graph(route, graph_experts)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, str(exc) + '\n')
    print(json.dumps({'schema': 1, 'scope': 'CPU host route packing; no EP or Halogen state',
                      'halogen_equivalence_qualified': False,
                      'selected_experts': route.selected_experts, 'ranked_experts': route.ranked_experts,
                      'graph_experts': graph_experts, 'routing_shape': list(packed.shape),
                      'routing_weights': packed.tolist(), 'coefficient_dtype': route.coefficient_dtype,
                      'selected_probability_mass': route.selected_probability_mass,
                      'boundary_probability_margin': route.boundary_probability_margin}, indent=2))


if __name__ == '__main__':
    main()
