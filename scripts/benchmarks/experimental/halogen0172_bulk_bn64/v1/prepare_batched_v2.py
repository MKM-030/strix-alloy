"""Prepare one longer-window pair to resolve v1's observed short-window drift."""
import hashlib
from pathlib import Path
SOURCE=Path(__file__).resolve().parent
TARGET=SOURCE.with_name('moe-bulk-bn64-component-v2-batched')
assert not TARGET.exists()
host=(SOURCE/'host.c').read_bytes()
assert hashlib.sha256(host).hexdigest()=='9f3c103dcac668b8da87ad868b9803c7286bb25fd5211e50f2dfac4e973e56ae'
text=host.decode()
old='GUARD=4096, CHUNK=4*1024*1024, DEFAULT_REPS=3, MAX_REPS=7'
new='GUARD=4096, CHUNK=4*1024*1024, BATCH=4, DEFAULT_REPS=3, MAX_REPS=7'
assert text.count(old)==1;text=text.replace(old,new)
old='''    if(!launch(functions[3*v],1,512,&ia,sizeof(ia)) ||
       !launch(functions[3*v+1],5*capacity,256,&gu,sizeof(gu)) ||
       !launch(functions[3*v+2],10*capacity,256,&dn,sizeof(dn)) ||
       !launch(functions[6],(20*N+7)/8,256,&fold,sizeof(fold)))return 0;
    return ok(EventRecord(end,NULL),"operation end") && ok(EventSync(end),"operation wait") &&
        ok(EventElapsed(ms,begin,end),"full-operation GPU event elapsed");'''
new='''    for(int batch=0;batch<BATCH;batch++) {
        if(!launch(functions[3*v],1,512,&ia,sizeof(ia)) ||
           !launch(functions[3*v+1],5*capacity,256,&gu,sizeof(gu)) ||
           !launch(functions[3*v+2],10*capacity,256,&dn,sizeof(dn)) ||
           !launch(functions[6],(20*N+7)/8,256,&fold,sizeof(fold)))return 0;
    }
    if(!ok(EventRecord(end,NULL),"operation end") || !ok(EventSync(end),"operation wait") ||
       !ok(EventElapsed(ms,begin,end),"full-operation GPU event elapsed"))return 0;
    *ms/=BATCH;
    return 1;'''
assert text.count(old)==1;text=text.replace(old,new)
old='"reps\\\":%d,\\\"kernarg_bytes'
# Record BATCH in the preflight without changing printf argument arity.
needle='\\\"exact_bit_contract\\\":true}'
assert text.count(needle)==1;text=text.replace(needle,'\\\"operations_per_arm\\\":4,'+needle)
coordinator=(SOURCE/'run.py').read_text()
for old,new in [('bulk-bn64-v1','bulk-bn64-v2-batched'),
                ('active0172_bulk_bn64_component','active0172_bulk_bn64_component_batched'),
                ('halogen0172.bulk-bn64-synthetic.v1','halogen0172.bulk-bn64-synthetic.v2-batched')]:
    assert coordinator.count(old)==1;coordinator=coordinator.replace(old,new)
TARGET.mkdir()
(TARGET/'host.c').write_text(text,encoding='utf-8',newline='\n')
(TARGET/'run.py').write_text(coordinator,encoding='utf-8',newline='\n')
review=(SOURCE/'fixture-abi-review.md').read_text()
(TARGET/'fixture-abi-review.md').write_text('# Batched v2 timing supplement\n\n'
    'Same pinned native ABI, inputs, two routes and complete word comparisons as v1. '
    'Only the event window changes: four consecutive items+GU+DN+fold operations per arm, '
    'elapsed divided by four. Initialization and comparison remain equally outside both arms. '
    'This addresses the actual broad timing drift observed in v1. '
    'It is not an engine or NPU measurement. The v1 comparison remains retained.\n\n'
    +review,encoding='utf-8',newline='\n')
print(TARGET)
