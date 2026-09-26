# GUFO AR4k model identity implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the first one-session, 4096-context, autoregressive GUFO profile to the existing three-shard Unsloth UD-IQ4_XS GGUF set by bounded descriptor inspection, exact file sizes, and pinned metadata, while rejecting GUFO projector auto-discovery.

**Architecture:** Add one pure profile-validation module above the existing bounded `inspect_gguf` reader. It reads only GGUF descriptors, compares all three shards to pinned identities, and returns a validated first-shard path and declared revision; it never launches a process or decides memory admission. A single test file uses tiny synthetic GGUF files and injected pins.

**Tech Stack:** Python standard library and existing `scripts/gufo_control/gguf.py`; `unittest` under `tests/gufo`.

## Global Constraints

- Worktree: `C:\Projects\strix-alloy-research\integration`; leave the original Strix checkout and GUFO source snapshots untouched.
- First profile only: native Windows, exactly one session, 4096 context, AR only, no MTP, no vision/projector and no disk prompt cache.
- Model lineage: Unsloth UD-IQ4_XS revision `38bb39ee97821de2c9009abb7e93950eec396e66`.
- GUFO's pinned loader searches `mmproj-BF16.gguf` in the resolved model directory **and its parent**, even with no `--mmproj`; reject either candidate and revalidate immediately before any later process creation.
- Descriptor SHA256 values below cover bytes `[0, descriptor_end)`, not tensor data. They are locally computed descriptor fingerprints. File size plus descriptor hash cannot prove full-file content or independently authenticate the publisher revision.
- The first shard has zero tensors and the architecture metadata. The second and third have 373 and 851 tensors, respectively, and only split metadata. Their tensor counts sum to the declared 1224.
- This task does not launch GUFO, qualify GPU/host memory, change admission policy, or verify weight bytes.

## Files and boundaries

- Create `scripts/gufo_control/model_identity.py`: pinned profile, bounded numeric-array extraction, descriptor hashing, path/projector checks, and pure validation entry point.
- Create `tests/gufo/test_model_identity.py`: tiny synthetic shards, injected pins, and refusal cases. No large files, GPU, HIP, WSL, subprocess, or live model paths.
- Reuse `scripts/gufo_control/gguf.py` unchanged. Its `inspect_gguf(path)` returns `path`, `size_bytes`, `mtime_ns`, `metadata`, `tensors`, and `descriptor_end`. Its `_Reader` and `SCALARS` implement the bounded GGUF metadata traversal; the new module uses them only for a second pass over the few selected numeric arrays, because `inspect_gguf` intentionally summarizes arrays.

### Task 1: Bind the one-session AR profile

**Files:** Create `C:\Projects\strix-alloy-research\integration\scripts\gufo_control\model_identity.py`; test `C:\Projects\strix-alloy-research\integration\tests\gufo\test_model_identity.py`.

**Interfaces:** `validate_ar4k_model(first_shard: str | Path, *, pins: ProfilePins = AR4K_PINS) -> ValidatedModel` raises `ModelIdentityError` on any mismatch. `ValidatedModel.first_shard` is the only model path a later launcher may pass to GUFO. `ValidatedModel.revision` is the pinned, declared source revision, **not** a revision read from a GGUF field. The caller must invoke this function again immediately before child creation; a prior result is not a lease on mutable files.

- [ ] **Step 1: Add the failing tests.** Create `tests/gufo/test_model_identity.py` with this complete content. The fixture creates a metadata-only first shard and two tiny tensor shards; it builds its own expected descriptor pins, so no real weights are touched.

