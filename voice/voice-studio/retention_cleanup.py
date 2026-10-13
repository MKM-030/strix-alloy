"""Remove SCC demo recording copies only after the fair; never stop any process.

The CLI clock and paths are fixed. Tests inject a clock and fake services into
cleanup(), which is not an HTTP endpoint. External source recordings, packaged
voice/model assets, access codes and ServiceNow records are outside this scope.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DUE_UTC = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)
PROFILE_REL = 'voice/voice-profile/runtime/profiles'
STUDIO_REL = 'voice/voice-studio/runtime'
PROFILE_ID = re.compile(r'^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$')
QUARANTINE_ID = re.compile(r'^([0-9]{8}T[0-9]{6}Z-[a-f0-9]{12})-([a-f0-9]{32})$')
TEMP_NAME = re.compile(r'^(upload-|\.staging-)[A-Za-z0-9_-]{6,64}$')
PROFILE_FILES = {'voice.json', 'owner.json', 'source.wav', 'reference.wav'}
PREVIEW_FILES = ('controlled-own-preview-20261013T191841Z.wav',)
MAX_ENTRIES = 512
MAX_FILE_BYTES = 6 * 1024 * 1024


class Deferred(RuntimeError):
    """A prerequisite failed. Do not force a deletion or change service ownership."""


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def due(now=None):
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise Deferred('clock_not_timezone_aware')
    return now >= DUE_UTC


def check_policy():
    value = json.loads((HERE / 'retention-policy.json').read_text(encoding='utf-8-sig'))
    expected = {'schema_version':1, 'event':'Smart Country Convention 2026',
        'due_at_utc':'2026-10-16T06:00:00Z', 'due_at_local':'2026-10-16T08:00:00+02:00',
        'timezone':'Europe/Berlin', 'profile_root_relative':PROFILE_REL,
        'studio_runtime_relative':STUDIO_REL, 'scope':'authorized_own_voice_demo_recordings',
        'keep_access_codes':True, 'keep_packaged_synthetic_voice':True,
        'keep_external_source_recordings':True}
    if value != expected:
        raise Deferred('retention_policy_changed')


def safe_path(path, root, *, directory=False):
    path, root = Path(path).absolute(), Path(root).absolute()
    try:
        path.relative_to(root)
    except ValueError:
        raise Deferred('path_outside_owned_root') from None
    for part in [root, *reversed(path.relative_to(root).parents), path.relative_to(root)]:
        current = part if part.is_absolute() else root / part
        if not current.exists() and not current.is_symlink():
            continue
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400):
            raise Deferred('reparse_path')
    if path.exists():
        info = path.lstat()
        if directory and not stat.S_ISDIR(info.st_mode):
            raise Deferred('expected_directory')
        if not directory and (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES):
            raise Deferred('unexpected_file')
    return path


def children(folder, root):
    safe_path(folder, root, directory=True)
    result = list(folder.iterdir()) if folder.exists() else []
    if len(result) > MAX_ENTRIES:
        raise Deferred('too_many_entries')
    return sorted(result)


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise Deferred('recording_timestamp_invalid')
    return result


def validate_revision(folder, profile_id, manager, project):
    if not PROFILE_ID.fullmatch(profile_id):
        raise Deferred('unexpected_revision_identifier')
    files = children(folder, project)
    names = {item.name for item in files}
    if not {'voice.json', 'reference.wav', 'source.wav'} <= names or not names <= PROFILE_FILES:
        raise Deferred('unexpected_revision_contents')
    for item in files:
        safe_path(item, project)
    profile = manager.read_profile(folder)  # validates consent, language and reference hash
    consent = profile.get('consent', {})
    if (profile.get('profile_id') != profile_id or profile.get('kind') != 'authorized_own_voice'
            or profile.get('language') != 'German'
            or profile.get('source') not in ('desktop_microphone', 'authorized_existing_own_recording')
            or consent.get('own_voice') is not True
            or consent.get('scope') != 'local_synthetic_voice_and_servicenow_demo'):
        raise Deferred('recording_provenance_changed')
    created = stamp(profile.get('created_at_utc', ''))
    encoded = datetime.strptime(profile_id.split('-')[0], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    if created > DUE_UTC or stamp(consent.get('confirmed_at_utc', '')) > DUE_UTC or abs((created-encoded).total_seconds()) > 2:
        raise Deferred('recording_outside_fair_scope')
    return files


def validate_upload(folder, project):
    """Only the existing Studio upload-/manager .staging- directory grammar."""
    files = []
    def visit(directory, depth=0):
        if depth > 4:
            raise Deferred('unexpected_upload_depth')
        for child in children(directory, project):
            if child.is_dir():
                safe_path(child, project, directory=True)
                allowed = ((depth == 0 and child.name == 'profiles')
                    or (depth == 1 and child.name == 'revisions')
                    or (depth == 2 and (PROFILE_ID.fullmatch(child.name) or TEMP_NAME.fullmatch(child.name))))
                if not allowed:
                    raise Deferred('unexpected_upload_directory')
                visit(child, depth + 1)
            else:
                allowed = {'recording.wav'} if depth == 0 else PROFILE_FILES
                if child.name not in allowed:
                    raise Deferred('unexpected_upload_file')
                files.append(safe_path(child, project))
    visit(folder)
    return files


def validate_quarantine(folder, profile_id, project):
    # A failed rmtree can leave only part of a formerly validated profile. The
    # matching private deletion journal authorizes finishing that exact folder;
    # it never authorizes following source_path or an arbitrary external path.
    encoded = datetime.strptime(profile_id.split('-')[0], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    if encoded > DUE_UTC: raise Deferred('quarantine_outside_fair_scope')
    files = children(folder, project)
    if not {item.name for item in files} <= PROFILE_FILES:
        raise Deferred('unexpected_quarantine_contents')
    for item in files: safe_path(item, project)
    metadata = folder / 'voice.json'
    if metadata.exists():
        value = json.loads(metadata.read_text(encoding='utf-8-sig'))
        if (value.get('profile_id') != profile_id or value.get('kind') != 'authorized_own_voice'
                or value.get('consent', {}).get('own_voice') is not True):
            raise Deferred('quarantine_provenance_changed')


def private_json(path, value):
    security = module('scc_retention_security', HERE / 'studio_server.py')
    security.atomic_private_json(path, value)


def private_directory(path):
    security = module('scc_retention_security', HERE / 'studio_server.py')
    security.restrict_private_path(path, directory=True)


def validate_preview_cleanup(path, project):
    """This one journal can name only Studio's ephemeral preview namespace."""
    safe_path(path, project)
    if path.name != 'preview-cleanup.json' or path.stat().st_size > 4096:
        raise Deferred('invalid_preview_cleanup_record')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        alias = record.get('alias', '')
        if (record.get('schema_version') != 1 or not isinstance(alias, str)
                or not re.fullmatch(r'scc-preview-[a-f0-9]{32}', alias)):
            raise ValueError()
    except (ValueError, AttributeError, UnicodeError):
        raise Deferred('invalid_preview_cleanup_identity') from None


