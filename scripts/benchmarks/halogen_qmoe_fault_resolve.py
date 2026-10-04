"""Resolve captured RIPs on the ordinary host thread after a caught native fault.

This never runs from VEH, changes exception context, loads a provider, reads
tensor memory or guesses a module. The raw collector records remain unchanged.
Resolution is a later observation and cannot prove attribution across unloads.
"""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path


class MemoryBasicInformation(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def resolve_captured_faults(path):
    """Read at most eight bounded metadata records and query their current maps."""
    if ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(MemoryBasicInformation) != 48:
        raise ValueError("Native x64 Windows memory-query ABI required")
    path = Path(path)
    if not path.exists():
        return []
    if path.stat().st_size > 8 * 8192:
        raise ValueError("Fault collector output exceeds its bound")
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) > 8:
        raise ValueError("Fault collector record limit exceeded")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleExW.argtypes = [wintypes.DWORD, ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.c_void_p)]
    kernel.GetModuleHandleExW.restype = wintypes.BOOL
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    kernel.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(MemoryBasicInformation),
                                    ctypes.c_size_t]
    kernel.VirtualQuery.restype = ctypes.c_size_t
    resolved = []
    for line in lines:
        record = json.loads(line)
        rip = int(record["rip"], 16)
        module = ctypes.c_void_p()
        info = MemoryBasicInformation()
        result = {"record": record.get("record"), "rip": hex(rip),
                  "scope": "ordinary host after caught fault; current module map",
                  "raw_collector_module_lookup": record.get("module_lookup"),
                  "module_lookup": "unknown", "module_path": None,
                  "module_base": None, "module_offset": None}
        if kernel.VirtualQuery(ctypes.c_void_p(rip), ctypes.byref(info), ctypes.sizeof(info)):
            result["memory_region"] = {
                "base": hex(info.BaseAddress or 0),
                "allocation_base": hex(info.AllocationBase or 0),
                "region_bytes": info.RegionSize, "state": info.State,
                "protection": info.Protect, "type": info.Type}
        # FROM_ADDRESS | UNCHANGED_REFCOUNT: query only; never load/free a DLL.
        if kernel.GetModuleHandleExW(6, ctypes.c_void_p(rip), ctypes.byref(module)):
            buffer = ctypes.create_unicode_buffer(32768)
            count = kernel.GetModuleFileNameW(module, buffer, len(buffer))
            if 0 < count < len(buffer) and module.value and rip >= module.value:
                result.update(module_lookup="resolved", module_path=buffer.value,
                              module_base=hex(module.value), module_offset=hex(rip - module.value))
            else:
                result["module_path_error"] = ctypes.get_last_error()
        else:
            result["module_lookup_error"] = ctypes.get_last_error()
        resolved.append(result)
    return resolved
