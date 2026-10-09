"""Prepare a bounded, default-off normal-runtime SDMA comparison; no hardware."""
import ast
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
TEMPLATE = PREP / 'bulk-bn64-engine-comparison-v2-resident-fix'

def replace_once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)

def main():
    assert not (WORK/'seal.json').exists(), 'Preparation already sealed'
    control=(TEMPLATE/'control.py').read_text(encoding='utf-8-sig')
    control=replace_once(control, '"""Observe owned normal/candidate handles and perform regular lifecycle stops."""', '"""Owned SDMA windows with the unchanged regular lifecycle."""')
    old="""    if window=='candidate':
        assert manifest['bulk_bn64_candidate']['enabled'] is True
        assert manifest['environment']['ALLOY_BULK_BN64_ENABLE']=='1'
    else:
        assert 'bulk_bn64_candidate' not in manifest
        assert not any(k.startswith('ALLOY_BULK_BN64') for k in manifest['environment'])"""
    new="""    assert 'bulk_bn64_candidate' not in manifest
    assert not any(k.startswith('ALLOY_BULK_BN64') for k in manifest['environment'])
    assert manifest['environment']['HSA_ENABLE_SDMA']==('0' if window=='candidate' else '1')
    assert bool(manifest.get('sdma0_candidate'))==(window=='candidate')"""
    control=replace_once(control,old,new)
    control=control.replace("active0173_bn64_comparison", "active0173_sdma0_comparison")
    # No BN64 audit action is exposed; preserve normal checkpoint/stop/start only.
    start=control.index('def audit(name):')
    end=control.index('def observe(',start)
    control=control[:start]+control[end:]
    control=control.replace("'launch_after','audit','observe'", "'launch_after','observe'")
    control=control.replace("    elif a.action=='audit': audit(a.window)\n", '')
    window=(TEMPLATE/'window.py').read_text(encoding='utf-8-sig')
    window=replace_once(window, '"""Frozen 0.17.3 bulk-BN64 window:', '"""Frozen 0.17.3 normal SDMA window:')
    old="""    if window=='candidate':
        assert manifest['bulk_bn64_candidate']['enabled'] is True and env['ALLOY_BULK_BN64_ENABLE']=='1'
    else:
        assert 'bulk_bn64_candidate' not in manifest and '_hg_flash_serve' not in env
        assert not any(key.startswith('ALLOY_BULK_BN64_') for key in env),'Stock window inherited BN64 environment'"""
    new="""    assert 'bulk_bn64_candidate' not in manifest and '_hg_flash_serve' not in env
    assert not any(key.startswith('ALLOY_BULK_BN64_') for key in env)
    assert env['HSA_ENABLE_SDMA']==('0' if window=='candidate' else '1')
    assert bool(manifest.get('sdma0_candidate'))==(window=='candidate')"""
    window=replace_once(window,old,new)
    for name,text in [('control.py',control),('window.py',window)]:
        ast.parse(text)
        (WORK/name).write_text(text,encoding='utf-8')
    inputs=[]
    for path in [WORK/'launch.py',WORK/'control.py',WORK/'window.py',WORK/'plan.md',
                 PREP/'halogen0173-migration-20261009/thinking-latest-profile.json',
                 ROOT/'backends/halogen-wsl2-0.17.3/scripts/service.py',
                 ROOT/'backends/halogen-wsl2-0.17.3/scripts/runner.py',
                 ROOT/'server/controller.py']:
        ast.parse(path.read_text(encoding='utf-8-sig')) if path.suffix=='.py' else None
        inputs.append(dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (WORK/'seal.json').write_text(json.dumps(dict(inputs=inputs,hardware_executed=False),indent=2),encoding='utf-8')
    print(json.dumps(dict(prepared=True,hardware_executed=False,inputs=len(inputs))))

if __name__=='__main__': main()
