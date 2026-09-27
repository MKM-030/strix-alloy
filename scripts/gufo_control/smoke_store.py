"""Fixed provenance and one-attempt evidence for the private AR4k smoke.

This module performs no model execution. The qualification record is deliberately
absent by default; only an independently reviewed, exact binding can admit a run.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from . import operator_store
from .model_identity import (AR4K_PINS, MTP_SIDECAR, SidecarPin, ValidatedModel,
                             validate_ar4k_model, validate_mtp_sidecar)
from .operator_policy import Baseline, PROBES


PROFILE_ID = 'ar4k-iq4xs-http-slots-smoke-v3'
ROOT = Path(r'C:\Projects\strix-alloy-research')
SOURCE = ROOT / 'sources/gufo-windows'
SDK = Path(r'C:\AI\sdk\therock1151')
BUILD = ROOT / 'build/gufo-hip-10.2'
EVIDENCE = ROOT / 'reports/gufo-ar4k-http-slots-smoke-runs'
QUALIFICATION = ROOT / 'reports/gufo-ar4k-http-slots-smoke-qualification.json'
MARGIN_REPORT = ROOT / 'reports/gufo-ar4k-measured-margin-review-20260926.md'
FIRST_SHARD = Path(r'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf')
MARGIN_SHA256 = 'CD55B870D7301398BB55665D57338BE1EA55668A52C5FCE50438A86EC583CD20'
GDN_RESULT_SHA256 = '709A899B77782E9BCEE456D1A4FFBCFC52A365BA106024AAF9A40BBDDE0017E6'
IQ_RESULT_SHA256 = '4D7C4646E9C14F2500EE282BCB753B950BB2CDAA45089DED3687F07F53547605'
FAILED_GDN_RESULT_SHA256 = operator_store.REVIEWED_RESULT_SHA256

SDK_DLLS = {
    'amdhip64_7.dll': (16578560, '71C41D9DB361E544D1CB6DFF91530D5705FFC5F1A91BA8EDCF583FB882E282BF'),
    'amd_comgr.dll': (122234880, 'EA2825C6588FD48536377309848999C9EF98137C0FA8E8424D0B7CAD95D0F724'),
    'rocm_kpack.dll': (181248, '9B6ABC1A45443709309AD136ED09C60EEEC45E77A003A23F6B35730036085649'),
    'hipblas.dll': (809472, 'ED7525F0BA29653E7A19623DC349CD3F44A87170E67C4D8591E79690FE6CE470'),
    'rocsolver.dll': (26473984, '409C0C2F6FD09B3E520D6BD8D4C76FB9C95D43BA9DE10B6E9A0810D2384D20A0'),
    'rocblas.dll': (21070848, 'E5B06BA780F635C2E5B14A67F089DC38329832CF479EA528C11D55F7325B81B0'),
    'libhipblaslt.dll': (2497536, '924C94CDC7DF260CA0BD044AD0379879E1A09AB5C64872AA0CFF036D705E9FEB'),
    'libtensilelite-host.dll': (4004352, '5FD691EA75E0D122CF4EFDC428C2B89DAD6FED5D5EA04A5BBAAC5397E8BE5DA8'),
    'origami.dll': (373760, 'E62466F4BC04189C7D1E692C937814B5A8BCF7813D237987F8285BCAB60D6B6F'),
}
VCPKG_DLLS = {
    'icudt78.dll': (33110528, '176440BC1E4D0164DCCA89DBB1C872D9C15BA66639111C5282C64C18D50B6FB3'),
    'icuin78.dll': (2779136, '219799E7A6863A7566ED0E1F29584FD6F301BCE83467B002920B6C17039759DB'),
    'icuuc78.dll': (1847808, '1F27BC1855EA987A112B72C39FF55ED050914F97C130A177FB7DE80B51E1CA57'),
    'jpeg62.dll': (694272, 'F0202808AB13D60354630B2080FAB64797969DB54F2C9FA4AC62956FA7ADD652'),
    'libcrypto-3-x64.dll': (5334528, 'EFD6048B9AA21CFF4BAF5076A03F638C1EC84AF7AE96CE0F4FDB8AF2FCBFCE65'),
    'libcurl.dll': (711680, '2D8D6046FB333567E1AD6250733232C80404EF08B6DD04A92842C593D2D0BA9B'),
    'libpng16.dll': (198656, '1860AC39E164DED76029F66918396528C7EBC43189419A1CC0EDF4EF484B6EDD'),
    'z.dll': (91136, '64F9BA80BCF671DEAB75E6129E4C895E36E3A54F3748BDD07759457181258AAB'),
}
TREES = {
    'hipblaslt': (100, 13164894, '79EB8214145013B0F9CAFDD128942B94542C10FCEFB80B827472940EB4D4BB56'),
    'rocblas': (150, 17243350, 'D160DEE878CB2DF152A39DB55506085C2918CAA83041C61E58096EA8B8E64D06'),
}
BOUNDS = {'gpu_gib': 68, 'host_gib': 4, 'shared_gib': 20,
          'prelaunch_gib': 49, 'runtime_gib': 24, 'commit_reserve_gib': 12}
BENCHMARK_4K = 'ar4k-iq4xs-correctness-pp1-v2'
BENCHMARK_16K = 'ar16k-iq4xs-pp1-cache-v3'
MTP_4K = 'mtp4k-iq4xs-draft1-bilingual-v1'
MTP_BOUNDS = dict(BOUNDS, gpu_gib=71)
MATCHED_AR = 'matched4k-iq4xs-ar-v1'
MATCHED_AR_V2 = 'matched4k-iq4xs-ar-v2'
MATCHED_MTP = 'matched4k-iq4xs-mtp-length-d1-v1'
MATCHED_MTP_BOUNDS = dict(BOUNDS, gpu_gib=72)
MATCHED_MTP_D3 = 'matched4k-iq4xs-mtp-length-d3-v1'
MATCHED_MTP_D3_BOUNDS = dict(BOUNDS, gpu_gib=73)
MATCHED_MARGIN_SHA256 = '49433BB54E71F7F27418FEC63E71DA98F4C372F31E19E6A95292E21148874344'
MATCHED_D3_MARGIN_SHA256 = '825F2BDE34A4BE070517EE4DD00EA3FA911A4141326591A8DDB47A43FD0AE66D'
SERVICE_SMOKE = 'ar4k-service-policy-smoke-v1'
INSTALLED_SERVICE = 'ar4k-native-installed-v1'
FINITE_SERVICE = 'ar4k-service-lifecycle-v1'
MTP_MARGIN_SHA256 = '7EC8175FFFC356058A0CA8F07B02F3A20AE3E8B88F44F9357D2E13C39F2E8AF6'
MTP_PREDECESSOR_SHA256 = '692149EEB38F89E662D9428A725533F14793680F5C70E8477A3B53E2DE8B04F3'
PROFILE_ROOTS = {PROFILE_ID: 'gufo-ar4k-http-slots-smoke-runs',
                 SERVICE_SMOKE: 'gufo-service-policy-smoke-v1-runs',
                 INSTALLED_SERVICE: 'gufo-native-installed-v1-runs',
                 FINITE_SERVICE: 'gufo-service-lifecycle-v1-runs',
                 BENCHMARK_4K: 'gufo-ar4k-benchmark-v2-runs',
                 BENCHMARK_16K: 'gufo-ar16k-benchmark-v3-runs',
                 MTP_4K: 'gufo-mtp4k-stage-v1-runs',
                 MATCHED_AR: 'gufo-matched-ar4k-v1-runs',
                 MATCHED_AR_V2: 'gufo-matched-ar4k-v2-runs',
                 MATCHED_MTP: 'gufo-matched-mtp4k-v1-runs',
                 MATCHED_MTP_D3: 'gufo-matched-mtp4k-d3-v1-runs'}


def profile_bounds(profile_id):
    if profile_id == MATCHED_MTP_D3:
        return MATCHED_MTP_D3_BOUNDS
    if profile_id == MTP_4K:
        return MTP_BOUNDS
    if profile_id == MATCHED_MTP:
        return MATCHED_MTP_BOUNDS
    if profile_id in (PROFILE_ID, BENCHMARK_4K, BENCHMARK_16K, MATCHED_AR,
                       MATCHED_AR_V2, SERVICE_SMOKE, INSTALLED_SERVICE, FINITE_SERVICE):
        return BOUNDS
    raise ValueError('unknown_profile')
FIRST_PREDECESSOR_RUN = '20260926T164942Z-a4d64a8f565248bdb508895b6f3ec931'
FIRST_PREDECESSOR_SHA256 = '58B222AA96BE4A84F4349697A9914B20E1953ECC7464085A4BE9984819121FBF'


@dataclass(frozen=True)
class PredecessorPin:
    profile_id: str
    run: Path
    result_sha256: str


@dataclass(frozen=True)
class StorePins:
    profile_id: str
    source: Path
    source_commit: str
    sdk: Path
    build: Path
    executable_name: str
    executable: tuple[int, str]
    sdk_dlls: dict[str, tuple[int, str]]
    vcpkg_dlls: dict[str, tuple[int, str]]
    host_openmp: Path
    host_openmp_pin: tuple[int, str]
    trees: dict[str, tuple[int, int, str]]
    first_shard: Path
    model_revision: str
    shard_names: tuple[str, str, str]
    model_descriptors: tuple[dict, dict, dict]
    evidence: Path
    operator_evidence: Path
    failed_run: Path
    gdn_run: Path
    iq_run: Path
    failed_result_sha256: str
    gdn_result_sha256: str
    iq_result_sha256: str
    margin_report: Path
    margin_sha256: str
    qualification: Path
    bounds: dict[str, int]
    experiment_json: str | None = None
    predecessors: tuple[PredecessorPin, ...] = ()
    acceptance_sha256: str | None = None
    sidecar: SidecarPin | None = None
    sidecar_stamp: tuple[str, int, int] | None = None
    operator_source_commit: str | None = None


PINS = StorePins(
    PROFILE_ID, SOURCE, operator_store.SOURCE_COMMIT, SDK, BUILD, 'gufo.exe',
    (42429952, 'E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943'),
    SDK_DLLS, VCPKG_DLLS, Path(r'C:\Windows\System32\libomp140.x86_64.dll'),
    (634936, '9AB1CB787E52B2A36133899C01C1DB1F876067D1471CD224EAD85F40A8152B99'),
    TREES, FIRST_SHARD, AR4K_PINS.revision,
    tuple(pin.filename for pin in AR4K_PINS.shards),
    tuple({'name': pin.filename, 'size_bytes': pin.size_bytes,
           'descriptor_sha256': pin.descriptor_sha256}
          for pin in AR4K_PINS.shards),
    EVIDENCE, operator_store.EVIDENCE, operator_store.REVIEWED_FAILED_RUN,
    operator_store.EVIDENCE / '20260926T132033Z-b76accd8438c4201bc454eff0c03e8ca',
    operator_store.EVIDENCE / '20260926T132127Z-3387e0be5a174fe199e197fc7c723d47',
    FAILED_GDN_RESULT_SHA256, GDN_RESULT_SHA256, IQ_RESULT_SHA256,
    MARGIN_REPORT, MARGIN_SHA256,
    QUALIFICATION, BOUNDS,
)


def _checked_artifact(path: Path, pin: tuple[int, str], label: str) -> dict:
    try:
        record = operator_store.artifact_record(path)
    except OSError as error:
        raise ValueError(f'artifact_missing:{label}') from error
    if (record['stamp'][1], record['sha256']) != pin:
        raise ValueError(f'artifact_mismatch:{label}')
    return {'label': label, **record}


def _tree_files(path: Path):
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f'tree_missing:{path}')
    files = []
    for entry in path.rglob('*'):
        if entry.is_symlink():
            raise ValueError(f'tree_symlink:{entry}')
        if entry.is_file():
            files.append((entry.relative_to(path).as_posix(), entry))
        elif not entry.is_dir():
            raise ValueError(f'tree_unknown_entry:{entry}')
    return sorted(files, key=lambda pair: pair[0])


def _tree_records(path: Path, pin: tuple[int, int, str], label: str) -> list[dict]:
    records = []
    lines = []
    total = 0
    for relative, file in _tree_files(path):
        record = operator_store.artifact_record(file)
        size = record['stamp'][1]
        total += size
        lines.append(f'{relative}|{size}|{record["sha256"].lower()}\n')
        records.append({'label': f'{label}/{relative}', **record})
    actual = sha256(''.join(lines).encode('utf-8')).hexdigest().upper()
    if (len(records), total, actual) != pin:
        raise ValueError(f'tree_manifest_mismatch:{label}')
    return records


def _json_artifact(path: Path, expected_sha: str | None, label: str):
    record = operator_store.artifact_record(path)
    if record['stamp'][1] > 2 * 1024 * 1024:
        raise ValueError(f'oversized_state:{label}')
    if expected_sha is not None and record['sha256'] != expected_sha:
        raise ValueError(f'{label}_hash_mismatch')
    try:
        value = operator_store.read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f'{label}_invalid') from error
    if operator_store.stamp(path) != record['stamp']:
        raise ValueError(f'{label}_changed')
    return value, {'label': label, **record}


def _baseline(value):
    try:
        return Baseline(tuple(value['identity']), value['available_min'],
                        value['committed_max'], tuple(value['gpu_max']),
                        value['first_start'], value['last_end'])
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError('operator_baseline_invalid') from error


def _operator_result(pins: StorePins, key: str, run: Path, digest: str):
    result, record = _json_artifact(run / 'result.json', digest, 'operator_result')
    expected_hashes = [PROBES[key].sha256,
                       *(operator_store.DLL_SHA256[n] for n in operator_store.DLLS),
                       *(operator_store.DLL_SHA256[n] for n in operator_store.DLLS)]
    try:
        manifest = result['manifest']
        if (result['success'] is not True or result['cleanup_confirmed'] is not True
                or result['owned_exit_confirmed'] is not True
                or result['collector_terminal'] is not True
                or result['recovery_samples'] != 5
                or manifest['policy'] != operator_store.POLICY_ID
                or manifest['source'] != (pins.operator_source_commit or pins.source_commit)
                or manifest['probe'] != key
                or manifest['executable'] != str(operator_store.BUILD / PROBES[key].filename)
                or manifest['sdk'] != str(pins.sdk)
                or manifest['runtime_policy'] != operator_store.RUNTIME_POLICY
                or [entry['sha256'] for entry in manifest['artifacts']] != expected_hashes):
            raise ValueError('operator_result_invalid')
        baseline = _baseline(result['original_baseline'])
    except (KeyError, TypeError, IndexError, ValueError) as error:
        raise ValueError('operator_result_invalid') from error
    return baseline, record


def _operator_sequence(pins: StorePins):
    if (pins.operator_evidence / 'incomplete.json').exists():
        raise ValueError('operator_incomplete')
    failed, failed_record = _json_artifact(
        pins.failed_run / 'result.json', pins.failed_result_sha256, 'operator_result')
    try:
        if (failed['success'] is not False or failed['cleanup_confirmed'] is not True
                or failed['owned_exit_confirmed'] is not True
                or failed['collector_terminal'] is not True
                or failed['recovery_samples'] != 5):
            raise ValueError('operator_result_invalid')
        failed_base = _baseline(failed['original_baseline'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('operator_result_invalid') from error
    gdn, gdn_record = _operator_result(pins, 'gdn', pins.gdn_run,
                                       pins.gdn_result_sha256)
    iq, iq_record = _operator_result(pins, 'iq-experts', pins.iq_run,
                                     pins.iq_result_sha256)
    sequence, sequence_record = _json_artifact(
        pins.operator_evidence / 'sequence.json', None, 'operator_sequence')
    try:
        if (sequence['stage'] != 'iq-experts' or sequence['success'] is not True
                or sequence['policy'] != operator_store.POLICY_ID
                or sequence['source'] != (pins.operator_source_commit or pins.source_commit)
                or sequence['binary'] != PROBES['iq-experts'].sha256
                or sequence['run'] != str(pins.iq_run)):
            raise ValueError('operator_sequence_invalid')
        if failed_base != gdn or gdn != iq or _baseline(sequence['baseline']) != gdn:
            raise ValueError('operator_baseline_mismatch')
    except (KeyError, TypeError, ValueError) as error:
        if str(error).startswith('operator_baseline'):
            raise
        raise ValueError('operator_sequence_invalid') from error
    return gdn, [failed_record, gdn_record, iq_record, sequence_record]


def _digest_valid(value):
    return isinstance(value, str) and re.fullmatch('[0-9A-F]{64}', value) is not None


def _experiment(value, profile_id):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('experiment_invalid')
    try:
        parsed = json.loads(value)
        canonical = json.dumps(parsed, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError) as error:
        raise ValueError('experiment_invalid') from error
    if profile_id in (MTP_4K, MATCHED_AR, MATCHED_AR_V2, MATCHED_MTP, MATCHED_MTP_D3):
        if profile_id == MTP_4K:
            from . import mtp_stage
            expected = mtp_stage.experiment_definition()
        else:
            from . import matched_profile
            expected = matched_profile.experiment_definition(profile_id)
        if (not isinstance(parsed, dict) or parsed.keys() != expected.keys()
                or canonical != value or any(type(parsed[k]) is not type(v) or parsed[k] != v
                                              for k, v in expected.items())):
            raise ValueError('experiment_invalid')
        return parsed
    four = profile_id == BENCHMARK_4K
    expected = dict(profile_id=profile_id,
        recipe_sha256=parsed.get('recipe_sha256') if isinstance(parsed, dict) else None,
        context_tokens=4096 if four else 16384,
        max_prompt_tokens=3072 if four else 16383, max_output_tokens=256,
        max_requests=36 if four else 13, sessions=1, max_connections=16,
        max_request_bytes=262144, max_response_bytes=1048576,
        request_seconds=60, startup_seconds=480, lifetime_seconds=600,
        speculative=False, disk_cache=False)
    if (profile_id not in (BENCHMARK_4K, BENCHMARK_16K)
            or not isinstance(parsed, dict) or parsed.keys() != expected.keys()
            or canonical != value or not _digest_valid(expected['recipe_sha256'])
            or any(type(parsed[k]) is not type(v) or parsed[k] != v for k, v in expected.items())):
        raise ValueError('experiment_invalid')
    return parsed


def _binding(pins):
    if pins.profile_id not in PROFILE_ROOTS:
        raise ValueError('unknown_profile')
    if pins.profile_id == FINITE_SERVICE:
        from .finite_profile import finite_binding
        return finite_binding(pins)
    if pins.profile_id == SERVICE_SMOKE:
        from .service_smoke_store import service_binding
        return service_binding(pins)
    if pins.profile_id == INSTALLED_SERVICE:
        from .service_store import installed_binding
        return installed_binding(pins)
    if pins.operator_source_commit is not None:
        raise ValueError('unexpected_operator_source')
    bounds = profile_bounds(pins.profile_id)
    if (not isinstance(pins.bounds, dict) or pins.bounds.keys() != bounds.keys()
            or any(type(pins.bounds[k]) is not int or pins.bounds[k] != v
                   for k, v in bounds.items())):
        raise ValueError('unsafe_bounds')
    if pins.profile_id in (MTP_4K, MATCHED_MTP, MATCHED_MTP_D3):
        margin_sha = (MTP_MARGIN_SHA256 if pins.profile_id == MTP_4K else
                      MATCHED_D3_MARGIN_SHA256 if pins.profile_id == MATCHED_MTP_D3 else
                      MATCHED_MARGIN_SHA256)
        margin_path = (ROOT/'reports/gufo-mtp4k-staged-envelope-review-20260926.md'
            if pins.profile_id == MTP_4K else
            ROOT/'reports/gufo-mtp-draft3-envelope-review-20260926.md'
            if pins.profile_id == MATCHED_MTP_D3 else
            ROOT/'reports/gufo-matched-mtp-envelope-review-20260926.md')
        if (not isinstance(pins.sidecar, SidecarPin) or pins.sidecar.path != MTP_SIDECAR.path
                or any(type(getattr(pins.sidecar, key)) is not int or
                       getattr(pins.sidecar, key) != getattr(MTP_SIDECAR, key)
                       for key in ('size_bytes', 'descriptor_end', 'tensor_count'))
                or pins.sidecar.descriptor_sha256 != MTP_SIDECAR.descriptor_sha256
                or pins.model_revision != AR4K_PINS.revision
                or pins.margin_sha256 != margin_sha
                or pins.margin_report != margin_path):
            raise ValueError('mtp_identity_invalid')
        stamp = pins.sidecar_stamp
        if (type(stamp) is not tuple or len(stamp) != 3
                or type(stamp[0]) is not str or stamp[0] != str(pins.sidecar.path)
                or type(stamp[1]) is not int or stamp[1] != pins.sidecar.size_bytes
                or type(stamp[2]) is not int or stamp[2] <= 0):
            raise ValueError('model_sidecar_stamp_invalid')
    elif pins.sidecar is not None or pins.sidecar_stamp is not None:
        raise ValueError('unexpected_sidecar')
    if pins.profile_id in (MATCHED_AR, MATCHED_AR_V2) and (pins.margin_sha256 != MATCHED_MARGIN_SHA256
            or pins.margin_report != ROOT/'reports/gufo-matched-mtp-envelope-review-20260926.md'):
        raise ValueError('matched_margin_invalid')
    if pins.profile_id == PROFILE_ID:
        if pins.experiment_json is not None or pins.predecessors != () or pins.acceptance_sha256 is not None:
            raise ValueError('legacy_benchmark_binding')
        return {}
    experiment = _experiment(pins.experiment_json, pins.profile_id)
    if not pins.evidence.is_absolute() or pins.evidence.name != PROFILE_ROOTS[pins.profile_id]:
        raise ValueError('benchmark_root_invalid')
    if pins.profile_id in (MATCHED_AR, MATCHED_AR_V2, MATCHED_MTP, MATCHED_MTP_D3) and (
            pins.evidence != ROOT/'reports'/PROFILE_ROOTS[pins.profile_id]
            or pins.qualification != ROOT/'reports'/(
                'gufo-matched-ar4k-v1-qualification.json' if pins.profile_id == MATCHED_AR
                else 'gufo-matched-ar4k-v2-qualification.json' if pins.profile_id == MATCHED_AR_V2
                else 'gufo-matched-mtp4k-d3-v1-qualification.json' if pins.profile_id == MATCHED_MTP_D3
                else 'gufo-matched-mtp4k-v1-qualification.json')):
        raise ValueError('matched_paths_invalid')
    if type(pins.predecessors) is not tuple or len(pins.predecessors) != 1:
        raise ValueError('predecessor_missing')
    predecessor = pins.predecessors[0]
    expected_id = PROFILE_ID if pins.profile_id == BENCHMARK_4K else BENCHMARK_4K
    if (not isinstance(predecessor, PredecessorPin) or predecessor.profile_id != expected_id
            or not isinstance(predecessor.run, Path) or not predecessor.run.is_absolute()
            or not _digest_valid(predecessor.result_sha256)):
        raise ValueError('predecessor_identity_invalid')
    if pins.profile_id in (BENCHMARK_16K, MTP_4K, MATCHED_AR, MATCHED_AR_V2, MATCHED_MTP, MATCHED_MTP_D3):
        if not _digest_valid(pins.acceptance_sha256):
            raise ValueError('acceptance_digest_missing')
        if pins.profile_id in (MTP_4K, MATCHED_AR, MATCHED_AR_V2, MATCHED_MTP, MATCHED_MTP_D3) and predecessor.result_sha256 != MTP_PREDECESSOR_SHA256:
            raise ValueError('mtp_predecessor_identity_invalid')
    elif pins.acceptance_sha256 is not None:
        raise ValueError('unexpected_acceptance')
    result = dict(experiment=experiment, predecessors=[dict(
        profile_id=predecessor.profile_id, run=str(predecessor.run),
        result_sha256=predecessor.result_sha256)])
    if pins.profile_id in (BENCHMARK_16K, MTP_4K, MATCHED_AR, MATCHED_AR_V2, MATCHED_MTP, MATCHED_MTP_D3):
        result['acceptance_sha256'] = pins.acceptance_sha256
    return result


def _incomplete_latches(pins, *, manifest=None, current_run=None):
    if (pins.operator_evidence / 'incomplete.json').exists():
        raise ValueError('operator_incomplete')
    roots = {pins.evidence, *(pins.evidence.parent / name for name in (
        'gufo-ar4k-smoke-runs', 'gufo-ar4k-connect-wait-smoke-runs',
        'gufo-ar4k-benchmark-runs', 'gufo-ar16k-benchmark-runs',
        'gufo-ar16k-benchmark-v2-runs',
        *PROFILE_ROOTS.values()))}
    for root in roots:
        if (root / 'incomplete.json').exists():
            if current_run is not None and root.resolve() == pins.evidence.resolve():
                if pins.profile_id == INSTALLED_SERVICE:
                    from .service_store import _current_run_markers as installed_current_run_markers
                    installed_current_run_markers(manifest, pins, current_run)
                else:
                    _current_run_markers(manifest, pins, current_run)
            else:
                raise ValueError('prior_smoke_incomplete')


def _predecessor_records(pins):
    records = []
    for pin in pins.predecessors:
        root = pins.evidence.parent / PROFILE_ROOTS[pin.profile_id]
        run = pin.run
        if (not run.is_absolute() or not run.is_dir() or run.resolve(strict=True) != run
                or run.parent != root or run.resolve(strict=True).parent != root.resolve(strict=True)):
            raise ValueError('predecessor_run_invalid')
        if pins.profile_id == BENCHMARK_4K and (
                run.name != FIRST_PREDECESSOR_RUN or pin.result_sha256 != FIRST_PREDECESSOR_SHA256):
            raise ValueError('predecessor_identity_invalid')
        if (root / 'incomplete.json').exists():
            raise ValueError('predecessor_incomplete')
        if any(path.is_symlink() or path.resolve(strict=True).parent != path.parent
               for path in (run/'result.json', root/'attempt.json')):
            raise ValueError('predecessor_artifact_path')
        result, stamp = _json_artifact(run/'result.json', pin.result_sha256, 'predecessor_result')
        marker, marker_stamp = _json_artifact(root/'attempt.json', None, 'predecessor_attempt')
        flags = ('success', 'owned_exit_confirmed', 'collector_terminal',
                 'collector_cleanup_confirmed', 'http_terminal', 'inspection_terminal',
                 'inspection_duplicate_closed', 'evidence_write_confirmed', 'cleanup_confirmed')
        if (not isinstance(result, dict) or result.get('profile') != pin.profile_id
                or any(result.get(key) is not True for key in flags)
                or type(result.get('recovery_samples')) is not int or result['recovery_samples'] != 5
                or not isinstance(marker, dict) or marker.get('run') != str(run)
                or marker.get('profile') != pin.profile_id):
            raise ValueError('predecessor_result_invalid')
        artifacts = []
        if pin.profile_id == BENCHMARK_4K:
            try:
                experiment = result['manifest']['experiment']
                _experiment(json.dumps(experiment, sort_keys=True, separators=(',', ':')), pin.profile_id)
                from . import benchmark_recipes
                expected_recipe = sha256(benchmark_recipes.recipe_json(BENCHMARK_4K).encode()).hexdigest().upper()
                if experiment['recipe_sha256'] != expected_recipe:
                    raise ValueError('predecessor_recipe_invalid')
                rows = result['http']['rows']
                if (result['http']['success'] is not True or not isinstance(rows, list)
                        or len(rows) != experiment['max_requests']):
                    raise ValueError('predecessor_rows_invalid')
                for ordinal, row in enumerate(rows):
                    artifact = row['artifact']
                    if (row['status'] != 'completed' or not isinstance(artifact, dict)
                            or set(artifact) != {'name', 'size_bytes', 'sha256'}
                            or artifact['name'] != f'request-{ordinal:03d}.json'
                            or type(artifact['size_bytes']) is not int
                            or not 0 < artifact['size_bytes'] <= 16*1024*1024
                            or not _digest_valid(artifact['sha256'])):
                        raise ValueError('predecessor_artifact_invalid')
                    path = run / artifact['name']
                    if path.is_symlink() or path.resolve(strict=True).parent != run.resolve(strict=True):
                        raise ValueError('predecessor_artifact_path')
                    if path.stat().st_size != artifact['size_bytes']:
                        raise ValueError('predecessor_artifact_size')
                    artifacts.append(_checked_artifact(path,
                        (artifact['size_bytes'], artifact['sha256']), 'predecessor_request'))
            except (KeyError, TypeError, OSError) as error:
                raise ValueError('predecessor_rows_invalid') from error
        records.append(dict(identity=dict(profile_id=pin.profile_id, run=str(run),
            result_sha256=pin.result_sha256), result=stamp, attempt=marker_stamp,
            artifacts=artifacts))
    return records


def _benchmark_records(pins):
    binding = _binding(pins)
    if pins.profile_id == SERVICE_SMOKE:
        return binding
    if not binding:
        return {}
    result = dict(experiment=binding['experiment'], predecessors=_predecessor_records(pins))
    if pins.profile_id in (BENCHMARK_16K, MTP_4K, MATCHED_AR, MATCHED_AR_V2, MATCHED_MTP, MATCHED_MTP_D3):
        path = pins.evidence.parent/'gufo-ar4k-benchmark-acceptance.json'
        if path.is_symlink() or path.resolve(strict=True).parent != path.parent:
            raise ValueError('acceptance_path_invalid')
        acceptance, stamp = _json_artifact(path, pins.acceptance_sha256, 'acceptance')
        identity = binding['predecessors'][0]
        if (not isinstance(acceptance, dict) or set(acceptance) !=
                {'profile_id', 'run', 'result_sha256', 'semantic_status', 'review_id'}
                or any(acceptance.get(k) != v for k, v in identity.items())
                or acceptance['semantic_status'] != 'passed'
                or not isinstance(acceptance['review_id'], str) or not acceptance['review_id'].strip()):
            raise ValueError('acceptance_invalid')
        result['acceptance'] = dict(record=acceptance, artifact=stamp)
    return result


def _recheck_benchmark(manifest, pins):
    """Cheap stamped recheck of the already hashed bounded predecessor evidence."""
    binding = _binding(pins)
    if pins.profile_id == SERVICE_SMOKE:
        if manifest.get('service') != binding['service'] or any(
                key in manifest for key in ('experiment', 'predecessors', 'acceptance')):
            raise ValueError('service_binding_changed')
        return
    if not binding:
        if any(key in manifest for key in ('experiment', 'predecessors', 'acceptance')):
            raise ValueError('legacy_benchmark_binding')
        return
    if manifest.get('experiment') != binding['experiment']:
        raise ValueError('benchmark_binding_changed')
    records = manifest['predecessors']
    if not isinstance(records, list) or len(records) != len(pins.predecessors):
        raise ValueError('predecessor_binding_changed')
    for pin, record, identity in zip(pins.predecessors, records, binding['predecessors']):
        if record['identity'] != identity:
            raise ValueError('predecessor_binding_changed')
        root = pins.evidence.parent / PROFILE_ROOTS[pin.profile_id]
        if (pin.run.parent != root or pin.run.is_symlink()
                or pin.run.resolve(strict=True).parent != root.resolve(strict=True)):
            raise ValueError('predecessor_run_invalid')
        expected = [(record['result'], pin.run/'result.json'),
                    (record['attempt'], root/'attempt.json')]
        if record['result']['sha256'] != pin.result_sha256:
            raise ValueError('predecessor_binding_changed')
        artifacts = record['artifacts']
        count = 36 if pin.profile_id == BENCHMARK_4K else 0
        if not isinstance(artifacts, list) or len(artifacts) != count:
            raise ValueError('predecessor_artifact_invalid')
        expected.extend((artifact, pin.run/f'request-{ordinal:03d}.json')
                        for ordinal, artifact in enumerate(artifacts))
        for artifact, path in expected:
            if (path.is_symlink() or artifact['stamp'][0] != str(path.resolve(strict=True))
                    or operator_store.stamp(path) != artifact['stamp']):
                raise ValueError('predecessor_artifact_changed')
    if pins.profile_id in (BENCHMARK_16K, MTP_4K, MATCHED_AR, MATCHED_AR_V2, MATCHED_MTP, MATCHED_MTP_D3):
        acceptance = manifest['acceptance']
        path = pins.evidence.parent/'gufo-ar4k-benchmark-acceptance.json'
        artifact = acceptance['artifact']
        record = acceptance['record']
        if (set(record) != {'profile_id', 'run', 'result_sha256', 'semantic_status', 'review_id'}
                or any(record.get(k) != v for k, v in binding['predecessors'][0].items())
                or record['semantic_status'] != 'passed'
                or not isinstance(record['review_id'], str) or not record['review_id'].strip()
                or artifact['sha256'] != pins.acceptance_sha256
                or artifact['stamp'][0] != str(path.resolve(strict=True))
                or operator_store.stamp(path) != artifact['stamp']):
            raise ValueError('acceptance_changed')
    elif 'acceptance' in manifest:
        raise ValueError('unexpected_acceptance')


def expected_qualification(pins: StorePins, guard_review_id: str) -> dict:
    """Exact record shape for an independent review to sign off later."""
    binding = _binding(pins)
    mtp_recipe = {}
    if pins.profile_id == MTP_4K:
        from . import mtp_stage
        mtp_recipe = {'mtp_recipe': mtp_stage.recipe_definition()}
    return {
        'profile': pins.profile_id,
        'source': pins.source_commit,
        'executable_sha256': pins.executable[1],
        'model_revision': pins.model_revision,
        'model_descriptors': list(pins.model_descriptors),
        'bounds': pins.bounds,
        'failed_gdn_result_sha256': pins.failed_result_sha256,
        'gdn_result_sha256': pins.gdn_result_sha256,
        'iq_result_sha256': pins.iq_result_sha256,
        'margin_report_sha256': pins.margin_sha256,
        'recovery_policy': 'per-run-recovery-stricter-runtime-v1',
        'guard_review_id': guard_review_id,
        **mtp_recipe,
        **({'sidecar': {'path': str(pins.sidecar.path), 'size_bytes': pins.sidecar.size_bytes,
                         'descriptor_end': pins.sidecar.descriptor_end,
                         'descriptor_sha256': pins.sidecar.descriptor_sha256,
                         'tensor_count': pins.sidecar.tensor_count,
                         'stamp': list(pins.sidecar_stamp)}} if pins.sidecar else {}),
        **binding,
    }


def _qualification(pins: StorePins):
    try:
        record, stamp = _json_artifact(pins.qualification, None, 'qualification')
    except OSError as error:
        raise ValueError('guard_review_missing') from error
    review_id = record.get('guard_review_id') if isinstance(record, dict) else None
    if not isinstance(review_id, str) or not review_id.strip():
        raise ValueError('guard_review_missing')
    if record != expected_qualification(pins, review_id):
        raise ValueError('qualification_mismatch')
    return record, stamp


def _projector_absent(first_shard: Path):
    for directory in (first_shard.parent, first_shard.parent.parent):
        try:
            if any(item.name.casefold() == 'mmproj-bf16.gguf'
                   for item in directory.iterdir()):
                raise ValueError(f'projector_candidate:{directory}')
        except OSError as error:
            raise ValueError(f'projector_directory_unavailable:{directory}') from error


def _verify_candidate_artifacts(pins: StorePins, *, model_validator) -> dict:
    """Immutable candidate payload checks, with no attempt or qualification state."""
    artifacts = [_checked_artifact(pins.build / pins.executable_name,
                                   pins.executable, 'server_executable')]
    for name, pin in pins.sdk_dlls.items():
        artifacts.append(_checked_artifact(pins.sdk / 'bin' / name, pin, f'sdk/{name}'))
        artifacts.append(_checked_artifact(pins.build / name, pin, f'local/{name}'))
    for name, pin in pins.vcpkg_dlls.items():
        artifacts.append(_checked_artifact(pins.build / name, pin, f'vcpkg/{name}'))
    artifacts.append(_checked_artifact(pins.host_openmp, pins.host_openmp_pin,
                                       'host_openmp'))
    for name, pin in pins.trees.items():
        for prefix, base in (('sdk', pins.sdk / 'bin'), ('local', pins.build)):
            artifacts.extend(_tree_records(base / name, pin,
                                           f'{prefix}/{name}'))
    model = model_validator(pins.first_shard)
    if (not isinstance(model, ValidatedModel)
            or model.first_shard != pins.first_shard.resolve(strict=True)
            or model.revision != pins.model_revision):
        raise ValueError('model_identity_mismatch')
    model_stamps = [operator_store.stamp(pins.first_shard.parent / name)
                    for name in pins.shard_names]
    sidecar = validate_mtp_sidecar(pins.first_shard, pins.sidecar) if pins.sidecar else None
    if pins.sidecar and (not isinstance(sidecar, dict)
                        or sidecar.get('stamp') != list(pins.sidecar_stamp)):
        raise ValueError('model_sidecar_changed')
    _projector_absent(pins.first_shard)
    return {
        'executable': str((pins.build / pins.executable_name).resolve()),
        'sdk': str(pins.sdk),
        'model': {'first_shard': str(model.first_shard),
                  'revision': model.revision, 'shards': model_stamps,
                  'payload_hash_limit': 'bounded GGUF metadata only',
                  **({'sidecar': sidecar} if sidecar else {})},
        'artifacts': artifacts,
    }


def _verify_static(pins: StorePins, *, source_validator, model_validator) -> dict:
    _binding(pins)
    _incomplete_latches(pins)
    benchmark = _benchmark_records(pins)
    source_validator()
    candidate = _verify_candidate_artifacts(pins, model_validator=model_validator)
    baseline, state = _operator_sequence(pins)
    margin = _checked_artifact(pins.margin_report,
                               (pins.margin_report.stat().st_size,
                                pins.margin_sha256), 'margin_report')
    qualification, qualification_stamp = _qualification(pins)
    if (pins.evidence / 'incomplete.json').exists():
        raise ValueError('prior_smoke_incomplete')
    if (pins.evidence / 'attempt.json').exists():
        raise ValueError('prior_smoke_attempt')
    return {
        'profile': pins.profile_id,
        'source': pins.source_commit,
        'bounds': dict(pins.bounds),
        **candidate,
        'operator': {'original_baseline': asdict(baseline),
                     'state': state},
        'margin_report': margin,
        'qualification': qualification,
        'qualification_stamp': qualification_stamp,
        **benchmark,
    }


def verify_static() -> dict:
    return _verify_static(PINS, source_validator=operator_store.source_identity,
                          model_validator=validate_ar4k_model)


def _expected_artifact_paths(pins: StorePins):
    expected = [('server_executable', pins.build / pins.executable_name)]
    for name in pins.sdk_dlls:
        expected.extend(((f'sdk/{name}', pins.sdk / 'bin' / name),
                         (f'local/{name}', pins.build / name)))
    for name in pins.vcpkg_dlls:
        expected.append((f'vcpkg/{name}', pins.build / name))
    expected.append(('host_openmp', pins.host_openmp))
    for name in pins.trees:
        for prefix, base in (('sdk', pins.sdk / 'bin'), ('local', pins.build)):
            tree = base / name
            expected.extend((f'{prefix}/{name}/{relative}', path)
                            for relative, path in _tree_files(tree))
    return [(label, str(path.resolve(strict=True))) for label, path in expected]


def _current_run_markers(manifest: dict, pins: StorePins, current_run: Path) -> None:
    run_dir = Path(current_run)
    root = pins.evidence.resolve(strict=True)
    if (not run_dir.is_absolute() or not run_dir.is_dir()
            or run_dir.parent.resolve(strict=True) != root
            or run_dir.resolve(strict=True).parent != root):
        raise ValueError('invalid_smoke_run_directory')
    run = str(run_dir)
    attempt = operator_store.read_json(pins.evidence / 'attempt.json')
    latch = operator_store.read_json(pins.evidence / 'incomplete.json')
    persisted = operator_store.read_json(run_dir / 'manifest.json')
    expected = json.loads(json.dumps(manifest, allow_nan=False))
    if (not isinstance(attempt, dict) or attempt.get('run') != run
            or attempt.get('profile') != pins.profile_id
            or not isinstance(latch, dict) or latch.get('run') != run
            or latch.get('original_baseline') != expected['operator']['original_baseline']
            or persisted != expected):
        raise ValueError('current_smoke_run_mismatch')


def _recheck_candidate_artifacts(manifest: dict, pins: StorePins) -> None:
    if (manifest['executable'] != str((pins.build / pins.executable_name).resolve())
            or manifest['sdk'] != str(pins.sdk)
            or manifest['model']['first_shard'] != str(pins.first_shard.resolve(strict=True))
            or manifest['model']['revision'] != pins.model_revision
            or len(manifest['model']['shards']) != 3):
        raise ValueError('manifest_identity_mismatch')
    present = [(record['label'], record['stamp'][0])
               for record in manifest['artifacts']]
    if present != _expected_artifact_paths(pins):
        raise ValueError('manifest_artifacts_mismatch')
    for record in manifest['artifacts']:
        if operator_store.stamp(record['stamp'][0]) != record['stamp']:
            raise ValueError(f'artifact_changed:{record["label"]}')
    for stamped, name in zip(manifest['model']['shards'], pins.shard_names):
        if stamped[0] != str((pins.first_shard.parent / name).resolve(strict=True)):
            raise ValueError('manifest_model_mismatch')
        if operator_store.stamp(stamped[0]) != stamped:
            raise ValueError('model_shard_changed')
    if pins.sidecar:
        sidecar = manifest['model']['sidecar']
        if (sidecar != {'path': str(pins.sidecar.path),
                        'size_bytes': pins.sidecar.size_bytes,
                        'descriptor_end': pins.sidecar.descriptor_end,
                        'tensor_count': pins.sidecar.tensor_count,
                        'descriptor_sha256': pins.sidecar.descriptor_sha256,
                        'stamp': list(pins.sidecar_stamp)}
                or operator_store.stamp(pins.sidecar.path) != list(pins.sidecar_stamp)
                or pins.sidecar.path.is_symlink() or pins.sidecar.path.parent.is_symlink()
                or pins.sidecar.path.resolve(strict=True) != pins.sidecar.path):
            raise ValueError('model_sidecar_changed')
    elif 'sidecar' in manifest['model']:
        raise ValueError('unexpected_sidecar')
    _projector_absent(pins.first_shard)


def _recheck_static(manifest: dict, pins: StorePins, *, source_validator,
                    current_run=None) -> None:
    _binding(pins)
    source_validator()
    try:
        _incomplete_latches(pins, manifest=manifest, current_run=current_run)
        _recheck_benchmark(manifest, pins)
        if (manifest['profile'] != pins.profile_id
                or manifest['source'] != pins.source_commit
                or manifest['bounds'] != pins.bounds
                or any(type(manifest['bounds'].get(k)) is not int for k in pins.bounds)):
            raise ValueError('manifest_identity_mismatch')
        _recheck_candidate_artifacts(manifest, pins)
        state_paths = [pins.failed_run / 'result.json', pins.gdn_run / 'result.json',
                       pins.iq_run / 'result.json',
                       pins.operator_evidence / 'sequence.json']
        if [(record['label'], record['stamp'][0]) for record in manifest['operator']['state']] != [
                (label, str(path.resolve(strict=True))) for label, path in zip(
                    ('operator_result', 'operator_result', 'operator_result',
                     'operator_sequence'), state_paths)]:
            raise ValueError('manifest_operator_mismatch')
        if manifest['margin_report']['stamp'][0] != str(pins.margin_report.resolve(strict=True)):
            raise ValueError('manifest_margin_mismatch')
        for record in [*manifest['operator']['state'], manifest['margin_report']]:
            if operator_store.stamp(record['stamp'][0]) != record['stamp']:
                raise ValueError(f'{record["label"]}_changed')
        record = manifest['qualification_stamp']
        if record['stamp'][0] != str(pins.qualification.resolve(strict=True)):
            raise ValueError('manifest_qualification_mismatch')
        if operator_store.stamp(record['stamp'][0]) != record['stamp']:
            raise ValueError('qualification_changed')
        if (manifest['qualification'] != expected_qualification(
                pins, manifest['qualification']['guard_review_id'])):
            raise ValueError('qualification_mismatch')
        if (pins.operator_evidence / 'incomplete.json').exists():
            raise ValueError('operator_incomplete')
        if current_run is None:
            if (pins.evidence / 'incomplete.json').exists():
                raise ValueError('prior_smoke_incomplete')
            if (pins.evidence / 'attempt.json').exists():
                raise ValueError('prior_smoke_attempt')
        else:
            _current_run_markers(manifest, pins, current_run)
    except (KeyError, TypeError, IndexError, OSError) as error:
        raise ValueError('manifest_recheck_invalid') from error


def recheck_static(manifest: dict, *, current_run=None) -> None:
    _recheck_static(manifest, PINS, source_validator=operator_store.source_identity,
                    current_run=current_run)


def _load_original_operator_baseline(pins: StorePins) -> Baseline:
    baseline, _ = _operator_sequence(pins)
    return baseline


def load_original_operator_baseline() -> Baseline:
    return _load_original_operator_baseline(PINS)


def _begin_run(run_dir: Path, manifest: dict, baseline: Baseline, pins: StorePins) -> None:
    run_dir = Path(run_dir)
    _binding(pins)
    _incomplete_latches(pins)
    _recheck_benchmark(manifest, pins)
    if (pins.evidence / 'incomplete.json').exists():
        raise ValueError('prior_smoke_incomplete')
    if (pins.evidence / 'attempt.json').exists():
        raise ValueError('prior_smoke_attempt')
    if run_dir.parent.resolve() != pins.evidence.resolve() or not run_dir.is_dir():
        raise ValueError('invalid_smoke_run_directory')
    if manifest['profile'] != pins.profile_id or asdict(baseline) != manifest['operator']['original_baseline']:
        raise ValueError('smoke_manifest_baseline_mismatch')
    # Write the permanent marker first. Any later write failure consumes the attempt.
    operator_store.atomic_json(pins.evidence / 'attempt.json',
                               {'run': str(run_dir), 'profile': pins.profile_id})
    operator_store.atomic_json(pins.evidence / 'incomplete.json',
                               {'run': str(run_dir), 'phase': 'before_create',
                                'original_baseline': asdict(baseline)})
    operator_store.atomic_json(run_dir / 'manifest.json', manifest)


def begin_run(run_dir: Path, manifest: dict, baseline: Baseline) -> None:
    recheck_static(manifest)
    _begin_run(run_dir, manifest, baseline, PINS)


def _finish_run(run_dir: Path, result: dict, pins: StorePins) -> None:
    run_dir = Path(run_dir)
    latch = operator_store.read_json(pins.evidence / 'incomplete.json')
    marker = operator_store.read_json(pins.evidence / 'attempt.json')
    if latch['run'] != str(run_dir) or marker['run'] != str(run_dir):
        raise ValueError('smoke_run_mismatch')
    operator_store.atomic_json(run_dir / 'result.json', result)
    if result.get('cleanup_confirmed') is True:
        (pins.evidence / 'incomplete.json').unlink()


def finish_run(run_dir: Path, result: dict) -> None:
    _finish_run(run_dir, result, PINS)
