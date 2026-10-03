"""CPU-only placement checks: sparse read-only mapping, no HIP/GPU workload."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
import ctypes,json,os,sys,tempfile
from pathlib import Path
library,case=sys.argv[1:]
os.environ.update(HALOGEN_PREFLIGHT_PROFILE='flash0162-v2-device64-chunk64-v1',
 HALOGEN_HYBRID_PROFILE='vgm64-v2-device64-v1',HALOGEN_HYBRID_COPY_BYTES='68719476736',
 HALOGEN_HYBRID_RECLAIM_COPY='1')
if case=='wrong_profile': os.environ['HALOGEN_PREFLIGHT_PROFILE']='flash0162-copy48-v1'
GIB=1024**3; SIZE=66687678432
class Range(ctypes.Structure):
 _fields_=[('begin',ctypes.c_uint64),('end',ctypes.c_uint64)]
libc=ctypes.CDLL(None,use_errno=True)
libc.mmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_long]
libc.mmap.restype=ctypes.c_void_p
libc.munmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
lib=ctypes.CDLL(library)
plan=lib.halogen_hybrid_preflight_v1
plan.argtypes=[ctypes.c_size_t,ctypes.c_size_t,ctypes.POINTER(Range),ctypes.c_size_t,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
plan.restype=ctypes.c_int
with tempfile.TemporaryDirectory(prefix='halogen-v2-planner-') as td:
 path=Path(td)/'fixture.hgn'
 with path.open('xb') as f: f.truncate(SIZE)
 assert path.stat().st_blocks==0, 'Fixture must have no allocated data blocks'
 fd=os.open(path,os.O_RDONLY)
 base=libc.mmap(None,SIZE,1,2,fd,0)
 assert base not in (None,ctypes.c_void_p(-1).value)
 try:
  rows=(Range*2)(Range(319488,SIZE),Range(0,0))
  size=SIZE; count=1; aggregate=SIZE-319488; host=ctypes.c_size_t()
  if case=='wrong_size': size-=1
  elif case=='empty': count=0
  elif case=='too_many': count=4097
  elif case=='unordered': rows[1]=Range(0,GIB); count=2
  elif case=='outside': rows[0].end=SIZE+1
  elif case=='wrong_sum': aggregate-=4096
  elif case=='host_overflow': rows=(Range*1)(Range(0,61*GIB)); count=1
  code=plan(base,size,rows,count,aggregate,ctypes.byref(host))
  if case in ('good','second_phase'):
   assert code==0 and host.value==0,(code,host.value)
   if case=='second_phase': assert plan(base,size,rows,count,aggregate,ctypes.byref(host))!=0
  else: assert code!=0, case
  print(json.dumps({'case':case,'status':'passed','host_bytes':host.value}))
 finally:
  assert libc.munmap(base,SIZE)==0
  os.close(fd)
'''

@unittest.skipUnless(os.name=='posix','Native Linux CPU placement fixture')
class V2PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='v2-planner-build-')
        cls.library=Path(cls.tmp.name)/'planner.so'
        subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-DHALOGEN_RESEARCH_VGM64=1','-DHALOGEN_PREFLIGHT_V1=1','-DHALOGEN_CHECKPOINT_V2=1',
            str(ROOT/'patches/hip-register-hybrid.c'),'-ldl','-pthread','-o',str(cls.library)],check=True)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def check_case(self,case):
        result=subprocess.run([sys.executable,'-c',HARNESS,str(self.library),case],
            capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_real_contiguous_v2_range_fully_device_planned(self): self.check_case('good')
    def test_second_phase_cannot_skip_completion(self): self.check_case('second_phase')
    def test_invalid_shapes_and_host_overflow_are_refused(self):
        for case in ['wrong_profile','wrong_size','empty','too_many','unordered','outside','wrong_sum','host_overflow']:
            with self.subTest(case=case): self.check_case(case)

if __name__=='__main__': unittest.main()
