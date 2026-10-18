"""Exact historical no-owned-allocation disposition; no recovery or launch."""
from hashlib import sha256
import json
import os
from pathlib import Path

from . import operator_store, service_recovery


REPORTS = Path(r'C:\Projects\strix-alloy-research\reports')
ROOT = REPORTS / 'small-c2-mtp-d3-20260927-v1-admission2-runs'
RUN = ROOT / '20260927T195059Z-ffb612d8d505475685dbaea057a67255'
PROFILE = 'small-c2-mtp-d3-20260927-v1'
FRESH_ROOT = REPORTS / 'small-c2-active-desktop-20260927-v1-runs'
CERTIFICATE = RUN / 'no-owned-allocation-disposition.json'
APPROVAL = REPORTS / 'small-c2-active-desktop-20260927-v1-approval.json'
AUDIT = REPORTS / 'small-c2-admission2-audit-20260927.md'
DISPOSITION_REVIEW = REPORTS / 'small-c2-no-launch-disposition-review-20260927.md'
DISPOSITION_REVIEW_SHA = 'AB43055CF2A45BEE3963282DAF284C9DD5817D59456DD2B86A63F8D662B1AF7B'
RESULT = RUN / 'result.json'
LATCH = ROOT / 'incomplete.json'
VERIFICATION = ROOT / 'verification-attempt.json'
TELEMETRY = RUN / 'telemetry.jsonl'
MODULE = Path(__file__)
GUARD_SOURCE = MODULE.with_name('smoke_guard.py')
POLICY_SOURCE = MODULE.with_name('operator_policy.py')

PINS = {
    'result': (RESULT, 'D2137DEC6DC4DA7014B206325161144A634611C3B325D8A692FDD37E8CB72A4F'),
    'latch': (LATCH, '5B2CDAF8420AD14F2A8CC4FC778899C2BE6105DF18B3A62094C29C41B8BEA514'),
    'verification': (VERIFICATION, 'C4D608187C91DFB54B7FB48890A1F80DB5E7F034E9EAB706A8AB4B1AC00409FD'),
    'telemetry': (TELEMETRY, 'E3A26AA5296A7FCB01BAB80E21CBB71CB3E5BC64FAB2173EF03D2F300C7F61E0'),
    'failed_audit': (AUDIT, '6CAF317703D65D44CE85785F11CB29F80F4F4FB5BE95684220A109C4AFCEA9DE'),
    'guard_source': (GUARD_SOURCE, 'EB7CE433835BC2A83B44EC472AEF737915E4690321C6DAF2AE6E0A23F492199A'),
    'policy_source': (POLICY_SOURCE, '4D2FF372AD13D5B055F49AE90AD9011A7EC0C1ED89CD85DEB11DF458164ABCF8'),
}
TERMINAL_FLAGS = ('owned_exit_confirmed', 'collector_terminal',
    'collector_cleanup_confirmed', 'http_terminal', 'inspection_terminal',
    'inspection_duplicate_closed', 'evidence_write_confirmed')
FAILURE = 'ValueError:baseline_unstable:available_physical_bytes;RuntimeError:recovery_unconfirmed'
CAPABILITY = 'small-c2-no-owned-allocation-disposition-v1'
MEANING = 'no_owned_allocation_disposition'
MAX_JSON = 2 * 1024 * 1024
MAX_TELEMETRY = 2 * 1024 * 1024


def _directory(path):
    if path.is_symlink() or path.resolve(strict=True) != path or not path.is_dir():
        raise ValueError('unexpected_evidence_directory')