def plan(project, manager):
    project = Path(project).absolute()
    profiles, runtime = project / PROFILE_REL, project / STUDIO_REL
    revisions = profiles / 'revisions'
    result = {'revisions':[], 'quarantine':[], 'uploads':[], 'staging':[], 'previews':[], 'journals':[],
              'preview_aliases':[]}
    preview_journal = runtime / 'preview-cleanup.json'
    if preview_journal.exists() or preview_journal.is_symlink():
        validate_preview_cleanup(preview_journal, project)
        result['preview_aliases'].append(preview_journal)
    for folder in children(revisions, project):
        if folder.name.startswith('.staging-') and TEMP_NAME.fullmatch(folder.name):
            files = children(folder, project)
            if not {item.name for item in files} <= PROFILE_FILES:
                raise Deferred('unexpected_staging_contents')
            for item in files: safe_path(item, project)
            result['staging'].append(folder)
        else:
            validate_revision(folder, folder.name, manager, project)
            result['revisions'].append(folder)
    journals = runtime / 'delete-journal'
    journal_records = {}
    for file in children(journals, project):
        safe_path(file, project)
        if not re.fullmatch(r'[a-f0-9]{32}\.json', file.name) or file.stat().st_size > 4096:
            raise Deferred('unexpected_delete_journal')
        record = json.loads(file.read_text(encoding='utf-8-sig'))
        match = QUARANTINE_ID.fullmatch(record.get('quarantine_name', ''))
        if (record.get('schema_version') != 1 or not match or match.group(2) != file.stem
                or record.get('profile_id') != match.group(1)
                or record.get('status') not in ('pending_purge', 'purge_failed', 'purged')
                or not re.fullmatch(r'(administrator|retention_cleanup|personal-[a-f0-9]{16})', record.get('requested_by', ''))):
            raise Deferred('invalid_delete_journal')
        stamp(record.get('created_at_utc', ''))
        journal_records[record['quarantine_name']] = file
        result['journals'].append(file)
    for folder in children(runtime / 'delete-quarantine', project):
        match = QUARANTINE_ID.fullmatch(folder.name)
        if not match or folder.name not in journal_records:
            raise Deferred('orphan_delete_quarantine')
        validate_quarantine(folder, match.group(1), project)
        result['quarantine'].append(folder)
    for folder in children(runtime, project):
        if folder.name.startswith('upload-'):
            if not TEMP_NAME.fullmatch(folder.name):
                raise Deferred('unexpected_upload_name')
            validate_upload(folder, project)
            result['uploads'].append(folder)
    for name in PREVIEW_FILES:
        path = runtime / name
        if path.exists() or path.is_symlink():
            result['previews'].append(safe_path(path, project))
    return result


