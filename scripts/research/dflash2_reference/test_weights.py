import copy,hashlib,inspect,io,json,os,struct,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
if __package__:
 from . import weights as w
else:import weights as w
class Contract(unittest.TestCase):
 def test_passive_namespace_import(self):
  p=subprocess.run([sys.executable,'-B','-c',"import sys;from scripts.research.dflash2_reference import weights,reference;assert 'torch' not in sys.modules"],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
 def test_actual_header_and_negative_contracts(self):
  h=w.expected_header();self.assertEqual(len(h),81)
  self.assertEqual(w.validate_header(h,total_bytes=1206140008,header_bytes=8800),1206131200)
  for mutate in ('missing','extra','dtype','shape','offset','metadata'):
   bad=copy.deepcopy(h);key=next(iter(bad))
   if mutate=='missing':del bad[key]
   elif mutate=='extra':bad['foreign']=bad[key]
   elif mutate=='metadata':bad['__metadata__']={'format':'foreign'}
   elif mutate=='dtype':bad[key]['dtype']='F16'
   elif mutate=='shape':bad[key]['shape']=[1]
   else:bad[key]['data_offsets'][1]-=2
   with self.subTest(mutate=mutate),self.assertRaises(ValueError):w.validate_header(bad,total_bytes=1206140008,header_bytes=8800)
  for total,hlen in ((1206140007,8800),(1206140009,8800),(1206140008,8799)):
   with self.assertRaises(ValueError):w.validate_header(h,total_bytes=total,header_bytes=hlen)
 def test_public_loader_rejects_short_and_bad_actual_header_without_torch(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.safetensors';p.write_bytes(struct.pack('<Q',2)+b'{}')
   with self.assertRaises(ValueError):w.load(p)
 def test_strict_json_and_public_fixed_identity_api(self):
  self.assertEqual(list(inspect.signature(w.load).parameters),['path'])
  with self.assertRaises(TypeError):w.LoadedWeights()
  with self.assertRaises(ValueError):w._json(b'{"x":{},"x":{}}')
  h=w.expected_header();key=next(iter(h));h[key]['data_offsets'][0]=False
  with self.assertRaises(ValueError):w.validate_header(h,total_bytes=1206140008,header_bytes=8800)
 @unittest.skipUnless(os.name=='nt','Windows share-mode qualification')
 def test_windows_read_handle_rejects_writer_and_delete(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'owned.bin';p.write_bytes(b'fixture')
   with w._open(p) as stream:
    self.assertEqual(stream.read(),b'fixture')
    with self.assertRaises(PermissionError):p.open('r+b')
    with self.assertRaises(PermissionError):p.unlink()
   p.unlink()

class OwnedCPU(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import torch
  cls.t=torch;torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.set_grad_enabled(False)
 def test_generic_reader_fixture_owned_bits_and_sha_fail_closed(self):
  header={'x':{'dtype':'BF16','shape':[2],'data_offsets':[0,4]}}
  raw=json.dumps(header,separators=(',',':')).encode();data=struct.pack('<Q',len(raw))+raw+bytes.fromhex('803f0040')
  class BoundStream(io.BytesIO):
   sizes=[]
   def readinto(self,buffer):
    self.sizes.append(len(buffer));return super().readinto(buffer)
  stream=BoundStream(data);stream.seek(8+len(raw))
  with patch.object(w,'CHUNK_BYTES',2):owned=w._read_owned(stream,header,len(raw),len(data),hashlib.sha256(data).hexdigest())
  self.assertEqual(stream.sizes,[2,2])
  self.assertEqual(owned['x'].tolist(),[1,2]);self.assertEqual(owned['x'].device.type,'cpu')
  stream.seek(8+len(raw))
  with self.assertRaises(ValueError):w._read_owned(stream,header,len(raw),len(data),'0'*64)
  stream.close();self.assertEqual(owned['x'].tolist(),[1,2])
if __name__=='__main__':
 if '--run-cpu' in sys.argv:sys.argv.remove('--run-cpu');unittest.main(verbosity=2)
 else:print('Passive default; --run-cpu explicitly runs synthetic CPU tests.')
