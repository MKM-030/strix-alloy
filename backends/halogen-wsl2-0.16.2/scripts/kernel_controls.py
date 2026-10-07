"""Explicit numeric controls for experiments with the pinned 0.16.2 engine.

These internal controls are not upstream support or numerical-quality claims.
Counter ceilings below bound this experiment interface; they are not advertised
upstream ranges. No path, driver, NPU or host-admission override is accepted.
The documented lookup-I/O thread policy is limited here to the matched 32/64
probe; an omitted control retains the image's default.
Gram mode requires explicit standalone normalization and compatible pinned
branch defaults; admitting the experiment does not qualify its numerics.
"""
import json

SWITCHES=frozenset('HALOGEN_'+name for name in (
    'DN_SCAN','DN_FUSED','DN_FUSED_NORM','DN_FUSED_GRAM','DN_FUSED_PAIR','DN_NORM_FOLD',
    'DN_PREP_W','DN_UT5','DN_XH','ATTN_QS','CACHE_FULL','CACHE_INPLACE',
    'FLASH_NGRAM_RANDOM'))
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
    'HALOGEN_NGRAM_GATHER_THREADS':frozenset((32,64)),
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
    if result.get('HALOGEN_DN_FUSED_GRAM',0)==1:
        # Raw Gram with native fused-norm default 1 omits normalization.
        # Explicit norm 0 retains the native standalone gated RMS norm.
        if result.get('HALOGEN_DN_FUSED_NORM')!=0:
            raise ValueError('Gram requires explicit HALOGEN_DN_FUSED_NORM=0')
        # Absent keys resolve to these exact 0.16.2 branch defaults without
        # emitting additional environment overrides.
        for key,required in (('HALOGEN_DN_FUSED',1),('HALOGEN_DN_SCAN',0),
                             ('HALOGEN_DN_FUSED_PAIR',0),('HALOGEN_DN_NORM_FOLD',0)):
            if result.get(key,required)!=required:
                raise ValueError('Gram requires resolved '+key+'='+str(required))
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
