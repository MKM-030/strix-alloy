"""Rank3 activation/output diagnostic; no full MTP or speed claim.

Root must call only inside the existing exclusive owned-process memory guard,
after complete frozen bank/graph/Header/provider/ORT-stage verification, WinML
bootstrap, and adding the pinned provider and ORT DLL search directories.
Arm the diagnostic native fault collector before this hook; pass its direct refresh export. This creates its own
public CAPI session; do not create an additional Python inference session.
No ORT import or Python internal pointer access is involved.
"""
import ctypes
import hashlib
from pathlib import Path


class RetainedReceipt(ctypes.Structure):
    _fields_ = [
        ("schema", ctypes.c_uint32),
        ("api_version", ctypes.c_uint32),
        ("session_creations", ctypes.c_uint32),
        ("allocator_acquired", ctypes.c_uint32),
        ("allocator_type", ctypes.c_uint32),
        ("allocator_mem_type", ctypes.c_int32),
        ("allocator_device_type", ctypes.c_uint32),
        ("calls_attempted", ctypes.c_uint32),
        ("calls_completed", ctypes.c_uint32),
        ("zero_outputs", ctypes.c_uint32),
        ("cleanup_completed", ctypes.c_uint32),
        ("provider_unregistered", ctypes.c_uint32),
        ("session_creation_attempts", ctypes.c_uint32),
        ("allocator_session_created", ctypes.c_uint32),
        ("allocator_session_released", ctypes.c_uint32),
        ("qpc_frequency", ctypes.c_uint64),
        ("call_ticks", ctypes.c_uint64 * 2),
    ]


def invoke_reviewed_diagnostic_native(library_path, expected_library_sha256, ort_path,
                           ep_path, model_path, header_path, profile_prefix, refresh_callback):
    """Invoke two frozen synthetic calls with a quiescent module refresh before each run."""
    if (ctypes.sizeof(RetainedReceipt) != 88
            or RetainedReceipt.qpc_frequency.offset != 64
            or RetainedReceipt.call_ticks.offset != 72):
        raise ValueError("Unexpected x64 native receipt ABI")
    library_path = Path(library_path).resolve(strict=True)
    if hashlib.sha256(library_path.read_bytes()).hexdigest() != expected_library_sha256:
        raise ValueError("Root-reviewed native library changed")
    ort_path = Path(ort_path).resolve(strict=True)
    ep_path = Path(ep_path).resolve(strict=True)
    model_path = Path(model_path).resolve(strict=True)
    header_path = Path(header_path).resolve(strict=True)
    profile_prefix = Path(profile_prefix).absolute()
    if profile_prefix.parent.resolve(strict=True) != profile_prefix.parent:
        raise ValueError("Profile prefix must have a canonical existing parent")
    if list(profile_prefix.parent.glob(profile_prefix.name + "*")):
        raise ValueError("Native profiling prefix must be fresh")
    receipt = RetainedReceipt()
    outputs = ctypes.create_string_buffer(2 * 5120)
    error = ctypes.create_string_buffer(4096)
    library = ctypes.CDLL(str(library_path))
    entry = library.qmoe_rank3_allocator_run
    entry.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                      ctypes.c_char_p, ctypes.c_char_p, ctypes.c_wchar_p,
                      ctypes.POINTER(RetainedReceipt), ctypes.c_void_p, ctypes.c_size_t,
                      ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    entry.restype = ctypes.c_int
    if not getattr(refresh_callback, "value", None):
        raise ValueError("Pinned native refresh callback address required")
    code = entry(str(ort_path), str(ep_path), str(model_path),
                 str(model_path.parent).encode("utf-8"), header_path.name.encode("utf-8"),
                 str(profile_prefix), ctypes.byref(receipt), outputs, len(outputs),
                 error, len(error), refresh_callback)
    result = {name: getattr(receipt, name) for name, _ in RetainedReceipt._fields_
              if name != "call_ticks"}
    result.update(return_code=code, error=error.value.decode("utf-8", errors="replace"),
                  call_ticks=list(receipt.call_ticks),
                  allocator_scope="public CreateAllocator on retained trivial Light session; exact OGA Cpu/device/default key",
                  equivalence_to_oga_trivial_session_initialization_proven=False,
                  allocator_holder_scope="function-local across one bounded invocation; not global across models",
                  complete_mtp_proven=False, speed_gain_established=False)
    if receipt.qpc_frequency and receipt.calls_completed:
        result["host_call_ms"] = [tick * 1000 / receipt.qpc_frequency
                                  for tick in receipt.call_ticks[:receipt.calls_completed]]
    raw = outputs.raw
    # Native calls_completed precedes zero validation and output memcpy. A
    # returned call with invalid output leaves this slot's sentinel untouched.
    # zero_outputs advances only on the path that copies a validated slot;
    # a fault during that copy raises instead of returning this native receipt.
    result["output_sha256"] = [hashlib.sha256(raw[i * 5120:(i + 1) * 5120]).hexdigest()
                               for i in range(receipt.zero_outputs)]
    result["output_hash_scope"] = "validated zero-bank outputs copied into output_receipts"
    result["passed"] = (code == 0 and receipt.schema == 2 and receipt.api_version == 29
                        and receipt.session_creations == receipt.session_creation_attempts == 2
                        and receipt.allocator_session_created == receipt.allocator_session_released == 1
                        and receipt.allocator_acquired == 1
                        and receipt.calls_attempted == receipt.calls_completed == receipt.zero_outputs == 2
                        and receipt.cleanup_completed == receipt.provider_unregistered == 1)
    return result