```python
import hashlib
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gufo_control.model_identity import (
    ModelIdentityError, ProfilePins, ShardPin, validate_ar4k_model,
)


def s(value):
    data = value.encode()
    return struct.pack('<Q', len(data)) + data


def m(key, kind, value):
    return s(key) + struct.pack('<I', kind) + value


def u(key, value):
    return m(key, 4, struct.pack('<I', value))


def arr(key, values):
    return m(key, 9, struct.pack('<IQ', 4, len(values))
             + b''.join(struct.pack('<I', x) for x in values))


def gguf(metadata, tensor_count):
    tensors = b''.join(s('w' + str(i)) + struct.pack('<I', 2)
                       + struct.pack('<QQIQ', 4, 4, 0, i * 64)
                       for i in range(tensor_count))
    descriptor = (b'GGUF' + struct.pack('<IQQ', 3, tensor_count, len(metadata))
                  + b''.join(metadata) + tensors)
    padded = (len(descriptor) + 31) // 32 * 32
    return descriptor + bytes(padded - len(descriptor)) + bytes(64 * tensor_count), len(descriptor)


class ModelIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'models'
        self.root.mkdir()
        files = (
            gguf([m('general.architecture', 8, s('qwen4exp')),
                  u('split.no', 0), u('split.count', 3),
                  u('split.tensors.count', 2), arr('geometry', [4, 4])], 0),
            gguf([u('split.no', 1), u('split.count', 3),
                  u('split.tensors.count', 2)], 1),
            gguf([u('split.no', 2), u('split.count', 3),
                  u('split.tensors.count', 2)], 1),
        )
        pins = []
        for index, (data, end) in enumerate(files):
            name = f'shard-{index + 1}.gguf'
            (self.root / name).write_bytes(data)
            pins.append(ShardPin(name, len(data), end,
                                 hashlib.sha256(data[:end]).hexdigest(),
                                 0 if index == 0 else 1, index))
        self.pins = ProfilePins('test-revision', tuple(pins),
                                {'general.architecture': 'qwen4exp'},
                                {'geometry': (4, 4)})
        self.first = self.root / 'shard-1.gguf'

    def validate(self, pins=None):
        return validate_ar4k_model(self.first, pins=pins or self.pins)

    def rewrite_shard(self, index, metadata, tensor_count):
        data, end = gguf(metadata, tensor_count)
        pin = self.pins.shards[index]
        (self.root / pin.filename).write_bytes(data)
        changed = list(self.pins.shards)
        changed[index] = replace(
            pin, size_bytes=len(data), descriptor_end=end,
            descriptor_sha256=hashlib.sha256(data[:end]).hexdigest(),
            tensor_count=tensor_count)
        return replace(self.pins, shards=tuple(changed))

    def test_accepts_zero_tensor_first_shard_and_returns_only_target(self):
        result = self.validate()
        self.assertEqual(result.first_shard, self.first.resolve())
        self.assertEqual(result.revision, 'test-revision')
        self.assertEqual(result.context_capacity, 4096)
        self.assertEqual(result.sessions, 1)
        self.assertFalse(result.mtp_enabled)

    def test_rejects_size_and_descriptor_changes_on_each_shard(self):
        for index, pin in enumerate(self.pins.shards):
            with self.subTest(index=index, mismatch='size'):
                changed = list(self.pins.shards)
                changed[index] = replace(pin, size_bytes=pin.size_bytes + 1)
                with self.assertRaises(ModelIdentityError):
                    self.validate(replace(self.pins, shards=tuple(changed)))
            with self.subTest(index=index, mismatch='descriptor'):
                changed = list(self.pins.shards)
                changed[index] = replace(pin, descriptor_sha256='0' * 64)
                with self.assertRaises(ModelIdentityError):
                    self.validate(replace(self.pins, shards=tuple(changed)))

    def test_rejects_missing_or_wrong_split_and_tensor_count(self):
        wrong = list(self.pins.shards)
        wrong[0] = replace(wrong[0], tensor_count=1)
        with self.assertRaises(ModelIdentityError):
            self.validate(replace(self.pins, shards=tuple(wrong)))
        (self.root / 'shard-3.gguf').unlink()
        with self.assertRaises(ModelIdentityError):
            self.validate()

    def test_rejects_wrong_split_metadata_with_matching_descriptor_pin(self):
        for key, value in (('split.no', 0), ('split.count', 4),
                           ('split.tensors.count', 3)):
            with self.subTest(key=key):
                metadata = {'split.no': 1, 'split.count': 3,
                            'split.tensors.count': 2}
                metadata[key] = value
                pins = self.rewrite_shard(1, [u(k, v) for k, v in metadata.items()], 1)
                with self.assertRaises(ModelIdentityError):
                    self.validate(pins)

    def test_rejects_nextn_flag_with_matching_descriptor_pin(self):
        metadata = [m('general.architecture', 8, s('qwen4exp')),
                    u('split.no', 0), u('split.count', 3),
                    u('split.tensors.count', 2), arr('geometry', [4, 4]),
                    m('qwen4exp.nextn_shared_target_tensors', 7, b'\x01')]
        pins = self.rewrite_shard(0, metadata, 0)
        with self.assertRaises(ModelIdentityError):
            self.validate(pins)

    def test_rejects_wrong_geometry_even_when_pins_are_updated(self):
        with self.assertRaises(ModelIdentityError):
            self.validate(replace(self.pins, arrays={'geometry': (4, 0)}))

    def test_rejects_projector_in_model_directory_and_parent(self):
        for directory in (self.root, self.root.parent):
            with self.subTest(directory=directory):
                projector = directory / 'mmproj-BF16.gguf'
                projector.write_bytes(b'')
                try:
                    with self.assertRaises(ModelIdentityError):
                        self.validate()
                finally:
                    projector.unlink()

    def test_rejects_wrong_first_path_and_sidecar_substitution(self):
        with self.assertRaises(ModelIdentityError):
            validate_ar4k_model(self.root / 'shard-2.gguf', pins=self.pins)
        bad = list(self.pins.shards)
        # A sidecar cannot be substituted for any of the three declared shards.
        bad[2] = replace(bad[2], filename='mtp.gguf')
        with self.assertRaises(ModelIdentityError):
            self.validate(replace(self.pins, shards=tuple(bad)))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Confirm the tests fail before implementation.** From the integration worktree, run `python -m unittest discover -s tests/gufo -p test_model_identity.py -v` with `PYTHONPATH` set to the worktree's `scripts` directory. Expected: import failure for `gufo_control.model_identity`.

- [ ] **Step 3: Implement the profile module.** Create `scripts/gufo_control/model_identity.py` with this complete content. The production constants come from `reports/gufo-descriptor-pins-20260926.md` and `reports/gufo-ar4k-envelope-20260926.md`.

```python
"""Bounded identity check for the first GUFO Flash Next AR4k model profile."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .gguf import GgufError, MAX_HEADER, SCALARS, _Reader, inspect_gguf


class ModelIdentityError(ValueError):
    """The selected files do not match the pinned first AR4k profile."""


@dataclass(frozen=True)
class ShardPin:
    filename: str
    size_bytes: int
    descriptor_end: int
    descriptor_sha256: str
    tensor_count: int
    split_no: int


@dataclass(frozen=True)
class ProfilePins:
    revision: str
    shards: tuple[ShardPin, ShardPin, ShardPin]
    first_scalars: dict
    arrays: dict


@dataclass(frozen=True)
class ValidatedModel:
    first_shard: Path
    revision: str
    context_capacity: int = 4096
    sessions: int = 1
    mtp_enabled: bool = False


AR4K_PINS = ProfilePins(
    revision='38bb39ee97821de2c9009abb7e93950eec396e66',
    shards=(
        ShardPin('Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf',
                 10946624, 10946618,
                 '9cd7aa82ad189b54ea3c97d1c89463b4473f9f6bd9472b8381c42236e5915de8', 0, 0),
        ShardPin('Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf',
                 49835229856, 23584,
                 '65aed4c0d6ffeda13b7188179f3c4d9764076012eedacf7cc5e4df52f46d7f70', 373, 1),
        ShardPin('Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf',
                 43836407744, 54317,
                 'f23293bb029821907bf79414b2a88d698ce66e87b274602d120bbcb3fe08c4a9', 851, 2),
    ),
    first_scalars={
        'general.architecture': 'qwen4exp',
        'qwen4exp.block_count': 48,
        'qwen4exp.context_length': 262144,
        'qwen4exp.embedding_length': 2560,
        'qwen4exp.attention.head_count': 24,
        'qwen4exp.attention.head_count_kv': 2,
        'qwen4exp.attention.key_length': 256,
        'qwen4exp.attention.value_length': 256,
        'qwen4exp.attention.layer_norm_rms_epsilon': 9.999999974752427e-7,
        'qwen4exp.full_attention_interval': 4,
        'qwen4exp.expert_count': 512,
        'qwen4exp.expert_used_count': 10,
        'qwen4exp.expert_feed_forward_length': 640,
        'qwen4exp.expert_shared_feed_forward_length': 640,
        'qwen4exp.ssm.conv_kernel': 4,
        'qwen4exp.ssm.state_size': 128,
        'qwen4exp.ssm.group_count': 16,
        'qwen4exp.ssm.time_step_rank': 48,
        'qwen4exp.ssm.inner_size': 6144,
        'qwen4exp.hyper_connection.count': 4,
        'qwen4exp.hyper_connection.low_rank': 320,
        'qwen4exp.attention.indexer.head_count': 4,
        'qwen4exp.attention.indexer.key_length': 128,
        'qwen4exp.attention.indexer.top_k': 2048,
        'qwen4exp.rope.dimension_count': 64,
        'qwen4exp.rope.freq_base': 10000000.0,
        'qwen4exp.ple.ngram_size': 3,
        'qwen4exp.ple.heads_per_ngram': 8,
        'qwen4exp.ple.conv_kernel': 4,
        'qwen4exp.ple.eos_token_id': 248044,
        'qwen4exp.ple.image_token_id': 248056,
        'qwen4exp.embedding_length_per_layer_input': 160,
    },
    arrays={
        'qwen4exp.attention.compress_ratios': (0, 0, 0, 4) * 12,
        'qwen4exp.rope.dimension_sections': (11, 11, 10, 0),
        'qwen4exp.ple.layers': (1,),
        'qwen4exp.ple.head_offsets': (
            0, 20000003, 40000026, 60000059, 80000106, 100000165,
            120000228, 140000297, 160000374, 180000455, 200000548,
            220000655, 240000802, 260000955, 280001114, 300001275),
        'qwen4exp.ple.head_vocab_sizes': (
            20000003, 20000023, 20000033, 20000047, 20000059, 20000063,
            20000069, 20000077, 20000081, 20000093, 20000107, 20000147,
            20000153, 20000159, 20000161, 20000171),
        'qwen4exp.ple.layer_multipliers': (
            23703573157769, 20109073645365, 8052911324071),
    },
)


def _numeric_arrays(path: Path, wanted: dict) -> dict:
    """Retain only requested short numeric arrays from the bounded header."""
    found = {}
    with path.open('rb', buffering=0) as stream:
        reader = _Reader(stream, os.fstat(stream.fileno()).st_size)
        if reader.advance(4) != b'GGUF' or reader.number('I') != 3:
            raise GgufError('expected GGUF v3')
        reader.number('Q')  # tensor count; inspect_gguf validates the directory
        count = reader.number('Q')
        if count > 100000:
            raise GgufError('metadata count exceeds limit')
        for _ in range(count):
            key = reader.string(limit=64 << 10)
            kind = reader.number('I')
            if key not in wanted:
                reader.value(kind)
                continue
            if kind != 9 or key in found:
                raise ModelIdentityError(f'invalid profile array: {key}')
            subtype, length = reader.number('I'), reader.number('Q')
            if subtype not in SCALARS or length > 256:
                raise ModelIdentityError(f'invalid profile array type/count: {key}')
            found[key] = tuple(reader.number(SCALARS[subtype]) for _ in range(length))
        if stream.tell() > MAX_HEADER:
            raise GgufError('descriptor exceeds limit')
    return found


def _descriptor_digest(path: Path, end: int, expected_size: int, expected_mtime: int) -> str:
    if not 0 <= end <= MAX_HEADER:
        raise ModelIdentityError('descriptor length outside bound')
    digest = hashlib.sha256()
    with path.open('rb', buffering=0) as stream:
        before = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (expected_size, expected_mtime):
            raise ModelIdentityError('file changed before descriptor hashing')
        remaining = end
        while remaining:
            block = stream.read(min(1 << 20, remaining))
            if not block:
                raise ModelIdentityError('truncated descriptor')
            digest.update(block)
            remaining -= len(block)
        after = os.fstat(stream.fileno())
        if (after.st_size, after.st_mtime_ns) != (expected_size, expected_mtime):
            raise ModelIdentityError('file changed during descriptor hashing')
    return digest.hexdigest()


def _reject_projector(model_dir: Path) -> None:
    for directory in (model_dir, model_dir.parent):
        try:
            if any(entry.name.casefold() == 'mmproj-bf16.gguf' for entry in directory.iterdir()):
                raise ModelIdentityError(f'GUFO projector auto-discovery candidate: {directory}')
        except OSError as error:
            raise ModelIdentityError(f'cannot inspect projector directory: {directory}') from error


def validate_ar4k_model(first_shard: str | Path, *, pins: ProfilePins = AR4K_PINS) -> ValidatedModel:
    """Validate the pinned three-shard target without reading tensor payloads."""
    try:
        first = Path(first_shard).resolve(strict=True)
        if first.name != pins.shards[0].filename:
            raise ModelIdentityError('first shard path/name mismatch')
        _reject_projector(first.parent)
        total = 0
        for pin in pins.shards:
            candidate = first.parent / pin.filename
            path = candidate.resolve(strict=True)
            if path != candidate or path.parent != first.parent:
                raise ModelIdentityError(f'shard escapes model directory: {pin.filename}')
            report = inspect_gguf(path)
            if (report['size_bytes'], report['descriptor_end'], len(report['tensors'])) != (
                    pin.size_bytes, pin.descriptor_end, pin.tensor_count):
                raise ModelIdentityError(f'shard size/directory mismatch: {pin.filename}')
            if _descriptor_digest(path, pin.descriptor_end,
                                  report['size_bytes'], report['mtime_ns']) != pin.descriptor_sha256:
                raise ModelIdentityError(f'shard descriptor mismatch: {pin.filename}')
            metadata = report['metadata']
            for key, value in {'split.no': pin.split_no, 'split.count': 3,
                               'split.tensors.count': sum(
                                   item.tensor_count for item in pins.shards)}.items():
                if type(metadata.get(key)) is not int or metadata[key] != value:
                    raise ModelIdentityError(f'shard split metadata mismatch: {pin.filename}: {key}')
            if pin.split_no == 0:
                for key, value in pins.first_scalars.items():
                    if type(metadata.get(key)) is not type(value) or metadata[key] != value:
                        raise ModelIdentityError(f'first shard scalar mismatch: {key}')
                if any(key.startswith('qwen4exp.nextn_') for key in metadata):
                    raise ModelIdentityError('MTP metadata in AR first shard')
                if _numeric_arrays(path, pins.arrays) != pins.arrays:
                    raise ModelIdentityError('first shard geometry arrays mismatch')
            elif set(metadata) != {'split.no', 'split.count', 'split.tensors.count'}:
                raise ModelIdentityError(f'unexpected metadata in split shard: {pin.filename}')
            total += len(report['tensors'])
        if total != sum(pin.tensor_count for pin in pins.shards):
            raise ModelIdentityError('total tensor count mismatch')
        _reject_projector(first.parent)
        return ValidatedModel(first, pins.revision)
    except (GgufError, OSError) as error:
        raise ModelIdentityError(f'model identity inspection failed: {error}') from error
```

- [ ] **Step 4: Run the focused and full offline suites.** From the integration worktree in PowerShell, run `$env:PYTHONPATH = 'C:\Projects\strix-alloy-research\integration\scripts'`, then `python -m unittest discover -s tests/gufo -p test_model_identity.py -v`, followed by `python -m unittest discover -s tests/gufo -v`. Expected: all eight focused identity tests and the full GUFO offline suite pass. Set this only in the test subprocess's environment; it does not change the user's persistent configuration. These tests use only temporary tiny files and must not access the live model, GPU, HIP, WSL, or a server.

- [ ] **Step 5: Review the production pins and run a metadata-only real-file check only after code review.** The pin report gives the compress-ratio values but not the key spelling; pinned GUFO `src/models/qwen38_flash_next/config.cpp:138` reads `key("attention.compress_ratios")`, yielding `qwen4exp.attention.compress_ratios`. Confirm that exact key and all other pinned array keys in the existing bounded header before accepting a real-file result. Run `validate_ar4k_model` against `C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf`. Expected: a `ValidatedModel` with context 4096, sessions 1, no MTP and the pinned revision. A failure is a refused profile, not permission to weaken a pin. Do not read tensor bodies.

- [ ] **Step 6: Integrate at the later launch boundary.** The lifecycle controller must call `validate_ar4k_model` immediately before child creation and pass only `result.first_shard` as the model path. Keep projector checks in that call; do not accept a stale earlier validation result. This plan does not implement or authorize that controller, admission, or process creation.

- [ ] **Step 7: Review and commit only the owned implementation files.** Inspect `git diff -- scripts/gufo_control/model_identity.py tests/gufo/test_model_identity.py` and `git status --short` from the integration worktree. Stage only `scripts/gufo_control/model_identity.py` and `tests/gufo/test_model_identity.py`, then commit with `git commit -m "feat: bind GUFO AR4k model identity"`. Record the passing test command and any real-file header-only acceptance outcome in the task report. Do not stage unrelated integration, source, model, or report files.

## Review gates and limits

- The descriptor fingerprint and exact byte size pin header geometry and layout only. A weight-body modification with unchanged size/header is outside this check. Do not label the returned revision as a full-file cryptographic verification.
- The model directory and its parent remain mutable after validation; immediate revalidation narrows the race but cannot make it atomic. A future launcher should hold appropriate file handles/identity checks through process creation if it needs a stronger guarantee.
- The pin report omits the literal compress-ratio metadata key; the pinned GUFO source supplies its expected spelling. Production acceptance must still confirm the actual existing header has that key and the listed values. No real-file validation has been run as part of this plan.
- Profile identity does not establish IQ4_XS runtime support, model correctness, memory safety, or benchmark performance.
