"""Owned worker prototype. Default-off: no server/native registration exists.

Explicit construction loads only the already-acquired drafter and target
bindings. The caller must authorize/own accelerator execution separately.
Windows tensor objects cannot borrow Linux/native device addresses.
"""
from dataclasses import dataclass
from pathlib import Path
import sys
import time

from abi import MASK_ID, OwnerStamp, selected_rows
from tensor_graphs import make_tensor_graphs


def reference_directory():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts/research/dflash_k3_reference"
        if (candidate / "reference.py").is_file():
            return candidate
    raise RuntimeError("Published qualified CPU reference is required")


def reference_modules():
    directory = str(reference_directory())
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import contract
    import offline_loader
    import compare
    return contract, offline_loader, compare


@dataclass(frozen=True)
class ReadyProposal:
    owner: OwnerStamp
    round_index: int
    current_id: int
    position: int
    raw_ids: tuple[int, int, int]
    offerable: bool
    host_phase_ns: tuple[tuple[str, int], ...]


class FixedCapacityWorker:
    def __init__(self, *, torch, graphs, stamp, mask_embedding, device="cpu", embedding_lookup=None):
        if device not in {"cpu", "cuda"}:
            raise ValueError("Only explicit CPU or installed PyTorch HIP cuda namespace is prepared")
        if not stamp.request_birth or not stamp.request_address:
            raise ValueError("Native pending owner must transfer to an actual Request before worker admission")
        contract, _, _ = reference_modules()
        self.torch, self.graphs, self.stamp = torch, graphs, stamp
        self.capacity, self.device = graphs.capacity, torch.device(device)
        # Explicit root-owned .to('cuda') is the only GPU preparation route.
        # No automatic device discovery, availability probe or native activation.
        relocated = {}
        for graph in (graphs.context, graphs.backbone, graphs.head):
            for module in graph.modules():
                for name, value in tuple(module._buffers.items()):
                    if value is not None:
                        if id(value) not in relocated:
                            relocated[id(value)] = value.to(device=self.device)
                        module._buffers[name] = relocated[id(value)]
            graph.eval()
        self.dtype = next(graphs.context.buffers()).dtype
        self.mask = mask_embedding.detach().to(device=self.device, dtype=self.dtype).clone()
        self._finite(self.mask, "mask embedding")
        self.cache = torch.zeros((5, 2, 2, self.capacity, 256), dtype=self.dtype, device=self.device)
        self.inv_freq = 1.0 / (10000000.0 ** (torch.arange(0, 256, 2, dtype=torch.float32, device=self.device) / 256))
        nonce = f"{stamp.session_hex}:{stamp.pending_ticket}:{stamp.request_address}:{stamp.request_birth}"
        self.frontier = contract.Frontier(nonce, stamp.lease_generation)
        self.ids, self.positions, self.pending = (), (), None
        self.prefill_complete = False
        self.retired = False
        self.embedding_lookup = embedding_lookup
        self.last_hidden = None
        self.last_logits = None
        self.retain_diagnostics = False
        self.last_context_update_ns = None
        self._native_round_adapter = None

    def _owner(self, stamp):
        if self.retired or stamp != self.stamp:
            raise ValueError("Retired or foreign/stale target ownership")

    def _finite(self, value, role):
        if not bool(self.torch.isfinite(value).all().item()):
            raise ValueError(f"Non-finite {role}")

    def _rope(self, positions):
        pos = self.torch.tensor([tuple(positions)], dtype=self.torch.long, device=self.device)
        freq = (self.inv_freq[None, :, None].float() @ pos[:, None, :].float()).transpose(1, 2)
        emb = self.torch.cat((freq, freq), dim=-1)
        return emb.cos()[0].to(self.dtype), emb.sin()[0].to(self.dtype)

    def _project(self, values, positions):
        if tuple(values.shape) != (len(positions), 12800):
            raise ValueError("HCconcat must be row-major selected rows by12800")
        owned = values.detach().to(device=self.device, dtype=self.dtype).clone().contiguous()
        self._finite(owned, "selected target features")
        cos, sin = self._rope(positions)
        append, finite = self.graphs.context(owned, cos, sin)
        if not bool(finite.item()):
            raise ValueError("Context projection produced invalid fused/context KV")
        return append

    def append_prefill(self, *, stamp, features, input_ids, positions, final=False):
        self._owner(stamp)
        if self.prefill_complete or self.pending is not None:
            raise ValueError("Prefill precedes the first query")
        ids, positions = tuple(input_ids), tuple(positions)
        start = len(self.ids)
        if not ids or len(ids) != len(positions) or positions != tuple(range(start, start + len(ids))):
            raise ValueError("Cache Off prefill is the complete contiguous prefix from0")
        if any(type(i) is not int or not 0 <= i < MASK_ID for i in ids) or start + len(ids) > self.capacity:
            raise ValueError("Invalid input IDs or bounded provider capacity exceeded")
        if final and stamp.total_prefill and start + len(ids) != stamp.total_prefill:
            raise ValueError("Final prefill does not match pending holder total")
        try:
            with self.torch.inference_mode():
                append = self._project(features, positions)
                self.cache[:, :, :, start:start + len(ids), :].copy_(append)
            self.ids += ids
            self.positions += positions
            if final:
                self.frontier.initialize(self.positions)
                self.prefill_complete = True
        except Exception:
            self.retire()
            raise

    def propose(self, *, stamp, round_index, current_id, anchor_embedding=None):
        self._owner(stamp)
        if not self.prefill_complete:
            raise ValueError("Complete accepted target prefill before a query")
        begin = time.perf_counter_ns()
        try:
            with self.torch.inference_mode():
                query = self.frontier.begin(round_index, current_id, len(self.ids))
                if anchor_embedding is None:
                    if self.embedding_lookup is None:
                        raise ValueError("Bind root-owned verified mmap row lookup for arbitrary anchors")
                    anchor_embedding = self.embedding_lookup(current_id)
                if tuple(anchor_embedding.shape) != (2560,):
                    raise ValueError("Current actual target embedding row is required")
                anchor = anchor_embedding.detach().to(device=self.device, dtype=self.dtype).clone()
                self._finite(anchor, "anchor embedding")
                embeddings = self.torch.stack((anchor, self.mask, self.mask), dim=0)
                cos, sin = self._rope(query.query_positions)
                prepared = time.perf_counter_ns()
                length = self.torch.tensor(len(self.ids), dtype=self.torch.long, device=self.device)
                hidden, finite = self.graphs.backbone(self.cache, length, embeddings, cos, sin)
                if not bool(finite.item()):
                    raise ValueError("Backbone produced invalid query hidden states")
                backbone_done = time.perf_counter_ns()
                ids, finite, logits = self.graphs.head(hidden)
                if not bool(finite.item()):
                    raise ValueError("Full head produced invalid logits; discard all internal argmax IDs")
                raw = tuple(int(i) for i in ids.tolist())
                head_done = time.perf_counter_ns()
                self.frontier.record_proposal(query, raw)
                if self.retain_diagnostics:
                    self.last_hidden, self.last_logits = hidden, logits
            ready = ReadyProposal(stamp, round_index, current_id, len(self.ids), raw,
                all(0 <= i < MASK_ID for i in raw),
                (("input_prepare", prepared - begin), ("backbone_including_finite_sync", backbone_done - prepared),
                 ("full_head_and_host_ID_copy", head_done - backbone_done), ("worker_propose_total", head_done - begin)))
            self.pending = ready
            return ready
        except Exception:
            self.retire()
            raise

    def apply_verification(self, *, stamp, round_index, verifier_features, verifier_ids,
                           verifier_positions, accepted_prefix, authoritative_bonus_id,
                           terminal=False):
        self._owner(stamp)
        if terminal:
            self.retire()
            return None
        if self.pending is None or round_index != self.pending.round_index:
            raise ValueError("Missing exact pending ready proposal")
        selected = selected_rows(current_id=self.pending.current_id, proposal_ids=self.pending.raw_ids,
            verifier_ids=verifier_ids, verifier_positions=verifier_positions, position=self.pending.position,
            accepted_prefix=accepted_prefix)
        plan = self.frontier.plan_commit(round_index, verifier_ids, verifier_positions,
                                         accepted_prefix, authoritative_bonus_id)
        if plan.next_anchor_position > self.capacity:
            self.retire()
            raise ValueError("Complete context no longer fits bounded provider; native scalar fallback required")
        try:
            started = time.perf_counter_ns()
            with self.torch.inference_mode():
                # Neither projection nor finite validation ever sees rejected
                # verifier rows. Existing persistent prefix is left untouched.
                append = self._project(verifier_features[selected], plan.retained_positions)
                start = len(self.ids)
                self.cache[:, :, :, start:plan.next_anchor_position, :].copy_(append)
            self.frontier.finish_commit(plan)
            self.ids += plan.retained_ids
            self.positions += plan.retained_positions
            self.pending = None
            self.last_hidden = None
            self.last_logits = None
            self.last_context_update_ns = time.perf_counter_ns() - started
            return plan
        except Exception:
            self.retire()
            raise

    def retire(self):
        self.retired = True
        self.frontier.retire()
        self.cache, self.pending = None, None
        self.last_hidden = None
        self.last_logits = None
        self.ids = self.positions = ()

    def native_rounds(self):
        if self._native_round_adapter is None:
            from scalar_support import NativeRoundAdapter
            self._native_round_adapter = NativeRoundAdapter(self)
        return self._native_round_adapter

    def propose_native(self, **kwargs):
        return self.native_rounds().propose(**kwargs)

    def apply_committed_verify(self, **kwargs):
        return self.native_rounds().apply_verify_commit(**kwargs)

    def apply_scalar(self, **kwargs):
        return self.native_rounds().apply_scalar(**kwargs)