def native_arguments(owner, project):
    # Reuse the live installed normal launcher's executable/configuration;
    # never infer a process from a stale copied venv path or its PID alone.
    if Path(owner.ROOT).absolute() != Path(project).absolute() or Path(owner.NATIVE).absolute() != Path(project).absolute() / 'voice/native-bridge':
        raise Deferred('native_launcher_root_changed')
    return [str(owner.PYTHON), '-u', str(owner.NATIVE / 'native_bridge.py'),
            '--config', str(owner.NATIVE / 'config.example.json')]


def native_sessions(status):
    sessions = status.get('nativeSessions')
    if type(sessions) is not int or sessions < 0 or status.get('authMode') != 'servicenow' or status.get('status') != 'ok':
        raise Deferred('native_health_invalid')
    return sessions


def check_services(project):
    """Inspect exact owned loopback workers. No connect to unknown listeners."""
    import psutil
    speech = module('scc_retention_speech', project / 'voice/native-speech-validation/speech_probe.py')
    owner = module('scc_retention_owner', project / 'voice/native-start/start_services.py')
    native_args = native_arguments(owner, project)
    native_pid = owner.owned_listener(8860, native_args)
    native_record = project / 'voice/native-start/runtime/native-owner.json'
    saved_native = json.loads(native_record.read_text(encoding='utf-8-sig')) if native_record.exists() else {}
    if native_pid:
        if not speech.same_process(saved_native) or saved_native.get('pid') != native_pid:
            raise Deferred('native_ownership_changed')
        with urllib.request.urlopen('http://127.0.0.1:8860/health', timeout=3) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise Deferred('native_health_oversized')
        status = json.loads(raw)
        sessions = native_sessions(status)
    else:
        if saved_native and speech.same_process(saved_native):
            raise Deferred('native_loading_or_not_listening')
        sessions = 0
    tts_sockets = speech.listening(8862)
    if tts_sockets:
        speech.assert_owned_listener(8862)
    elif speech.owners().get('tts') and speech.same_process(speech.owners()['tts']):
        raise Deferred('tts_loading_or_not_listening')
    # Catch a worker which is loading but has no receipt/listener yet.
    for process in psutil.process_iter(['name', 'cmdline']):
        name, args = process.info.get('name') or '', process.info.get('cmdline') or []
        if (not tts_sockets and name.lower() == 'tts-server.exe') or (
                not native_pid and str(project / 'voice/native-bridge/native_bridge.py') in args):
            raise Deferred('unregistered_loading_worker')
    return {'native_sessions':sessions, 'native_running':bool(native_pid), 'tts_running':bool(tts_sockets),
            'native_pid':native_pid, 'tts_pid':speech.owners().get('tts', {}).get('pid') if tts_sockets else None}


