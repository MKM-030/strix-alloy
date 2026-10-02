"""Extract Halogen's 31 embedded mtp.* tensors into a standalone HGN head."""
import argparse, os, pathlib, struct
HDR,ENT=0x68,0xA0
P=argparse.ArgumentParser(); P.add_argument("source",type=pathlib.Path); P.add_argument("output",type=pathlib.Path)
a=P.parse_args()
def read(path):
    with path.open("rb") as f:
        h=f.read(HDR); magic,ver,n,toff,doff,fsize=struct.unpack("<IIQQQQ",h[:0x28])
        if magic!=0x314E4748 or fsize!=path.stat().st_size: raise ValueError("invalid HGN")
        ents=[]; f.seek(toff)
        for _ in range(n):
            b=bytearray(f.read(ENT)); name=b[:96].split(b"\0")[0].decode()
            off,size,chk,var=struct.unpack_from("<QQII",b,0x88)
            if name.startswith("mtp."): ents.append((name,b,off,size,chk,var))
        return ver,ents
ver,ents=read(a.source)
if len(ents)!=31: raise ValueError(f"expected 31 mtp tensors, got {len(ents)}")
if a.output.exists(): raise FileExistsError(a.output)
table_end=HDR+ENT*len(ents); data_off=(table_end+63)//64*64
with a.source.open("rb") as src, a.output.open("xb") as out:
    out.write(b"\0"*data_off); cursor=data_off; packed=[]
    for name,b,old,size,chk,var in ents:
        cursor=(cursor+63)//64*64; out.seek(cursor); src.seek(old)
        left=size
        while left:
            chunk=src.read(min(left,8<<20))
            if not chunk: raise EOFError(name)
            out.write(chunk); left-=len(chunk)
        struct.pack_into("<QQII",b,0x88,cursor,size,chk,var); packed.append(bytes(b)); cursor+=size
    end=(cursor+63)//64*64; out.truncate(end); ident=b"qwen3.8-flash-next-mtp"
    out.seek(0); out.write(struct.pack("<IIQQQQ",0x314E4748,ver,len(ents),HDR,data_off,end)+ident+b"\0"*(64-len(ident)))
    out.seek(HDR); out.write(b"".join(packed)); out.flush(); os.fsync(out.fileno())
print(f"{a.output}: {len(ents)} tensors, {a.output.stat().st_size} bytes")
