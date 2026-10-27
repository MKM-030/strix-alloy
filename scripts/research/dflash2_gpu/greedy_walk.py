"""Comparison/index-only greedy selector tail, caller-owned CPU/GPU tensors.

Adapted from CandidateSelector.sample_path in SGLang revision
3c560089e1818a5217a73f2168273485a5350341, Apache-2.0; license at
../dflash2_reference/sources/SGLANG_LICENSE, source SHA256
b7b541368cbbb072a679d08ba5bf0f952f4a43f02b6c078562b2ea7a9ddfd01b.

Dense-head matmul/top16, learned projection, BF16 products and full FP32
lattice remain unchanged outside this helper. One last-axis argmax invocation
replaces initial/transition argmax calls; unused first-slot predecessor rows
are extra comparisons, not floating sums. Direct FP32 point-mass scatter avoids
the intermediate int64 one_hot allocation/cast. No changed dot reduction,
candidate ordering, score/tie rule, sampling, precision, or tensor host read.
GPU launch count/latency savings require Root's measurement; head bandwidth is
unchanged. Import is passive. Same-stream input readiness remains caller-owned.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GreedyWalk:
    tokens: object
    q_rows: object
    path_indices: object


def walk_greedy(candidate_ids,edge_scores):
    """Return owned greedy tokens/q/path for [B,slots3/7,16] and full lattice.

    Drop-in tail: pass original candidate_ids and edge_scores after unchanged
    head/top16/rank256 scoring, and retain those original diagnostic tensors in
    PrivateProposal. Outputs stay on their input device; no CPU-only validator.
    """
    import torch
    if not isinstance(candidate_ids,torch.Tensor) or candidate_ids.dtype!=torch.int64:
        raise TypeError('int64 candidate IDs required')
    if not isinstance(edge_scores,torch.Tensor) or edge_scores.dtype!=torch.float32:
        raise TypeError('Original FP32 edge lattice required')
    if candidate_ids.ndim!=3 or not 1<=candidate_ids.shape[0]<=8 or candidate_ids.shape[1] not in (3,7) or candidate_ids.shape[2]!=16:
        raise ValueError('Whole block4/8 top16 candidate geometry required')
    batch,slots,_=candidate_ids.shape
    if edge_scores.device!=candidate_ids.device or edge_scores.shape!=(batch,slots,16,16):
        raise ValueError('Matching device/full predecessor lattice required')
    with torch.inference_mode():
        maps=edge_scores.argmax(-1)
        index=maps[:,0,0]
        path=[index]
        for slot in range(1,slots):
            index=maps[:,slot].gather(-1,index[:,None])[:,0]
            path.append(index)
        path=torch.stack(path,dim=1)
        tokens=candidate_ids.gather(-1,path.unsqueeze(-1))[:,:,0]
        q=torch.zeros((batch,slots,16),device=edge_scores.device,dtype=torch.float32)
        q.scatter_(-1,path.unsqueeze(-1),1.)
        return GreedyWalk(tokens,q,path)
