"""Refuse an unqualified GUFO compiler before configuring or loading a model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PINS=Path(__file__).with_name('compatibility.json')

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def check_sdk(directory, pins):
    root=Path(directory).resolve(strict=True)
    version=(root/'.info/version').read_text(encoding='utf-8').strip()
    if version!=pins['sdk_version']:
        raise ValueError(f"GUFO requires qualified TheRock {pins['sdk_version']}; found {version}. Display-driver version is separate.")
    compiler=root/'lib/llvm/bin/clang++.exe'
    if digest(compiler)!=pins['compiler_sha256']:
        raise ValueError('Compiler bytes differ from the qualified SDK archive')
    for name, expected in pins['runtime_hashes'].items():
        if not (root/'bin'/name).is_file():
            raise ValueError('SDK runtime component missing: '+name)
        if digest(root/'bin'/name)!=expected:
            raise ValueError('SDK runtime bytes changed: '+name)
    return {'sdk_version':version,'compiler_sha256':pins['compiler_sha256']}

def check_source(directory, pins):
    root=Path(directory).resolve(strict=True)
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True,
                                       timeout=20).strip()
    if git('rev-parse','HEAD')!=pins['source_commit']:
        raise ValueError('GUFO source revision differs from the qualified candidate')
    modified=git('status','--porcelain','--untracked-files=no')
    patch=pins.get('source_patch')
    if patch:
        files=patch.get('files') or {patch['path']:patch}
        for rel, expected in files.items():
            target=(root/rel).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError('Missing or escaped compatibility source: '+rel)
            if digest(target)!=expected['after_sha256']:
                raise ValueError('Required compatibility source patch missing or changed: '+rel)
        changed=set(git('diff','HEAD','--name-only').splitlines())
        if patch.get('files'):
            changed.update(git('ls-files','--others','--exclude-standard').splitlines())
        if changed != set(files):
            raise ValueError('Unexpected source changes outside the pinned compatibility patch')
    elif modified:
        raise ValueError('Tracked GUFO source is modified; qualify it separately')
    for name,expected in pins['tests'].items():
        path=root/'tests/models/qwen38_flash_next'/(name+'_test.cpp')
        if digest(path)!=expected:
            raise ValueError('Numerical test changed: '+name)
    return {'source_commit':pins['source_commit'],'unchanged_tests':len(pins['tests']),
            'source_patch_sha256':patch['sha256'] if patch else None}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--source',type=Path)
    args=p.parse_args();pins=json.loads(PINS.read_text(encoding='utf-8'))
    result=check_sdk(args.sdk,pins)
    if args.source:result.update(check_source(args.source,pins))
    print(json.dumps(result,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
