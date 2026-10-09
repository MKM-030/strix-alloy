"""Portable local safetensors loader: no safetensors package or network access."""
from __future__ import annotations

import mmap
import sys
from types import MappingProxyType

from contract import (CHECKPOINT_SHA256, inspect_safetensors, numel, sha256_file,
                      validate_checkpoint_manifest)


def cpu_torch():
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Numerical reference requires an existing PyTorch CPU runtime") from exc
    return torch


class OwnedTensorFile:
    """Private copy-on-write map held by both this object and frombuffer tensors.

    There is deliberately no close() or context-manager unmap. Borrowed tensor
    storage must remain mapped until all consumers are gone. ACCESS_COPY never
    modifies the source file. Consumers must treat exposed tensors as read-only;
    the numerical provider owns cloned target bindings and keeps model views
    private. No pickle/torch.load or automatic download is used.
    """
    def __init__(self, path, *, expected_sha256: str, pinned_drafter=False):
        if sys.byteorder != "little":
            raise RuntimeError("This zero-copy reference loader requires a little-endian CPU host")
        if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)):
            raise ValueError("An exact file SHA256 is required")
        self.manifest = inspect_safetensors(path)
        if pinned_drafter:
            validate_checkpoint_manifest(self.manifest)
            if expected_sha256 != CHECKPOINT_SHA256:
                raise ValueError("Different drafter SHA256 is not the pinned supplied checkpoint")
        self.sha256 = sha256_file(self.manifest.path)
        if self.sha256 != expected_sha256:
            raise ValueError("Tensor file SHA256 differs from its immutable receipt")
        torch = cpu_torch()
        with self.manifest.path.open("rb") as f:
            self._mapping = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_COPY)
        self._tensors = {}
        for name, info in self.manifest.tensors.items():
            dtype = {"BF16": torch.bfloat16, "F32": torch.float32}[info.dtype]
            tensor = torch.frombuffer(self._mapping, dtype=dtype, count=numel(info.shape),
                                      offset=self.manifest.data_offset + info.start).reshape(info.shape)
            if tensor.device.type != "cpu":
                raise RuntimeError("Offline loader produced a non-CPU tensor")
            self._tensors[name] = tensor
        self.tensors = MappingProxyType(self._tensors)


def load_drafter(path):
    return OwnedTensorFile(path, expected_sha256=CHECKPOINT_SHA256, pinned_drafter=True)
