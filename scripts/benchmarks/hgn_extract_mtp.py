"""Parse an HGN v1/v2 container and extract MTP payloads without loading the model."""
import argparse,hashlib,json,pathlib,struct
P=argparse.ArgumentParser(); P.add_argument("hgn",type=pathlib.Path); P.add_argument("--out",type=pathlib.Path,required=True)
P.add_argument("--extract-dir",type=pathlib.Path); P.add_argument("--verify-xor",action="store_true"); a=P.parse_args()
HDR=104; ENT=160; MAGIC=0x314E4748
with a.hgn.open("rb") as f:
    h=f.read(HDR); magic,version=struct.unpack_from("<II",h,0); n,table,data,size=struct.unpack_from("<QQQQ",h,8)
    ident=h[40:104].split(b"\0",1)[0].decode("ascii")
    if magic!=MAGIC or version not in (1,2) or size!=a.hgn.stat().st_size: raise SystemExit("invalid HGN header")
    f.seek(table); entries=[]
    for _ in range(n):
        b=f.read(ENT); name=b[:96].split(b"\0",1)[0].decode("ascii"); store,rank=struct.unpack_from("<II",b,96)
        dims=list(struct.unpack_from("<qqqq",b,104))[:rank]; off,sz=struct.unpack_from("<QQ",b,136); xor,variant=struct.unpack_from("<II",b,152)
        if off+sz>size: raise SystemExit("payload outside file: "+name)
        if name.startswith("mtp."): entries.append(dict(name=name,store=store,rank=rank,dims=dims,offset=off,size=sz,xor32=xor,variant=variant))
    if a.extract_dir: a.extract_dir.mkdir(parents=True,exist_ok=True)
    for e in entries:
        f.seek(e["offset"]); payload=f.read(e["size"])
        if a.verify_xor:
            import numpy as np
            padded=payload if len(payload)%4==0 else payload+b"\0"*(4-len(payload)%4)
            x=int(np.bitwise_xor.reduce(np.frombuffer(padded,dtype="<u4"),initial=np.uint32(0)))
            if x!=e["xor32"]: raise SystemExit("checksum mismatch: "+e["name"])
        e["sha256"]=hashlib.sha256(payload).hexdigest()
        if a.extract_dir:
            p=a.extract_dir/(e["name"].replace("/","_")+".bin"); p.write_bytes(payload); e["extracted"]=str(p)
result={"schema":1,"path":str(a.hgn),"identity":ident,"version":version,"file_size":size,"tensor_count":n,
        "mtp_count":len(entries),"mtp_bytes":sum(x["size"] for x in entries),"entries":entries}
a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in result.items() if k!="entries"},indent=2))
