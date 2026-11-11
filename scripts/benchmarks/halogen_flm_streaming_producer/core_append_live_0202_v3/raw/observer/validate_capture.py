"""Offline exact-0.20.2 RAW journal validation against one causal API response."""
import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

MAGIC = 0x3357415231393048
HEADER = struct.Struct('<8Q')
RECORD = struct.Struct('<6Q4q4Q4Iq')
CAPTURE_BYTES = HEADER.size + 64 * RECORD.size
FIELDS = ('caller_rva caller_stack saved_r14 saved_r15 saved_rbx object request_id native '
          'native_start tid raw_before raw_after prefill_accum_bits published_prefill_bits '
          'site status prompt generated native_slot').split()
BINDING = Path(__file__).resolve().parent.parent / 'binding.json'
PHASE_ROUNDING_MS = 0.050001


class UnsupportedCapture(ValueError):
    """The native endpoint convention cannot qualify this request's phases."""


def need(ok, why):
    if not ok:
        raise ValueError(why)


def positive_int(value, name, maximum=0x7fffffffffffffff):
    need(type(value) is int and 0 < value <= maximum, 'invalid ' + name)
    return value


def bound_pcs():
    binding = json.loads(BINDING.read_bytes())
    need(binding.get('provider') and binding.get('fresh_provider_verified') is True,
         'fresh ELF/provider binding incomplete')
    need(binding.get('engine_sha256') ==
         'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c',
         'wrong exact engine binding')
    names = ('prefill_begin', 'prefill_end', 'decode_begin', 'decode_end')
    need(tuple(row['name'] for row in binding['endpoints']) == names,
         'unexpected endpoint binding order')
    return {i + 1: int(row['return_rva'], 16)
            for i, row in enumerate(binding['endpoints'])}


def f64(bits):
    return struct.unpack('<d', struct.pack('<Q', bits))[0]


def parse_epoch(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{16}', value) is not None,
         'epoch must be 16 lowercase hexadecimal digits')
    nonce = int(value, 16)
    need(nonce != 0, 'epoch nonce must be nonzero')
    return nonce


def read_capture(data, expected_ordinal=None, expected_epoch=None):
    need(len(data) == CAPTURE_BYTES, 'incomplete or wrong-sized journal')
    magic, version, count, flags, done, ordinal, cohort_count, epoch_nonce = HEADER.unpack_from(data)
    need(magic == MAGIC and version == 3, 'unsupported journal identity/version')
    need(flags == 0, 'capture flagged overflow, interference or unknown failure')
    need(done == 1 and 0 < count <= 64 and cohort_count == 4 and ordinal < 4,
         'invalid header or incomplete capture')
    need(epoch_nonce != 0 and (expected_epoch is None or epoch_nonce == expected_epoch),
         'missing or wrong capture epoch nonce')
    need(expected_ordinal is None or ordinal == expected_ordinal, 'wrong capture ordinal')
    return [dict(zip(FIELDS, RECORD.unpack_from(data, HEADER.size + i * RECORD.size)))
            for i in range(count)]


def response_counts(response, request=None, require_cold=False):
    """Bind OAI usage counters and private D-record identity before reading journals."""
    need(type(response) is dict and type(response.get('usage')) is dict
         and type(response.get('timings')) is dict, 'missing OAI response usage/timings')
    usage = response['usage']
    timings = response['timings']
    prompt = positive_int(usage.get('prompt_tokens'), 'actual API prompt count', 0xffffffff)
    generated = usage.get('completion_tokens')
    need(type(generated) is int and 0 <= generated <= 0xffffffff, 'invalid actual API output count')
    request_id = positive_int(timings.get('raw_native_request_id'), 'causal API native request ID')
    cached = timings.get('cache_n', 0)
    processed = timings.get('prompt_n')
    need(type(cached) is int and 0 <= cached <= prompt, 'invalid API cached prompt count')
    need(type(processed) is int and processed == prompt - cached,
         'API processed/full/cached prompt counts differ')
    need(timings.get('predicted_n') == generated
         and type(timings.get('predicted_n')) is int, 'API predicted/actual output counts differ')
    need(type(usage.get('total_tokens')) is int
         and usage['total_tokens'] == prompt + generated, 'API total token count differs')
    if require_cold:
        need(cached == 0, 'cold capture required but API reports cached prompt tokens')
    if generated < 2:
        raise UnsupportedCapture('actual output below 2 has no bound native decode-end timestamp')
    if processed == 0:
        raise UnsupportedCapture('zero processed prompt tokens cannot qualify a prefill rate')
    cap = None
    if request is not None:
        need(type(request) is dict and request.get('stream', False) is False,
             'one nonstreaming frozen request required')
        caps = [(key, request[key]) for key in
                ('max_completion_tokens', 'max_output_tokens', 'max_tokens') if key in request]
        need(len(caps) == 1, 'one explicit frozen output cap required')
        cap = positive_int(caps[0][1], 'frozen output cap', 0xffffffff)
        need(generated <= cap, 'actual API output exceeds frozen output cap')
    return dict(request_id=request_id, prompt=prompt, generated=generated,
                processed_prompt=processed, cached_prompt=cached, output_cap=cap)


