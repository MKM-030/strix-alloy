"""Explicit numeric controls for experiments with the pinned 0.16.2 engine.

These internal controls are not upstream support or numerical-quality claims.
Counter ceilings below bound this experiment interface; they are not advertised
upstream ranges. No path, driver, NPU or host-admission override is accepted.
"""
import json

SWITCHES=frozenset('HALOGEN_'+name for name in (
    'DN_SCAN','DN_FUSED','DN_FUSED_NORM','DN_FUSED_PAIR','DN_NORM_FOLD',
    'DN_PREP_W','DN_UT5','DN_XH','ATTN_QS','CACHE_FULL','CACHE_INPLACE'))
COUNTER_MAX={
    'HALOGEN_ATTN_FA':32768,
    'HALOGEN_FLASH_MOE_GEMM':32768,
    'HALOGEN_FLASH_MOE_FUSED_N':32768,
    'HALOGEN_CACHE_BRANCHES':8,
    'HALOGEN_CACHE_ENTRIES':32,
    'HALOGEN_CACHE_CKPT':1,
    'HALOGEN_CACHE_RESERVE_MB':4096,
}
MODES={
    'HALOGEN_FA_OPT':frozenset(range(8)),  # low-three-bit optimization mask
    # Mode zero does not disable every dispatch using the V2 getter.
    'HALOGEN_FLASH_MOE_V2':frozenset((0,1,2)),
}


def validate(controls):
    if type(controls) is not dict:
        raise ValueError('Kernel controls must be a JSON object')
    result={}
    for key,value in controls.items():
        if key not in SWITCHES and key not in COUNTER_MAX and key not in MODES:
            raise ValueError('Unsupported kernel control: '+str(key))
        if type(value) is not int:
            raise ValueError('Kernel control values must be explicit integers: '+key)
        if key in SWITCHES and value not in (0,1):
            raise ValueError('Kernel switch must be 0 or 1: '+key)
        if key in COUNTER_MAX and not 0<=value<=COUNTER_MAX[key]:
            raise ValueError('Kernel counter is outside the experiment budget: '+key)
        if key in MODES and value not in MODES[key]:
            raise ValueError('Unsupported kernel mode: '+key)
        result[key]=value
    return result


def parse(text):
    if not isinstance(text,str) or len(text)>8192:
        raise ValueError('Kernel controls JSON exceeds the 8192-character budget')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('Duplicate kernel control: '+key)
            result[key]=value
        return result
    return validate(json.loads(text,object_pairs_hook=unique))


def environment(controls):
    return {key:str(value) for key,value in validate(controls).items()}
