"""Read-only native gateway profile selection; never start, stop or probe services."""
import argparse
import contextlib
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate profile key')
        value[key] = item
    return value


def profile_modules(server):
    server = Path(server).resolve(strict=True)
    sys.path.insert(0, str(server))
    gateway = importlib.import_module('gateway')
    controller = importlib.import_module('controller')
    for name, module in [('gateway', gateway), ('controller', controller)]:
        if Path(module.__file__).resolve() != server / (name + '.py'):
            raise ValueError('Configuration validator module identity differs')
    return controller, gateway


def local_file(value, base=None):
    path = Path(value)
    if not path.is_absolute():
        if base is None:
            raise ValueError('Explicit local path required')
        path = base / path
    path = path.resolve(strict=True)
    if (not re.fullmatch(r'[A-Za-z]:', path.drive) or ':' in str(path)[2:]
            or not path.is_file()):
        raise ValueError('Existing local drive file required')
    return path


def load_native_profile(profile, expected_sha256, server):
    if type(expected_sha256) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('Explicit reviewed profile SHA-256 required')
    profile = local_file(profile)
    with profile.open('rb') as source:
        raw = source.read(65537)
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Profile byte identity differs')
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_object,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
    if (type(value) is not dict or type(value.get('schema')) is not int or value['schema'] != 1
            or type(value.get('minimum_reserve_gib')) not in (int, float)
            or not math.isfinite(value['minimum_reserve_gib']) or value['minimum_reserve_gib'] < 18
            or type(value.get('concurrency')) is not int or value['concurrency'] != 1):
        raise ValueError('Native profile must retain one request and at least 18 GiB reserve')
    engine = value.get('engine')
    if (type(engine) is not dict or engine.get('kind') != 'native' or engine.get('qualified') is not True
            or type(engine.get('runtime_hashes')) is not dict or not engine['runtime_hashes']):
        raise ValueError('Qualified native profile with runtime pins required')
    command = engine.get('command')
    if type(command) is not list or not command or any(type(part) is not str for part in command):
        raise ValueError('Native argument vector required')
    local_file(command[0])
    # No literal API key is accepted in a command or in launcher output.
    if any(part == '--api-key' or part.startswith('--api-key=') or part == '-ak' for part in command):
        raise ValueError('Native credentials must remain in a key file')
    public_key = local_file(value['token_file'], profile.parent)
    backend_key = local_file(value['backend_token_file'], profile.parent)
    if any(path.stat().st_size > 8192 for path in (public_key, backend_key)):
        raise ValueError('Credential file is oversized')
    backend_bytes = backend_key.read_bytes()
    if not re.fullmatch(rb'[A-Za-z0-9._~+/=-]{32,8192}(?:\r?\n)?', backend_bytes):
        raise ValueError('Backend credential must be exactly one non-comment ASCII key')
    controller, gateway = profile_modules(server)
    controller.memory_reserve_gib(value)
    controller.validate_engine(engine, Path(server).resolve().parent)
    selected = gateway.load_config(profile)
    port = urlsplit(selected.backend.upstream).port
    if port == 8841:
        raise ValueError('Gateway cannot point at its own listener')
    # Native llama.cpp serving profiles must describe the same listener, alias,
    # capacity and backend credential which the unchanged gateway will use.
    protected_flags = {'--host', '--port', '--alias', '--ctx-size', '--parallel', '--api-key-file', '--api-key'}
    short_overrides = {'-H', '-p', '-a', '-c', '-np', '-ak'}
    for part in command[1:]:
        normalized = part.partition('=')[0].replace('_', '-')
        if part in short_overrides or (normalized in protected_flags and part != normalized):
            raise ValueError('Alternative native serving controls are not accepted')
    for flag, expected in [('--host', '127.0.0.1'), ('--port', str(port)), ('--alias', selected.backend.model),
                           ('--ctx-size', str(selected.backend.context)), ('--parallel', '1')]:
        if command.count(flag) != 1 or command.index(flag) + 1 >= len(command) or command[command.index(flag) + 1] != expected:
            raise ValueError('Native serving arguments differ from gateway profile')
    flag = '--api-key-file'
    if (command.count(flag) != 1 or command.index(flag) + 1 >= len(command)
            or local_file(command[command.index(flag) + 1]) != backend_key):
        raise ValueError('Native backend credential reference differs')
    if profile.read_bytes() != raw:
        raise ValueError('Profile changed while validating')
    return {'profile': str(profile), 'profile_sha256': expected_sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--server', required=True)
    args = parser.parse_args()
    try:
        # Imported validator diagnostics and arbitrary malformed values must
        # never reach the console, logs or the deployment binding response.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = load_native_profile(args.profile, args.sha256, args.server)
    except Exception:
        print('REFUSED: native gateway profile could not be verified', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__': raise SystemExit(main())