def _record(path, limit):
    if path.is_symlink() or path.resolve(strict=True) != path or not path.is_file():
        raise ValueError('unexpected_evidence_path')
    before = operator_store.stamp(path)
    if not 0 < before[1] <= limit:
        raise ValueError('evidence_size_bound')
    digest = sha256()
    size = 0
    with path.open('rb') as stream:
        while block := stream.read(65536):
            size += len(block)
            if size > limit:
                raise ValueError('evidence_size_bound')
            digest.update(block)
    if size != before[1] or operator_store.stamp(path) != before:
        raise ValueError('evidence_changed_during_hash')
    return dict(stamp=before, sha256=digest.hexdigest().upper())


def _pinned(name, *, parse=False):
    path, expected = PINS[name]
    limit = MAX_TELEMETRY if name == 'telemetry' else MAX_JSON
    record = _record(path, limit)
    if record['sha256'] != expected:
        raise ValueError('pinned_evidence_changed:' + name)
    if parse:
        # Existing helper also enforces a 2 MiB JSON read bound.
        return record, service_recovery.read_pinned(path, expected)
    return record, None


def _files_only(directory, allowed):
    names = {entry.name for entry in directory.iterdir()}
    if names - allowed:
        raise ValueError('unexpected_historical_artifact')
    for entry in directory.iterdir():
        if entry.is_symlink() or entry.resolve(strict=True) != entry:
            raise ValueError('unexpected_historical_path')


def _validate_result(result):
    if (not isinstance(result, dict) or result.get('run') != str(RUN)
            or result.get('profile') != PROFILE
            or result.get('failure') != FAILURE
            or result.get('success') is not False
            or result.get('cleanup_confirmed') is not False):
        raise ValueError('unexpected_original_outcome')
    for key in ('current_baseline', 'runtime_baseline', 'identity',
                'resumed_monotonic', 'http', 'exit_code', 'module_inspection'):
        if key not in result or result[key] is not None:
            raise ValueError('historical_child_or_runtime_present:' + key)
    if (type(result.get('runtime_samples')) is not int or result['runtime_samples'] != 0
            or result.get('service_ready') is not False):
        raise ValueError('historical_runtime_present')
    for key in TERMINAL_FLAGS:
        if result.get(key) is not True:
            raise ValueError('unconfirmed_terminal_state:' + key)
    for key in ('collector_queries', 'collector_completed_queries',
                'collector_retained_queries'):
        if type(result.get(key)) is not int or result[key] != 69:
            raise ValueError('collector_query_count_changed:' + key)
    if (not isinstance(result.get('manifest'), dict)
            or result['manifest'].get('profile') != PROFILE
            or result['manifest'].get('source') != 'cff564964e8506c0abb3e530cecb55332187ac6c'):
        raise ValueError('historical_source_binding_changed')


def validate_history():
    """Recheck the one failed run and return pinned artifact records; no mutation."""
    for directory in (REPORTS, ROOT, RUN, MODULE.parent):
        _directory(directory)
    if RUN.parent != ROOT or ROOT.parent != REPORTS:
        raise ValueError('unexpected_historical_parent')
    _files_only(ROOT, {RUN.name, 'incomplete.json', 'verification-attempt.json', 'runner.lock'})
    _files_only(RUN, {'decisions.jsonl', 'phase.json', 'result.json',
                      'telemetry.jsonl', CERTIFICATE.name})
    records = {}
    values = {}
    for name in PINS:
        records[name], values[name] = _pinned(name, parse=name in ('result', 'latch', 'verification'))
    result, latch, marker = values['result'], values['latch'], values['verification']
    _validate_result(result)
    if (not isinstance(latch, dict) or latch.get('run') != str(RUN)
            or latch.get('phase') != 'cleanup_unconfirmed'
            or latch.get('original_baseline') != result.get('original_baseline')):
        raise ValueError('historical_latch_changed')
    if (not isinstance(marker, dict) or marker.get('evaluation') != PROFILE
            or marker.get('module_sha256') != '51E75C4F865957FC31AF422A16E3DE24E5B055AD7293E5A32C1B9A49684E3D55'):
        raise ValueError('verification_marker_changed')
    # The pinned failure comes from baseline construction before the owned
    # factory call. Exact artifact names and absence of argv/owned/request files
    # corroborate that historical no-child path; the audit is pinned above.
    return records


