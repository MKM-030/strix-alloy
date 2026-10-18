"""PP-only calibration copied from the frozen benchmark recipe.

Provenance: scripts/gufo_control/benchmark_recipes.py; the filler itself traces
to Halogen commit c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf,
tools/halogen-bench.py (SHA256 0587690C50CFA6769B54D67C7553BA8AA3EC861E677082590D322B0B2F0F846F).
"""
FILLER = 'The unified memory architecture changes how inference engines schedule work across the accelerator and the host processor. '


def calibrated_prompt(target: int, first_tokens: int, second_tokens: int) -> str:
    if (any(type(x) is not int or x < 0 for x in (target,first_tokens,second_tokens))
            or not 1 <= target <= 16383 or second_tokens <= first_tokens):
        raise ValueError('invalid_calibration_counts')
    units = max(1,round(max(0,target-first_tokens)/((second_tokens-first_tokens)/20)))
    if 1 + len(FILLER.encode('utf-8'))*units > 260000:
        raise ValueError('calibration_body_limit')
    return 'x'+FILLER*units
