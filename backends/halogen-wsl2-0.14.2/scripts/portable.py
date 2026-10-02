"""Explicit, version-pinned WSL2 setup. No model download or system configuration edits."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import pathlib
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/".local"
RELEASE=json.loads((ROOT/"profiles/release.json").read_text())
IMAGE=RELEASE["image"]
DXG_HASH='0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6'
WHEEL_HASH='3bf4a72d11aa2a4ee1e90572c73630f937d38c1b7af4dda45b483b54655138a7'
MODELS=[('qwen38-flash-next-w4b.hgn', 124068083904, '9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6'), ('qwen38-flash-next-w4b.overlay.hgn', 2572466560, '1cdfc3a9f988955bfe9a71bb808d393030abbf9f99d34ffa1ef93815a49b39ab')]

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

def digest(path):
    with pathlib.Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def check_hash(path, expected):
    if digest(path) != expected: raise ValueError('Hash mismatch: ' + str(path))

def validate_wsl_config(text):
    config = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        config.read_string(text)
        if config.get('wsl2', 'memory').strip().upper() != '56GB':
            raise ValueError('WSL [wsl2] memory=56GB is required')
    except configparser.Error as exc:
        raise ValueError('Invalid or ambiguous WSL configuration') from exc


def verify_sources():
    manifest=json.loads((ROOT/'profiles/sources.json').read_text())
    for name,sha in manifest['files'].items():
        path=ROOT/name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Unsafe package source path')
        check_hash(path,sha)


def preflight(distro,user,models,dxg,wheel=None,verify_model_hash=False):
    if os.name!='nt' or sys.version_info<(3,12):
        raise ValueError('Windows Python 3.12+ is required')
    verify_sources()
    distro=identity(distro,'distribution')
    user=identity(user or wsl(distro,None,'id','-un'),'Linux user')
    models=linux_path(models,native=True)
    if bool(dxg)==bool(wheel): raise ValueError('Supply exactly one -DxgLibrary or -AmdWheel')
    validate_wsl_config((Path.home()/'.wslconfig').read_text(encoding='utf-8-sig'))
    workspace=linux_path(wsl(distro,user,'wslpath','-a','-u',str(ROOT)))
    pwsh=shutil.which('pwsh')
    if not pwsh: raise ValueError('Install PowerShell 7 and add pwsh to PATH')
    if int(run([pwsh,'-NoProfile','-Command','$PSVersionTable.PSVersion.Major']))<7:
        raise ValueError('PowerShell 7 required')
    if not wsl(distro,user,'gcc','-dumpfullversion').startswith('13.3.'):
        raise ValueError('The pinned adapters require GCC 13.3 on Ubuntu 24.04')
    release=wsl(distro,user,'cat','/etc/os-release')
    if 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:
        raise ValueError('Ubuntu 24.04 required')
    image=json.loads(wsl(distro,user,'docker','image','inspect',IMAGE))[0]
    env=image.get('Config',{}).get('Env',[])
    if env.count('HALOGEN_IMAGE_VERSION=0.14.2')!=1:
        raise ValueError('Wrong Halogen image version')
    wsl(distro,user,'test','-c','/dev/dxg')
    wsl(distro,user,'test','-r','/usr/lib/wsl/lib/libdxcore.so')
    if wsl(distro,user,'stat','-f','-c','%T',models)!='ext2/ext3':
        raise ValueError('Models must reside on native WSL Ext4')
    for name,size,sha in MODELS:
        path=models+'/'+name
        if wsl(distro,user,'stat','-f','-c','%T',path)!='ext2/ext3':
            raise ValueError('Model files must reside on native WSL Ext4')
        if wsl(distro,user,'stat','-c','%s',path)!=str(size):
            raise ValueError('Wrong model size: '+name)
        if verify_model_hash and wsl(distro,user,'sha256sum',path,timeout=1800).split()[0]!=sha:
            raise ValueError('Wrong model hash: '+name)
    for name in ('tokenizer.json','tokenizer_config.json'):
        wsl(distro,user,'test','-s',models+'/tokenizer/'+name)
    if dxg:
        dxg=linux_path(dxg)
        if wsl(distro,user,'sha256sum',dxg).split()[0]!=DXG_HASH:
            raise ValueError('Wrong DXG library hash')
    else:
        check_hash(wheel,WHEEL_HASH)
        with zipfile.ZipFile(wheel) as z:
            data=z.read('_rocm_sdk_core/lib/librocdxg.so.1')
        if len(data)!=6606449 or hashlib.sha256(data).hexdigest()!=DXG_HASH:
            raise ValueError('Wrong wheel DXG member')
        dxg=workspace+'/.local/librocdxg.so.1'
    return dict(schema=1,version='0.14.2',image=IMAGE,distro=distro,user=user,
                models=models,dxg=dxg,workspace=workspace,pwsh=pwsh)


def reject_links(path):
    path=Path(path)
    for item in [path,*path.parents]:
        if item.is_symlink() or item.is_junction():
            raise ValueError('Linked installation path refused: '+str(item))
        if item==ROOT: break
    if not path.resolve().is_relative_to(LOCAL.resolve()):
        raise ValueError('Installation path escapes local installation')


def install(distro,user,models,dxg,wheel=None,explicit=False,verify_model_hash=False):
    reject_links(LOCAL)
    if LOCAL.exists() and any(p.is_file() and not p.is_relative_to(LOCAL/'attempts') for p in LOCAL.rglob('*')):
        raise ValueError('Existing version-specific installation; stop and uninstall it first')
    config=preflight(distro,user,models,dxg,wheel,verify_model_hash and explicit)
    if not explicit:
        print('Preflight passed. No build, download, configuration write or model launch.')
        return config
    LOCAL.mkdir(exist_ok=True)
    def ws(*args,timeout=30): return wsl(config['distro'],config['user'],*args,timeout=timeout)
    def local_path(relative): return config['workspace']+'/.local/'+relative
    cid=None; name='halogen0142-setup-'+uuid.uuid4().hex
    completed=False; cleanup_ok=False
    try:
        if wheel:
            with zipfile.ZipFile(wheel) as z:
                (LOCAL/'librocdxg.so.1').write_bytes(z.read('_rocm_sdk_core/lib/librocdxg.so.1'))
        # Extract dependencies from a stopped, unprivileged container. Never start it.
        cid=ws('docker','create','--name',name,'--network','none','--label',
               'strix-alloy.setup=halogen0142','--entrypoint','/bin/true',IMAGE)
        if not re.fullmatch('[0-9a-f]{64}',cid): raise ValueError('Invalid setup container ID')
        extracts=[('/usr/local/bin/flash_serve','flash_serve'),
                  ('/usr/local/bin/entrypoint.sh','entrypoint-upstream.sh'),
                  ('/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/include','hip-include')]
        for source,target in extracts:
            ws('docker','cp',cid+':'+source,local_path(target),timeout=120)
        check_hash(LOCAL/'flash_serve',RELEASE['engine_sha256'])
        check_hash(LOCAL/'entrypoint-upstream.sh',RELEASE['entrypoint_sha256'])
        check_hash(LOCAL/'hip-include/hip/hip_runtime_api.h',RELEASE['hip_header_sha256'])
        import bridge_adapter, entrypoint_adapter
        bridge_adapter.verify_engine((LOCAL/'flash_serve').read_bytes())
        (LOCAL/'entrypoint-wsl.sh').write_bytes(entrypoint_adapter.transform((LOCAL/'entrypoint-upstream.sh').read_bytes()))
        check_hash(LOCAL/'entrypoint-wsl.sh',RELEASE['adapted_entrypoint_sha256'])
        commands=[
            (['-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
              '-DHALOGEN_RESEARCH_VGM64=1','-DHALOGEN_PREFLIGHT_V1=1',
              '-mno-avx','-mno-avx2','-mno-avx512f',
              'patches/hip-register-hybrid.c','patches/halogen-preflight-bridge.c',
              'patches/halogen-preflight-trampoline.S','-ldl','-pthread',
              '-Wl,-z,relro,-z,now,-z,noexecstack,-z,defs'],
             'libhalogen0142-preflight.so','bridge_sha256'),
            (['-DHALOGEN_RESEARCH_VGM64=1','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',
              'patches/hip-register-private-rw.c','-ldl','-pthread'],
             'hip-register-private-rw.so','private_sha256'),
            (['-O2','-Wall','-Wextra','-Werror','-D__HIP_PLATFORM_AMD__',
              '-I.local/hip-include','scripts/halogen0142_hip_probe.c','-ldl'],
             'halogen0142_hip_probe','probe_sha256')]
        for flags,target,hash_key in commands:
            ws('timeout','--signal=TERM','--kill-after=5s','120s','env','-C',config['workspace'],
               'gcc',*flags,'-o','.local/'+target,timeout=130)
            check_hash(LOCAL/target,RELEASE[hash_key])
        (LOCAL/'machine.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
        completed=True
    finally:
        try:
            if cid:
                info=json.loads(ws('docker','inspect',cid))[0]
                if (info['Id']!=cid or info['Name']!='/'+name or info['State']['Running'] or
                    info['Config']['Image']!=IMAGE or
                    info['Config']['Labels'].get('strix-alloy.setup')!='halogen0142'):
                    raise ValueError('Setup cleanup identity mismatch; container retained')
                ws('docker','rm',cid)
            cleanup_ok=True
        finally:
            files={p.relative_to(LOCAL).as_posix():digest(p) for p in LOCAL.rglob('*') if p.is_file() and not p.is_symlink() and not p.is_relative_to(LOCAL/'attempts')}
            (LOCAL/'install-manifest.json').write_text(json.dumps(
                dict(schema=1,version='0.14.2',completed=completed and cleanup_ok,files=files),indent=2),encoding='utf-8')
    print('Installed Halogen 0.14.2 adapters. No model or GPU workload was started.')
    return config


def installed():
    verify_sources()
    reject_links(LOCAL/'install-manifest.json')
    manifest=json.loads((LOCAL/'install-manifest.json').read_text())
    if manifest.get('version')!='0.14.2' or manifest.get('completed') is not True:
        raise ValueError('Halogen 0.14.2 installation did not finish')
    for name,sha in manifest['files'].items():
        path=LOCAL/name; reject_links(path); check_hash(path,sha)
    config=json.loads((LOCAL/'machine.json').read_text())
    if config.get('schema')!=1 or config.get('version')!='0.14.2' or config.get('image')!=IMAGE:
        raise ValueError('Wrong installed configuration')
    identity(config['distro'],'distribution'); identity(config['user'],'Linux user')
    linux_path(config['models'],native=True); linux_path(config['dxg']); linux_path(config['workspace'])
    if not Path(config['pwsh']).is_absolute() or not Path(config['pwsh']).is_file():
        raise ValueError('Recorded PowerShell executable is unavailable')
    return config


def uninstall():
    reject_links(LOCAL/'install-manifest.json')
    if (LOCAL/'runner.lock').exists(): raise ValueError('Active or unresolved run; retain files and evidence')
    manifest=json.loads((LOCAL/'install-manifest.json').read_text())
    if manifest.get('schema')!=1 or manifest.get('version')!='0.14.2': raise ValueError('Unknown install manifest')
    targets=[]
    for name,sha in manifest['files'].items():
        if name.startswith(('attempts/','runner.lock')): raise ValueError('Uninstall cannot own run evidence')
        path=LOCAL/name; reject_links(path)
        if path.exists(): check_hash(path,sha); targets.append(path)
    for path in targets: path.unlink()
    (LOCAL/'install-manifest.json').unlink()
    print('Removed only manifest-owned generated files. Models, images and run evidence retained.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','uninstall'])
    parser.add_argument('--distro',default='Ubuntu-24.04'); parser.add_argument('--user')
    parser.add_argument('--models'); parser.add_argument('--dxg'); parser.add_argument('--wheel')
    parser.add_argument('--install',action='store_true'); parser.add_argument('--verify-model-hash',action='store_true')
    args=parser.parse_args()
    if args.action=='uninstall': uninstall()
    else: install(args.distro,args.user,args.models,args.dxg,args.wheel,args.install,args.verify_model_hash)
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr); raise SystemExit(2)
