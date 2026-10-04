"""One read-only CPU/paging snapshot; orchestration and persistence belong to caller.

host_snapshot(pids) uses only Windows getters. guest_snapshot(engine_pid) reads
procfs in the caller's Linux/PID namespace. Neither starts a process, polls,
sleeps, writes a file, purges a cache, or changes engine/system settings.
Send this source plus a single guest_snapshot call to Python stdin if needed.

Windows PageFaultCount combines soft and hard faults; it is NOT a hard/major
fault count. Windows IO counters are process IO, not physical disk traffic.
Linux system pgfault includes minor and major faults; /proc/PID/stat minflt
and majflt count the process separately from its waited-for children.
Linux IO rchar counts read characters, including cache hits; read_bytes counts
bytes attributed to storage reads. Neither alone identifies the lookup file.
Each side has its own monotonic clock; epoch timestamps do not calibrate it
against the other side. Snapshots are bounded acquisitions, not atomic reads.
"""

import ctypes as C
import json
import os
import socket
import time
from pathlib import Path


def _stamp():
    value = {"epoch_ns": time.time_ns(), "perf_counter_ns": time.perf_counter_ns()}
    if hasattr(time, "CLOCK_MONOTONIC_RAW"):
        value["monotonic_raw_ns"] = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    return value


class _FileTime(C.Structure):
    _fields_ = [("low", C.c_uint32), ("high", C.c_uint32)]


class _PerformanceInfo(C.Structure):
    _fields_ = [("cb", C.c_uint32)] + [
        (name, C.c_size_t) for name in (
            "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal",
            "PhysicalAvailable", "SystemCache", "KernelTotal", "KernelPaged",
            "KernelNonpaged", "PageSize")
    ] + [(name, C.c_uint32) for name in ("HandleCount", "ProcessCount", "ThreadCount")]