def _approval(path, records):
    path = Path(path)
    if path != APPROVAL:
        raise ValueError('unexpected_approval_path')
    approval_record = _record(path, MAX_JSON)
    approval = operator_store.read_json(path)
    if (not isinstance(approval, dict) or approval.get('approved') is not True
            or approval.get('capability') != CAPABILITY
            or approval.get('meaning') != MEANING
            or approval.get('historical_run') != str(RUN)
            or approval.get('evaluation') != PROFILE
            or approval.get('admission') != 'active_desktop_reserved_variation'
            or approval.get('intended_run_root') != str(FRESH_ROOT)
            or approval.get('result_sha256') != records['result']['sha256']
            or approval.get('failed_audit_sha256') != records['failed_audit']['sha256']
            or not isinstance(approval.get('helpers'), dict)
            or approval['helpers'].get(MODULE.name) != _record(MODULE, MAX_JSON)['sha256']
            or approval.get('disposition_review_path') != str(DISPOSITION_REVIEW)
            or approval.get('disposition_review_sha256') != DISPOSITION_REVIEW_SHA
            or approval.get('decision') != 'approved'
            or approval.get('disposition_decision') != 'approved_for_exact_historical_disposition'):
        raise ValueError('disposition_approval_binding_invalid')
    disposition_review_record = _record(DISPOSITION_REVIEW, MAX_JSON)
    if disposition_review_record['sha256'] != DISPOSITION_REVIEW_SHA:
        raise ValueError('disposition_review_changed')
    review_path = Path(approval.get('review_path', ''))
    if (review_path.parent != REPORTS or review_path.suffix.lower() != '.md'
            or review_path in (AUDIT, DISPOSITION_REVIEW)):
        raise ValueError('disposition_review_path_invalid')
    review_record = _record(review_path, MAX_JSON)
    if review_record['sha256'] != approval.get('review_sha256'):
        raise ValueError('disposition_review_changed')
    return approval_record, review_record, disposition_review_record


def _certificate_payload(records, approval_record, review_record, disposition_review_record):
    return dict(capability=CAPABILITY, meaning=MEANING,
        historical_run=str(RUN), profile_id=PROFILE,
        intended_root=str(FRESH_ROOT),
        original_success=False, original_cleanup_confirmed=False,
        original_recovery_deadline_not_certified=True,
        historical_model_process_created=False, historical_generation_posts=0,
        fresh_admission_required=True,
        historical_artifacts=records, approval=approval_record,
        review=review_record, disposition_review=disposition_review_record,
        disposition_module=_record(MODULE, MAX_JSON))


def create_certificate(approval_path):
    """Create the one exclusive certificate after independent review approval."""
    records = validate_history()
    if CERTIFICATE.exists() or CERTIFICATE.is_symlink():
        raise ValueError('disposition_already_consumed')
    approval_record, review_record, disposition_review_record = _approval(approval_path, records)
    payload = _certificate_payload(records, approval_record, review_record,
                                   disposition_review_record)
    encoded = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(encoded) > MAX_JSON:
        raise ValueError('certificate_size_bound')
    with CERTIFICATE.open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return certificate()


def certificate():
    """Revalidate exact history, certificate, approval, and review for new Store."""
    records = validate_history()
    certificate_record = _record(CERTIFICATE, MAX_JSON)
    saved = operator_store.read_json(CERTIFICATE)
    approval_record, review_record, disposition_review_record = _approval(APPROVAL, records)
    expected = _certificate_payload(records, approval_record, review_record,
                                    disposition_review_record)
    if saved != expected:
        raise ValueError('disposition_certificate_changed')
    return [*records.values(), approval_record, review_record,
            disposition_review_record, certificate_record,
            expected['disposition_module']]
