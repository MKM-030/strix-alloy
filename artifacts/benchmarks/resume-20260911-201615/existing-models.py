import pathlib,subprocess,sys,time
r=pathlib.Path(sys.argv[1]);root=pathlib.Path(sys.argv[2])
while not (r/'rocmfp4-mtp2-correctness/stopped.json').exists():time.sleep(2)
for name,spec,tag in [('ice-old',2,'ice-old-mtp2-screen'),('rocmfp4',0,'rocmfp4-no-spec-screen')]:
 cmd=[sys.executable,str(root/'scripts/ornith-eval/eval_native.py'),'--name',name,'--spec',str(spec),'--stage','screen','--tag',tag]
 with (r/(tag+'.log')).open('w') as f:z=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 print(tag,z.returncode,flush=True)
