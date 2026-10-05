"""CPU-only diagnostic for the original count1 embedding RMS reduction tree.

Pure stdlib, supplied BF16 words only: no files, model, NumPy/provider or device.
Python >=3.13 math.fma is required. Fixed width2560/block256; each lane sums ten
stride256 squares, then the original LDS halving tree128..1. Every arithmetic
boundary is FP32, followed by the original epsilon/product order/BF16 RNE.

The CPU inverse is one FP32 rounding of 1/sqrt(mean+epsilon). The retained
gfx1151 shader uses v_rsq_f32; its bit semantics are NOT established by this
CPU formula. Root must compare all requested outputs independently. No token,
column, observed output, calibration, tolerance or fitted value is accepted.
This diagnostic does not modify or admit the sealed early producer.

The supported input domain requires each nonzero BF16 square to be normal and
exact in FP32, as expected for the bounded original embedding rows. That makes
the BF16 product exact before accumulation; math.fma plus explicit FP32 round
models the shader's FP32 square-accumulation boundary without a product round.
Other domains are rejected rather than assuming unreviewed denormal behavior.
"""
import math
import struct


WIDTH, LANES = 2560, 256
_F32, _U32 = struct.Struct("<f"), struct.Struct("<I")
EPSILON_BITS = 0x358637BD
_MIN_NORMAL_F32 = _F32.unpack(_U32.pack(0x00800000))[0]


def _f32(value):
    try:
        result = _F32.unpack(_F32.pack(value))[0]
    except OverflowError as error:
        raise ValueError("FP32 overflow in original-order CPU diagnostic") from error
    if not math.isfinite(result):
        raise ValueError("finite FP32 arithmetic required")
    return result


def _bits(value):
    return _U32.unpack(_F32.pack(value))[0]


def _words(value, label):
    if type(value) not in (tuple, list) or len(value) != WIDTH:
        raise ValueError(label + " must supply exactly2560 copied BF16 words")
    if any(type(word) is not int or not 0 <= word <= 0xFFFF or (word & 0x7F80) == 0x7F80 for word in value):
        raise ValueError(label + " must contain finite unsigned16 BF16 words")
    return tuple(_F32.unpack(_U32.pack(word << 16))[0] for word in value)


def _bf16_rne(value):
    bits = _bits(value)
    word = ((bits + 0x7FFF + ((bits >> 16) & 1)) >> 16) & 0xFFFF
    if (word & 0x7F80) == 0x7F80:
        raise ValueError("BF16 output overflow")
    return word


def rms_bf16_words(raw_words, raw_gamma_words):
    """Return (2560 BF16 words, diagnostic metadata) for one supplied raw row.

    This is an unqualified CPU diagnostic, never an original-native receipt.
    All selected rows must use the same rule; no observed output is an input.
    """
    if not hasattr(math, "fma"):
        raise RuntimeError("Python >=3.13 with math.fma required")
    raw, gamma = _words(raw_words, "raw input"), _words(raw_gamma_words, "raw gamma")
    for value in raw:
        square = value * value
        if _f32(square) != square or square != 0 and square < _MIN_NORMAL_F32:
            raise ValueError("normal exact-FP32 BF16 squares required for reviewed accumulation domain")
    partials = [0.0] * LANES
    for lane in range(LANES):
        partial = 0.0
        for column in range(lane, WIDTH, LANES):
            value = raw[column]
            partial = _f32(math.fma(value, value, partial))
        partials[lane] = partial
    for stride in (128, 64, 32, 16, 8, 4, 2, 1):
        for lane in range(stride):
            partials[lane] = _f32(partials[lane] + partials[lane + stride])
    total = partials[0]
    mean = _f32(total / _f32(WIDTH))
    epsilon = _F32.unpack(_U32.pack(EPSILON_BITS))[0]
    mean_epsilon = _f32(mean + epsilon)
    inverse = _f32(1.0 / math.sqrt(mean_epsilon))
    output = []
    for value, raw_gamma in zip(raw, gamma):
        first = _f32(value * inverse)
        weight = _f32(raw_gamma + 1.0)
        output.append(_bf16_rne(_f32(first * weight)))
    return tuple(output), dict(
        schema="halogen0162.embedding-rms-cpu-tree-diagnostic.v1",
        width=WIDTH, lanes=LANES, terms_per_lane=10, reduction_strides=[128,64,32,16,8,4,2,1],
        square_accumulation="math.fma followed by explicit FP32 round; exact normal BF16 square domain",
        epsilon_fp32_bits=f"0x{EPSILON_BITS:08x}", sum_fp32_bits=f"0x{_bits(total):08x}",
        mean_fp32_bits=f"0x{_bits(mean):08x}", mean_epsilon_fp32_bits=f"0x{_bits(mean_epsilon):08x}",
        inverse_fp32_bits=f"0x{_bits(inverse):08x}",
        inverse="one FP32 rounding of CPU 1/sqrt; native v_rsq_f32 parity unqualified",
        products="FP32 raw*inverse then*(FP32 raw_gamma+1); BF16 RNE",
        original_native_RMS_qualified=False, early_producer_adopted=False,
        FC_executed=False, npu_executed=False, tolerance_adjustment=False, arithmetic_fitting=False, speed_claim=False)
