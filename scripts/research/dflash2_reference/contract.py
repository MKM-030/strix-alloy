"""Immutable real-model geometry; standard library only, no inference imports."""
import hashlib
import json
from pathlib import Path

MODEL_ID = 'incoai/Qwen3.8-Flash-Next-DFlash2'
MODEL_REVISION = 'a22a1744e85c17364dcc54a6a420af7135d4c7f6'
PAYLOAD_SHA256 = 'd6723f2a359eaf33ec0c95f22ae8edda896774020c552296a85e1913b4d3186f'
PAYLOAD_BYTES = 1206140008
WIDTH, GROUP_WIDTH, GROUPS, TAPS = 2560, 16, 160, 2
SELECTOR_RANK, TOP_K = 256, 16
COMPLETED_TARGET_LAYERS = (5, 15, 25, 35, 45)
SOURCES = Path(__file__).with_name('sources')

def verify_saved_contract():
    """Explicit source/header validation only; never opens model tensor data."""
    if __package__:
        from .source_oracle import SOURCE, SOURCE_SHA256
    else:
        from source_oracle import SOURCE, SOURCE_SHA256
    pins = {SOURCE.name: SOURCE_SHA256,
            'config.json': '2409575986f9ea24d455343eb469c0e6940def5edab1d1be503bb8eb4cc3b1b9',
            'safetensors-header.json': '5ef4772f77b6a3ea349c6515aceffdb999868946aafb04578416494c64ef0513'}
    for name,expected in pins.items():
        if hashlib.sha256((SOURCES/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Pinned source/header differs: '+name)
    config = json.loads((SOURCES / 'config.json').read_bytes())
    header = json.loads((SOURCES / 'safetensors-header.json').read_bytes())
    expected = {'block_size': 8, 'conv_group_size': GROUP_WIDTH,
                'conv_kernel_size': TAPS, 'mask_token_id': 248077,
                'selector_rank': SELECTOR_RANK, 'selector_top_k': TOP_K,
                'target_layer_ids': list(COMPLETED_TARGET_LAYERS)}
    if (config['dflash_config'] != expected or config['hidden_size'] != WIDTH or
            config['architectures'] != ['DFlash2DraftModel']):
        raise ValueError('Actual model configuration differs')
    tensors = {k:v for k,v in header.items() if k != '__metadata__'}
    shapes = {
        'candidate_selector.hidden_projection.weight': [256, 2560],
        'candidate_selector.predecessor_codebook': [248320, 256],
        'candidate_selector.successor_codebook': [248320, 256],
        'fc.weight': [2560,12800], 'hidden_norm.weight': [2560], 'norm.weight': [2560]}
    for layer in range(5):
        prefix = f'layers.{layer}.'
        for conv in ('attention_conv','mlp_conv'):
            shapes[prefix+conv+'.base_kernel'] = [2,2,2560]
            shapes[prefix+conv+'.kernel_projection.weight'] = [640,2560]
        for norm in ('input_layernorm','post_attention_layernorm'):
            shapes[prefix+norm+'.weight'] = [2560]
        for name,shape in {'mlp.down_proj':[2560,7680], 'mlp.gate_proj':[7680,2560],
                           'mlp.up_proj':[7680,2560], 'self_attn.k_norm':[128],
                           'self_attn.q_norm':[128], 'self_attn.k_proj':[1024,2560],
                           'self_attn.v_proj':[1024,2560], 'self_attn.q_proj':[4096,2560],
                           'self_attn.o_proj':[2560,4096]}.items():
            shapes[prefix+name+'.weight'] = shape
    if set(shapes) != set(tensors) or len(tensors) != 81:
        raise ValueError('Exact81 tensor names required')
    end = parameters = 0
    for name,entry in sorted(tensors.items(), key=lambda kv:kv[1]['data_offsets'][0]):
        if entry['dtype'] != 'BF16' or entry['shape'] != shapes[name]:
            raise ValueError('Tensor shape/dtype differs: '+name)
        words = 1
        for dimension in entry['shape']:words *= dimension
        start,stop = entry['data_offsets']
        if start != end or stop-start != 2*words:raise ValueError('Tensor coverage differs')
        end = stop; parameters += words
    if parameters != 603065600 or end != 1206131200:
        raise ValueError('Parameter extent differs')
    return dict(model_id=MODEL_ID, revision=MODEL_REVISION, tensors=81,
                parameters=parameters, model_payload_opened=False)
