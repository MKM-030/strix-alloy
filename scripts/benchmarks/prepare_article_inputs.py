"""Fetch pinned public code as benchmark data; never execute downloaded source."""
import argparse,hashlib,json,urllib.request
from pathlib import Path


def write_verified(path,data,expected):
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Input checksum mismatch: '+str(path))
    path=Path(path)
    if path.exists():
        if path.read_bytes()!=data:raise ValueError('Existing input differs; nothing overwritten: '+str(path))
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(data)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--tokenizer',type=Path,required=True)
    a=p.parse_args()
    manifest=json.loads(Path(__file__).with_name('article-corpus-manifest.json').read_text())
    repo='llamastash/llamastash'
    if manifest['repository']!=repo:raise ValueError('Unexpected public input repository')
    token=a.tokenizer.read_bytes()
    write_verified(a.work/'tokenizer.json',token,manifest['tokenizer_sha256'])
    corpus=[]
    for entry in manifest['files']:
        name=entry['path']
        if '..' in Path(name).parts or not name.startswith('src/tui/'):raise ValueError('Invalid source path')
        url='https://raw.githubusercontent.com/'+repo+'/'+manifest['revision']+'/'+name
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read(4*1024**2+1)
        if len(data)>4*1024**2:raise ValueError('Unexpected oversized source file')
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Pinned source changed: '+name)
        corpus.append({'path':name,'sha256':entry['sha256'],'text':data.decode('utf-8')})
    encoded=json.dumps(corpus,ensure_ascii=False).encode('utf-8')
    write_verified(a.work/'corpus.json',encoded,hashlib.sha256(encoded).hexdigest())
    notices=Path(__file__).with_name('THIRD_PARTY_NOTICES.md').read_bytes()
    write_verified(a.work/'CORPUS_LICENSE.txt',notices,hashlib.sha256(notices).hexdigest())
    print('Prepared twelve checksum-verified code files as data and the matching local tokenizer.')
    print('No model, driver, server or downloaded code was executed.')
    return 0

if __name__=='__main__':raise SystemExit(main())
