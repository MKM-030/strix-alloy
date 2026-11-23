"""Compare an offline CPU acoustic frame with a qwentts.cpp first-frame dump."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .fixtures import acoustic_sampler_inputs, load_first_frame
from .frame import FramePredictor, ranked_cdf
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
    temperature, uniforms = acoustic_sampler_inputs(args.seed, 0, args.temperature)
    hidden, reference = load_first_frame(args.dump_dir)
    weights = load_weights(args.gguf)
    predictor = FramePredictor(weights)
    predicted = predictor.predict(hidden, int(reference[0]), temperature, uniforms, top_k=TOP_K)

    differences = np.flatnonzero(reference != predicted.codes)
    first_mismatch = None
    teacher_forced = None
    if differences.size:
        first = int(differences[0])
        first_mismatch = {
            'codebook': first,
            'reference_code': int(reference[first]),
            'predicted_code': int(predicted.codes[first]),
        }
        forced = predictor.predict(
            hidden, int(reference[0]), temperature, uniforms, top_k=TOP_K,
            forced_codes=reference[1:],
        )
        teacher_forced = {
            'logits_f32_le_sha256': _digest(forced.logits, '<f4'),
            'heads': _head_diagnostics(reference, forced, temperature, uniforms),
        }

    return {
        'schema': 'qwen_tts_frame.offline_replay.v1',
        'execution': 'offline_cpu_numpy',
        'fixture': {
            'name': name,
            'frame_index': 0,
            'seed': args.seed,
            'temperature': args.temperature,
            'effective_temperature': float(temperature),
            'subsequence_base': 0,
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
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gguf', type=Path, required=True, help='Pinned Qwen3-TTS Base Q8_0 model')
    parser.add_argument('--dump-dir', type=Path, required=True, help='Directory with the native first-frame dump')
    parser.add_argument('--name', required=True, help='Name for the captured frame in the JSON report')
    parser.add_argument('--seed', type=int, required=True, help='Resolved native request seed')
    parser.add_argument('--temperature', type=float, required=True, help='Native subtalker temperature, 0 for greedy')
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
