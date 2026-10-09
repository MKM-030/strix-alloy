"""Root-owned Linux invocation of the sealed real-FL component DSO."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
from capture_format import inspect
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seal',type=Path,required=True)
    ap.add_argument('--library',type=Path,required=True);ap.add_argument('--native',type=Path,required=True)
    ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--capture',type=Path,required=True)
    ap.add_argument('--check-only',action='store_true');a=ap.parse_args()
    seal=json.loads(a.seal.read_text(encoding='utf-8'))
    for role,path in [('replay',a.library),('native',a.native),('candidate',a.candidate)]:
        if digest(path)!=seal['artifacts'][role]['sha256']:raise ValueError('Sealed '+role+' identity changed')
    operation=inspect(a.capture)
    print(json.dumps(dict(type='actual_operation',capture_sha256=operation['sha256'],bytes=operation['bytes'],
                         tokens=operation['tokens'],selected_experts=operation['selected_experts'],
                         check_only=a.check_only)),flush=True)
    if a.check_only:return 0
    if sys.platform!='linux':raise ValueError('Hardware component is root-owned Linux only')
    library=ctypes.CDLL(str(a.library.resolve()),mode=os.RTLD_NOW|os.RTLD_LOCAL)
    entry=library.main;entry.argtypes=[ctypes.c_int,ctypes.POINTER(ctypes.c_char_p)];entry.restype=ctypes.c_int
    values=[b'owned-real-fl-component',os.fsencode(a.native),os.fsencode(a.candidate),os.fsencode(a.capture)]
    argv=(ctypes.c_char_p*len(values))(*values)
    return entry(len(values),argv)
if __name__=='__main__':raise SystemExit(main())