def prepare_from_assets(*, checkpoint, config, bindings_receipt, capacity, stamp,
                        device="cpu", compute_dtype="bf16", attention_mode="repeat",
                        head_mode="chunked", embedding_lookup=None):
    """Explicit root-owned preparation; CPU default. No serving registration."""
    import json
    contract, loader, compare = reference_modules()
    torch = loader.cpu_torch()
    cfg = json.loads(Path(config).read_text(encoding="utf-8"))
    contract.validate_config(cfg)
    drafter = loader.load_drafter(checkpoint)
    binding, rows, row_receipts, head_owner = compare.load_binding_receipt(bindings_receipt, torch)
    graphs = make_tensor_graphs(torch, weights=drafter.tensors, full_head=binding._head,
                               capacity=capacity, compute_dtype=compute_dtype,
                               attention_mode=attention_mode, head_mode=head_mode)
    worker = FixedCapacityWorker(torch=torch, graphs=graphs, stamp=stamp,
                                mask_embedding=binding._mask, device=device,
                                embedding_lookup=embedding_lookup)
    # Keep source ownership and immutable provenance receipts for the lifetime
    # of the worker; no published CPU provider is changed or instantiated.
    worker.asset_owners = (drafter, head_owner, binding)
    worker.embedding_rows = rows
    worker.embedding_receipts = row_receipts
    worker.binding_identity = binding.identity
    return worker
