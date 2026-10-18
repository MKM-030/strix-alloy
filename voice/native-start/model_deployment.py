"""Read-only binding to the reviewed model profile; never reads credentials.

The manifest and profile are bounded, duplicate-free JSON with exact byte pins.
This helper does not start processes, sample services, or open token/lock files.
Exact prompt-cache health is checked separately by the existing caller guard.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import sys

MANIFEST = Path(__file__).with_name('model-deployment.json')
MANIFEST_SHA256 = '5e3134230a0decec060c185f0f5f1a1eb6909677ebc21e4b870c1536306aac87'
MAX_JSON_BYTES = 65536
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_FIELD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,7}\Z')
_MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
_DOS_DEVICE = re.compile(r'(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])\Z')


def _local_path(value, *, base=None):
    """Resolve an explicit local drive path, never a UNC/device/stream path."""
    if isinstance(value, Path):
        value = str(value)
    if (type(value) is not str or not 1 <= len(value) <= 4096
            or any(ord(c) < 32 for c in value)
            or any(c in value for c in '"<>|?*')
            or value.startswith(('\\\\', '//'))):
        raise ValueError('Deployment paths must be explicit local file paths')
    path = Path(value)
    if not path.is_absolute():
        if base is None or path.drive or value.startswith(('\\', '/')):
            raise ValueError('Deployment paths must be absolute local file paths')
        path = base / path
    if not re.fullmatch(r'[A-Za-z]:', path.drive) or ':' in str(path)[2:]:
        raise ValueError('Deployment paths must remain on a local drive')
    if any(_DOS_DEVICE.fullmatch(part.partition('.')[0].rstrip(' ').upper()) for part in path.parts[1:]):
        raise ValueError('Deployment paths cannot name a Windows device')
    try:
        path = path.resolve()
    except (OSError, RuntimeError, ValueError):
        raise ValueError('Deployment path cannot be resolved') from None
    if not re.fullmatch(r'[A-Za-z]:', path.drive) or ':' in str(path)[2:]:
        raise ValueError('Deployment paths must remain on a local drive')
    if any(_DOS_DEVICE.fullmatch(part.partition('.')[0].rstrip(' ').upper()) for part in path.parts[1:]):
        raise ValueError('Deployment paths cannot name a Windows device')
    return path


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate deployment JSON key')
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError('Non-finite deployment JSON value')


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Non-finite deployment JSON value')
    return number


def _pinned_json(path, expected_hash):
    if type(expected_hash) is not str or not _SHA256.fullmatch(expected_hash):
        raise ValueError('Deployment SHA-256 must be explicit lowercase hexadecimal')
    if not path.is_file():
        raise ValueError('Deployment JSON file is missing')
    with path.open('rb') as source:
        raw = source.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('Deployment JSON exceeds 64 KiB')
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('Deployment JSON SHA-256 mismatch')
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError('Deployment JSON is invalid or contains duplicate keys') from None
    if type(value) is not dict:
        raise ValueError('Deployment JSON must be an object')
    return value


def _exact(value, expected):
    return type(value) is type(expected) and value == expected


def _expected_health(backend):
    expected = backend.get('expected')
    required = {'status':'ok', 'version.match':True, 'context':32768,
        'slot_ctx':32768, 'kv_pool_positions':32768, 'slots':1, 'vision.enabled':True}
    if type(expected) is not dict or not 1 <= len(expected) <= 64:
        raise ValueError('Profile health expectations are missing or oversized')
    for key, value in expected.items():
        if (type(key) is not str or len(key) > 128 or not _FIELD.fullmatch(key)
                or type(value) not in (str, bool, int, float, type(None))
                or (type(value) is str and len(value) > 1024)
                or (type(value) is float and not math.isfinite(value))):
            raise ValueError('Profile health expectations must be bounded dotted scalar fields')
        if any(other.startswith(key + '.') for other in expected if other != key):
            raise ValueError('Profile health expectation paths conflict')
    if any(not _exact(expected.get(key), value) for key, value in required.items()):
        raise ValueError('Profile must retain 32k context, one slot, and enabled Vision')
    api, engine = expected.get('version.api'), expected.get('version.engine')
    if type(api) is not str or not 1 <= len(api) <= 64 or api != engine:
        raise ValueError('Profile requires exact matching API and engine versions')
    return expected.copy()


def load_deployment(manifest_path=MANIFEST, *, manifest_sha256=MANIFEST_SHA256):
    """Read only pinned manifest/profile bytes and return JSON-safe binding data."""
    manifest = _pinned_json(_local_path(manifest_path), manifest_sha256)
    if (set(manifest) != {'schema','controller_root','profile','profile_sha256'}
            or not _exact(manifest.get('schema'), 1)):
        raise ValueError('Unsupported deployment manifest schema or fields')
    controller_root = _local_path(manifest['controller_root'])
    if not controller_root.is_dir():
        raise ValueError('Deployment controller root must be a local directory')
    profile_path = _local_path(manifest['profile'])
    profile = _pinned_json(profile_path, manifest['profile_sha256'])
    if not _exact(profile.get('schema'), 1):
        raise ValueError('Unsupported model profile schema')
    if not _exact(profile.get('minimum_reserve_gib'), 18) or not _exact(profile.get('concurrency'), 1):
        raise ValueError('Profile must retain 18 GiB runtime reserve and one concurrent request')
    backend, engine = profile.get('backend'), profile.get('engine')
    if type(backend) is not dict or type(engine) is not dict:
        raise ValueError('Profile backend and engine are required')
    if (not _exact(backend.get('upstream'), 'http://127.0.0.1:8731')
            or not _exact(backend.get('context'), 32768)
            or not _exact(engine.get('context'), 32768)
            or not _exact(engine.get('prompt_cache'), 'Exact')
            or not _exact(engine.get('disable_vision'), False)):
        raise ValueError('Profile must retain loopback backend, 32k context, Exact cache, and Vision')
    model = backend.get('model')
    if type(model) is not str or not _MODEL.fullmatch(model):
        raise ValueError('Profile model identifier is invalid')
    expected = _expected_health(backend)
    if 'model' in expected and not _exact(expected['model'], model):
        raise ValueError('Profile model and health expectation conflict')
    directory = engine.get('directory')
    if type(directory) is not str or Path(directory).is_absolute() or Path(directory).drive:
        raise ValueError('Engine directory must be relative to the controller root')
    engine_root = _local_path(directory, base=controller_root)
    if engine_root == controller_root or not engine_root.is_relative_to(controller_root):
        raise ValueError('Engine directory must remain inside the controller root')
    token_file = _local_path(profile.get('backend_token_file'), base=profile_path.parent)
    runner_lock = _local_path(engine_root / '.local/runner.lock')
    return {'profile':str(profile_path), 'profile_sha256':manifest['profile_sha256'],
        'controller_root':str(controller_root), 'model_token_file':str(token_file),
        'runner_lock':str(runner_lock), 'expected':expected, 'model':model,
        'context':backend['context'], 'slots':expected['slots'], 'prompt_cache':engine['prompt_cache']}


def health_matches(value, binding):
    """Require each pinned dotted health leaf and model, with exact JSON types."""
    if type(value) is not dict or type(binding) is not dict:
        return False
    expected = binding.get('expected')
    if type(expected) is not dict or not expected or type(binding.get('model')) is not str:
        return False
    if not _exact(value.get('model'), binding['model']):
        return False
    for dotted, required in expected.items():
        if type(dotted) is not str or not _FIELD.fullmatch(dotted):
            return False
        observed = value
        for key in dotted.split('.'):
            if type(observed) is not dict or key not in observed:
                return False
            observed = observed[key]
        if not _exact(observed, required):
            return False
    return True


def main():
    if len(sys.argv) != 1:
        raise ValueError('Deployment helper accepts no command-line overrides')
    print(json.dumps(load_deployment(), allow_nan=False, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError):
        print('REFUSED: deployment binding could not be verified', file=sys.stderr)
        raise SystemExit(2)
