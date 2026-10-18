"""Verify checkpoints once per file identity; never trust file length alone."""
import json
from pathlib import Path
import portable

SIZE=66687678432
SHA='71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687'
NGRAM_NAME,NGRAM_SIZE,NGRAM_SHA=portable.MODELS[0]
STAT_CODE="""import json,os,sys
s=os.stat(sys.argv[1])
print(json.dumps(dict(size=s.st_size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)))"""
HASH_CODE=Path(__file__).with_name('bounded_hash.py').read_text(encoding='utf-8')


def receipt_matches(receipt, identity, *, size=SIZE, sha=SHA, source=None):
    return (isinstance(identity,dict)
            and all(type(identity.get(key)) is int for key in ('size','device','inode','mtime_ns','ctime_ns'))
            and isinstance(receipt,dict) and receipt.get('sha256')==sha
            and receipt.get('identity')==identity and identity.get('size')==size
            and (source is None or receipt.get('source')==source))


def _verify_file(machine, local, model, name, size, sha, label, bind_source=False):
    receipt_path=Path(local)/name
    portable.reject_links(receipt_path)
    source=model if bind_source else None
    def ws(code,timeout=30):
        return json.loads(portable.wsl(machine['distro'],machine['user'],
                                      'python3','-c',code,model,timeout=timeout))
    identity=ws(STAT_CODE)
    if not isinstance(identity,dict) or identity.get('size')!=size:
        raise ValueError(label+' is incomplete or has the wrong size')
    if receipt_path.exists():
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt_matches(receipt,identity,size=size,sha=sha,source=source): return receipt
    print('Verifying the complete '+label+' SHA-256 before GPU allocation.',flush=True)
    receipt=ws(HASH_CODE,timeout=600)
    if bind_source and isinstance(receipt,dict): receipt['source']=model
    if not receipt_matches(receipt,identity,size=size,sha=sha,source=source):
        raise ValueError(label+' checksum or file identity does not match the pinned checkpoint')
    temporary=receipt_path.with_suffix('.tmp')
    portable.reject_links(temporary)
    temporary.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    temporary.replace(receipt_path)
    return receipt


def verify(machine, local):
    return _verify_file(machine,local,machine['models']+'/qwen38-flash-next-v2.hgn',
                        'v2-integrity.json',SIZE,SHA,'v2 checkpoint')


def verify_ngram(machine, local):
    source=portable.linux_path(machine.get('ngram_source') or machine['models']+'/'+NGRAM_NAME)
    return _verify_file(machine,local,source,'ngram-integrity.json',
                        NGRAM_SIZE,NGRAM_SHA,'N-gram source',bind_source=True)
