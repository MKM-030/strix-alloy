"""ROOT ONLY, explicit opt-in: saved kernel bits vs actual PyTorch GPU mean.

No engine or native pointer. Run only after complete capture-mechanism review.
This fixture deliberately performs copies and waits outside production enqueue.
"""
import argparse
from array import array
import json
from pathlib import Path
import sys

def main(directory,actual_path):
    import torch
    folder=Path(directory);meta=json.loads((folder/'fixture.json').read_text())
    raw=array('H');raw.frombytes((folder/'raw.u16').read_bytes())
    actual=array('H');actual.frombytes(Path(actual_path).read_bytes())
    if sys.byteorder!='little' or len(actual)!=meta['output_elements']:raise ValueError('fixture format differs')
    # Separate owned tensor and stream; no borrowed native storage.
    cpu=torch.tensor(raw,dtype=torch.uint16,device='cpu').view(torch.bfloat16).view(meta['full_rows'],4,2560)
    stream=torch.cuda.Stream()
    with torch.cuda.stream(stream):
        owned=cpu.to('cuda')
        source=owned[meta['source_first']:meta['source_first']+meta['rows']].mean(-2)
        source_cpu=source.to('cpu')
    stream.synchronize()
    expected=source_cpu.view(torch.uint16).tolist();total=non_nan=0
    for row in range(meta['rows']):
        begin=(meta['destination_first']+row)*12800+meta['tap']*2560
        for col,b in enumerate(expected[row]):
            a=actual[begin+col]
            total+=a!=b
            non_nan+=a!=b and not ((a&0x7fff)>0x7f80 and (b&0x7fff)>0x7f80)
    print(json.dumps(dict(torch_version=torch.__version__,torch_git=torch.version.git_version,
                         hip=torch.version.hip,source_gpu_bit_mismatches=total,non_nan_mismatches=non_nan)))
    return bool(non_nan)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-gpu',action='store_true',required=True)
    p.add_argument('directory');p.add_argument('actual');a=p.parse_args()
    raise SystemExit(main(a.directory,a.actual))
