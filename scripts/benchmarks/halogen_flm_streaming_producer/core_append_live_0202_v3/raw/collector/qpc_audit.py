"""Pure same-response RAW/QPC audit. No calibration or runtime actions."""
import math
import re


def need(ok, why):
    if not ok:
        raise ValueError(why)


def positive_integer(value, name, maximum=0x7fffffffffffffff):
    need(type(value) is int and 0 < value <= maximum, 'invalid ' + name)
    return value


def digest(value, name):
    need(type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None,
         'invalid ' + name)
    return value


def audit_qpc(report, samples, request_sha256):
    """Compare unadjusted phase bounds with each matching whole-HTTP QPC interval.

    The collector supplies measured QPC seconds. When nanosecond boundaries are
    present, both boundaries must exist and reproduce those seconds exactly.
    Integer QPC differences are used directly for the fit comparison when given.
    """
    digest(request_sha256, 'frozen request SHA256')
    need(type(report) is dict and report.get('schema') == 'halogen0202.raw-side.cohort.v3'
         and report.get('valid') is True and report.get('request_sha256') == request_sha256,
         'RAW validator request identity differs')
    need(report.get('warmup_excluded') is True and report.get('measured_repetitions') == 3,
         'RAW validator cohort convention differs')
    rows = report.get('samples')
    need(type(rows) is list and type(samples) is list and len(rows) == len(samples) == 4,
         'four paired RAW/QPC rows required')
    results = []
    ids = set()
    previous_qpc_end = None
    boundaries_present = []
    cases = {sample.get('case') for sample in samples if type(sample) is dict}
    need(len(cases) == 1, 'RAW/QPC cohort case differs')
    for ordinal, (raw, sample) in enumerate(zip(rows, samples)):
        need(type(raw) is dict and type(sample) is dict, 'invalid RAW/QPC sample')
        need(type(raw.get('ordinal')) is int and type(sample.get('ordinal')) is int
             and raw['ordinal'] == sample['ordinal'] == ordinal, 'RAW/QPC ordinal differs')
        phase = 'warmup_excluded' if ordinal == 0 else 'measured'
        need(raw.get('phase') == sample.get('phase') == phase and raw.get('valid') is True
             and raw.get('api_phase_agreement') is True
             and raw.get('api_native_identity_agreement') is True,
             'RAW/QPC phase or causal native agreement differs')
        request_id = positive_integer(raw.get('request_id'), 'RAW native request ID')
        timings = sample.get('timings')
        need(type(timings) is dict
             and positive_integer(timings.get('raw_native_request_id'), 'API native request ID')
             == request_id, 'RAW/QPC causal native request ID differs')
        need(request_id not in ids, 'RAW/QPC reused native request ID')
        ids.add(request_id)
        response_sha = digest(raw.get('response_sha256'), 'RAW response SHA256')
        need(digest(sample.get('response_sha256'), 'sample response SHA256') == response_sha,
             'RAW/QPC exact response SHA256 differs')
        need(sample.get('request_sha256', request_sha256) == request_sha256,
             'RAW/QPC sample request SHA256 differs')
        if 'API_response_id' in raw and 'API_response_id' in sample:
            need(raw['API_response_id'] == sample['API_response_id'], 'RAW/QPC API response ID differs')
        prompt = positive_integer(sample.get('actual_input_tokens'), 'actual input count', 0xffffffff)
        generated = positive_integer(sample.get('actual_output_tokens'), 'actual output count', 0xffffffff)
        need(generated >= 2 and raw.get('prompt') == prompt and raw.get('generated_begin') == 1
             and raw.get('generated_end') == generated and raw.get('generated_delta') == generated - 1
             and raw.get('decode_numerator') == generated,
             'RAW/QPC actual token counts or native count convention differs')
        cap = positive_integer(raw.get('output_cap'), 'frozen output cap', 0xffffffff)
        need(generated <= cap and sample.get('output_cap', cap) == cap,
             'RAW/QPC output cap differs or actual output exceeds cap')
        qpc = sample.get('http_qpc_seconds')
        need(type(qpc) in (float, int) and math.isfinite(qpc) and qpc > 0,
             'invalid whole-HTTP QPC duration')
        has_start = 'qpc_start_ns' in sample
        has_end = 'qpc_end_ns' in sample
        need(has_start == has_end, 'both QPC boundaries required when provided')
        boundaries_present.append(has_start)
        qpc_ns = qpc * 1e9
        qpc_boundaries = {}
        if has_start:
            start = sample['qpc_start_ns']
            end = sample['qpc_end_ns']
            need(type(start) is int and type(end) is int and 0 <= start < end,
                 'invalid QPC nanosecond boundaries')
            need((end - start) / 1e9 == qpc, 'QPC boundaries and measured seconds differ')
            need(previous_qpc_end is None or start >= previous_qpc_end,
                 'whole-HTTP QPC requests overlap or are reordered')
            previous_qpc_end = end
            qpc_ns = end - start
            qpc_boundaries = dict(qpc_start_ns=start, qpc_end_ns=end,
                                  whole_http_qpc_ns=qpc_ns)
        durations = {}
        for name in ('prefill', 'decode'):
            for suffix in ('raw_lower_ns', 'raw_upper_ns', 'native_ns'):
                key = name + '_' + suffix
                durations[key] = positive_integer(raw.get(key), key)
            need(durations[name + '_raw_lower_ns'] <= durations[name + '_raw_upper_ns'],
                 'invalid RAW phase duration bounds')
        lower = durations['prefill_raw_lower_ns'] + durations['decode_raw_lower_ns']
        upper = durations['prefill_raw_upper_ns'] + durations['decode_raw_upper_ns']
        midpoint = (lower + upper) / 2
        native = (durations['prefill_native_ns'] + durations['decode_native_ns']) / 1e9
        results.append(dict(ordinal=ordinal, phase=phase, case=sample.get('case'),
            native_request_id=request_id, API_response_id=sample.get('API_response_id'),
            response_sha256=response_sha, request_sha256=request_sha256,
            actual_input_tokens=prompt, actual_output_tokens=generated, output_cap=cap,
            generated_begin=1, generated_delta=generated - 1, decode_numerator=generated,
            whole_http_qpc_seconds=qpc, raw_phase_sum_lower_ns=lower,
            raw_phase_sum_mid_ns=midpoint, raw_phase_sum_upper_ns=upper,
            raw_phase_sum_lower_seconds=lower / 1e9,
            raw_phase_sum_mid_seconds=midpoint / 1e9,
            raw_phase_sum_upper_seconds=upper / 1e9,
            http_residual_after_raw_lower_seconds=qpc - lower / 1e9,
            http_residual_after_raw_mid_seconds=qpc - midpoint / 1e9,
            http_residual_after_raw_upper_seconds=qpc - upper / 1e9,
            raw_lower_fits_whole_http=lower <= qpc_ns,
            full_raw_upper_bracket_fits_whole_http=upper <= qpc_ns,
            native_phase_sum_seconds=native,
            native_phase_sum_fits_whole_http=native <= qpc,
            http_residual_after_native_seconds=qpc - native, **qpc_boundaries))
    lower_fit = all(row['raw_lower_fits_whole_http'] for row in results)
    upper_fit = all(row['full_raw_upper_bracket_fits_whole_http'] for row in results)
    return dict(schema='halogen0202.raw-phase.qpc-audit.v1', valid=lower_fit and upper_fit,
        request_sha256=request_sha256, all_lower_bounds_fit=lower_fit,
        all_full_upper_brackets_fit=upper_fit, impossible_phase_duration=not lower_fit,
        measured_repetitions=3, warmup_excluded=True,
        serial_qpc_boundaries_verified=all(boundaries_present),
        pairing='Four serial request ordinals, frozen request SHA, exact response SHA, '
                'causal API/native request ID and actual token counts.',
        adjustment='No scaling, overhead subtraction, correction factor or tolerance.',
        whole_http_convention='QPC begins before posting and ends after response.read. '
                              'It includes post-decode journal flush and excludes collector disk writes.',
        api_phase_clock_qualified=False, samples=results)
