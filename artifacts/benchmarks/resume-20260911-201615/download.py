import json,subprocess,pathlib,hashlib,time,shutil,sys
p=pathlib.Path(sys.argv[1]); rows=json.loads(p.read_text()); root=p.parent
for r in rows:
 dest=pathlib.Path(r['directory']); dest.mkdir(parents=True,exist_ok=True)
 if shutil.disk_usage(dest).free<r['bytes']+30*1024**3: raise RuntimeError('Insufficient disk headroom')
 files=[r['file'],'README.md'] + (['config.json','manifest.json','LICENSE'] if r['id']=='ornith-dflash2' else [])
 cmd=['hf','download',r['repo'],*files,'--revision',r['revision'],'--local-dir',str(dest)]
 r.update(status='DOWNLOADING',command=cmd,started=time.time()); p.write_text(json.dumps(rows,indent=2))
 with (root/(r['id']+'-download.log')).open('w',encoding='utf-8') as log: result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 r['exit_code']=result.returncode
 if result.returncode==0:
  path=dest/r['file']; h=hashlib.sha256()
  with path.open('rb') as f:
   for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
  r.update(actual_sha256=h.hexdigest(),actual_bytes=path.stat().st_size,status='VERIFIED' if h.hexdigest()==r['sha256'] and path.stat().st_size==r['bytes'] else 'CHECKSUM_FAILED')
 else: r['status']='DOWNLOAD_FAILED'
 r['finished']=time.time();p.write_text(json.dumps(rows,indent=2));print(r['id'],r['status'],flush=True)
