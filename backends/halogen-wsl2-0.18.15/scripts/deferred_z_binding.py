"""Fixed, source-pinned Deferred-Z binding. Generated for one reviewed DSO."""
from pathlib import Path
import portable

ROOT=Path(__file__).resolve().parents[1]
NAME='libhalogen01815-deferred-z.so'
DEST='/candidate/'+NAME
FLAG='HALOGEN_DEFERRED_Z'
BASE_PRELOAD='/candidate/libhalogen01815-v2-preflight.so:/candidate/hip-register-private-rw.so'
DSO_SHA='60365174dc91b2f94b12094b93b535865624cf75b6a8a0a7bdc93b2ee567ee09'
DSO_BYTES=1460128
MACHINE_SHA='48bef879b694b23dd455467b19f7e5c1e4b3734c065d7fb59b5589b3fe0acdc3'
INSTALL_SHA='51798d2f3576134afe57de3a1603b927589e41b1376eee45689833117974b1cc'
RELEASE_SHA='bb3eab7ccad4c4c148b189ef767a6116619165775bd490d976efad057f0844a7'

def verify():
    for relative,expected in (('.local/'+NAME,DSO_SHA),('.local/machine.json',MACHINE_SHA),
                              ('.local/install-manifest.json',INSTALL_SHA),('profiles/release.json',RELEASE_SHA)):
        path=ROOT/relative
        if (not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()) or
            any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents))):
            raise ValueError('Deferred-Z binding path is missing or linked')
        portable.check_hash(path,expected)
    path=ROOT/'.local'/NAME
    if path.stat().st_size!=DSO_BYTES:
        raise ValueError('Deferred-Z binary size differs')
    return path

def environment(env,checkpoint):
    value=env.pop(FLAG,None)
    if value in (None,'0'):
        return env
    if value!='1' or checkpoint!='v2' or env.get('HALOGEN_DECODE_PREFETCH')!='0':
        raise ValueError('Deferred-Z requires v2 and explicit native prefetch=0')
    if env.get('LD_PRELOAD')!=BASE_PRELOAD:
        raise ValueError('Deferred-Z baseline preload differs')
    verify()
    env[FLAG]='1'
    env['LD_PRELOAD']=DEST+':'+BASE_PRELOAD
    return env

def bind_manifest(m,linux_path):
    if m['environment'].get(FLAG)!='1':
        return
    path=verify()
    if DEST in m['mounts']:
        raise ValueError('Deferred-Z mount already exists')
    m['mounts'][DEST]=linux_path(path)
    m['deferred_z']={'sha256':DSO_SHA,'bytes':DSO_BYTES,'container_path':DEST}

def validate_manifest(m,linux_path):
    env=m.get('environment',{})
    active=env.get(FLAG)=='1'
    if not active:
        if FLAG in env or DEST in m.get('mounts',{}) or 'deferred_z' in m:
            raise ValueError('Unexpected inactive Deferred-Z binding')
        if DEST in env.get('LD_PRELOAD','').split(':'):
            raise ValueError('Unbound Deferred-Z preload')
        return
    path=verify()
    if (m.get('checkpoint')!='v2' or env.get('HALOGEN_DECODE_PREFETCH')!='0' or
        env.get('LD_PRELOAD')!=DEST+':'+BASE_PRELOAD or
        m.get('mounts',{}).get(DEST)!=linux_path(path) or
        m.get('deferred_z')!={'sha256':DSO_SHA,'bytes':DSO_BYTES,'container_path':DEST}):
        raise ValueError('Deferred-Z manifest identity differs')
