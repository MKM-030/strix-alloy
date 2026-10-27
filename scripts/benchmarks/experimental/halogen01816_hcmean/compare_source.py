"""ROOT CPU-only comparison of a saved device fixture against source mean bits."""
import argparse
from array import array
import json
from pathlib import Path
import sys

def main(directory,actual_path):
    if sys.byteorder!='little':raise ValueError('little-endian words required')
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    folder=Path(directory);meta=json.loads((folder/'fixture.json').read_text())
    raw=array('H');raw.frombytes((folder/'raw.u16').read_bytes())
    actual=array('H');actual.frombytes(Path(actual_path).read_bytes())
    explicit=array('H');explicit.frombytes((folder/'expected.u16').read_bytes())
    if len(actual)!=len(explicit):raise ValueError('device output size differs')
    x=torch.tensor(raw,dtype=torch.uint16,device='cpu').view(torch.bfloat16).view(meta['full_rows'],4,2560)
    source=x[meta['source_first']:meta['source_first']+meta['rows']].mean(-2).view(torch.uint16)
    source_bits=array('H',explicit)
    for row in range(meta['rows']):
        begin=(meta['destination_first']+row)*12800+meta['tap']*2560
        source_bits[begin:begin+2560]=array('H',source[row].tolist())
    mismatch=sum(a!=b for a,b in zip(actual,source_bits))
    non_nan=sum(a!=b and not ((a&0x7fff)>0x7f80 and (b&0x7fff)>0x7f80) for a,b in zip(actual,source_bits))
    print(json.dumps(dict(torch_version=torch.__version__,source_cpu_bit_mismatches=mismatch,
                         non_nan_mismatches=non_nan,device_equals_explicit=actual==explicit)))
    # NaN payload difference reported separately; finite/zero/Inf are bit-exact.
    return bool(non_nan or actual!=explicit)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('actual');a=p.parse_args()
    raise SystemExit(main(a.directory,a.actual))
