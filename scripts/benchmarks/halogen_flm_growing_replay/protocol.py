"""Default-off authority controller for a serial, externally owned raw NPU backend.

No process, DLL, device or transport is opened by this module. The target server
must never await this worker. Native backend binding is separate preparation.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import struct
import time

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('growing_original_feedback',
    HERE / 'token_feedback.py')
feedback = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(feedback)

SEED = 512
OUTPUTS = 128
MAX_LOCAL = SEED + OUTPUTS
ROWS = 248070
RUNTIME_SHA256 = 'd77388dcd21fcd7422005d0f780a044142d525e3afaafef3bcb9e980b8c18501'
WEIGHTS_SHA256 = '787428ffe87be5e3e5a8fcaf241844b69896ca0c74a41f2432c436739f7ba4e4'
PROPOSER_TOKENIZER_SHA256 = '5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42'


def require(value, message):
    if not value:
        raise ValueError(message)


def prefix_hash(ids):
    digest = hashlib.sha256(feedback.HASH_DOMAIN)
    for token in ids:
        digest.update(struct.pack('<i', feedback.token_id(token)))
    return digest.hexdigest()


class GrowingProducer:
    def __init__(self, backend, *, enabled=False, clock_ns=time.perf_counter_ns):
        self.enabled = enabled is True
        self.backend, self.clock = backend, clock_ns
        self.authority = feedback.TokenFeedback(enabled=self.enabled)
        self.observations = []
        self._epoch, self._request, self._prefix = None, None, None
        self._ready, self._busy = None, False
        self._native_inflight = False
        self._generation, self._sequence, self._local = 0, 0, 0
        self.last_result = None

    def _retire(self):
        if self._epoch is not None:
            self.authority.cancel(self._epoch, reason='producer_retired')
        self._generation += 1
        self._epoch = self._request = self._prefix = self._ready = None
        self._busy = False

    def cancel(self, epoch):
        if self._epoch == epoch:
            self._retire()

    def _run(self, operation, expected_count, observed_ns):
        require(not self._native_inflight, 'A native operation is still in flight')
        generation = self._generation
        request, epoch = self._request, self._epoch
        self._ready, self._busy = None, True
        submitted = self.clock()
        self._native_inflight = True
        try:
            result = operation()
            received = self.clock()
            if generation != self._generation:
                return None
            require(type(result) is dict and result.get('request_id') == request
                    and result.get('request_epoch') == epoch, 'Native request binding differs')
            require(type(result.get('local_count')) is int and result['local_count'] == expected_count
                    and result.get('owned_rows') is True and result.get('row_count') == ROWS
                    and result.get('speculative_inputs') == 0,
                    'Native owned-logit history or speculative-input count differs')
            token = result.get('greedy_id')
            require(type(token) is int and 0 <= token < ROWS, 'Native greedy ID is not shared')
            timing = result.get('native_timing', {})
            require(timing.get('clock') == 'Windows QPC'
                    and type(timing.get('frequency')) is int and timing['frequency'] > 0
                    and type(timing.get('operation_started_ticks')) is int
                    and type(timing.get('logits_owned_ticks')) is int
                    and 0 <= timing['operation_started_ticks'] <= timing['logits_owned_ticks'],
                    'Actual native QPC endpoints are required')
            require(submitted <= received, 'Host clock moved backwards')
            self._local, self._busy = expected_count, False
            self.last_result = copy.deepcopy(result)
            self._sequence += 2
            if self._prefix['generated_count'] < OUTPUTS:
                self._ready = dict(schema='halogen0201.growing-count1-ready.v1',
                    ready_sequence=self._sequence, request_id=request, request_epoch=epoch,
                    prefix_count=self._prefix['prefix_count'], prefix_sha256=self._prefix['prefix_sha256'],
                    engine_sha256=feedback.ENGINE_SHA256, tokenizer_sha256=feedback.TOKENIZER_SHA256,
                    proposer_runtime_sha256=RUNTIME_SHA256, proposer_weights_sha256=WEIGHTS_SHA256,
                    proposer_tokenizer_sha256=PROPOSER_TOKENIZER_SHA256,
                    token_ids=[token], local_count=expected_count, seed_count=SEED,
                    oracle_future_IDs=False, speculative_inputs=0,
                    producer_clock='time.perf_counter_ns', authority_received_qpc_ns=observed_ns,
                    backend_submitted_qpc_ns=submitted, backend_received_qpc_ns=received,
                    producer_ready_qpc_ns=self.clock(), native_timing=copy.deepcopy(timing),
                    consumer_arrival_timestamp=None, target_need_timestamp=None,
                    consumer_arrived_before_target_need=None)
            return self.ready()
        except BaseException:
            self._retire()
            raise
        finally:
            self._native_inflight = False

    def begin(self, request_id, epoch, prompt_ids):
        if not self.enabled:
            return None
        self._retire()
        observed = self.clock()
        try:
            require(not self._native_inflight, 'A native operation is still in flight')
            require(type(prompt_ids) is list and SEED <= len(prompt_ids) <= 262144,
                    'A full prompt of512..262144 native IDs is required')
            tail = prompt_ids[-SEED:]
            require(all(type(token) is int and 0 <= token < ROWS for token in tail),
                    'The exact last512 IDs must be shared with the proposer')
            prefix = self.authority.begin(request_id, epoch, prompt_ids)
            self._request, self._epoch, self._prefix = request_id, epoch, prefix
            self.observations = []
            return self._run(lambda: self.backend.begin(request_id, epoch, list(tail)), SEED, observed)
        except BaseException:
            self._retire()
            raise

    def feed_line(self, raw, epoch):
        if not self.enabled:
            return None
        observed = self.clock()
        try:
            require(self._epoch == epoch and not self._busy, 'Producer epoch is retired or busy')
            packet = self.authority.feed_line(raw, request_epoch=epoch)
            if packet is None:
                return None
            if packet['kind'] != 'commit':
                self._retire()
                return None
            old = self._ready
            self._ready = None
            require(packet['generated_count'] <= OUTPUTS, 'Planned128 native outputs exceeded')
            token, = packet['token_ids']
            require(token < ROWS, 'Authoritative ID is outside the proposer shared range')
            self.observations.append(dict(request_epoch=epoch,
                generated_count=packet['generated_count'], native_token_id=token,
                predicted_token_id=old['token_ids'][0] if old else None,
                prediction_equal_to_observed_native_ID=(old['token_ids'][0] == token) if old else None,
                native_acceptance=None, scope='component exact one-ID observation, not native acceptance'))
            self._prefix = packet
            request = self._request
            return self._run(lambda: self.backend.append_authoritative(request, epoch, token),
                             SEED + packet['generated_count'], observed)
        except BaseException:
            self._retire()
            raise

    def ready(self):
        return copy.deepcopy(self._ready) if self._epoch is not None and not self._busy else None

    def publish_ready(self, send):
        """Measure the actual sender call; this does not establish receiver arrival."""
        packet = self.ready()
        if packet is None:
            return None
        started = self.clock()
        error = None
        try:
            submitted = send(copy.deepcopy(packet)) is True
        except OSError as failure:
            submitted, error = False, type(failure).__name__
        returned = self.clock()
        return dict(request_id=packet['request_id'], request_epoch=packet['request_epoch'],
            ready_sequence=packet['ready_sequence'], submitted=submitted, error=error,
            producer_clock='time.perf_counter_ns', send_started_qpc_ns=started,
            send_returned_qpc_ns=returned, still_current=self.ready() == packet,
            consumer_arrival_timestamp=None, target_need_timestamp=None,
            consumer_arrived_before_target_need=None)
