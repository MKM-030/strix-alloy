"""Fail-closed geometry check for reusing FLM Qwen3.8-27B MTP kernels with Halogen Flash-Next."""
import argparse,json,struct,pathlib
P=argparse.ArgumentParser();P.add_argument('hgn',type=pathlib.Path);P.add_argument('--out',type=pathlib.Path,required=True);a=P.parse_args()
HDR,ENT=0x68,0xA0
with a.hgn.open('rb') as f:
 h=f.read(HDR);magic,ver,n,toff,doff,size=struct.unpack('<IIQQQQ',h[:0x28]);f.seek(toff); tensors={}
 for _ in range(n):
  b=f.read(ENT);name=b[:96].split(b'\0')[0].decode();rank=struct.unpack_from('<I',b,0x64)[0];shape=struct.unpack_from('<4q',b,0x68)[:rank]
  if name.startswith('mtp.'):tensors[name]=shape
fc=tensors.get('mtp.fc_hidden.weight'); q=tensors.get('mtp.layers.0.self_attn.q_proj.weight'); gate=tensors.get('mtp.layers.0.mlp.experts.gate_up_proj.weight')
flash={'base_hidden':2560,'hyperconnection_width':10240,'experts':512,'fc_shape':fc,'q_shape':q,'gate_shape':gate}
flm27={'hidden':5120,'intermediate':17408,'dense_mtp':True}
reasons=[]
if fc and 5120 not in fc: reasons.append('MTP fusion width is not FLM 27B hidden_size 5120')
if gate and len(gate)>=3 and gate[0]==512: reasons.append('Flash-Next MTP is 512-expert MoE; FLM 27B MTP is dense')
if q and q[-1]!=5120: reasons.append('attention projection input geometry differs from FLM 27B')
result={'schema':1,'flash_next':flash,'flm_qwen38_27b':flm27,'drop_in_compatible':not reasons,'reasons':reasons,
 'decision':'requires Flash-Next-specific NPU xclbin/layout' if reasons else 'candidate'}
a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if not reasons: raise SystemExit('unexpected compatibility: manually review before use')
