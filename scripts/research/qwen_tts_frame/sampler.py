"""Emit a guarded ONNX top-k sampler for the acoustic frame reference."""

import numpy as np
from onnx import TensorProto, helper


def _constant(graph, name, value, dtype):
    name = 'acoustic_sampler.' + name
    if any(tensor.name == name for tensor in graph.initializers):
        return name
    return graph.constant(name, value, dtype)


def emit_sample(graph, logits, temperature, uniform, *, top_k=50):
    """Return a scalar code and validity flag, using code zero when invalid.

    The extra rank detects ties inside top-k and at the cutoff. The flag
    checks the values computed by this graph. Reference agreement across
    arithmetic backends still requires a separate comparison.
    """
    if type(top_k) is not int or top_k < 1:
        raise ValueError('The sampler requires a positive integer top-k')
    op = graph.apply
    zero = _constant(graph, 'zero_i64', 0, np.int64)
    zero_float = _constant(graph, 'zero_f32', 0.0, np.float32)
    one_float = _constant(graph, 'one_f32', 1.0, np.float32)
    first = _constant(graph, 'slice_zero', [0], np.int64)
    second = _constant(graph, 'slice_one', [1], np.int64)
    k = _constant(graph, f'count_{top_k}', top_k, np.int64)
    top_end = _constant(graph, f'slice_{top_k}', [top_k], np.int64)
    extra_end = _constant(graph, f'slice_{top_k + 1}', [top_k + 1], np.int64)

    scaled = op('Div', logits, temperature)
    stem = f'acoustic_top_{len(graph.nodes)}'
    values, indices = stem + '_scores', stem + '_ids'
    graph.nodes.append(helper.make_node('TopK', [scaled, extra_end], [values, indices],
                                        name=stem, axis=0, largest=1, sorted=1))
    top_values = op('Slice', values, first, top_end)
    right_values = op('Slice', values, second, extra_end)
    differences = op('Greater', top_values, right_values)
    no_ties = op('Cast', op('ReduceMin', op('Cast', differences, to=TensorProto.INT32),
                           keepdims=0), to=TensorProto.BOOL)

    probabilities = op('Softmax', top_values, axis=0)
    cdf = op('CumSum', probabilities, zero)
    crossed = op('Greater', cdf, uniform)
    rank = op('Sub', k, op('ReduceSum', op('Cast', crossed, to=TensorProto.INT64), keepdims=0))
    has_crossing = op('Less', rank, k)

    invalid = op('Or', op('IsNaN', scaled), op('IsInf', scaled))
    all_finite = op('Not', op('Cast', op('ReduceMax', op('Cast', invalid, to=TensorProto.INT32),
                                        keepdims=0), to=TensorProto.BOOL))
    temperature_ok = op('And', op('Greater', temperature, zero_float), op('Not', op('IsInf', temperature)))
    draw_ok = op('And', op('GreaterOrEqual', uniform, zero_float), op('Less', uniform, one_float))
    valid = op('And', op('And', no_ties, has_crossing), op('And', all_finite, op('And', temperature_ok, draw_ok)))
    selected = op('Gather', indices, op('Where', valid, rank, zero), axis=0)
    return op('Where', valid, selected, zero), valid
