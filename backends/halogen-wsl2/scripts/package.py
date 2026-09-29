"""Portable, explicit setup for the one qualified experimental machine profile."""
import argparse
import configparser
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import uuid
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DXG_HASH = '0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6'
WHEEL_HASH = '3bf4a72d11aa2a4ee1e90572c73630f937d38c1b7af4dda45b483b54655138a7'
MODES = dict(Trace32k='PreflightTrace32k', Single32k='PreflightPinned32k',
             Single256k='PreflightPinned256k', Sessions32k='PreflightSessions32k', Serve32k='PreflightServe32k')
MODELS = [('qwen38-flash-next-w4b.hgn', 124068083904, '9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6'),
          ('qwen38-flash-next-w4b.overlay.hgn', 2572466560, '1cdfc3a9f988955bfe9a71bb808d393030abbf9f99d34ffa1ef93815a49b39ab')]

def linux_path(value, native=False):
    if (not isinstance(value, str) or not value.startswith('/') or value == '/' or
            any(c in value for c in ':,\\"\'\r\n\t\0') or any(ord(c) < 32 for c in value) or
            any(p in ('.', '..', '') for p in value.split('/')[1:])):
        raise ValueError('Use an absolute Linux path without ambiguous separators or control characters')
    if native and re.match(r'^/mnt/[a-z](?:/|$)', value):
        raise ValueError('Models must be on native WSL ext4, never a Windows drive mount')
    return value

def identity(value, label):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', value or ''):
        raise ValueError('Invalid ' + label)
    return value

def wsl_command(distro, user, arguments):
    result = ['wsl.exe', '-d', identity(distro, 'distribution')]
    if user: result += ['-u', identity(user, 'Linux user')]
    return result + ['--exec'] + list(arguments)

def run(arguments, timeout=30):
    try:
        return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=timeout,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    except FileNotFoundError as exc:
        raise ValueError('Missing prerequisite executable: ' + arguments[0] + '. Install it manually and add it to PATH.') from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError('Prerequisite/command failed; install or correct it manually: ' +
                         repr(arguments) + '\n' + (exc.stderr or '').strip()) from exc

def wsl(distro, user, *arguments, timeout=30):
    return run(wsl_command(distro, user, arguments), timeout)

def profile_mode(mode):
    if mode not in MODES: raise ValueError('Unqualified profile: ' + mode)
    return MODES[mode]

def serve_seconds(value):
    if not 30 <= value <= 300: raise ValueError('Serve32k duration must be 30..300 seconds')
    return value

def digest(path):
    with pathlib.Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def check_hash(path, expected):
    if digest(path) != expected: raise ValueError('Hash mismatch: ' + str(path))

def environment(entries):
    result = {}
    for entry in entries:
        key, value = entry.split('=', 1)
        if key in result: raise ValueError('Duplicate environment key: ' + key)
        if key == 'HALOGEN_LOOKUP_RANDOM': raise ValueError('Lookup-random is not qualified')
        result[key] = value
    return result

def validate_wsl_config(text):
    config = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        config.read_string(text)
        if config.get('wsl2', 'memory').strip().upper() != '56GB':
            raise ValueError('WSL [wsl2] memory=56GB is required')
    except configparser.Error as exc:
        raise ValueError('Invalid or ambiguous WSL configuration') from exc

def check_sources(root):
    check_hash(root / 'profiles/build.json', '4ba62f3db0359b6bf4a3f3a0727ab4bb3992cd64f7326469b0794b0a213d9edd')
    check_hash(root / 'profiles/environment.json', 'a929f73ac1aa2649fe0735229e8d6d8b43a2f59c768e2d0ff3a393bb7437e087')
    manifest = json.loads((root / 'profiles/build.json').read_text(encoding='utf-8-sig'))
    for item in manifest['sources']: check_hash(root / item['path'], item['sha256'])
    private = manifest['adapters'][1]
    check_hash(root / private['source'], private['sourceSha256'])
    return manifest

