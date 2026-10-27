"""Private incremental committed-input KV; import has no device side effects.

These immutable host receipts ASSERT the saved native owner's observations;
they do not authenticate a GEN, a commit, a capture or GPU completion. Root's
joined native boundary must establish all four before calling this module.
Only already-projected PrivateContext rows enter this ring. No HC source,
model file, tokenizer, native pointer, proposal publication or loader is used.
"""
from dataclasses import dataclass
from .graph import PrivateContext, _explicit_device, _metadata

WINDOW, MAX_POSITION, DEFINED_IDS = 2048, 262144, 248077


@dataclass(frozen=True)
class SequenceKey:
    """Caller-supplied Bridge birth/model/tokenizer/generation identity."""
    birth: bytes
    model: bytes
    tokenizer: bytes
    generation: int


@dataclass(frozen=True)
class InputCommit:
    """Real Verify INPUT selection, never its emitted correction/bonus token.

    captured_input_ids describes the ordered features actually projected.
    committed_input_ids must come from the actual native commit receipt and
    equal its first accepted+1 rows. This class cannot verify that provenance.
    """
    sequence: SequenceKey
    round: int
    start_position: int
    captured_input_ids: tuple
    accepted: int
    committed_input_ids: tuple


def _sequence(key):
    if type(key) is not SequenceKey:
        raise TypeError('Exact SequenceKey required')
    for tag in (key.birth, key.model, key.tokenizer):
        if type(tag) is not bytes or len(tag) != 32 or not any(tag):
            raise ValueError('Nonzero32-byte native identity assertions required')
    if type(key.generation) is not int or not 0 < key.generation < 2**64:
        raise ValueError('Positive exact native generation required')


def _ids(values, rows):
    if type(values) is not tuple or len(values) != rows:
        raise ValueError('Owned host tuple with one input ID per captured row required')
    if any(type(value) is not int or not 0 <= value < DEFINED_IDS for value in values):
        raise ValueError('Defined actual target input IDs required')


