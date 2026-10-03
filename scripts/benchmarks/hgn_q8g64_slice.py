"""Decode selected rows of an HGN q8g64 tensor (storage code 7)."""
import argparse,json,pathlib,numpy as np
P=argparse.ArgumentParser(); P.add_argument("hgn",type=pathlib.Path); P.add_argument("--manifest",type=pathlib.Path,required=True)
P.add_argument("--tensor",required=True); P.add_argument("--row-start",type=int,default=0); P.add_argument("--rows",type=int,default=1)
P.add_argument("--out",type=pathlib.Path,required=True); a=P.parse_args()
m=json.loads(a.manifest.read_text(encoding="utf-8")); e=next(x for x in m["entries"] if x["name"]==a.tensor)
if e["store"]!=7 or e["variant"]!=0: raise SystemExit("requires q8g64 variant 0")
K=e["dims"][-1]; N=int(np.prod(e["dims"][:-1])) if len(e["dims"])>1 else 1
if K%64: raise SystemExit("K must be divisible by 64")
if not (0<=a.row_start<N and 0<a.rows<=N-a.row_start): raise SystemExit("row slice outside tensor")
groups=K//64; row_bytes=K+K//16
if row_bytes*N!=e["size"]: raise SystemExit("q8g64 payload size mismatch")
out=np.empty((a.rows,K),dtype=np.float32)
with a.hgn.open("rb") as f:
    for j,row in enumerate(range(a.row_start,a.row_start+a.rows)):
        base=e["offset"]+row*row_bytes; f.seek(base)
        q=np.frombuffer(f.read(K),dtype=np.uint8).astype(np.float32)
        affine=np.frombuffer(f.read(K//16),dtype="<f2").astype(np.float32).reshape(groups,2)
        out[j]=q*np.repeat(affine[:,0],64)+np.repeat(affine[:,1],64)
a.out.parent.mkdir(parents=True,exist_ok=True); np.save(a.out,out)
print(json.dumps({"tensor":a.tensor,"shape":e["dims"],"row_start":a.row_start,"rows":a.rows,"K":K,
 "output_shape":list(out.shape),"min":float(out.min()),"max":float(out.max()),"finite":bool(np.isfinite(out).all())},indent=2))
