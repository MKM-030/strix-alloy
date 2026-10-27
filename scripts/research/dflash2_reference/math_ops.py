"""Faithful DFlash2 convolution and selector equations; lazy PyTorch only.

Adapted from SGLang@3c560089e1818a5217a73f2168273485a5350341,
Apache-2.0 (sources/SGLANG_LICENSE). See provenance.json for exact source pins.
Callers own tensor allocation and execution. No device is selected here.
"""
if __package__:
    from .contract import WIDTH, GROUPS, GROUP_WIDTH, TAPS, SELECTOR_RANK, TOP_K
else:
    from contract import WIDTH, GROUPS, GROUP_WIDTH, TAPS, SELECTOR_RANK, TOP_K

def _same_tensors(*values):
    import torch
    if not values or any(not isinstance(x, torch.Tensor) for x in values):
        raise TypeError('Tensor arguments required')
    if values[0].dtype not in (torch.float32, torch.bfloat16):
        raise TypeError('Reference supports float32 and bfloat16')
    if any(x.dtype != values[0].dtype for x in values):
        raise TypeError('Floating tensor dtypes must match')
    if any(x.device != values[0].device for x in values):
        raise ValueError('Tensor devices must match')
    return torch

def _block(block_size):
    if type(block_size) is not int or block_size not in (4, 8):
        raise ValueError('Only runtime block4 and trained block8 are in scope')

def _hidden(x):
    if x.ndim != 2 or x.shape[0] <= 0 or x.shape[1] != WIDTH:
        raise ValueError('hidden_states must have shape [positive rows,2560]')

def grouped_conv(hidden_states, delta, base, block_size, num_groups, group_size, taps):
    """Source two-tap convolution with no cross-block history or inplace writes.

    hidden:[rows,2560], delta:[rows,2,160], base:[2,2560]. Strided inputs
    are accepted wherever source view/unflatten accepts them.
    """
    torch = _same_tensors(hidden_states, delta, base)
    _hidden(hidden_states); _block(block_size)
    if (num_groups, group_size, taps) != (GROUPS, GROUP_WIDTH, TAPS):
        raise ValueError('Expected 160 groups of width16 and two taps')
    if delta.shape != (hidden_states.shape[0], TAPS, GROUPS) or base.shape != (TAPS, WIDTH):
        raise ValueError('Convolution coefficient shape differs')
    blocks = hidden_states.unflatten(-1, (num_groups, group_size))
    coefficients = base.view(1, taps, num_groups, group_size) + delta.unsqueeze(-1)
    out = coefficients[:, 0] * blocks
    position = torch.arange(hidden_states.shape[0], device=hidden_states.device)
    if block_size & (block_size - 1) == 0:
        position = position & (block_size - 1)
    else:
        position = position % block_size
    for tap in range(1, taps):
        shifted = torch.nn.functional.pad(blocks[:-tap], (0, 0, 0, 0, tap, 0))
        shifted = torch.where((position >= tap).view(-1, 1, 1), shifted, 0)
        out = out + coefficients[:, tap] * shifted
    return out.flatten(-2)

def prepare_convolution(hidden_states, projection, base_kernel, block_size):
    """Input-side convolution and retained output-side coefficients.

    projection:[640,2560], base:[input/output,2,2560]. Output coefficients
    come from this input projection, never a fresh output projection.
    """
    torch = _same_tensors(hidden_states, projection, base_kernel)
    _hidden(hidden_states); _block(block_size)
    if projection.shape != (2 * TAPS * GROUPS, WIDTH) or base_kernel.shape != (2, TAPS, WIDTH):
        raise ValueError('Expected projection[640,2560] and base[2,2,2560]')
    coefficients = torch.nn.functional.linear(hidden_states, projection).reshape(
        *hidden_states.shape[:-1], 2, TAPS, GROUPS)
    prepared = grouped_conv(hidden_states, coefficients[..., 0, :, :], base_kernel[0],
                            block_size, GROUPS, GROUP_WIDTH, TAPS)
    return prepared, coefficients[..., 1, :, :]