def validate(events, response, pcs=None, request=None, require_cold=False):
    counts = response_counts(response, request, require_cold)
    pcs = bound_pcs() if pcs is None else pcs
    need(4 <= len(events) <= 64, 'missing or excessive endpoint records')
    ids = {event['request_id'] for event in events}
    need(ids == {counts['request_id']}, 'RAW/API native request ID differs or mixed IDs')
    slots = {event['native_slot'] for event in events}
    need(len(slots) == 1 and next(iter(slots)) in (0, 1), 'mixed or invalid two-slot identity')
    pf_open = {}
    pf_pairs = []
    decode_begin = None
    decode_pair = None
    previous_after = 0
    for event in events:
        need(event['raw_before'] >= previous_after, 'global RAW event order violated')
        previous_after = event['raw_after']
        need(event['prompt'] == counts['prompt'], 'RAW/API actual prompt count differs')
        site = event['site']
        need(site in pcs and event['caller_rva'] == pcs[site], 'unbound endpoint')
        need(event['status'] == 0, 'capture event flagged invalid')
        need(0 < event['raw_before'] <= event['raw_after'], 'invalid RAW bracket')
        expected_object = event['saved_r15'] if site <= 2 else event['saved_r14']
        need(event['object'] == expected_object, 'saved register/object mismatch')
        key = (event['object'], event['caller_stack'], event['tid'])
        if site == 1:
            need(not pf_open and decode_begin is None and decode_pair is None, 'nested or late PF')
            need(event['native_start'] == event['native'], 'PF begin native mismatch')
            pf_open[key] = event
        elif site == 2:
            need(key in pf_open, 'PF end has no matching begin')
            begin = pf_open.pop(key)
            need(event['native_start'] == begin['native'], 'PF native start mismatch')
            pf_pairs.append((begin, event))
        elif site == 3:
            need(decode_begin is None and decode_pair is None and pf_pairs and not pf_open,
                 'decode before closed PF or duplicate decode begin')
            need(event['native_start'] == event['native'], 'decode begin native mismatch')
            decode_begin = event
        else:
            need(decode_begin is not None and decode_pair is None, 'decode end missing/duplicated begin')
            need(event['native_start'] == decode_begin['native'] == event['saved_rbx'],
                 'decode carried/object native start mismatch')
            decode_pair = (decode_begin, event)
    need(not pf_open and pf_pairs and decode_pair is not None, 'unclosed phases')
    need(events[-1]['site'] == 4, 'decode end must close capture')

    def duration(pair):
        begin, end = pair
        need(end['native'] >= begin['native'] and end['raw_before'] >= begin['raw_after'],
             'backward or overlapping pair timestamps')
        return (end['native'] - begin['native'],
                end['raw_before'] - begin['raw_after'],
                end['raw_after'] - begin['raw_before'])

    prefill = [duration(pair) for pair in pf_pairs]
    decode_native, decode_lower, decode_upper = duration(decode_pair)
    prior = 0
    for (begin, end), (native, _, _) in zip(pf_pairs, prefill):
        for event in (begin, end):
            accumulated = f64(event['prefill_accum_bits'])
            need(math.isfinite(accumulated) and abs(accumulated - prior / 1e6) <= 1e-6,
                 'PF accumulator prefix differs from native pair sum')
        prior += native
    prefill_native = sum(item[0] for item in prefill)
    prefill_lower = sum(item[1] for item in prefill)
    prefill_upper = sum(item[2] for item in prefill)
    published_begin = f64(decode_pair[0]['published_prefill_bits'])
    published = f64(decode_pair[1]['published_prefill_bits'])
    need(math.isfinite(published_begin) and abs(published_begin - published) <= 1e-6,
         'decode published PF changed')
    need(math.isfinite(published) and abs(published - prefill_native / 1e6) <= 1e-6,
         'published PF differs from native pair sum')
    begin, end = decode_pair
    need(begin['generated'] == 1 and end['generated'] == counts['generated'],
         'native count convention or RAW/API actual output differs')
    if min(prefill_native, prefill_lower, decode_native, decode_lower) <= 0:
        raise UnsupportedCapture('zero phase duration cannot qualify a phase rate')
    for name, native in (('prefill', prefill_native), ('decode', decode_native)):
        value = response['timings'].get('prompt_ms' if name == 'prefill' else 'predicted_ms')
        need(type(value) in (int, float) and math.isfinite(value)
             and abs(value - native / 1e6) <= PHASE_ROUNDING_MS,
             'API native ' + name + ' differs beyond D-record rounding')
    report = dict(schema='halogen0202.raw-side.report.v3', valid=True,
                  request_id=counts['request_id'], native_slot=next(iter(slots)),
                  records=len(events), prefill_pairs=len(prefill), prompt=counts['prompt'],
                  processed_prompt=counts['processed_prompt'], cached_prompt=counts['cached_prompt'],
                  output_cap=counts['output_cap'], generated_begin=begin['generated'],
                  generated_end=end['generated'], generated_delta=end['generated'] - begin['generated'],
                  decode_numerator=counts['generated'],
                  prefill_native_ns=prefill_native, prefill_raw_lower_ns=prefill_lower,
                  prefill_raw_upper_ns=prefill_upper, decode_native_ns=decode_native,
                  decode_raw_lower_ns=decode_lower, decode_raw_upper_ns=decode_upper,
                  published_prefill_ms=published, api_native_identity_agreement=True,
                  api_phase_agreement=True, api_phase_rounding_tolerance_ms=PHASE_ROUNDING_MS)
    for name, numerator in (('prefill', counts['processed_prompt']), ('decode', counts['generated'])):
        native = report[name + '_native_ns']
        lower = report[name + '_raw_lower_ns']
        upper = report[name + '_raw_upper_ns']
        report[name + '_native_over_raw_mid'] = native / ((lower + upper) / 2)
        report[name + '_native_tps'] = numerator * 1e9 / native
        report[name + '_raw_tps_lower'] = numerator * 1e9 / upper
        report[name + '_raw_tps_upper'] = numerator * 1e9 / lower
        report[name + '_raw_tps_mid'] = numerator * 1e9 / ((lower + upper) / 2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('journal', type=Path)
    parser.add_argument('--response-file', type=Path, required=True)
    parser.add_argument('--request-file', type=Path, required=True)
    parser.add_argument('--ordinal', type=int, choices=range(4), required=True)
    parser.add_argument('--epoch', type=parse_epoch, required=True)
    parser.add_argument('--require-cold', action='store_true')
    args = parser.parse_args()
    response_data = args.response_file.read_bytes()
    request_data = args.request_file.read_bytes()
    response = json.loads(response_data)
    request = json.loads(request_data)
    response_counts(response, request, args.require_cold)
    data = args.journal.read_bytes()
    report = validate(read_capture(data, args.ordinal, args.epoch), response, request=request,
                      require_cold=args.require_cold)
    report.update(ordinal=args.ordinal, phase='warmup_excluded' if args.ordinal == 0 else 'measured',
                  epoch_nonce=f'{args.epoch:016x}',
                  journal_sha256=hashlib.sha256(data).hexdigest(),
                  request_sha256=hashlib.sha256(request_data).hexdigest(),
                  response_sha256=hashlib.sha256(response_data).hexdigest(),
                  binding_sha256=hashlib.sha256(BINDING.read_bytes()).hexdigest(),
                  engine_sha256=json.loads(BINDING.read_bytes())['engine_sha256'])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
