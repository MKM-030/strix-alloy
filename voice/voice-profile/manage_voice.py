"""Manage consented German self-voice references for the existing native TTS.

No models are loaded, downloaded, stopped or restarted. Stage is CPU-only;
activate registers a reference through the owned loopback TTS worker.
"""
from __future__ import annotations

import argparse
import array
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
import wave

HERE = Path(__file__).resolve().parent
PROFILE_ROOT = HERE / 'runtime' / 'profiles'
DEFAULT_PROFILE = HERE.parent / 'assets' / 'scc-demo'
REGISTRATION_RECEIPT = HERE.parent / 'native-start' / 'runtime' / 'registered-voice.json'
VOICE_ALIAS = 'scc-demo'
CONSENT_SCOPE = 'local_synthetic_voice_and_servicenow_demo'
MAX_WAV_BYTES = 6 * 1024 * 1024


class RegistrationRejected(RuntimeError):
    """The server explicitly rejected a reference before replacing the alias."""


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024:
        raise ValueError('Voice metadata exceeds 64 KiB')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_consent(request):
    consent = request.get('consent', {})
    if (not isinstance(consent, dict) or consent.get('own_voice') is not True
            or consent.get('scope') != CONSENT_SCOPE):
        raise ValueError('Explicit own-voice consent for the local demo is required')
    try:
        stamp = datetime.fromisoformat(consent['confirmed_at_utc'].replace('Z', '+00:00'))
        if stamp.utcoffset() is None:
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('Voice consent requires a timezone-aware confirmation timestamp') from None
    if request.get('language') != 'German':
        raise ValueError('The native demo voice requires German')
    text = request.get('reference_text')
    if not isinstance(text, str) or not 5 <= len(text.strip()) <= 1500:
        raise ValueError('A complete reference transcript is required (5–1500 characters)')
    if not isinstance(request.get('name'), str) or not request['name'].strip():
        raise ValueError('A voice name is required')
    if len(request['name']) > 80:
        raise ValueError('Voice name exceeds 80 characters')
    if request.get('source') not in ('desktop_microphone', 'authorized_existing_own_recording'):
        raise ValueError('Unsupported own-voice reference source')


