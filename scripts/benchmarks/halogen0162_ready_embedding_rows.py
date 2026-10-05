"""Bounded ready-projection artifact codec. No provider or hardware imports.

All arithmetic/source qualification belongs in the pinned producer receipt.
Changing a serving generation does not change projection words or provenance.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

MAGIC=b'HGNERC01'
HEADER=struct.Struct('<8s6I16s32s32s16s')
ROW=struct.Struct('<iI2560H')
MAX_ROWS,TOKENS,ROW_BYTES=64,248320,5120
MAX_BYTES=HEADER.size+MAX_ROWS*ROW.size

def hex_bytes(value, length):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{'+str(length*2)+'}',value):
        raise ValueError('invalid lowercase digest/generation')
    result=bytes.fromhex(value)
    if not any(result): raise ValueError('zero digest/generation')
    return result

def sha(raw): return hashlib.sha256(raw).hexdigest()

def words(raw):
    if len(raw)!=ROW_BYTES: raise ValueError('row must contain2560 BF16 values')
    result=struct.unpack('<2560H',raw)
    if any(value&0x7f80==0x7f80 for value in result):
        raise ValueError('nonfinite BF16 projection')
    return result

def encode(rows, generation, model_binding, provenance, origin):
    if origin not in (1,2) or not 1<=len(rows)<=MAX_ROWS: raise ValueError('origin/count')
    output=bytearray(HEADER.pack(MAGIC,1,HEADER.size,ROW_BYTES,len(rows),origin,0,
        hex_bytes(generation,16),hex_bytes(model_binding,32),hex_bytes(provenance,32),bytes(16)))
    seen=set()
    for token,raw in rows:
        if type(token) is not int or not 0<=token<TOKENS or token in seen:
            raise ValueError('unsupported/duplicate token')
        seen.add(token);output.extend(ROW.pack(token,0,*words(raw)))
    return bytes(output)

def decode(raw):
    if not HEADER.size+ROW.size<=len(raw)<=MAX_BYTES: raise ValueError('artifact size')
    magic,version,size,row_bytes,count,origin,reserved,generation,binding,provenance,pad=HEADER.unpack_from(raw)
    if (magic,version,size,row_bytes,reserved,pad)!=(MAGIC,1,HEADER.size,ROW_BYTES,0,bytes(16)):
        raise ValueError('artifact header')
    if not 1<=count<=MAX_ROWS or origin not in (1,2) or len(raw)!=HEADER.size+count*ROW.size:
        raise ValueError('artifact record count')
    rows=[]
    for index in range(count):
        offset=HEADER.size+index*ROW.size
        token,reserved,*_=ROW.unpack_from(raw,offset)
        if reserved: raise ValueError('row reserved bytes')
        rows.append((token,raw[offset+8:offset+ROW.size]))
    checked=encode(rows,generation.hex(),binding.hex(),provenance.hex(),origin)
    if checked!=raw: raise ValueError('artifact canonical encoding')
    return dict(generation=generation.hex(),model_binding=binding.hex(),provenance=provenance.hex(),origin=origin,rows=rows)

def bounded(path,limit):
    with Path(path).open('rb') as stream: raw=stream.read(limit+1)
    if len(raw)>limit: raise ValueError('file exceeds bounded input budget')
    return raw

def pack(manifest):
    raw=bounded(manifest,65536)
    value=json.loads(raw)
    if value.get('schema')!='halogen_ready_embedding_rows.v1': raise ValueError('manifest schema')
    records=value['rows']
    if not isinstance(records,list) or not 1<=len(records)<=MAX_ROWS: raise ValueError('manifest count')
    rows=[]
    for record in records:
        path=Path(record['file'])
        if not path.is_absolute(): path=Path(manifest).parent/path
        data=bounded(path,ROW_BYTES)
        if sha(data)!=record['sha256']: raise ValueError('producer row seal changed')
        rows.append((record['token'],data))
    return encode(rows,value['generation'],value['model_binding'],value['provenance'],value['origin'])

def rebind(raw,generation):
    value=decode(raw)
    return encode(value['rows'],generation,value['model_binding'],value['provenance'],value['origin'])

def metadata(raw):
    value=decode(raw)
    return {k:v for k,v in value.items() if k!='rows'}|dict(sha256=sha(raw),bytes=len(raw),tokens=[token for token,_ in value['rows']],row_sha256=[sha(row) for _,row in value['rows']],arithmetic_qualified_by_codec=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--manifest',type=Path)
    group.add_argument('--artifact',type=Path)
    parser.add_argument('--generation')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    raw=pack(args.manifest) if args.manifest else bounded(args.artifact,MAX_BYTES)
    if args.expected_sha256 and sha(raw)!=args.expected_sha256: raise ValueError('input artifact seal changed')
    if args.generation: raw=rebind(raw,args.generation)
    result=metadata(raw)
    if args.output:
        with args.output.open('xb') as stream: stream.write(raw)
        with args.output.with_suffix(args.output.suffix+'.json').open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
