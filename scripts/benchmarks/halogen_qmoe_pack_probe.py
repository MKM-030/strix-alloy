"""Bounded official AMD offline INT4 packing at Halogen head geometry.

Requires a root-owned child guard. Loads the exact staged native packer and
installed XRT dependency; performs no provider registration or inference.
Synthetic arrays exercise geometry/packing only, not draft quality.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(r"C:\Projects\strix-alloy-clean")
PAYLOAD = ROOT / "server/.local/optimization9h-20261004/qmoe-dd-stage-8bba3dba41e94053bb9196b918c2456f/payload/ryzenai_dynamic_dispatch"
XRT = Path(r"C:\Windows\System32\DriverStore\FileRepository\kipudrv.inf_amd64_7b0051e064968f34")
XRT_SHA = "04a26d37c6e0c713491ad0bfae74ce74ea94c74136d2aa056333616dac6c3a44"
PY_SHA = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
NATIVE = PAYLOAD / "_DynamicDispatch.cp312-win_amd64.pyd"

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root-owned-admission',action='store_true')
    p.add_argument('--expected-probe-sha256',required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--write-synthetic-bank',type=Path)
    a=p.parse_args()
    if not a.root_owned_admission or os.name!='nt' or sys.version_info[:2]!=(3,12):
        raise ValueError('Requires root-owned Windows CPython3.12 child')
    if sha(Path(sys.executable))!=PY_SHA or sha(Path(__file__))!=a.expected_probe_sha256:
        raise ValueError('Frozen interpreter/probe changed')
    report=a.report.absolute()
    if not report.is_relative_to(ROOT/'server/.local/optimization9h-20261004') or report.exists():
        raise ValueError('Fresh task-local report required')
    bank=a.write_synthetic_bank.absolute() if a.write_synthetic_bank else None
    if bank is not None and (not bank.is_relative_to(report.parent) or bank.exists()):
        raise ValueError('Synthetic bank must be fresh in the owned report directory')
    review=json.loads((PAYLOAD.parent.parent/'static-review.json').read_text())
    if not review['passed'] or review['executed']:
        raise ValueError('Verified static acquisition receipt required')
    expected={Path(r['name']).name:r['sha256'] for r in review['extracted']}
    for name in ('_DynamicDispatch.cp312-win_amd64.pyd','dyn_bins.dll','dyn_bins.zip'):
        if sha(PAYLOAD/name)!=expected[name]:raise ValueError('Frozen native payload changed')
    if sha(XRT/'xrt_coreutil.dll')!=XRT_SHA:raise ValueError('Installed XRT dependency changed')
    result=dict(passed=False,scope='official offline packing of synthetic single-expert FC1/FC2 at actual geometry',
                native_packer_sha256=expected[NATIVE.name],xrt_coreutil_sha256=XRT_SHA,
                source_sha256=a.expected_probe_sha256,provider_inference=False,full_mtp=False,
                acceptance_qualified=False,speed_gain=False,rows=[],stage='native_import')
    handles=[]
    packed_parts=[]
    try:
        import numpy as np
        for directory in (PAYLOAD,XRT):handles.append(os.add_dll_directory(str(directory)))
        # Import the actual extension without unrelated ONNX graph helper imports.
        package=types.ModuleType('ryzenai_dynamic_dispatch')
        package.__path__=[str(PAYLOAD)]
        sys.modules[package.__name__]=package
        spec=importlib.util.spec_from_file_location(package.__name__+'._DynamicDispatch',NATIVE)
        native=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=native
        spec.loader.exec_module(native)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype=ctypes.c_void_p
        kernel.GetModuleFileNameW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint]
        kernel.GetModuleFileNameW.restype=ctypes.c_uint
        loaded=ctypes.create_unicode_buffer(32768)
        handle=kernel.GetModuleHandleW('xrt_coreutil.dll')
        if not handle or not kernel.GetModuleFileNameW(handle,loaded,len(loaded)):
            raise RuntimeError('Loaded XRT path unavailable')
        if Path(loaded.value).resolve()!=(XRT/'xrt_coreutil.dll').resolve():
            raise RuntimeError('Loaded XRT dependency is not the reviewed DriverStore file')
        result['loaded_xrt_coreutil']=loaded.value
        attr_type=native.Attributes
        pack=native.matmulnbits.matmulnbits_pack_const_float32
        result['stage']='packing'
        for label,k,n,expected_kn in (('FC1',2560,1280,[2560,2560]),('FC2',640,2560,[768,3072])):
            weights=np.full((n,k//2),0x88,dtype=np.uint8)
            scales=np.ones((n,k//32),dtype=np.float32)
            zeros=np.full((n,(k//32+1)//2),0x88,dtype=np.uint8)
            bias=np.zeros(n,dtype=np.float32)
            attr=attr_type()
            for key,value in {'K':k,'N':n,'lora':False,'mladf_version':'v2',
                              'asymmetric_quant':True,'bias_en':False,'block_size':32}.items():
                attr.set(key,value)
            began=time.perf_counter()
            data,size,padded_k,padded_n=pack(weights,bias,scales,zeros,attr)
            elapsed=(time.perf_counter()-began)*1000
            if not isinstance(data,np.ndarray) or data.dtype!=np.uint8 or data.ndim!=1 or data.nbytes!=size:
                raise RuntimeError('Official packer return dtype/length mismatch')
            if not 0<size<=64<<20 or [padded_k,padded_n]!=expected_kn:
                raise RuntimeError('Packing geometry or bounded byte limit mismatch')
            result['rows'].append(dict(label=label,logical_kn=[k,n],padded_kn=[padded_k,padded_n],bytes=size,
                pack_host_ms=elapsed,packed_sha256=hashlib.sha256(memoryview(data)).hexdigest(),
                synthetic_weights=True,no_npu_inference=True))
            if bank is not None:packed_parts.append(data)
            del data,weights,scales,zeros,bias,attr
        if bank is not None:
            # Same zero expert repeated in index order; admission only. Never
            # materialize the complete resident bank as a Python/NumPy array.
            stride=(sum(part.nbytes for part in packed_parts)+65535)//65536*65536
            padding=bytes(stride-sum(part.nbytes for part in packed_parts))
            digest=hashlib.sha256()
            with bank.open('xb') as stream:
                for expert in range(512):
                    for part in packed_parts:
                        block=memoryview(part)
                        stream.write(block);digest.update(block)
                    stream.write(padding);digest.update(padding)
                    if (expert+1)%64==0:print('BANK_WRITTEN_EXPERTS '+str(expert+1),flush=True)
                stream.flush();os.fsync(stream.fileno())
            if bank.stat().st_size!=stride*512:raise RuntimeError('Synthetic bank write extent differs')
            result['bank']=dict(path=str(bank),num_experts=512,expert_stride=stride,
                fc1_bytes=packed_parts[0].nbytes,fc2_raw_bytes=packed_parts[1].nbytes,
                fc2_tail_padding=len(padding),fc2_padded_bytes=packed_parts[1].nbytes+len(padding),
                bytes=stride*512,sha256=digest.hexdigest(),synthetic=True,
                scope='zero experts for provider admission only; no quality or throughput result')
        result['stage']='complete';result['passed']=True
    except BaseException as exc:
        result['error']=type(exc).__name__+': '+str(exc)
    finally:
        for handle in reversed(handles):handle.close()
        with report.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
