"""Apply only the pinned source-only numerical compatibility patch; preserve user edits."""
import argparse,json,subprocess
from pathlib import Path
from verify_toolchain import digest,check_source,PINS

def apply_source(root,pins,patch_file,apply=False):
    root=Path(root).resolve(strict=True);patch_file=Path(patch_file)
    spec=pins['source_patch'];files=spec.get('files') or {spec['path']:spec}
    if digest(patch_file)!=spec['sha256']:raise ValueError('Compatibility patch digest changed')
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True,timeout=30).strip()
    if git('rev-parse','HEAD')!=pins['source_commit']:raise ValueError('Unexpected upstream source revision')
    paths={}
    for name,expected in files.items():
        target=(root/name).resolve()
        if not target.is_relative_to(root):raise ValueError('Patch path escapes source checkout')
        paths[name]=target
    if all(p.is_file() and digest(p)==files[n]['after_sha256'] for n,p in paths.items()):
        check_source(root,pins)
        return {'already_applied':True,'source_patch_sha256':spec['sha256']}
    if git('status','--porcelain','--untracked-files=all'):
        raise ValueError('Source has local changes or a partial patch; nothing was overwritten')
    for name,target in paths.items():
        before=files[name].get('before_sha256')
        if before is None:
            if target.exists():raise ValueError('New helper path already exists')
        elif not target.is_file() or digest(target)!=before:
            raise ValueError('Original source bytes differ: '+name)
    subprocess.run(['git','-C',str(root),'apply','--check',str(patch_file.resolve())],check=True,timeout=30)
    if not apply:return {'would_apply':True,'source_patch_sha256':spec['sha256']}
    subprocess.run(['git','-C',str(root),'apply',str(patch_file.resolve())],check=True,timeout=30)
    return {'applied':True,**check_source(root,pins)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();pins=json.loads(PINS.read_text(encoding='utf-8'))
    patch_file=PINS.parent/pins['source_patch']['file']
    print(json.dumps(apply_source(args.source,pins,patch_file,args.apply),indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
