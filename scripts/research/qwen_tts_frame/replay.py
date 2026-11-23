"""Compare an offline CPU acoustic frame with a qwentts.cpp Vulkan dump."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .fixtures import acoustic_sampler_inputs, load_native_frame, load_native_logits
from .frame import FramePredictor, FrameResult, ranked_cdf, sample_code
from .weights import load_weights

TOP_K = 50


def _digest(values, dtype):
    return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes()).hexdigest()


def _head_diagnostics(reference, forced, temperature, uniforms):
    heads = []
    for codebook, logits in enumerate(forced.logits, start=1):
        expected_code = int(reference[codebook])
        selected_code = int(forced.codes[codebook])
        expected_logit = logits[expected_code]
        competitors = logits.copy()
        competitors[expected_code] = -np.inf
        best_other_code = int(np.argmax(competitors))
        ranked, cdf = ranked_cdf(logits, temperature, TOP_K)
        matches = np.flatnonzero(ranked == expected_code)
        interval = None
        if matches.size:
            index = matches[0]
            interval = [float(cdf[index - 1]) if index else 0.0, float(cdf[index])]
        heads.append({
            'codebook': codebook,
            'reference_code': expected_code,
            'selected_code': selected_code,
            'reference_rank': int(np.count_nonzero(logits > expected_logit)) + 1,
            'reference_rank_ties': int(np.count_nonzero(logits == expected_logit)),
            'reference_logit': float(expected_logit),
            'selected_logit': float(logits[selected_code]),
            'best_other_code': best_other_code,
            'best_other_logit': float(logits[best_other_code]),
            'reference_margin_to_best_other': float(expected_logit) - float(logits[best_other_code]),
            'replay_reference_cdf_interval': interval,
            'uniform_draw': float(uniforms[codebook - 1]),
        })
    return heads


def _compare(args):
    name = args.name.strip()
    if not name:
        raise ValueError('Provide a name for the local frame fixture')
    subsequence_base = args.frame_index * 16
    temperature, uniforms = acoustic_sampler_inputs(args.seed, subsequence_base, args.temperature)
    hidden, reference = load_native_frame(args.dump_dir, args.frame_index)
    native_logits = load_native_logits(args.dump_dir, args.frame_index, reference) if args.native_logits else None
    weights = load_weights(args.gguf)
    predictor = FramePredictor(weights)
    predicted = predictor.predict(hidden, int(reference[0]), temperature, uniforms, top_k=TOP_K)

    differences = np.flatnonzero(reference != predicted.codes)
    first_mismatch = None
    teacher_forced = None
    native = None
    if differences.size:
        first = int(differences[0])
        first_mismatch = {
            'codebook': first,
            'reference_code': int(reference[first]),
            'predicted_code': int(predicted.codes[first]),
        }
    if differences.size or native_logits is not None:
        forced = predictor.predict(
            hidden, int(reference[0]), temperature, uniforms, top_k=TOP_K,
            forced_codes=reference[1:],
        )
        teacher_forced = {
            'logits_f32_le_sha256': _digest(forced.logits, '<f4'),
            'heads': _head_diagnostics(reference, forced, temperature, uniforms),
        }
    if native_logits is not None:
        resampled = np.empty_like(reference)
        resampled[0] = reference[0]
        for head, logits in enumerate(native_logits):
            resampled[head + 1] = sample_code(logits, temperature, uniforms[head], TOP_K)
        native = {
            'logits_f32_le_sha256': _digest(native_logits, '<f4'),
            'host_sampler_matches': int(np.count_nonzero(resampled[1:] == reference[1:])),
            'heads': _head_diagnostics(reference, FrameResult(resampled, native_logits), temperature, uniforms),
            'max_abs_logit_delta_per_head': np.max(np.abs(forced.logits - native_logits), axis=1).tolist(),
        }

    return {
        'schema': 'qwen_tts_frame.offline_replay.v1',
        'execution': 'offline_cpu_numpy',
        'fixture': {
            'name': name,
            'frame_index': args.frame_index,
            'seed': args.seed,
            'temperature': args.temperature,
            'effective_temperature': float(temperature),
            'subsequence_base': subsequence_base,
            'top_k': TOP_K,
            'hidden_f32_le_sha256': _digest(hidden, '<f4'),
            'uniforms_f32_le_sha256': _digest(uniforms, '<f4'),
        },
        'weights': {key: value for key, value in weights.receipt.items() if key != 'path'},
        'exact_code_match': first_mismatch is None,
        'expected_codes': reference.tolist(),
        'predicted_codes': predicted.codes.tolist(),
        'expected_codes_sha256': _digest(reference, '<i4'),
        'predicted_codes_sha256': _digest(predicted.codes, '<i4'),
        'first_mismatch': first_mismatch,
        'teacher_forced': teacher_forced,
        'native_logits': native,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gguf', type=Path, required=True, help='Pinned Qwen3-TTS Base Q8_0 model')
    parser.add_argument('--dump-dir', type=Path, required=True, help='Directory with the native frame dump')
    parser.add_argument('--name', required=True, help='Name for the captured frame in the JSON report')
    parser.add_argument('--seed', type=int, required=True, help='Resolved native request seed')
    parser.add_argument('--temperature', type=float, required=True, help='Native subtalker temperature, 0 for greedy')
    parser.add_argument('--frame-index', type=int, choices=(0, 1), default=0)
    parser.add_argument('--native-logits', action='store_true', help='Compare against private Vulkan logits dumps')
    args = parser.parse_args(argv)

    try:
        report = _compare(args)
    except (OSError, OverflowError, ValueError) as error:
        print(json.dumps({'error': str(error)}))
        return 2

    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['exact_code_match'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