def inspect_audio(path):
    path = Path(path)
    if not path.is_file() or not 44 < path.stat().st_size <= MAX_WAV_BYTES:
        raise ValueError('Reference WAV is missing or exceeds 6 MiB')
    try:
        with wave.open(str(path), 'rb') as handle:
            rate, channels, width = handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
            duration = handle.getnframes() / rate
            if width != 2 or channels not in (1, 2) or not 8000 <= rate <= 48000:
                raise ValueError('Use mono/stereo PCM16 WAV at 8–48 kHz')
            if not 3 <= duration <= 30:
                raise ValueError('Reference speech must last 3–30 seconds')
            frame_count = handle.getnframes()
            raw = handle.readframes(frame_count)
            if len(raw) != frame_count * channels * width:
                raise ValueError('Reference WAV is truncated; declared frames do not match PCM bytes')
            samples = array.array('h', raw)
    except (wave.Error, EOFError):
        raise ValueError('Cannot read PCM WAV reference') from None
    if sys.byteorder != 'little':
        samples.byteswap()
    mono = [sum(samples[i:i + channels]) / channels for i in range(0, len(samples), channels)]
    peak = max(abs(value) for value in mono) / 32768
    rms = math.sqrt(sum(value * value for value in mono) / len(mono)) / 32768
    clipping = sum(abs(value) >= 32700 for value in samples) / len(samples)
    window = max(1, rate // 50)
    blocks = [math.sqrt(sum(v*v for v in mono[i:i+window]) / len(mono[i:i+window])) / 32768
              for i in range(0, len(mono), window)]
    speech_fraction = sum(value >= 0.003 for value in blocks) / len(blocks)
    if rms < 0.004 or peak < 0.02 or speech_fraction < 0.15:
        raise ValueError('Reference is silent or too quiet; record clear close-microphone speech')
    if clipping > 0.005:
        raise ValueError('Reference is clipped; lower microphone level and record again')
    return mono, rate, {'duration_seconds': round(duration, 4), 'source_sample_rate': rate,
        'source_channels': channels, 'source_peak': round(peak, 6),
        'source_rms_db': round(20 * math.log10(rms), 3),
        'clipped_fraction': round(clipping, 6), 'speech_fraction': round(speech_fraction, 4)}


def write_normalized(path, mono, rate):
    peak = max(abs(value) for value in mono)
    gain = min(4.0, 0.8 * 32767 / peak)
    if rate == 24000 and gain <= 1:
        gain = 1.0
    samples = array.array('h')
    for index in range(round(len(mono) * 24000 / rate)):
        position = index * rate / 24000
        left = min(int(position), len(mono)-1)
        right = min(left + 1, len(mono)-1)
        value = mono[left] + (mono[right] - mono[left]) * (position - left)
        samples.append(max(-32768, min(32767, round(value * gain))))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(24000)
        handle.writeframes(samples.tobytes())
    return round(gain, 5)


def stage(request, profile_root=PROFILE_ROOT):
    validate_consent(request)
    source = Path(request['wav_path']).resolve()
    mono, rate, audio = inspect_audio(source)
    profile_root = Path(profile_root).resolve()
    revisions = profile_root / 'revisions'
    revisions.mkdir(parents=True, exist_ok=True)
    profile_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
    target = revisions / profile_id
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=revisions) as temporary:
        staging = Path(temporary)
        shutil.copyfile(source, staging / 'source.wav')
        # Keep already suitable source bytes verbatim, otherwise normalize the
        # real recording to the native codec format without generating speech.
        if rate == 24000 and audio['source_channels'] == 1:
            shutil.copyfile(source, staging / 'reference.wav'); gain = 1.0
        else:
            gain = write_normalized(staging / 'reference.wav', mono, rate)
        profile = {'schema_version': 1, 'profile_id': profile_id, 'name': request['name'].strip(),
            'kind': 'authorized_own_voice', 'language': 'German',
            'reference_text': request['reference_text'].strip(),
            'reference_sha256': hashlib.sha256((staging / 'reference.wav').read_bytes()).hexdigest(),
            'source_sha256': hashlib.sha256((staging / 'source.wav').read_bytes()).hexdigest(),
            'source': request['source'], 'source_path': str(source),
            'consent': request['consent'], 'created_at_utc': utc_now(),
            'reference_sample_rate': 24000, 'normalization_gain': gain, 'audio': audio}
        atomic_json(staging / 'voice.json', profile)
        staging.rename(target)
    return dict(profile, profile_dir=str(target))


def read_profile(folder):
    folder = Path(folder).resolve()
    profile = read_json(folder / 'voice.json')
    if profile.get('schema_version') != 1 or profile.get('language') != 'German':
        raise ValueError('Unsupported German voice profile')
    if profile.get('kind') == 'authorized_own_voice':
        validate_consent(profile)
    elif profile.get('kind') != 'designed_synthetic_voice':
        raise ValueError('Unsupported voice provenance')
    reference = folder / 'reference.wav'
    if reference.stat().st_size > MAX_WAV_BYTES:
        raise ValueError('Reference WAV exceeds 6 MiB')
    if hashlib.sha256(reference.read_bytes()).hexdigest() != profile.get('reference_sha256'):
        raise ValueError('Reference audio hash changed; registration refused')
    return dict(profile, profile_id=profile.get('profile_id', 'synthetic-scc-demo'), profile_dir=str(folder))


def selected_profile(profile_root=PROFILE_ROOT):
    profile_root = Path(profile_root).resolve()
    pointer = profile_root / 'active.json'
    if not pointer.exists():
        return read_profile(DEFAULT_PROFILE) if DEFAULT_PROFILE.is_dir() else None
    selection = read_json(pointer)
    profile_id = selection.get('profile_id', '')
    if not isinstance(profile_id, str) or Path(profile_id).name != profile_id or profile_id in ('', '.', '..'):
        raise ValueError('Invalid active voice revision')
    if profile_id == 'synthetic-scc-demo':
        profile = read_profile(DEFAULT_PROFILE)
    else:
        profile = read_profile(profile_root / 'revisions' / profile_id)
    if profile['reference_sha256'] != selection.get('reference_sha256'):
        raise ValueError('Active voice reference hash differs')
    return profile


