"""Decode selected rows of an HGN q4c variant-2 tensor for NPU prototyping."""
import argparse,json,pathlib,struct,numpy as np
P=argparse.ArgumentParser(); P.add_argument("hgn",type=pathlib.Path); P.add_argument("--manifest",type=pathlib.Path,required=True)
P.add_argument("--tensor",required=True); P.add_argument("--row-start",type=int,default=0); P.add_argument("--rows",type=int,default=1)
P.add_argument("--out",type=pathlib.Path,required=True); a=P.parse_args()
m=json.loads(a.manifest.read_text(encoding="utf-8")); e=next(x for x in m["entries"] if x["name"]==a.tensor)
if e["store"]!=5 or e["variant"]!=2: raise SystemExit("requires q4c variant 2")
K=e["dims"][-1]; N=int(np.prod(e["dims"][:-1])) if len(e["dims"])>1 else 1
if not (0<=a.row_start<N and 0<a.rows<=N-a.row_start): raise SystemExit("row slice outside tensor")
code_bytes=K//2; code_plane_bytes=N*code_bytes; scale_base=e["offset"]+64+((code_plane_bytes+63)//64)*64
scale_stride=((K//16+15)//16)*16; groups=K//32
out=np.empty((a.rows,K),dtype=np.float32)
with a.hgn.open("rb") as f:
    f.seek(e["offset"]); codebook=np.frombuffer(f.read(64),dtype="<f4").copy()
    for j,row in enumerate(range(a.row_start,a.row_start+a.rows)):
        f.seek(e["offset"]+64+row*code_bytes); packed=np.frombuffer(f.read(code_bytes),dtype=np.uint8)
        codes=np.empty(K,dtype=np.uint8); codes[0::2]=packed&15; codes[1::2]=packed>>4
        f.seek(scale_base+row*scale_stride); scales=np.frombuffer(f.read(groups*2),dtype="<f2").astype(np.float32)
        out[j]=codebook[codes]*np.repeat(scales,32)
a.out.parent.mkdir(parents=True,exist_ok=True); np.save(a.out,out)
print(json.dumps({"tensor":a.tensor,"shape":e["dims"],"row_start":a.row_start,"rows":a.rows,"K":K,
 "output_shape":list(out.shape),"min":float(out.min()),"max":float(out.max()),"finite":bool(np.isfinite(out).all())},indent=2))
