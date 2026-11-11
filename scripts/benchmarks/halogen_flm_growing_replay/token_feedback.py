"""Default-off, CPU-only observer for Halogen0.20.1 native output IDs.

Packets describe nativeT publication. They carry no native round boundary,
accepted-prefix attribution, transport or external-proposal integration.
"""
import hashlib
import re
import struct

ENGINE_SHA256 = '7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577'
TOKENIZER_SHA256 = '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
HEAD_ROWS = 248320
DEFINED_TARGET_IDS = 248077
SHARED_NPU_IDS = 248070
HASH_DOMAIN = b'halogen-authoritative-token-ids-v1\0'


def token_id(value):
    if type(value) is not int or not 0 <= value < HEAD_ROWS:
        raise ValueError('Native token ID is outside the head')
    return value


class TokenFeedback:
    def __init__(self, enabled=False):
        self.enabled = enabled is True
        self._active = False
        self._epoch = None
        self._seen_epochs = set()

    def begin(self, request_id, request_epoch, prompt_ids):
        if not self.enabled:
            return None
        if type(request_id) is not int or not 0 <= request_id < (1 << 63):
            raise ValueError('Native request ID must be a nonnegative int64')
        if type(request_epoch) is not str or re.fullmatch('[0-9a-f]{32}', request_epoch) is None:
            raise ValueError('Request epoch must be32 lowercase hexadecimal characters')
        if request_epoch in self._seen_epochs:
            raise ValueError('A new request or reset requires a fresh epoch')
        hasher = hashlib.sha256(HASH_DOMAIN)
        count, defined, shared = 0, True, True
        for value in prompt_ids:
            value = token_id(value)
            hasher.update(struct.pack('<i', value))
            count += 1
            defined = defined and value < DEFINED_TARGET_IDS
            shared = shared and value < SHARED_NPU_IDS
        self._request_id = request_id
        self._epoch = request_epoch
        self._seen_epochs.add(request_epoch)
        self._hasher = hasher
        self._prompt_count = count
        self._prefix_count = count
        self._generated_count = 0
        self._defined = defined
        self._shared = shared
        self._active = True
        return self._packet('begin')

    def _packet(self, kind, ids=(), *, reason=None, complete=False):
        return dict(
            schema='halogen0201.authoritative-token-feedback.v1', kind=kind,
            request_id=self._request_id, request_epoch=self._epoch,
            engine_sha256=ENGINE_SHA256, tokenizer_sha256=TOKENIZER_SHA256,
            token_ids=list(ids), generated_count=self._generated_count,
            prefix_count=self._prefix_count, prefix_sha256=self._hasher.hexdigest(),
            defined_target_ids_only=self._defined, shared_NPU_ids_only=self._shared,
            source='native_T', native_round_id=None, native_accepted_prefix_count=None,
            reason=reason, complete_native_stream=complete)

    def _check_epoch(self, request_epoch):
        if self._epoch is None or request_epoch != self._epoch:
            raise ValueError('Request epoch differs from the current request')

    def feed_line(self, raw, *, request_epoch):
        if not self.enabled:
            return None
        self._check_epoch(request_epoch)
        if not self._active:
            return None
        if type(raw) is not bytes or not raw.endswith(b'\n') or raw.count(b'\n') != 1:
            raise ValueError('One complete native protocol line is required')
        try:
            parts = raw.decode('ascii').split()
        except UnicodeDecodeError as error:
            raise ValueError('Native protocol line is not ASCII') from error
        if not parts or parts[0] not in ('T', 'D'):
            return None
        kind = parts[0]
        if len(parts) < 3:
            raise ValueError('Incomplete native ' + kind + ' line')
        try:
            request_id = int(parts[1])
        except ValueError as error:
            raise ValueError('Invalid native request ID') from error
        if request_id != self._request_id:
            return None
        if kind == 'T':
            try:
                value = token_id(int(parts[2]))
            except ValueError as error:
                raise ValueError('Invalid native token ID') from error
            # Optional logprob/top-logprob fields do not identify the committed ID.
            self._hasher.update(struct.pack('<i', value))
            self._generated_count += 1
            self._prefix_count += 1
            self._defined = self._defined and value < DEFINED_TARGET_IDS
            self._shared = self._shared and value < SHARED_NPU_IDS
            return self._packet('commit', (value,))
        self._active = False
        if parts[2] == 'error':
            return self._packet('error', reason='native_error')
        if len(parts) < 7:
            raise ValueError('Incomplete native D line')
        try:
            native_prompt_count = int(parts[3])
            native_count = int(parts[4])
        except ValueError as error:
            raise ValueError('Invalid native prompt or generated count') from error
        if native_prompt_count != self._prompt_count:
            raise ValueError('Observed prefix differs from the native prompt count')
        if native_count != self._generated_count:
            raise ValueError('Observed token IDs differ from the native generated count')
        return self._packet('done', reason=parts[2], complete=True)

    def cancel(self, request_epoch, *, reason='cancelled'):
        if not self.enabled:
            return None
        self._check_epoch(request_epoch)
        if not self._active:
            return None
        self._active = False
        return self._packet('cancelled', reason=reason)
