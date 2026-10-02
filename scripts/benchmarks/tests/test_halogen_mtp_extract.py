import pathlib,struct,subprocess,sys,tempfile,unittest
HDR,ENT=0x68,0xA0
class TestExtract(unittest.TestCase):
 def test_extracts_only_mtp_and_preserves_metadata(self):
  with tempfile.TemporaryDirectory() as td:
   td=pathlib.Path(td); src=td/'src.hgn'; out=td/'out.hgn'; names=[f'mtp.t{i}' for i in range(31)]+['model.other']
   doff=((HDR+ENT*len(names)+63)//64)*64; payloads=[]; cursor=doff; entries=[]
   for i,n in enumerate(names):
    data=bytes([i])*64; b=bytearray(ENT); b[:len(n)]=n.encode(); struct.pack_into('<II',b,0x60,0,1); struct.pack_into('<4q',b,0x68,32,0,0,0); struct.pack_into('<QQII',b,0x88,cursor,len(data),i,0); entries.append(bytes(b));payloads.append((cursor,data));cursor+=64
   with src.open('wb') as f:
    f.write(struct.pack('<IIQQQQ',0x314E4748,2,len(names),HDR,doff,cursor)+b'x'+b'\0'*63);f.write(b''.join(entries));f.seek(doff)
    for off,data in payloads:f.seek(off);f.write(data)
   script=pathlib.Path(__file__).parents[1]/'halogen_mtp_extract.py'; subprocess.run([sys.executable,str(script),str(src),str(out)],check=True,capture_output=True,text=True)
   with out.open('rb') as f:
    h=f.read(HDR);magic,ver,n,toff,doff2,size=struct.unpack('<IIQQQQ',h[:0x28]);self.assertEqual((magic,ver,n),(0x314E4748,2,31));self.assertEqual(size,out.stat().st_size);f.seek(toff); got=[]
    for _ in range(n): got.append(f.read(ENT)[:96].split(b'\0')[0].decode())
   self.assertEqual(got,[f'mtp.t{i}' for i in range(31)])
if __name__=='__main__':unittest.main()