def native_module():
    path = HERE.parent / 'native-speech-validation' / 'speech_probe.py'
    spec = importlib.util.spec_from_file_location('scc_owned_speech', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def native_register(profile):
    import base64
    try:
        native = native_module()
        native.assert_owned_listener(8862)
        import psutil
        if psutil.virtual_memory().available < 18 * 1024**3:
            raise RuntimeError('Free memory is below the existing 18 GiB reserve')
        payload = {'name': VOICE_ALIAS, 'ref_text': profile['reference_text'],
            'wav_b64': base64.b64encode((Path(profile['profile_dir']) / 'reference.wav').read_bytes()).decode('ascii')}
        # A POST can commit even if its response is lost. Never let startup
        # reuse a receipt that could describe the previous registry entry.
        REGISTRATION_RECEIPT.unlink(missing_ok=True)
    except Exception as error:
        raise RegistrationRejected('TTS preflight rejected; previous voice unchanged: ' + str(error)) from None
    try:
        raw, timing = native.request(8862, '/v1/audio/voices', 'POST',
                                   json.dumps(payload).encode('utf-8'), timeout=45)
    except (native.ProbePreflightError, native.ProbeListenerNotReady) as error:
        raise RegistrationRejected('TTS ownership preflight rejected before HTTP: ' + str(error)) from None
    except native.ProbeHTTPError as error:
        raise RegistrationRejected('Native TTS rejected the reference (HTTP ' + str(error.status) + ')') from None
    response = json.loads(raw)
    if response.get('status') != 'registered':
        raise RuntimeError('Native TTS registration returned an unexpected response')
    return timing


@contextmanager
def activation_lock(profile_root):
    path = Path(profile_root) / 'activation.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('Another voice activation is in progress') from None
        try:
            yield
        finally:
            if sys.platform == 'win32':
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def activate(profile_dir, profile_root=PROFILE_ROOT, register=None):
    profile_root = Path(profile_root).resolve()
    profile = read_profile(profile_dir)
    if Path(profile['profile_dir']).parent != profile_root / 'revisions':
        raise ValueError('Activate a staged revision under the configured voice profiles')
    return select_profile(profile, profile_root, register or native_register)


def restore_synthetic(profile_root=PROFILE_ROOT, register=None):
    return select_profile(read_profile(DEFAULT_PROFILE), Path(profile_root).resolve(), register or native_register)


def select_profile(profile, profile_root, register):
    with activation_lock(profile_root):
        previous = selected_profile(profile_root)
        try:
            timing = register(profile)
        except RegistrationRejected:
            raise
        except Exception as error:
            restore_previous(previous, register, error)
        selection = {'schema_version': 1, 'profile_id': profile['profile_id'],
            'reference_sha256': profile['reference_sha256'], 'active_voice': VOICE_ALIAS,
            'previous_profile_id': previous['profile_id'] if previous else None,
            'activated_at_utc': utc_now()}
        try:
            atomic_json(profile_root / 'active.json', selection)
        except Exception as error:
            restore_previous(previous, register, error)
        return dict(selection, ok=True, profile_dir=profile['profile_dir'], registration=timing)


def restore_previous(previous, register, original_error):
    if previous is None:
        raise RuntimeError('Activation state is uncertain; no prior reference is available to restore') from original_error
    try:
        register(previous)
    except Exception as rollback_error:
        raise RuntimeError('Activation state is uncertain; previous voice restoration failed') from rollback_error
    raise RuntimeError('Activation failed; previous voice restored and selection unchanged') from original_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'activate', 'status', 'restore-synthetic'))
    parser.add_argument('--request', help='UTF-8 JSON own-voice request')
    parser.add_argument('--profile-dir', help='An existing immutable staged revision')
    parser.add_argument('--profile-root', default=str(PROFILE_ROOT))
    parser.add_argument('--json', action='store_true', help='Return one machine-readable JSON object')
    args = parser.parse_args()
    try:
        if args.action == 'status':
            profile = selected_profile(args.profile_root)
            result = {'ok': True, 'active_voice': VOICE_ALIAS, 'profile': profile}
        elif args.action == 'restore-synthetic':
            result = restore_synthetic(args.profile_root)
        else:
            if args.request:
                profile = stage(read_json(args.request), args.profile_root)
            elif args.profile_dir and args.action == 'activate':
                profile = read_profile(args.profile_dir)
            else:
                raise ValueError('--request is required, or --profile-dir for a staged activation')
            result = (activate(profile['profile_dir'], args.profile_root) if args.action == 'activate'
                      else dict(profile, ok=True, active=False))
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error), 'error_type': type(error).__name__}, ensure_ascii=True), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