def preflight(root, distro, user, models, dxg, wheel, verify_model_hash=False):
    if sys.version_info < (3, 12): raise ValueError('Install Python 3.12+ and add it to PATH')
    identity(distro, 'distribution')
    user = identity(user or wsl(distro, None, 'id', '-un'), 'Linux user')
    models = linux_path(models, native=True)
    if bool(dxg) == bool(wheel): raise ValueError('Specify exactly one DXG library path or AMD wheel path')
    manifest = check_sources(root)
    workspace = linux_path(wsl(distro, user, 'wslpath', '-a', '-u', str(root.resolve())))
    if wsl(distro, user, 'stat', '-f', '-c', '%T', models) != 'ext2/ext3':
        raise ValueError('Model directory must use the qualified native ext4 filesystem')
    if not wsl(distro, user, 'gcc', '-dumpfullversion').startswith('13.3.'):
        raise ValueError('Qualified compiler is GCC 13.3 on Ubuntu 24.04; install prerequisites manually')
    release = wsl(distro, user, 'cat', '/etc/os-release')
    if 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:
        raise ValueError('Only Ubuntu 24.04 is qualified')
    wsl(distro, user, 'docker', 'version', '--format', '{{.Server.Version}}')
    wsl(distro, user, 'docker', 'image', 'inspect', json.loads((root / 'profiles/environment.json').read_text())['image'])
    for name, size, sha in MODELS:
        path = models + '/' + name
        if wsl(distro, user, 'stat', '-f', '-c', '%T', path) != 'ext2/ext3':
            raise ValueError('Model files must use the qualified native ext4 filesystem')
        if wsl(distro, user, 'stat', '-c', '%s', path) != str(size): raise ValueError('Model size mismatch: ' + name)
        if verify_model_hash and wsl(distro, user, 'timeout', '--signal=TERM', '--kill-after=5s', '1800s',
                                     'sha256sum', path, timeout=1810).split()[0] != sha:
            raise ValueError('Model SHA256 mismatch: ' + name)
    for name in ('tokenizer.json', 'tokenizer_config.json'):
        wsl(distro, user, 'test', '-s', models + '/tokenizer/' + name)
    wsl(distro, user, 'test', '-r', '/usr/lib/wsl/lib/libdxcore.so')
    wsl(distro, user, 'test', '-c', '/dev/dxg')
    if dxg:
        linux_path(dxg)
        if wsl(distro, user, 'sha256sum', dxg).split()[0] != DXG_HASH: raise ValueError('DXG SHA256 mismatch')
    else:
        check_hash(wheel, WHEEL_HASH)
        with zipfile.ZipFile(wheel) as archive:
            item = archive.getinfo('_rocm_sdk_core/lib/librocdxg.so.1')
            if item.file_size != 6606449: raise ValueError('Unexpected DXG member size')
            with archive.open(item) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != DXG_HASH: raise ValueError('Wheel DXG hash mismatch')
        dxg = workspace + '/.local/dependencies/librocdxg.so.1'
    return dict(schema='strix-alloy-machine-v1', distro=distro, user=user, models=models,
                dxg=dxg, workspace=workspace, profile='flash0138-copy48-v1')

def create_json(path, value):
    with path.open('x', encoding='utf-8') as stream: json.dump(value, stream, indent=2)

def build_adapters(root, config):
    manifest = check_sources(root)
    created = []
    (root / 'bin').mkdir(exist_ok=True)
    try:
        for index, adapter in enumerate(manifest['adapters']):
            destination = root / adapter['binary']
            if destination.exists(): raise ValueError('Existing adapter; uninstall the owned installation first')
            temporary = destination.with_name(destination.name + '.build-' + uuid.uuid4().hex)
            relative = temporary.relative_to(root).as_posix()
            if index == 0:
                flags = manifest['compilerArguments'][:-1] + [relative]
            else:
                flags = ['-DHALOGEN_RESEARCH_VGM64=1', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                         adapter['source'], '-o', relative, '-ldl', '-pthread']
            try:
                wsl(config['distro'], config['user'], 'timeout', '--signal=TERM', '--kill-after=5s', '120s',
                    'env', '-C', config['workspace'], 'gcc', *flags, timeout=130)
                check_hash(temporary, adapter['binarySha256'])
                # Atomic create-new publication; an existing destination is never replaced.
                os.link(temporary, destination)
                created.append(destination)
            finally:
                if temporary.exists(): temporary.unlink()
    except BaseException:
        for path in created: path.unlink()
        raise
    return created