@contextmanager
def cleanup_lock(runtime, project):
    safe_path(runtime, project, directory=True)
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / 'retention.lock'
    safe_path(path, project)
    with path.open('a+b') as handle:
        if handle.tell() == 0: handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Deferred('retention_already_running') from None
        try: yield
        finally:
            if sys.platform == 'win32':
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(handle, fcntl.LOCK_UN)


def purge_tree(folder, project):
    """No recursive wildcard delete: unlink validated plain files, then directories."""
    for child in children(folder, project):
        if child.is_dir():
            safe_path(child, project, directory=True)
            purge_tree(child, project)
        else:
            safe_path(child, project).unlink()
    safe_path(folder, project, directory=True).rmdir()


def assert_idle(state):
    if (type(state.get('native_sessions')) is not int or state['native_sessions'] != 0
            or type(state.get('tts_running')) is not bool or type(state.get('native_running')) is not bool):
        raise Deferred('call_active_or_status_invalid')
    if not state['tts_running'] and state['native_running']:
        raise Deferred('tts_unavailable_while_native_running')


def cleanup(project=ROOT, *, manager=None, now=None, apply=False, service_check=None, report=True):
    project, now = Path(project).absolute(), now or datetime.now(timezone.utc)
    result = {'schema_version':1, 'due_at_utc':'2026-10-16T06:00:00Z',
        'attempted_at_utc':now.isoformat(), 'status':'not_due'}
    if not due(now): return result
    try:
        check_policy()
        manager = manager or module('scc_retention_manager', project / 'voice/voice-profile/manage_voice.py')
        if Path(manager.PROFILE_ROOT).absolute() != project / PROFILE_REL:
            raise Deferred('profile_root_changed')
        if Path(manager.DEFAULT_PROFILE).absolute() != project / 'voice/assets/scc-demo':
            raise Deferred('packaged_default_path_changed')
        if Path(manager.REGISTRATION_RECEIPT).absolute() != project / 'voice/native-start/runtime/registered-voice.json':
            raise Deferred('registration_receipt_path_changed')
        for directory in (manager.PROFILE_ROOT, manager.DEFAULT_PROFILE):
            safe_path(directory, project, directory=True)
        for file in (Path(manager.PROFILE_ROOT) / 'active.json',
                     Path(manager.PROFILE_ROOT) / 'activation.lock',
                     Path(manager.DEFAULT_PROFILE) / 'voice.json',
                     Path(manager.DEFAULT_PROFILE) / 'reference.wav',
                     manager.REGISTRATION_RECEIPT):
            safe_path(file, project)
        service_check = service_check or (lambda: check_services(project))
        with cleanup_lock(project / STUDIO_REL, project):
            pending = plan(project, manager)
            result.update(profiles=len(pending['revisions']), quarantine=len(pending['quarantine']),
                          upload_directories=len(pending['uploads']), staging_directories=len(pending['staging']),
                          preview_files=len(pending['previews']), preview_aliases=len(pending['preview_aliases']))
            state = service_check(); assert_idle(state)
            if not apply:
                return dict(result, status='dry_run')
            # The existing manager owns TTS registration and pointer rollback. An
            # offline metadata fallback is permitted only with no running workers.
            register = None if state['tts_running'] else lambda profile: {'offline':True}
            manager.restore_synthetic(manager.PROFILE_ROOT, register=register)
            with manager.activation_lock(manager.PROFILE_ROOT):
                state = service_check(); assert_idle(state)
                selected = manager.selected_profile(manager.PROFILE_ROOT)
                if not selected or selected.get('profile_id') != 'synthetic-scc-demo':
                    raise Deferred('default_voice_not_selected')
                pending = plan(project, manager)  # revalidate all before first physical removal
                for journal in pending['preview_aliases']:
                    state = service_check(); assert_idle(state)
                    validate_preview_cleanup(journal, project)
                    if state['tts_running']:
                        security = module('scc_retention_preview_cleanup', HERE / 'studio_server.py')
                        try:
                            # Both helpers retain exact live listener ownership
                            # checks; the shared activation mutex remains held.
                            security.recover_preview_alias(manager.native_module(), journal)
                        except security.APIError:
                            raise Deferred('preview_cleanup_failed') from None
                    else:
                        # assert_idle permits this only when both workers are
                        # positively offline, so their former registry is gone.
                        safe_path(journal, project).unlink()
                # Finish older requested deletions before admitting another
                # quarantined revision. Every new move has a private journal.
                for folder in pending['quarantine'] + pending['uploads'] + pending['staging']:
                    assert_idle(service_check())
                    purge_tree(folder, project)
                quarantine = project / STUDIO_REL / 'delete-quarantine'
                journals = project / STUDIO_REL / 'delete-journal'
                for directory in (quarantine, journals):
                    safe_path(directory, project, directory=True)
                    directory.mkdir(parents=True, exist_ok=True); private_directory(directory)
                for folder in pending['revisions']:
                    assert_idle(service_check())
                    token = uuid.uuid4().hex
                    target = quarantine / (folder.name + '-' + token)
                    journal = journals / (token + '.json')
                    record = {'schema_version':1, 'profile_id':folder.name,
                        'quarantine_name':target.name, 'requested_by':'retention_cleanup',
                        'created_at_utc':now.isoformat(), 'status':'pending_purge'}
                    private_json(journal, record)
                    try: folder.rename(target)
                    except Exception:
                        journal.unlink(missing_ok=True); raise
                    purge_tree(target, project)
                    safe_path(journal, project).unlink()
                for file in pending['previews'] + pending['journals']:
                    safe_path(file, project).unlink()
                # Invalidate only our selected-voice registration receipt; the
                # normal startup will register/reconcile the packaged reference.
                receipt = Path(manager.REGISTRATION_RECEIPT)
                if receipt.exists(): safe_path(receipt, project).unlink()
                remaining = plan(project, manager)
                if any(remaining.values()): raise Deferred('recordings_remain_retry_needed')
                result['status'] = 'purged'
    except Exception as error:
        result['status'] = 'deferred'
        result['reason'] = str(error) if isinstance(error, Deferred) else type(error).__name__
    if report:
        runtime = project / STUDIO_REL
        try:
            safe_path(runtime, project, directory=True); runtime.mkdir(parents=True, exist_ok=True)
            destination = runtime / 'retention-last-result.json'; safe_path(destination, project)
            temporary = runtime / ('retention-result-' + uuid.uuid4().hex + '.tmp')
            with temporary.open('x', encoding='utf-8') as handle:
                json.dump(result, handle, ensure_ascii=True); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            result['report_failed'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Purge only when fixed due date is reached')
    args = parser.parse_args()
    if sys.platform != 'win32':
        print(json.dumps({'status':'deferred', 'reason':'windows_demo_host_required'})); return 1
    result = cleanup(apply=args.apply)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 1 if result['status'] == 'deferred' else 0


if __name__ == '__main__': raise SystemExit(main())
