"""File-only audit of saved 0.18.0 phases and their exact native producers.

Reads immutable evidence and a hash-pinned pure Python ELF parser. No HTTP,
process inspection, subprocess, native-library loading, device, or lifecycle
API exists here. Matching HTTP/phase sums never qualify a phase clock.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import unittest

ENGINE_SHA = "71d72b283f0937aec024baf6b6ec919e27dacd57cfc043832468ffdd603c8e08"
PROVIDER_SHA = "972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00"
IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:de3b47d2e5f24f98a38ba5fb66b0075b0cd8a3219c38917c78fb4bbeb42b88d9"
CLOCK_SYMBOL = "_ZNSt6chrono3_V212steady_clock3nowEv"
PREP_REL = "server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008"
FUNCTIONS = [
    (0x17fc440, 0x1812623, "709765e9f505d3844fe72889339ead28a079287e01f56577f24e53cd6c21890b"),
    (0x1813bc0, 0x18143b8, "2a4e657ee2d86550fdb23bfa3f34b0610e028ba56226b605c0ada6379f75bcd8"),
    (0x1814a20, 0x1815a6a, "b9f0352236e9fc784206be52876bbd16e14151562e5f167609f40c98f0d014bc"),
    (0x1815c80, 0x181620e, "6d91b671106f44fefa869ebb384fbe77a22d55b93f71c50f66c89b18afe24b96"),
    (0x1816210, 0x18175a5, "c3abe9a82b2e9c05f15dd80453c91dae0798fcaedf36edbd599aa1e9d321ef47"),
    (0x18176f0, 0x181781c, "01aae15122af227eded0cdb91bf26755758dd0086c04cbe1b89e2fe693f887c4"),
    (0x1818170, 0x1818a94, "88d4c00f99dc9323f51ba1ca609f1d4680dcf7b19adf44d33c3ed238ac6ffd75"),
    (0x181b040, 0x181b7c3, "1259f3eabeab20127964a2ece7b68caa6e14e3260fa23c61af494074f875b550"),
]
# These windows were decoded from complete, actual FDE-bounded functions with
# pinned Windows LLVM. They are version-specific; no global RVA shift is used.
SPANS = [
    ('prefill_start', 0x1814a31, 0x1814a44, '4189d44989f64989ffe8e18d1b004889442418'),
    ('prefill_end', 0x1814e41, 0x1814e7b, 'e8da891b00482b4424180f57c0f2480f2ac0f20f5e0585ef7ffef2410f588650040000f2410f11865004000049c7874001000000000000498b07'),
    ('prefill_progress_native_start', 0x1814be5, 0x1814bf8, '488b442418498986a8040000498986b8040000'),
    ('decode_start', 0x1817123, 0x1817142, '418b4654418986bc01000041c7465801000000e8e5661b00498986c8010000'),
    ('decode_end', 0x181b09a, 0x181b0d9, '498b9ec80100004d89c44489cdf20f11442468e86e271b00f20f104424684189e94d89e04829d80f57c9f2480f2ac8f20f5e0d0f8d7ffe488b842400030000'),
    ('formatter_request_id', 0x181b061, 0x181b072, '4989c84989d648897424704989ff488b02'),
    ('formatter_native_start', 0x181b09a, 0x181b0a1, '498b9ec8010000'),
    ('formatter_counts_and_prefill', 0x181b07a, 0x181b09a, '448b4a548b4258f20f1082c0010000660f57c948898424b800000083f8027c37'),
    ('move_ctor_id', 0x1815c8b, 0x1815c91, '0f10060f1107'),
    ('move_ctor_counts', 0x1815ce3, 0x1815ceb, '0f104e500f114f50'),
    ('move_ctor_scalar', 0x1815fa9, 0x1815fc1, '498dbeb8010000488db3b8010000ba81000000e89f751b00'),
    ('move_assign_id', 0x181817b, 0x1818181, '0f10060f1107'),
    ('move_assign_counts', 0x1818223, 0x181822c, '410f1046500f114350'),
    ('move_assign_scalar', 0x18186ee, 0x1818706, '488dbbb8010000498db6b8010000ba81000000e85a4e1b00'),
    ('append_and_growth', 0x18176f0, 0x181781c, '554157415641554154534883ec184889fb4c8b7f084c3b7f1074154c89ffe86de5ffff4881430838030000e9e100000048897424104c8b234c89fd4c29e548b8e0fcffffffffff7f4839c50f84cf0000004889e848c1f80348b9571b43d31decb7da480fafc84d39e7b801000000480f45c1488d140848be0452c97959c427004839f2480f43d64801c8480f42d64869fa3803000048897c2408e8e15d1b004989c54801c54889ef488b742410e8dee4ffff4c89ed4d39e7742c4c89ed4d89e64889ef4c89f6e8c5e4ffff4c89f7e8fdcdffff4981c6380300004881c5380300004d39fe75da4d85e4740f488b73104c29e64c89e7e8065d1b004881c5380300004c892b48896b084c036c24084c896b104883c4185b415c415d415e415f5dc3488d3daf8780fee8745f1b00'),
    ('stack_insertion', 0x180059c, 0x18005b1, '488dbc24c0010000488db424600a0000e83f710100'),
    ('stack_insertion_alternate', 0x180b282, 0x180b297, '488dbc24c0010000488db424600a0000e859c40000'),
    ('vector_handle', 0x17fc6c1, 0x17fc6d1, '488d8424c00100004889842488080000'),
    ('heap_element', 0x1813bd6, 0x1813bed, '4889fb488b074c8b77084c69ee380300004c8b384d01ef'),
    ('formatter_call', 0x1813f4f, 0x1813f63, '4c89f74c89fa4889e94531c04531c9e8dd700000'),
    ('prefill_to_request_primary', 0x1800058, 0x1800081, '4c8db424600a00004c89f7e8185c0100488bbc2488000000f30f7e8750040000660fd68424200c0000'),
    ('prefill_to_request_alternate', 0x180011d, 0x180014c, '488bb42488000000488dbc24600a0000e84e5b01004c8bb42488000000f3410f7e8650040000660fd68424200c0000'),
    ('prefill_to_request_later', 0x180b017, 0x180b048, '488bb424880000004c8db424600a00004c89f7e851ac0000488bbc2488000000f30f7e8750040000660fd68424200c0000'),
]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def pinned(path, expected_sha, expected_bytes=None):
    data = path.read_bytes()
    require(sha(data) == expected_sha, 'File SHA changed: ' + str(path))
    require(expected_bytes is None or len(data) == expected_bytes, 'File size changed: ' + str(path))
    return data


def check_window(actual, expected_hex):
    require(actual == bytes.fromhex(expected_hex), 'Native instruction bytes changed')


def dynamic_contract(data, elf):
    strings_section = elf.sections['.dynstr']
    strings = data[strings_section['file_offset']:strings_section['file_offset'] + strings_section['bytes']]

    def string(index):
        require(0 <= index < len(strings), 'Dynamic string offset outside section')
        return strings[index:strings.index(b'\0', index)].decode('ascii')

    section = elf.sections['.dynamic']
    tags = [struct.unpack_from('<qQ', data, off) for off in
            range(section['file_offset'], section['file_offset'] + section['bytes'], 16)]
    needed = [string(value) for tag, value in tags if tag == 1]
    runpath = [string(value) for tag, value in tags if tag == 29]
    dynsym = elf.sections['.dynsym']
    clock_symbols = []
    for index, off in enumerate(range(dynsym['file_offset'], dynsym['file_offset'] + dynsym['bytes'], 24)):
        name, _, _, defined, value, size = struct.unpack_from('<IBBHQQ', data, off)
        if string(name) == CLOCK_SYMBOL:
            clock_symbols.append((index, defined, value, size))
    require(len(clock_symbols) == 1 and clock_symbols[0][1] == 0, 'Chrono import changed')
    versions = elf.sections['.gnu.version']
    version_index = struct.unpack_from('<H', data, versions['file_offset'] + 2 * clock_symbols[0][0])[0] & 0x7fff
    needs = elf.sections['.gnu.version_r']
    at, end = needs['file_offset'], needs['file_offset'] + needs['bytes']
    version_names = {}
    for _ in range(64):
        require(at + 16 <= end, 'Version need record outside section')
        _, count, _, aux, next_record = struct.unpack_from('<HHIII', data, at)
        cursor = at + aux
        require(count <= 64, 'Version auxiliary bound exceeded')
        for _ in range(count):
            require(cursor + 16 <= end, 'Version auxiliary outside section')
            _, _, other, name, next_aux = struct.unpack_from('<IHHII', data, cursor)
            version_names[other & 0x7fff] = string(name)
            cursor += next_aux
        if not next_record:
            break
        at += next_record
    require(version_names.get(version_index) == 'GLIBCXX_3.4.19', 'Chrono symbol version changed')
    require('libstdc++.so.6' in needed, 'Normal chrono provider dependency absent')
    require(runpath == ['/usr/local/lib/python3.12/site-packages/_rocm_sdk_devel/lib'], 'Engine RUNPATH changed')
    return dict(needed=needed, runpath=runpath, clock_symbol=CLOCK_SYMBOL, clock_version=version_names[version_index])


def audit_static(root):
    base = root / PREP_REL
    parser = base / 'static-compatibility-audit/passive_elf_review.py'
    pinned(parser, '671297d02e798107827e5b51def19a288479a8c733c41b2221854bc96af9eddd')
    spec = importlib.util.spec_from_file_location('_phase_audit_elf', parser)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = base / 'halogen0180-normal-bridge-preparation-20261011/artifacts/flash_serve'
    data = pinned(engine, ENGINE_SHA, 27078280)
    elf = module.Elf(data)
    functions = []
    for start, end, digest in FUNCTIONS:
        actual = elf.unwind_range(start)
        require(actual['start_rva'] == start and actual['end_rva_exclusive'] == end, 'FDE function bounds changed')
        require(sha(data[actual['start_file_offset']:actual['end_file_offset_exclusive']]) == digest, 'FDE body changed')
        functions.append(dict(start_rva=hex(start), end_rva_exclusive=hex(end), bytes=end-start, sha256=digest))
    windows = []
    for name, start, end, expected in SPANS:
        actual = elf.unwind_range(start)
        require(actual['end_rva_exclusive'] >= end and any(start >= s and end <= t for s, t, _ in FUNCTIONS),
                'Instruction window outside pinned FDE closure')
        offset = elf.offset(start, end-start)
        raw = data[offset:offset+end-start]
        check_window(raw, expected)
        windows.append(dict(name=name, rva=hex(start), end_rva_exclusive=hex(end), file_offset=hex(offset),
                            bytes=end-start, instruction_bytes_hex=raw.hex(), sha256=sha(raw)))
    plt = data[elf.offset(0x19cd820,16):elf.offset(0x19cd820,16)+16]
    check_window(plt, 'ff25127700006837000000e970fcffff')
    got = 0x19cd820 + 6 + struct.unpack_from('<i', plt, 2)[0]
    relocation = elf.relocation_names()[got]
    require(relocation == dict(symbol=CLOCK_SYMBOL, relocation_type=7, addend=0), 'Chrono PLT relocation changed')
    require(struct.unpack_from('<d', data, elf.offset(0x13de0,8))[0] == 1000000.0, 'Millisecond divisor changed')
    dynamic = dynamic_contract(data, elf)
    provider_dir = base / 'halogen0180-normal-bridge-preparation-20261011/root-provider-inspection'
    receipt = json.loads(pinned(provider_dir/'receipt.json', 'a2e8f0cc902864ea7664f880ac4c051d854616a57007184d31e6cfd245f4c198'))
    closure = json.loads(pinned(provider_dir/'stdout.json', '9f164df22ce608a1aa5a05691191fc5cca0b332c749ec68ea87d8f95c4e7585f'))
    require(receipt['image'] == IMAGE and receipt['completed'] and receipt['owned_container_closed_removed'],
            'Saved exact-image CPU provider receipt incomplete')
    image_provider = [p for p in closure['mapped_loader_closure'] if p['path'] == '/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33']
    require(len(image_provider) == 1 and image_provider[0]['sha256'] == PROVIDER_SHA and image_provider[0]['bytes'] == 2497768,
            'Exact-image normal chrono provider bytes not bound')
    provider = root / 'server/.local/optimization9h-20261004/rocr-base-image-libs/libstdc++.so.6'
    provider_data = pinned(provider, PROVIDER_SHA, 2497768)
    provider_elf = module.Elf(provider_data)
    off = provider_elf.offset(0xd5490,39)
    provider_code = provider_data[off:off+39]
    check_window(provider_code, 'f30f1efa4883ec18bf010000004889e6e8eb83fcff4869042400ca9a3b48034424084883c418c3')
    slot = provider_data[provider_elf.offset(0x9d890,16):provider_elf.offset(0x9d890,16)+16]
    require(slot[:2] == b'\xff\x25', 'Provider clock_gettime PLT shape changed')
    provider_got = 0x9d890+6+struct.unpack_from('<i',slot,2)[0]
    require(provider_elf.relocation_names()[provider_got]['symbol'] == 'clock_gettime', 'Provider clock call changed')
    return dict(engine_sha256=ENGINE_SHA, engine_bytes=len(data), image=IMAGE, functions=functions,
        windows=windows, clock_plt_rva='0x19cd820', clock_got_rva=hex(got), dynamic=dynamic,
        provider_sha256=PROVIDER_SHA, provider_bytes=len(provider_data), provider_symbol_rva='0xd5490',
        provider_symbol_bytes_hex=provider_code.hex(), normal_provider_clock='CLOCK_MONOTONIC (clock id 1)',
        exact_image_provider_file_bound=True, live_engine_provider_binding_observed=False,
        request_layout=dict(signed_id='0x0', prompt_count='0x54', predicted_count='0x58', prefill_ms='0x1c0',
                            decode_start_ns='0x1c8', stride='0x338', scalar_move_begin='0x1b8', scalar_move_end='0x239',
                            prefill_accumulator='0x450'),
        phase_calls=dict(prefill_begin='0x1814a3a', prefill_end='0x1814e41', decode_begin='0x1817136', decode_end='0x181b0ad'))


def inspect_response(raw, client):
    require(sha(raw) == client['raw_response_sha256'], 'Raw response/client hash differs')
    timings = json.loads(raw)['timings']
    require(timings == client['accounting']['timings'], 'Saved/native timing fields differ')
    wall, begin, end = (client[k] for k in ('wall_seconds', 'qpc_start', 'qpc_end'))
    require(all(type(v) in (int,float) and math.isfinite(v) for v in (wall,begin,end)) and wall > 0
            and abs(end-begin-wall) <= 1e-9, 'QPC wall identity differs')
    for count, duration, rate in [('prompt_n','prompt_ms','prompt_per_second'), ('predicted_n','predicted_ms','predicted_per_second')]:
        require(type(timings[count]) is int and timings[count] > 0, 'Invalid API token count')
        require(all(type(timings[k]) in (int,float) and math.isfinite(timings[k]) and timings[k] > 0 for k in (duration,rate)),
                'Invalid API timing observation')
        require(abs(round(timings[count]*1000/timings[duration],3)-timings[rate]) <= 1e-9, 'API rate arithmetic differs')
    phase_sum = math.fsum([timings['prompt_ms'], timings['predicted_ms']])/1000
    return dict(native_api_timings=timings, qpc_whole_request_seconds=wall, api_phase_sum_seconds=phase_sum,
                whole_request_minus_api_phase_ms=(wall-phase_sum)*1000,
                api_phase_sum_over_qpc=phase_sum/wall, api_phase_clock_qualified=False,
                phase_rate_scaling_applied=False, qualified_raw_phase_rates=None)


def audit_cohorts(root):
    packet = root/'docs/benchmarks/halogen0180-fixed-adaptive-natural16k-20261011.json'
    comparison = load(packet)
    require(comparison['schema'] == 'halogen0180.fixed2-adaptive-natural16k-comparison.v1', 'Comparison schema differs')
    protocol = comparison['protocol']
    require(protocol['engine_version'] == '0.18.0' and protocol['context_capacity'] == 32768
            and protocol['actual_input_tokens'] == 16384 and protocol['output_cap'] == 128, 'Cohort protocol differs')
    base = root/PREP_REL/'halogen0180-adaptive-option-20261011'
    measure_sha = comparison['protocol']['measurement_client']['sha256']
    pinned(base/'client/measure.py', measure_sha)
    pinned(base/'client/request-16384.json', protocol['request']['sha256'])
    rows = []
    for arm in ('fixed2','adaptive'):
        record = comparison['arms'][arm]
        qualification = json.loads(pinned(base/f'{arm}-32k-cohort/qualification.json', record['qualification']['sha256']))
        require(qualification['passed'] and not qualification['api_phase_clock_qualified'], 'Cohort qualification scope differs')
        evidence = [record['excluded_warmup'], *record['measured_evidence']]
        for rep, saved in enumerate(evidence):
            folder = base/f'{arm}-32k-cohort'
            raw = pinned(folder/f'response-{rep}.raw', saved['raw_response']['sha256'])
            client = json.loads(pinned(folder/f'client-{rep}.json', saved['client']['sha256']))
            require(client['rep'] == rep and client['phase'] == ('warmup' if rep == 0 else 'measured')
                    and client['identity'] == record['identity'], 'Per-request identity/order differs')
            row = inspect_response(raw,client)
            require(row['native_api_timings']['prompt_n'] == 16384 and row['native_api_timings']['predicted_n'] == 128,
                    'Actual cohort token counts differ')
            rows.append(dict(arm=arm, rep=rep, measured=rep>0, **row))
    api = root/PREP_REL/'halogen0180-normal-bridge-preparation-20261011/artifacts/tools/serve_api.py'
    pinned(api, '1cdd97732df7819c203e38fb4531546e2308f6ea29c4871ca12a7fa9ffef9902')
    return dict(comparison_sha256=sha(packet.read_bytes()), client_sha256=measure_sha, responses=rows,
                saved_api_phase_clock_qualified=False, phase_rate_scaling_applied=False,
                saved_cohort_has_phase_raw_journal=False,
                scope='API durations/rates are unchanged observations; residual is a closure diagnostic, never calibration')


def fixture():
    value = {"timings": {"prompt_n": 100, "predicted_n": 10,
        "prompt_ms": 1000.0, "predicted_ms": 1000.0,
        "prompt_per_second": 100.0, "predicted_per_second": 10.0}}
    raw = json.dumps(value).encode()
    return raw, {"qpc_start": 2.0, "qpc_end": 4.0, "wall_seconds": 2.0,
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "accounting": {"timings": copy.deepcopy(value["timings"])}}


class AuditTests(unittest.TestCase):
    def test_matching_sum_does_not_qualify_native_phases(self):
        raw, client = fixture()
        self.assertFalse(inspect_response(raw, client)["api_phase_clock_qualified"])

    def test_matching_sum_does_not_create_qualified_raw_rates(self):
        raw, client = fixture()
        value = inspect_response(raw,client)
        self.assertIsNone(value['qualified_raw_phase_rates'])
        self.assertFalse(value['phase_rate_scaling_applied'])

    def test_response_hash_tamper_is_rejected(self):
        raw, client = fixture()
        with self.assertRaisesRegex(ValueError,'hash'):
            inspect_response(raw+b' ',client)

    def test_qpc_interval_tamper_is_rejected(self):
        raw, client = fixture(); client['qpc_end'] += 0.1
        with self.assertRaisesRegex(ValueError,'QPC'):
            inspect_response(raw,client)

    def test_response_accounting_tamper_is_rejected(self):
        raw, client = fixture(); client['accounting']['timings']['predicted_ms'] += 1
        with self.assertRaisesRegex(ValueError,'fields'):
            inspect_response(raw,client)

    def test_negative_closure_is_preserved_without_inventing_phase_rates(self):
        raw, client = fixture(); client.update(qpc_end=3.9,wall_seconds=1.9)
        value = inspect_response(raw,client)
        self.assertLess(value['whole_request_minus_api_phase_ms'],0)
        self.assertFalse(value['api_phase_clock_qualified'])

    def test_native_byte_tamper_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'bytes'):
            check_window(b'\x90','c3')

    def test_rate_arithmetic_tamper_is_rejected(self):
        raw, client = fixture(); value = json.loads(raw); value['timings']['predicted_per_second'] += 1
        raw = json.dumps(value).encode(); client['raw_response_sha256'] = sha(raw)
        client['accounting']['timings'] = value['timings']
        with self.assertRaisesRegex(ValueError,'arithmetic'):
            inspect_response(raw,client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--self-test',action='store_true',help='Only memory fixtures; does not read any cohort')
    parser.add_argument('--full',action='store_true',help='Print complete native pins and source map')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AuditTests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    try:
        static, cohorts = audit_static(args.root), audit_cohorts(args.root)
        result = dict(schema='halogen0180.phase-clock-offline-audit.v1', offline_only=True,
                      native_static_pins_verified=True, api_phase_clock_qualified=False, static=static, cohorts=cohorts,
                      missing_runtime_evidence=['exact_engine_loaded_chrono_provider_binding',
                         'phase_local_MONOTONIC_and_RAW_endpoint_pairs', 'native_D_and_API_phase_field_binding',
                         'complete_request_RAW_vs_QPC_clock_agreement_with_uncertainty'])
        if not args.full:
            result['static'] = dict(engine_sha256=ENGINE_SHA, image=IMAGE,
                function_count=len(static['functions']), window_count=len(static['windows']),
                normal_provider_clock=static['normal_provider_clock'], live_engine_provider_binding_observed=False)
        print(json.dumps(result,indent=2))
    except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
        print(json.dumps(dict(schema='halogen0180.phase-clock-offline-audit.v1', offline_only=True,
                             passed=False, api_phase_clock_qualified=False, error=str(error))))
        raise SystemExit(2)
