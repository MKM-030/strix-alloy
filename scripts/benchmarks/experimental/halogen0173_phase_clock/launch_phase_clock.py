"""Checked opt-in launcher; --check-only is passive and safe on the host."""
from pathlib import Path
import argparse, hashlib, json, os, struct, sys
ENGINE_SHA='af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
ADAPTER_SHA='176e78652589523f3d6f4e9404c0f247843f7792ec3f7056342ee60500d16e91'
WINDOWS={
 0x1746b31:'4189d44989f64989ffe8f1da1a004889442418',
 0x1746f11:'e81ad71a00482b4424180f57c0f2480f2ac0f20f5e0555cd8cfef2410f588618040000f2410f11861804000049c7874001000000000000',
 0x17490a3:'418b46544189868c01000041c7465801000000e875b51a0049898698010000',
 0x174c9fa:'4c8bbb980100004d89c44489cdf20f11442468e81e7c1a00f20f104424684189e94d89e04c29f80f57c9f2480f2ac8f20f5e0d4f728cfe',
 0x1747c4b:'0f10060f1107',
 0x1747f1d:'498dbe88010000488db388010000ba81000000e83bc41a00',
 0x174a0fb:'0f10060f1107',
 0x174a603:'488dbb88010000498db688010000ba81000000e8559d1a00',
 0x173d711:'488dbc24d0010000488db424000a0000e84abf0000',
 0x172ed03:'488d8424d00100004889842420080000',
 0x1745e64:'4889fb488b074c8b77084c69ee080300004c8b384d01ef',
 0x1745f6a:'4c89f74c89fae999020000',
 0x1746202:'4c89f74c89fa4531c04531c9e88d670000',
 0x174c9c4:'4889d348897424784989fe488b02',
}
def verify_engine(path):
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ENGINE_SHA:raise ValueError('Exact native0.17.3 engine SHA rejected')
    if data[:7]!=b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH',data,16)!=(3,62):raise ValueError('Expected x86-64 ET_DYN')
    phoff=struct.unpack_from('<Q',data,32)[0];phsize,phnum=struct.unpack_from('<HH',data,54)
    if phsize!=56 or phnum>64:raise ValueError('ELF geometry rejected')
    segments=[struct.unpack_from('<IIQQQQQQ',data,phoff+i*phsize) for i in range(phnum)]
    for rva,hexbytes in WINDOWS.items():
        blob=bytes.fromhex(hexbytes)
        matching=[p for p in segments if p[0]==1 and p[1]==5 and p[3]<=rva and rva+len(blob)<=p[3]+p[5]]
        if len(matching)!=1:raise ValueError('Measurement window not uniquely executable')
        p=matching[0];off=p[2]+rva-p[3]
        if data[off:off+len(blob)]!=blob:raise ValueError('Measurement instruction bytes rejected')
def residency_probe(engine_args):
    return any(x=='--resident-gib' or x.startswith('--resident-gib=') for x in engine_args)
def compose_phase_environment(adapter,enable=False,journal=None,engine_args=(),environ=None,arm_file=None):
    """Preserve independent preloads; strip phase instrumentation for residency.

    Root's normal lifecycle wrapper may call this on Linux. An enabled serving
    process must treat constructor exit125 as terminal rather than retrying it.
    """
    env=dict(os.environ if environ is None else environ)
    env.pop('HGN0173_PHASE_RAW',None);env.pop('HGN0173_PHASE_JOURNAL',None);env.pop('HGN0173_PHASE_ARM_FILE',None)
    adapter=str(Path(adapter).resolve())
    preloads=[x for x in env.get('LD_PRELOAD','').replace(':',' ').split() if x!=adapter]
    if enable and not residency_probe(engine_args):
        if not journal or not journal.is_absolute() or journal.exists() or not journal.parent.is_dir():
            raise ValueError('Activation requires a fresh absolute journal in an existing directory')
        if any(c.isspace() or c==':' for c in adapter):raise ValueError('LD_PRELOAD adapter path cannot contain whitespace/colon')
        preloads.insert(0,adapter)
        env['HGN0173_PHASE_RAW']='1';env['HGN0173_PHASE_JOURNAL']=str(journal)
        if arm_file is not None:
            if not arm_file.is_absolute() or arm_file.exists() or not arm_file.parent.is_dir() or arm_file==journal:
                raise ValueError('Deferred activation requires a fresh distinct absolute arming path')
            env['HGN0173_PHASE_ARM_FILE']=str(arm_file)
    if preloads:env['LD_PRELOAD']=' '.join(preloads)
    else:env.pop('LD_PRELOAD',None)
    return env
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',required=True,type=Path);p.add_argument('--adapter',required=True,type=Path)
    p.add_argument('--enable',action='store_true');p.add_argument('--journal',type=Path)
    p.add_argument('--arm-file',type=Path,help='Defer journal/pairs until root creates an empty owned0600 file after ready')
    p.add_argument('--check-only',action='store_true');p.add_argument('engine_args',nargs=argparse.REMAINDER)
    args=p.parse_args();verify_engine(args.engine)
    if hashlib.sha256(args.adapter.read_bytes()).hexdigest()!=ADAPTER_SHA:raise ValueError('Adapter SHA rejected')
    engine_args=args.engine_args
    if engine_args and engine_args[0]=='--':engine_args=engine_args[1:]
    bypass=residency_probe(engine_args)
    print(json.dumps(dict(engine_sha256=ENGINE_SHA,adapter_sha256=ADAPTER_SHA,
        instruction_windows=len(WINDOWS),decode_pairing_version=2,enabled_requested=args.enable,enabled_effective=bool(args.enable and not bypass),
        residency_bypass=bypass,deferred_arm=bool(args.arm_file and args.enable and not bypass),check_only=args.check_only)),file=sys.stderr,flush=True)
    if args.check_only:return
    if sys.platform!='linux':raise ValueError('Actual launch requires Linux; host permits check-only')
    env=compose_phase_environment(args.adapter,args.enable,args.journal,engine_args,arm_file=args.arm_file)
    os.execvpe(str(args.engine.resolve()),[str(args.engine.resolve()),*engine_args],env)
if __name__=='__main__':main()
