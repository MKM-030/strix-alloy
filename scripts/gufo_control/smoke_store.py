"""Fixed provenance and one-attempt evidence for the private AR4k smoke.

This module performs no model execution. The qualification record is deliberately
absent by default; only an independently reviewed, exact binding can admit a run.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from . import operator_store
from .model_identity import AR4K_PINS, ValidatedModel, validate_ar4k_model
from .operator_policy import Baseline, PROBES


PROFILE_ID = 'ar4k-iq4xs-single-smoke-v1'
ROOT = Path(r'C:\Projects\strix-alloy-research')
SOURCE = ROOT / 'sources/gufo-windows'
SDK = Path(r'C:\AI\sdk\therock1151')
BUILD = ROOT / 'build/gufo-hip-10.2'
EVIDENCE = ROOT / 'reports/gufo-ar4k-smoke-runs'
QUALIFICATION = ROOT / 'reports/gufo-ar4k-smoke-qualification.json'
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
                or manifest['source'] != pins.source_commit
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
                or sequence['source'] != pins.source_commit
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


def expected_qualification(pins: StorePins, guard_review_id: str) -> dict:
    """Exact record shape for an independent review to sign off later."""
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


def _verify_static(pins: StorePins, *, source_validator, model_validator) -> dict:
    if pins.profile_id != PROFILE_ID:
        raise ValueError('unknown_profile')
    source_validator()
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
    _projector_absent(pins.first_shard)
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
        'profile': PROFILE_ID,
        'source': pins.source_commit,
        'executable': str((pins.build / pins.executable_name).resolve()),
        'sdk': str(pins.sdk),
        'bounds': dict(pins.bounds),
        'model': {'first_shard': str(model.first_shard),
                  'revision': model.revision, 'shards': model_stamps,
                  'payload_hash_limit': 'bounded GGUF metadata only'},
        'artifacts': artifacts,
        'operator': {'original_baseline': asdict(baseline),
                     'state': state},
        'margin_report': margin,
        'qualification': qualification,
        'qualification_stamp': qualification_stamp,
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
            or attempt.get('profile') != PROFILE_ID
            or not isinstance(latch, dict) or latch.get('run') != run
            or latch.get('original_baseline') != expected['operator']['original_baseline']
            or persisted != expected):
        raise ValueError('current_smoke_run_mismatch')


def _recheck_static(manifest: dict, pins: StorePins, *, source_validator,
                    current_run=None) -> None:
    source_validator()
    try:
        if (manifest['profile'] != PROFILE_ID
                or manifest['source'] != pins.source_commit
                or manifest['executable'] != str((pins.build / pins.executable_name).resolve())
                or manifest['sdk'] != str(pins.sdk)
                or manifest['bounds'] != pins.bounds
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
        _projector_absent(pins.first_shard)
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
    if (pins.evidence / 'incomplete.json').exists():
        raise ValueError('prior_smoke_incomplete')
    if (pins.evidence / 'attempt.json').exists():
        raise ValueError('prior_smoke_attempt')
    if run_dir.parent.resolve() != pins.evidence.resolve() or not run_dir.is_dir():
        raise ValueError('invalid_smoke_run_directory')
    if manifest['profile'] != PROFILE_ID or asdict(baseline) != manifest['operator']['original_baseline']:
        raise ValueError('smoke_manifest_baseline_mismatch')
    # Write the permanent marker first. Any later write failure consumes the attempt.
    operator_store.atomic_json(pins.evidence / 'attempt.json',
                               {'run': str(run_dir), 'profile': PROFILE_ID})
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
