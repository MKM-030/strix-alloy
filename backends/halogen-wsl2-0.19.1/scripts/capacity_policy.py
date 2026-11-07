"""Bounded opt-in two-request capacity. Pure validation; no device or lifecycle I/O."""


def resolve(context, checkpoint='v2', *, slots=1, kv_pool_positions=None,
            disable_vision=False):
    if type(context) is not int or not 4096 <= context <= 262144:
        raise ValueError('Context must be an integer from 4096 to 262144')
    if checkpoint not in ('v2', 'w4b'):
        raise ValueError('Unknown checkpoint')
    if type(disable_vision) is not bool:
        raise ValueError('disable_vision must be a boolean')
    if type(slots) is not int or slots not in (1, 2):
        raise ValueError('Slots must be integer 1 or opt-in 2')
    if kv_pool_positions is not None and (
            type(kv_pool_positions) is not int or kv_pool_positions not in (32768, 65536)):
        raise ValueError('Explicit KV pool must be integer 32768 or 65536')
    opt_in = slots != 1 or kv_pool_positions is not None
    if opt_in:
        if context != 32768 or checkpoint != 'v2' or disable_vision is not True:
            raise ValueError('Capacity opt-in requires v2, 32768 context and text-only serving')
    pool = context if kv_pool_positions is None else kv_pool_positions
    if opt_in and (pool < context or pool % 256):
        raise ValueError('KV pool must cover context and be 256-aligned')
    return dict(context=context, slots=slots, kv_pool_positions=pool)


def validate_manifest(manifest):
    env = manifest.get('environment')
    if type(env) is not dict:
        raise ValueError('Capacity manifest requires an environment object')
    slots = manifest.get('slots')
    explicit = slots != 1 or 'kv_pool_positions' in manifest
    pool = manifest.get('kv_pool_positions')
    if explicit and (type(pool) is not int or pool not in (32768, 65536)):
        raise ValueError('Opt-in manifest must declare its exact KV pool as integer 32768 or 65536')
    resolved = resolve(manifest.get('context'), manifest.get('checkpoint', 'v2'),
        slots=slots, kv_pool_positions=pool,
        disable_vision=env.get('HALOGEN_VISION_TOWER') in (None, '', '0'))
    if explicit and env.get('HALOGEN_PROMPT_CACHE') != '0':
        raise ValueError('Capacity opt-in requires CacheOff (HALOGEN_PROMPT_CACHE=0)')
    for key, value in (('HALOGEN_CTX', resolved['context']),
                       ('HALOGEN_KV_SLOTS', resolved['slots']),
                       ('HALOGEN_KV_POOL_POSITIONS', resolved['kv_pool_positions'])):
        if env.get(key) != str(value):
            raise ValueError('Capacity manifest/environment mismatch: ' + key)
    return resolved