def install(root, distro, user, models, dxg, wheel, explicit=False, verify_model_hash=False):
    local = root / '.local'
    for directory in (local, root / 'bin', local / 'dependencies'):
        if directory.is_symlink() or directory.is_junction():
            raise ValueError('Refusing linked installation directories: ' + str(directory))
    if (local / 'machine.json').exists() or (local / 'install-manifest.json').exists():
        raise ValueError('Existing installation; run Uninstall.ps1 before reinstalling. No automatic migration.')
    if (root / 'bin').exists() and any((root / 'bin').iterdir()):
        raise ValueError('Unknown existing bin files; refusing to overwrite')
    config = preflight(root, distro, user, models, dxg, wheel, verify_model_hash and explicit)
    if not explicit:
        print('Preflight passed. Dry run: no build, download, config or container changes.')
        return config
    local.mkdir(exist_ok=True)
    owned = []
    manifest = local / 'install-manifest.json'
    # Reserve the manifest name before creating any generated artifact.
    create_json(manifest, {'schema': 'strix-alloy-install-v1', 'files': []})
    try:
        if wheel:
            dependencies = local / 'dependencies'; dependencies.mkdir(exist_ok=True)
            destination = dependencies / 'librocdxg.so.1'
            with destination.open('xb') as output:
                owned.append(destination)
                with zipfile.ZipFile(wheel) as archive:
                    output.write(archive.read('_rocm_sdk_core/lib/librocdxg.so.1'))
            check_hash(destination, DXG_HASH)
        owned.extend(build_adapters(root, config))
        machine = local / 'machine.json'
        with machine.open('x', encoding='utf-8') as stream:
            owned.append(machine)
            json.dump(config, stream, indent=2)
    finally:
        # This manifest was exclusively created by this operation; never claims user files.
        manifest.write_text(json.dumps({'schema': 'strix-alloy-install-v1', 'files': [
            {'path': p.relative_to(root).as_posix(), 'sha256': digest(p)} for p in owned]}, indent=2), encoding='utf-8')
    print('Installed pinned adapters and local configuration. No container was started.')
    return config

def uninstall(root):
    local = root / '.local'
    manifest = local / 'install-manifest.json'
    for path in (local, manifest):
        if (path.is_symlink() or path.is_junction() or
                not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('Unsafe uninstall path: ' + str(path))
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('schema') != 'strix-alloy-install-v1': raise ValueError('Unknown installation manifest')
    allowed = {'.local/machine.json', '.local/dependencies/librocdxg.so.1'}
    build_path = root / 'profiles/build.json'
    if build_path.exists():
        check_hash(build_path, '4ba62f3db0359b6bf4a3f3a0727ab4bb3992cd64f7326469b0794b0a213d9edd')
        allowed.update(a['binary'] for a in json.loads(build_path.read_text(encoding='utf-8-sig'))['adapters'])
    targets = []
    for entry in data['files']:
        name = entry['path']
        path = root / name
        ancestry=[path]+list(path.parents)[:len(path.relative_to(root).parts)-1]
        if (name not in allowed or any(p.is_symlink() or p.is_junction() for p in ancestry) or
                not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('Unsafe uninstall target: ' + name)
        if path.exists(): check_hash(path, entry['sha256']); targets.append(path)
    for path in targets: path.unlink()
    manifest.unlink()
    print('Removed manifest-owned generated files only. Run logs and all user data were retained.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall', 'validate'])
    parser.add_argument('--distro', default='Ubuntu-24.04'); parser.add_argument('--user')
    parser.add_argument('--models'); parser.add_argument('--dxg'); parser.add_argument('--wheel')
    parser.add_argument('--install', action='store_true'); parser.add_argument('--verify-model-hash', action='store_true')
    args = parser.parse_args()
    if args.action == 'uninstall': uninstall(ROOT)
    elif args.action == 'validate':
        config = json.loads((ROOT / '.local/machine.json').read_text())
        validate_wsl_config((pathlib.Path.home() / '.wslconfig').read_text(encoding='utf-8-sig'))
        actual = preflight(ROOT, config['distro'], config['user'], config['models'], config['dxg'], None)
        if actual != config: raise ValueError('Machine configuration drift')
    else: install(ROOT, args.distro, args.user, args.models, args.dxg, args.wheel, args.install, args.verify_model_hash)

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr); raise SystemExit(2)