def finish_convolution(hidden_states, coefficients, base_kernel, block_size):
    """Convolve sublayer output with the coefficients retained by prepare."""
    _same_tensors(hidden_states, coefficients, base_kernel)
    if base_kernel.shape != (2, TAPS, WIDTH):
        raise ValueError('Expected base[2,2,2560]')
    return grouped_conv(hidden_states, coefficients, base_kernel[1],
                        block_size, GROUPS, GROUP_WIDTH, TAPS)

def _ids(torch, x, device, shape, upper, name):
    if not isinstance(x, torch.Tensor) or x.dtype != torch.int64:
        raise TypeError(name + ' must be int64')
    if x.device != device or x.shape != shape:
        raise ValueError(name + ' shape/device differs')
    if x.numel() and (bool((x < 0).any()) or bool((x >= upper).any())):
        raise ValueError(name + ' outside supplied table/map domain')

def score_edges(*, predecessor_table, successor_table, candidate_ids,
                unary_logits, hidden, anchor_token_ids, top_k):
    """Source selector lattice [batch,slots,16,16].

    hidden is already projected to rank256. Unary logits are FP32; tables and
    projected hidden share FP32/BF16 dtype. Table bounds do not establish the
    defined-token domain; that belongs to the future model binding.
    """
    torch = _same_tensors(predecessor_table, successor_table, hidden)
    if (type(top_k) is not int or top_k != TOP_K or
            predecessor_table.ndim != 2 or predecessor_table.shape[1] != SELECTOR_RANK or
            predecessor_table.shape[0] < TOP_K or successor_table.shape != predecessor_table.shape):
        raise ValueError('Expected matching tables[vocab>=16,256] and top16')
    if hidden.ndim != 3 or hidden.shape[-1] != SELECTOR_RANK or min(hidden.shape[:2]) <= 0:
        raise ValueError('Projected hidden must be [positive batch,positive slots,256]')
    batch, slots = hidden.shape[:2]
    if not isinstance(unary_logits, torch.Tensor) or unary_logits.dtype != torch.float32:
        raise TypeError('Unary logits must be float32, matching source transform')
    if unary_logits.shape != (batch, slots, TOP_K) or unary_logits.device != hidden.device:
        raise ValueError('Unary logits shape/device differs')
    _ids(torch, candidate_ids, hidden.device, (batch, slots, TOP_K), predecessor_table.shape[0], 'candidate_ids')
    _ids(torch, anchor_token_ids, hidden.device, (batch,), predecessor_table.shape[0], 'anchor_token_ids')
    keys = successor_table[candidate_ids]
    predecessor_ids = torch.cat(
        [anchor_token_ids[:, None, None].expand(-1, 1, top_k), candidate_ids[:, :-1]], dim=1)
    predecessors = predecessor_table[predecessor_ids]
    return unary_logits[:, :, None] + torch.einsum(
        'blpr,blcr->blpc', predecessors * hidden[:, :, None], keys)

def follow_maps(maps, initial_indices, edges):
    """Source sequential walk over precomputed successor maps; no resampling."""
    import torch
    if not isinstance(maps, torch.Tensor) or maps.dtype != torch.int64:
        raise TypeError('maps must be int64')
    if type(edges) is not int or edges < 0:
        raise ValueError('edges must be a nonnegative integer')
    if maps.ndim != 3 or maps.shape[0] <= 0 or maps.shape[1] != edges or maps.shape[2] != TOP_K:
        raise ValueError('maps must have shape [positive batch,edges,16]')
    _ids(torch, initial_indices, maps.device, (maps.shape[0],), TOP_K, 'initial_indices')
    if maps.numel() and (bool((maps < 0).any()) or bool((maps >= TOP_K).any())):
        raise ValueError('Successor map index outside top16')
    index = initial_indices
    path = [index]
    for edge in range(edges):
        index = maps[:, edge].gather(-1, index[:, None])[:, 0]
        path.append(index)
    return torch.stack(path, dim=1)