class _MemoryCounters(C.Structure):
    _fields_ = [("cb", C.c_uint32), ("PageFaultCount", C.c_uint32)] + [
        (name, C.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")
    ]


class _IoCounters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


def _windows_api():
    if os.name != "nt":
        raise RuntimeError("host_snapshot requires Windows")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    psapi = C.WinDLL("psapi", use_last_error=True)
    api = {}
    for library, name, result, arguments in (
        (psapi, "GetPerformanceInfo", C.c_int, [C.c_void_p, C.c_uint32]),
        (kernel, "GetSystemTimes", C.c_int, [C.c_void_p] * 3),
        (kernel, "GetTickCount64", C.c_uint64, []),
        (kernel, "OpenProcess", C.c_void_p, [C.c_uint32, C.c_int, C.c_uint32]),
        (kernel, "CloseHandle", C.c_int, [C.c_void_p]),
        (kernel, "GetProcessTimes", C.c_int, [C.c_void_p] * 5),
        (kernel, "QueryFullProcessImageNameW", C.c_int,
         [C.c_void_p, C.c_uint32, C.c_void_p, C.c_void_p]),
        (psapi, "GetProcessMemoryInfo", C.c_int, [C.c_void_p, C.c_void_p, C.c_uint32]),
        (kernel, "GetProcessIoCounters", C.c_int, [C.c_void_p, C.c_void_p]),
        (kernel, "GetPriorityClass", C.c_uint32, [C.c_void_p]),
    ):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        api[name] = function
    return api


def _win_error(operation):
    return {"operation": operation, "winerror": C.get_last_error()}


def _filetime(value):
    return (int(value.high) << 32) | int(value.low)


def host_snapshot(pids):
    """Capture one host snapshot for explicit PIDs; denied/exited PIDs stay visible."""
    pids = sorted(set(int(pid) for pid in pids))
    if any(pid <= 0 or pid > 0xffffffff for pid in pids):
        raise ValueError("Windows PIDs must be positive DWORD values")
    api = _windows_api()
    result = {"schema_version": 1, "kind": "windows_host", "before": _stamp(),
              "identity": {"computer_name": socket.gethostname(),
                           "uptime_ms": int(api["GetTickCount64"]())},
              "errors": [], "processes": []}
    memory = _PerformanceInfo()
    memory.cb = C.sizeof(memory)
    if api["GetPerformanceInfo"](C.byref(memory), C.sizeof(memory)):
        result["memory"] = {
            "page_size_bytes": int(memory.PageSize),
            "pages": {name: int(getattr(memory, name)) for name, _ in memory._fields_
                      if name not in ("cb", "PageSize", "HandleCount", "ProcessCount", "ThreadCount")},
            "counts": {name: int(getattr(memory, name))
                       for name in ("HandleCount", "ProcessCount", "ThreadCount")},
        }
        result["memory"]["bytes"] = {
            name: pages * int(memory.PageSize) for name, pages in result["memory"]["pages"].items()}
    else:
        result["errors"].append(_win_error("GetPerformanceInfo"))
    system = [_FileTime() for _ in range(3)]
    result["system_cpu_before"] = _stamp()
    if api["GetSystemTimes"](*(C.byref(value) for value in system)):
        result["system_cpu_100ns"] = dict(zip(("idle", "kernel_including_idle", "user"),
                                                  map(_filetime, system)))
    else:
        result["errors"].append(_win_error("GetSystemTimes"))
    result["system_cpu_after"] = _stamp()
    for pid in pids:
        entry = {"pid": pid, "before": _stamp(), "errors": []}
        handle = api["OpenProcess"](0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            entry["errors"].append(_win_error("OpenProcess.QUERY_LIMITED_INFORMATION"))
        else:
            try:
                times = [_FileTime() for _ in range(4)]
                if api["GetProcessTimes"](handle, *(C.byref(value) for value in times)):
                    entry["creation_time_100ns"] = _filetime(times[0])
                    entry["exit_time_100ns"] = _filetime(times[1])
                    entry["cpu_100ns"] = {"kernel": _filetime(times[2]), "user": _filetime(times[3])}
                else:
                    entry["errors"].append(_win_error("GetProcessTimes"))
                image, length = C.create_unicode_buffer(32768), C.c_uint32(32768)
                if api["QueryFullProcessImageNameW"](handle, 0, image, C.byref(length)):
                    entry["image"] = image.value
                else:
                    entry["errors"].append(_win_error("QueryFullProcessImageNameW"))
                priority = int(api["GetPriorityClass"](handle))
                if priority:
                    entry["priority_class"] = priority
                else:
                    entry["errors"].append(_win_error("GetPriorityClass"))
                io = _IoCounters()
                if api["GetProcessIoCounters"](handle, C.byref(io)):
                    entry["io_counters"] = {name: int(getattr(io, name)) for name, _ in io._fields_}
                else:
                    entry["errors"].append(_win_error("GetProcessIoCounters"))
                # Memory needs VM_READ in addition to query rights; optional failures are explicit.
                memory_handle = api["OpenProcess"](0x1010, False, pid)
                if not memory_handle:
                    entry["errors"].append(_win_error("OpenProcess.QUERY_LIMITED_INFORMATION|VM_READ"))
                else:
                    try:
                        counters = _MemoryCounters()
                        counters.cb = C.sizeof(counters)
                        if api["GetProcessMemoryInfo"](memory_handle, C.byref(counters), C.sizeof(counters)):
                            entry["page_fault_count_soft_and_hard"] = int(counters.PageFaultCount)
                            entry["memory_bytes"] = {name: int(getattr(counters, name))
                                                     for name, _ in counters._fields_
                                                     if name not in ("cb", "PageFaultCount")}
                        else:
                            entry["errors"].append(_win_error("GetProcessMemoryInfo"))
                    finally:
                        if not api["CloseHandle"](memory_handle):
                            entry["errors"].append(_win_error("CloseHandle.memory"))
            finally:
                if not api["CloseHandle"](handle):
                    entry["errors"].append(_win_error("CloseHandle.process"))
        entry["after"] = _stamp()
        entry["identity_valid"] = "creation_time_100ns" in entry
        result["processes"].append(entry)
    result["after"] = _stamp()
    result["valid"] = "memory" in result and "system_cpu_100ns" in result
    return result


def _proc_stat(text, engine_pid):
    end = text.rfind(")")
    start = text.find("(")
    if start < 0 or end < start or int(text[:start].strip()) != engine_pid:
        raise ValueError("invalid engine /proc/PID/stat identity")
    fields = text[end + 1:].split()  # field 3 onward; comm may contain spaces or ')'.
    if len(fields) < 22:
        raise ValueError("short engine /proc/PID/stat")
    return {"pid": engine_pid, "comm": text[start + 1:end], "state": fields[0],
            "ppid": int(fields[1]), "start_ticks": int(fields[19]),
            "counters": {name: int(fields[index]) for name, index in (
                ("minflt", 7), ("children_minflt", 8), ("majflt", 9), ("children_majflt", 10),
                ("utime_ticks", 11), ("stime_ticks", 12),
                ("children_utime_ticks", 13), ("children_stime_ticks", 14))},
            "num_threads": int(fields[17]), "virtual_bytes": int(fields[20]),
            "rss_pages": int(fields[21]),
            "delayacct_blkio_ticks": int(fields[39]) if len(fields) > 39 else None}


def guest_snapshot(engine_pid):
    """Read once in the engine's Linux/PID namespace; no container/WSL launch."""
    engine_pid = int(engine_pid)
    if engine_pid <= 0:
        raise ValueError("engine PID must be positive")
    if os.name != "posix":
        raise RuntimeError("guest_snapshot requires Linux procfs")
    result = {"schema_version": 1, "kind": "linux_guest", "before": _stamp(),
              "identity": {"engine_pid": engine_pid}, "errors": [], "optional_errors": []}
    try:
        result["identity"].update(boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                                  pid_namespace=os.readlink("/proc/self/ns/pid"))
        result["clock_ticks_per_second"] = int(os.sysconf("SC_CLK_TCK"))
        result["page_size_bytes"] = int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError) as exc:
        result["errors"].append({"operation": "guest_identity", "error": str(exc)})
    for name, path in (("stat", "/proc/stat"), ("vmstat", "/proc/vmstat"),
                       ("meminfo", "/proc/meminfo"), ("engine", f"/proc/{engine_pid}/stat")):
        try:
            text = Path(path).read_text()
            if name == "stat":
                lines = text.splitlines()
                cpu = next(line.split()[1:] for line in lines if line.startswith("cpu "))
                names = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice")
                if len(cpu) < 8:
                    raise ValueError("short /proc/stat aggregate CPU counters")
                result["system_cpu_ticks"] = dict(zip(names, map(int, cpu)))
                result["stat_counters"] = {parts[0]: int(parts[1]) for line in lines
                                           if (parts := line.split()) and parts[0] in ("ctxt", "processes")}
                result["stat_gauges"] = {parts[0]: int(parts[1]) for line in lines
                                         if (parts := line.split()) and parts[0] in ("procs_running", "procs_blocked", "btime")}
            elif name == "vmstat":
                values = {key: int(value) for key, value in (line.split() for line in text.splitlines())}
                result["vmstat_counters"] = {key: value for key, value in values.items()
                    if (key.startswith(("pg", "pswp", "allocstall", "kswapd_", "compact_", "workingset_"))
                        and key != "workingset_nodes") or key == "oom_kill"}
                if not {"pgfault", "pgmajfault", "pswpin", "pswpout"} <= result["vmstat_counters"].keys():
                    raise ValueError("required fault/swap counters unavailable")
            elif name == "meminfo":
                result["meminfo_bytes"], result["meminfo_counts"] = {}, {}
                for line in text.splitlines():
                    key, rest = line.split(":", 1)
                    parts = rest.split()
                    if len(parts) == 2 and parts[1] == "kB":
                        result["meminfo_bytes"][key] = int(parts[0]) * 1024
                    elif len(parts) == 1:
                        result["meminfo_counts"][key] = int(parts[0])
                    else:
                        raise ValueError("unknown /proc/meminfo unit")
            else:
                result["engine"] = _proc_stat(text, engine_pid)
                result["identity"]["engine_start_ticks"] = result["engine"]["start_ticks"]
        except (OSError, ValueError, StopIteration) as exc:
            result["errors"].append({"operation": path, "error": str(exc)})
    for name, path in (("status", f"/proc/{engine_pid}/status"), ("io", f"/proc/{engine_pid}/io")):
        try:
            text = Path(path).read_text()
            if name == "status":
                fields = {key: rest.split() for key, rest in (line.split(":", 1) for line in text.splitlines())}
                result["engine_status"] = {"Threads": int(fields["Threads"][0])}
                for key in ("VmRSS", "VmSwap"):
                    if fields[key][1:] != ["kB"]:
                        raise ValueError("unknown process status memory unit")
                    result["engine_status"][key + "_bytes"] = int(fields[key][0]) * 1024
            else:
                result["engine_io_counters"] = {key: int(value.strip())
                    for key, value in (line.split(":", 1) for line in text.splitlines())}
        except (OSError, ValueError, KeyError) as exc:
            result["optional_errors"].append({"operation": path, "error": str(exc)})
    try:
        final_identity = _proc_stat(Path(f"/proc/{engine_pid}/stat").read_text(), engine_pid)
        if final_identity["start_ticks"] != result["identity"].get("engine_start_ticks"):
            raise ValueError("engine PID identity changed within snapshot")
    except (OSError, ValueError) as exc:
        result["errors"].append({"operation": "engine_identity_recheck", "error": str(exc)})
    result["after"] = _stamp()
    result["valid"] = not result["errors"]
    return result


def _elapsed(before, after, start_key="before", end_key="after"):
    clock = "monotonic_raw_ns" if before["kind"] == "linux_guest" else "perf_counter_ns"
    a0, a1 = before[start_key], before[end_key]
    b0, b1 = after[start_key], after[end_key]
    elapsed = ((b0[clock] + b1[clock]) - (a0[clock] + a1[clock])) / 2e9
    if elapsed <= 0 or a1[clock] < a0[clock] or b1[clock] < b0[clock]:
        raise ValueError("nonpositive or reversed monotonic snapshot interval")
    return {"elapsed_seconds": elapsed, "clock": clock,
            "sampling_uncertainty_seconds": ((a1[clock] - a0[clock]) + (b1[clock] - b0[clock])) / 2e9}


def _counters(before, after):
    if before.keys() != after.keys():
        raise ValueError("counter fields changed between snapshots")
    delta = {key: after[key] - value for key, value in before.items()}
    decreased = [key for key, value in delta.items() if value < 0]
    if decreased:
        raise ValueError("counter decreased/reset/wrapped: " + ", ".join(decreased))
    return delta


def _check_pair(before, after, kind):
    if before.get("kind") != kind or after.get("kind") != kind:
        raise ValueError("snapshot kinds do not match")
    if not before.get("valid") or not after.get("valid"):
        raise ValueError("required snapshot acquisition incomplete; inspect snapshot errors")


def host_snapshot_delta(before, after):
    """Pure comparison; PID reuse/optional failures produce explicit invalid entries."""
    try:
        _check_pair(before, after, "windows_host")
        if (before["identity"]["computer_name"] != after["identity"]["computer_name"] or
                after["identity"]["uptime_ms"] < before["identity"]["uptime_ms"]):
            raise ValueError("host identity/uptime changed")
        interval = _elapsed(before, after, "system_cpu_before", "system_cpu_after")
        cpu = _counters(before["system_cpu_100ns"], after["system_cpu_100ns"])
        total = cpu["kernel_including_idle"] + cpu["user"]
        busy = total - cpu["idle"]
        if total <= 0 or busy < 0:
            raise ValueError("invalid system CPU accounting interval")
        result = {"valid": True, "kind": "windows_host_delta", **interval,
                  "system_cpu_delta_100ns": cpu, "system_busy_fraction": busy / total,
                  "memory_gauge_delta_bytes": {key: value - before["memory"]["bytes"][key]
                                               for key, value in after["memory"]["bytes"].items()},
                  "processes": []}
        old = {entry["pid"]: entry for entry in before["processes"]}
        new = {entry["pid"]: entry for entry in after["processes"]}
        for pid in sorted(old.keys() | new.keys()):
            entry = {"pid": pid, "valid": False, "errors": []}
            try:
                a, b = old[pid], new[pid]
                if not a["identity_valid"] or not b["identity_valid"] or a["creation_time_100ns"] != b["creation_time_100ns"]:
                    raise ValueError("process identity unavailable or PID reused")
                process_interval = _elapsed({"kind": "windows_host", **a}, {"kind": "windows_host", **b})
                counters = _counters(a["cpu_100ns"], b["cpu_100ns"])
                entry.update(valid=True, creation_time_100ns=a["creation_time_100ns"], **process_interval,
                             cpu_delta_100ns=counters,
                             average_logical_cores=sum(counters.values()) * 1e-7 / process_interval["elapsed_seconds"])
                for key, output in (("io_counters", "io_delta"),):
                    if key in a and key in b:
                        entry[output] = _counters(a[key], b[key])
                    else:
                        entry["errors"].append({"operation": key, "error": "optional read unavailable"})
                key = "page_fault_count_soft_and_hard"
                if key in a and key in b:
                    entry["page_fault_delta_soft_and_hard"] = _counters({key: a[key]}, {key: b[key]})[key]
                else:
                    entry["errors"].append({"operation": key, "error": "optional read unavailable"})
            except (KeyError, ValueError) as exc:
                entry.update(valid=False)
                entry["errors"].append({"operation": "process_delta", "error": str(exc)})
            result["processes"].append(entry)
        return result
    except (KeyError, ValueError) as exc:
        return {"valid": False, "kind": "windows_host_delta", "error": str(exc)}


def guest_snapshot_delta(before, after):
    """Pure comparison within one boot and the same engine PID/start-time identity."""
    try:
        _check_pair(before, after, "linux_guest")
        if before["identity"] != after["identity"]:
            raise ValueError("guest boot/PID namespace/engine identity changed")
        if (before["clock_ticks_per_second"] != after["clock_ticks_per_second"] or
                before["page_size_bytes"] != after["page_size_bytes"]):
            raise ValueError("guest counter units changed")
        interval = _elapsed(before, after)
        cpu = _counters(before["system_cpu_ticks"], after["system_cpu_ticks"])
        vm = _counters(before["vmstat_counters"], after["vmstat_counters"])
        process = _counters(before["engine"]["counters"], after["engine"]["counters"])
        minor = vm["pgfault"] - vm["pgmajfault"]
        if minor < 0:
            raise ValueError("invalid derived system minor fault delta")
        # guest/guest_nice are already included in user/nice: do not double count.
        total = sum(value for key, value in cpu.items() if key not in ("guest", "guest_nice"))
        busy = total - cpu["idle"] - cpu["iowait"]
        if total <= 0 or busy < 0:
            raise ValueError("invalid guest CPU accounting interval")
        result = {"valid": True, "kind": "linux_guest_delta", "identity": before["identity"], **interval,
                "system_cpu_delta_ticks": cpu, "system_busy_fraction_excluding_iowait": busy / total,
                "stat_counter_delta": _counters(before["stat_counters"], after["stat_counters"]),
                "vmstat_counter_delta": vm, "system_minor_fault_delta_derived": minor,
                "engine_counter_delta": process,
                "engine_cpu_seconds": (process["utime_ticks"] + process["stime_ticks"]) / before["clock_ticks_per_second"],
                "swap_in_bytes": vm["pswpin"] * before["page_size_bytes"],
                "swap_out_bytes": vm["pswpout"] * before["page_size_bytes"],
                "meminfo_gauge_delta_bytes": {key: value - before["meminfo_bytes"][key]
                                             for key, value in after["meminfo_bytes"].items()},
                "optional_errors": []}
        for key, output, counters in (("engine_io_counters", "engine_io_delta", True),
                                      ("engine_status", "engine_status_gauge_delta", False)):
            if key not in before or key not in after:
                result["optional_errors"].append({"operation": key, "error": "optional read unavailable"})
                continue
            try:
                a, b = before[key], after[key]
                if counters:
                    # cancelled_write_bytes can decrease; preserve it as a signed adjustment.
                    result[output] = _counters({k: v for k, v in a.items() if k != "cancelled_write_bytes"},
                                               {k: v for k, v in b.items() if k != "cancelled_write_bytes"})
                    if "cancelled_write_bytes" in a and "cancelled_write_bytes" in b:
                        result[output]["cancelled_write_bytes"] = b["cancelled_write_bytes"] - a["cancelled_write_bytes"]
                else:
                    if a.keys() != b.keys():
                        raise ValueError("optional status fields changed")
                    result[output] = {k: b[k] - v for k, v in a.items()}
            except ValueError as exc:
                result["optional_errors"].append({"operation": key, "error": str(exc)})
        return result
    except (KeyError, ValueError) as exc:
        return {"valid": False, "kind": "linux_guest_delta", "error": str(exc)}