class ContextRing:
    """Single-owner mirrored2048-row KV storage on an explicit device.

    Two copies of the circular storage make every chronological window a view,
    including rollover. BF16 K+V storage is80MiB (FP32 is160MiB). Per append,
    only the new committed rows are copied twice; previous rows are neither
    projected again nor reordered. This is a source mechanism, not a measured
    performance or peak-memory improvement.

    Calls must be serialized on the caller's same ordered stream. Returned
    contexts alias persistent storage and expire on the next mutation. Reset,
    retire and Python metadata do not drain outstanding device work: the caller
    must finish old readers/writers before reusing storage or another stream.
    No event/fence, native lease or security boundary is implemented here.
    """
    @classmethod
    def allocate(cls, *, device, dtype):
        import torch
        chosen = _explicit_device(device, torch)
        if dtype not in (torch.float32, torch.bfloat16):
            raise TypeError('Explicit FP32/BF16 dtype required')
        obj = cls()
        obj._t, obj.device, obj.dtype = torch, chosen, dtype
        with torch.inference_mode():
            obj._key = torch.empty((5, WINDOW * 2, 8, 128), dtype=dtype, device=chosen)
            obj._value = torch.empty_like(obj._key)
        obj._active, obj._sequence, obj._generation = False, None, 0
        obj._model, obj._tokenizer = None, None
        obj._end, obj._prompt_end, obj._round = 0, 0, 0
        obj._ids = ()
        return obj

    def begin(self, sequence, *, prompt_tokens):
        """Start a fresh native generation; full native Prefill is unchanged.

        Project/append actual contiguous PF suffix chunks from
        max(0,prompt_tokens-2048) through prompt_tokens. A suffix is sufficient
        for this local-window graph; it does not prove full stock PF semantics.
        """
        _sequence(sequence)
        if type(prompt_tokens) is not int or not 0 <= prompt_tokens <= MAX_POSITION:
            raise ValueError('Exact in-range prompt length required')
        if sequence.generation <= self._generation:
            raise ValueError('Stale or repeated native generation')
        if self._model is not None and (sequence.model != self._model or sequence.tokenizer != self._tokenizer):
            raise ValueError('Ring remains bound to its original model/tokenizer')
        self._model, self._tokenizer = sequence.model, sequence.tokenizer
        self._sequence, self._generation = sequence, sequence.generation
        self._active, self._round, self._ids = True, 1, ()
        self._prompt_end = prompt_tokens
        self._end = max(0, prompt_tokens - WINDOW)

    def _live(self, sequence):
        _sequence(sequence)
        if not self._active or sequence != self._sequence:
            raise ValueError('Retired, uninitialized or foreign native generation')

    def _prepared(self, context):
        if type(context) is not PrivateContext:
            raise TypeError('Already projected PrivateContext required')
        if type(context.start_position) is not int or context.start_position != self._end:
            raise ValueError('Gap, duplicate or out-of-order target input rows')
        if type(context.rows) is not int or not 1 <= context.rows <= WINDOW or self._end + context.rows > MAX_POSITION:
            raise ValueError('One contiguous in-range input chunk required')
        shape = (5, context.rows, 8, 128)
        _metadata(context._key, shape, self.dtype, self.device, self._t, 'prepared context key')
        _metadata(context._value, shape, self.dtype, self.device, self._t, 'prepared context value')
        owned = {self._key.untyped_storage().data_ptr(), self._value.untyped_storage().data_ptr()}
        if context._key.untyped_storage().data_ptr() in owned or context._value.untyped_storage().data_ptr() in owned:
            raise ValueError('Captured input rows cannot alias the persistent destination')

    def _append(self, context, input_ids):
        # All host receipt/metadata checks are complete before any write.
        # At most two contiguous pieces each written to both mirrored halves.
        count, source = len(input_ids), 0
        offset = self._end % WINDOW
        try:
            with self._t.inference_mode():
                while source < count:
                    rows = min(count - source, WINDOW - offset)
                    for destination in (offset, offset + WINDOW):
                        self._key[:, destination:destination + rows].copy_(context._key[:, source:source + rows])
                        self._value[:, destination:destination + rows].copy_(context._value[:, source:source + rows])
                    source += rows
                    offset = 0
        except BaseException:
            # A partial device submission cannot leave a publishable ring.
            self._active = False
            raise
        self._ids = (self._ids + input_ids)[-WINDOW:]
        self._end += count

    def append_prompt(self, context, *, sequence, input_ids):
        self._live(sequence)
        if self._round != 1 or self._end >= self._prompt_end:
            raise ValueError('Prompt suffix is already complete')
        self._prepared(context)
        _ids(input_ids, context.rows)
        if self._end + context.rows > self._prompt_end:
            raise ValueError('Prompt input rows extend beyond actual prompt')
        self._append(context, input_ids)

    def append_committed(self, context, receipt):
        """Append first accepted+1 captured Verify inputs exactly once.

        Prepare only this new1..4-row block with ContextGraph.prepare, using
        its absolute input start. Rejected rows and emitted bonus/correction
        never enter retained KV. A later real target forward can supply them.
        """
        if type(receipt) is not InputCommit:
            raise TypeError('Actual-input commit assertion required')
        self._live(receipt.sequence)
        if self._end < self._prompt_end:
            raise ValueError('Prompt suffix is incomplete')
        if type(receipt.round) is not int or receipt.round != self._round or self._round >= 2**64 - 1:
            raise ValueError('Stale, repeated or out-of-order native round')
        if type(receipt.start_position) is not int or receipt.start_position != self._end:
            raise ValueError('Commit is not the next canonical input position')
        self._prepared(context)
        if not 1 <= context.rows <= 4:
            raise ValueError('Current native Verify capture contains1..4 rows')
        _ids(receipt.captured_input_ids, context.rows)
        if type(receipt.accepted) is not int or not 0 <= receipt.accepted < context.rows:
            raise ValueError('Native accepted count must select1..captured rows')
        count = receipt.accepted + 1
        _ids(receipt.committed_input_ids, count)
        if receipt.committed_input_ids != receipt.captured_input_ids[:count]:
            raise ValueError('Native commit differs from captured target INPUT prefix')
        self._append(context, receipt.committed_input_ids)
        self._round += 1

    def context_for(self, sequence, *, round, anchor_position, block_size):
        """Private view for this exact Frontier.position and native round.

        Bridge Frontier.prefix_tokens counts the still-unprocessed frontier
        token too. Use its position (processed input count) here. Every query
        sees the same source window ending at anchor_position+block_size-1;
        the invisible oldest block_size rows are omitted from the view.
        """
        self._live(sequence)
        if type(round) is not int or round != self._round or self._end < self._prompt_end:
            raise ValueError('Incomplete prompt or stale native round')
        if type(anchor_position) is not int or anchor_position != self._end:
            raise ValueError('Context must end immediately before the actual anchor')
        if type(block_size) is not int or block_size not in (4, 8) or anchor_position + block_size > MAX_POSITION:
            raise ValueError('In-range query block4/8 required')
        first = max(0, anchor_position + block_size - WINDOW)
        rows = anchor_position - first
        if rows > len(self._ids):
            raise ValueError('Required contiguous committed history is missing')
        offset = first % WINDOW
        return PrivateContext(self._key[:, offset:offset + rows], self._value[:, offset:offset + rows], first)

    @property
    def input_ids(self):
        """Owned host canonical input tail; no tensor read or full prefix claim."""
        if not self._active:
            raise ValueError('Retired or uninitialized ring')
        return self._ids

    def retire(self, sequence):
        self._live(sequence)
        self._active, self._ids = False, ()
