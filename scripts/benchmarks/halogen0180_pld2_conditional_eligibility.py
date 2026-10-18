"""Offline N2/K3 lookup opportunities on the frozen natural16K greedy output.

No model, network, engine, credentials, WSL or lifecycle access. Requires an
already installed `tokenizers` package; never installs one. Native head openings,
round boundaries and current-version occurrence semantics are unavailable, so
results are conditional all-token-boundary opportunities, not native acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

MAX_FILE = 32 * 1024 * 1024
REQUEST_SHA = '0b616f5eb0aa779244cdbba4c2c7d42c8ee43ec200fc41f596e8331440f5a28c'
PROMPT_SHA = 'cbaeec7395187803e2e570d3f5554b45d2eb99e5fa80b61c370c7fe87390a663'
TOKENIZER_SHA = '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
OUTPUT_SHA = '940e8b3abd3e9ecb0f0d3b14ec3e1df6140eb83c99d219b6b6e2ac27112f7dec'
OWNED_MEMORY_JOB = None


def bound_own_memory(memory_mib):
    """Limit only this offline process to the explicitly authorized memory cap."""
    if sys.platform != 'win32':
        raise ValueError('This finite run requires the Windows process-memory bound')
    import ctypes
    from ctypes import wintypes
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                    ('max_ws', ctypes.c_size_t), ('active', wintypes.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                    ('scheduling', wintypes.DWORD)]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', ctypes.c_ulonglong * 6),
                    ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                    ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            ctypes.c_void_p, wintypes.DWORD]
    api.SetInformationJobObject.restype = wintypes.BOOL
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.AssignProcessToJobObject.restype = wintypes.BOOL
    api.GetCurrentProcess.restype = wintypes.HANDLE
    global OWNED_MEMORY_JOB
    OWNED_MEMORY_JOB = api.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.process_memory = memory_mib * 1024 * 1024
    if (not OWNED_MEMORY_JOB or
            not api.SetInformationJobObject(OWNED_MEMORY_JOB, 9, ctypes.byref(info), ctypes.sizeof(info)) or
            not api.AssignProcessToJobObject(OWNED_MEMORY_JOB, api.GetCurrentProcess())):
        raise ctypes.WinError(ctypes.get_last_error())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, expected=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError('Expected a bounded regular source file')
    data = path.read_bytes()
    if len(data) > MAX_FILE or (expected and sha(data) != expected):
        raise ValueError('Source size or SHA256 differs: ' + str(path))
    return data


def ids_sha(ids):
    return sha(struct.pack('<' + 'i' * len(ids), *ids))


class LatestKnownLookup:
    """Predeclared latest earlier exact match; zero future-token input."""
    def __init__(self, n, prefix):
        self.n = n
        self.known = list(prefix)
        self.index = {}
        for start in range(len(self.known) - n + 1):
            self._add(start)

    def _add(self, start):
        key = tuple(self.known[start:start + self.n])
        self.index.setdefault(key, []).append(start)

    def propose(self):
        if len(self.known) < self.n:
            return None
        key = tuple(self.known[-self.n:])
        for start in reversed(self.index.get(key, ())):
            following = start + self.n
            if following >= len(self.known):
                continue
            end = min(following + 3, len(self.known))
            return dict(source_start=start, following_start=following,
                        source_end_exclusive=end, ids=self.known[following:end])
        return None

    def commit(self, token):
        self.known.append(token)
        start = len(self.known) - self.n
        if start >= 0:
            self._add(start)


def screen(prompt, authoritative):
    # All policies are recorded before a frontier's next token enters either
    # index. Target labels are used for scoring only after every proposal freezes.
    policies = {n: LatestKnownLookup(n, prompt) for n in (2, 3)}
    frozen = []
    for boundary, token in enumerate(authoritative):
        if boundary >= 3:  # Both requests have produced their required suffix.
            frozen.append(dict(output_boundary=boundary,
                causal_prefix_length=len(prompt) + boundary,
                causal_prefix_sha256=ids_sha(policies[2].known),
                proposals={str(n): policies[n].propose() for n in (2, 3)}))
        for policy in policies.values():
            policy.commit(token)  # The authoritative history advances after freeze.
    proposal_freeze_sha = sha(json.dumps(frozen, sort_keys=True,
                                       separators=(',', ':')).encode())
    sums = {str(n): dict(offers=0, full_width_offers=0, retokenized_prefix_matches=0,
                        matching_first_retokenized_tokens=0, matched_third_retokenized_tokens=0)
            for n in (2, 3)}
    new_offers = []
    changed_offers = []
    for record in frozen:
        boundary = record['output_boundary']
        results = {}
        for n in (2, 3):
            proposal = record['proposals'][str(n)]
            matched = 0
            if proposal is not None:
                for actual, predicted in zip(authoritative[boundary:], proposal['ids']):
                    if actual != predicted:
                        break
                    matched += 1
                sums[str(n)]['offers'] += 1
                sums[str(n)]['full_width_offers'] += len(proposal['ids']) == 3
                sums[str(n)]['retokenized_prefix_matches'] += matched
                sums[str(n)]['matching_first_retokenized_tokens'] += matched > 0
                sums[str(n)]['matched_third_retokenized_tokens'] += matched == 3
            results[str(n)] = matched
        record['evaluator_retokenized_prefix_matches'] = results
        stock, candidate = record['proposals']['3'], record['proposals']['2']
        if candidate is not None and stock is None:
            new_offers.append(boundary)
        if candidate is not None and stock is not None and candidate['ids'] != stock['ids']:
            changed_offers.append(boundary)
    return dict(proposal_freeze_sha256=proposal_freeze_sha,
        policy='latest earlier exact occurrence with at least one known following ID; K<=3',
        boundary_scope='every committed-output token boundary after first three output tokens',
        actual_native_rounds=False, native_occurrence_rule_qualified=False,
        native_allowance_qualified=False, native_opening_references_available=False,
        eligible_native_offers=None, native_acceptance=None, speed_gain=None,
        summaries=sums, new_N2_offer_boundaries=new_offers,
        changed_N2_offer_boundaries=changed_offers,
        net_all_boundary_retokenized_match_delta=(sums['2']['retokenized_prefix_matches'] - sums['3']['retokenized_prefix_matches']),
        caveat='Retokenized IDs are conditional trajectory evaluation only, not recorded target IDs; no stock-neural union or causal selector is constructed.',
        rows=frozen)


def self_test():
    # No future source continuation: the newest current key has no following ID.
    p = LatestKnownLookup(2, [1, 2, 7, 8, 9, 1, 2])
    assert p.propose()['ids'] == [7, 8, 9]
    # A known partial continuation stays partial and cannot read past the frontier.
    p = LatestKnownLookup(2, [1, 2, 7, 1, 2, 8, 1, 2])
    assert p.propose()['source_start'] == 3
    assert p.propose()['ids'] == [8, 1, 2]
    p = LatestKnownLookup(3, [1, 2, 3, 4, 1, 2, 3])
    assert p.propose()['ids'] == [4, 1, 2]
    # Changing evaluator labels after a boundary cannot change its frozen proposal.
    a = screen([1, 2, 7, 8, 9], [4, 1, 2, 7, 8, 9])
    b = screen([1, 2, 7, 8, 9], [4, 1, 2, 99, 98, 97])
    assert a['rows'][0]['proposals'] == b['rows'][0]['proposals']
    assert a['eligible_native_offers'] is None
    assert a['native_acceptance'] is None
    return dict(passed=True, cases=4, model_executed=False, http_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--response', type=Path)
    parser.add_argument('--tokenizer', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--memory-mib', type=int, choices=(100, 512), default=100)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()))
        return
    if any(v is None for v in (args.request, args.response, args.tokenizer, args.output)):
        parser.error('request, response, tokenizer and output are required')
    bound_own_memory(args.memory_mib)
    request_raw = read(args.request, REQUEST_SHA)
    response_raw = read(args.response)
    read(args.tokenizer, TOKENIZER_SHA)
    request, response = json.loads(request_raw), json.loads(response_raw)
    prompt = request['prompt']
    output = response['choices'][0]['text']
    if sha(prompt.encode()) != PROMPT_SHA or sha(output.encode()) != OUTPUT_SHA:
        raise ValueError('Frozen prompt or qualified greedy output changed')
    if (request['temperature'] != 0 or request['max_tokens'] != 128 or
            response['usage']['prompt_tokens'] != 16384 or
            response['usage']['completion_tokens'] != 128 or
            response['choices'][0]['finish_reason'] != 'length'):
        raise ValueError('Frozen workload/count/finish policy differs')
    try:
        from tokenizers import Tokenizer
        import tokenizers
    except ImportError as exc:
        raise SystemExit('Existing tokenizers package unavailable; no screen or installation performed.') from exc
    tokenizer = Tokenizer.from_file(str(args.tokenizer))
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False).ids
    output_ids = tokenizer.encode(output, add_special_tokens=False).ids
    joined = tokenizer.encode(prompt + output, add_special_tokens=False).ids
    if len(prompt_ids) != 16384 or len(output_ids) != 128 or joined != prompt_ids + output_ids:
        raise ValueError('Retokenization/count/boundary differs; raw generated IDs are required')
    if tokenizer.decode(output_ids, skip_special_tokens=False) != output:
        raise ValueError('Output byte roundtrip differs; raw generated IDs are required')
    result = dict(schema='halogen0180.pld2-conditional-eligibility.v1',
        source=dict(request_sha256=sha(request_raw), response_sha256=sha(response_raw),
                    tokenizer_sha256=TOKENIZER_SHA, output_sha256=OUTPUT_SHA,
                    script_sha256=sha(Path(__file__).read_bytes()),
                    tokenizers_version=tokenizers.__version__),
        input_tokens=len(prompt_ids), output_tokens=len(output_ids),
        prompt_ids_sha256=ids_sha(prompt_ids), output_ids_sha256=ids_sha(output_ids),
        retokenization_boundary_and_roundtrip_passed=True,
        raw_generated_ids_available=False, process_memory_limit_bytes=args.memory_mib * 1024 * 1024,
        model_executed=False, http_executed=False,
        result=screen(prompt_ids, output_ids))
    read(args.tokenizer, TOKENIZER_SHA)  # Source must remain identical through the run.
    with args.output.open('xb') as stream:
        stream.write((json.dumps(result, indent=2, allow_nan=False) + '\n').encode())
    print(json.dumps(dict(output=str(args.output), summaries=result['result']['summaries'],
        eligible_native_offers=None, native_acceptance=None, model_executed=False,
        new_N2_offer_boundaries=result['result']['new_N2_offer_boundaries'])))


if __name__ == '__main__':
    main()
