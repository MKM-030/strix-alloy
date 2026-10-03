"""Verify v2 once per file identity; never trust a preallocated file's length alone."""
import json
from pathlib import Path
import portable

SIZE=66687678432
SHA='71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687'
STAT_CODE="""import json,os,sys
s=os.stat(sys.argv[1])
print(json.dumps(dict(size=s.st_size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)))"""
HASH_CODE=Path(__file__).with_name('bounded_hash.py').read_text(encoding='utf-8')


def receipt_matches(receipt, identity):
    return (isinstance(receipt,dict) and receipt.get('sha256')==SHA
            and receipt.get('identity')==identity and identity.get('size')==SIZE)


def verify(machine, local):
    model=machine['models']+'/qwen38-flash-next-v2.hgn'
    receipt_path=Path(local)/'v2-integrity.json'
    def ws(code,timeout=30):
        return json.loads(portable.wsl(machine['distro'],machine['user'],
                                      'python3','-c',code,model,timeout=timeout))
    identity=ws(STAT_CODE)
    if identity.get('size')!=SIZE: raise ValueError('v2 checkpoint is incomplete or has the wrong size')
    if receipt_path.exists():
        portable.reject_links(receipt_path)
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt_matches(receipt,identity): return receipt
    print('Verifying the complete v2 checkpoint SHA-256 before GPU allocation.',flush=True)
    receipt=ws(HASH_CODE,timeout=600)
    if not receipt_matches(receipt,identity):
        raise ValueError('v2 checksum or file identity does not match the pinned checkpoint')
    temporary=receipt_path.with_suffix('.tmp')
    portable.reject_links(temporary)
    temporary.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    temporary.replace(receipt_path)
    return receipt
