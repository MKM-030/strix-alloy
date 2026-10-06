"""Own and validate the native post-warmup GPU PDH epoch.

The measurement coordinator supplies proven warmup/request QPC bounds and a
callback that freshly verifies admitted WSL proxy handles or explicitly marked
local Win32_Process provider births. This wrapper
never inventories processes or assigns guest/allocation ownership. Every native
interval, including idle margins, gates the whole epoch; no samples are filtered
by request interior. Native raw arrays/pairs remain in the original JSONL.

Usage by the coordinator (all QPC bounds are conservative integer ticks):
    window = PdhWindow(warmup_completion_qpc=(lower, upper),
                       admitted_wsl_proxies=verified_proxies, seconds=120)
    window.start_after_warmup(out_dir, native_exe, pinned_sha, verify_proxies)
    window.assert_live()  # also at each measured boundary
    window.add_request_bracket(before_qpc, after_qpc)  # exactly three times
    coverage = window.stop_after_measurements(final_upper_qpc)
On an earlier failure call window.abort(reason); it requests the same owned stop
marker, drains/retains output and records an invalid epoch without requiring
three requests. It never restarts a sampler or touches the serving process.
"""
from __future__ import annotations

from collections import Counter
import ctypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import ntpath
import os
from pathlib import Path
import re
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "server") not in sys.path:
    sys.path.insert(0, str(ROOT / "server"))
from owned_child import JobChild

SCHEMA = "halogen.gpu-pdh.window.v1"
COUNTER_PATH = r"\GPU Engine(*)\Utilization Percentage"
MAX_RAW_BYTES = 64 * 1024**2       # Matches the native collector's output cap.
MAX_LINE_BYTES = 8 * 1024**2
VALID_STATUSES = {0, 1}            # PDH VALID_DATA and NEW_DATA are both valid.
INSTANCE = re.compile(
    r"^pid_(\d+)_luid_(0x[0-9a-f]+_0x[0-9a-f]+)_phys_(\d+)_eng_(\d+)_engtype_([^#]+)(?:#(\d+))?$",
    re.IGNORECASE,
)


class PdhWindowError(RuntimeError):
    """The retained epoch is invalid; it must not qualify a measurement."""


def require(value, message):
    if not value:
        raise PdhWindowError(message)


def decimal(value, name, *, signed=False, positive=False):
    # Native 64-bit fields must remain decimal strings, never rounded floats.
    require(isinstance(value, str) and re.fullmatch(r"-?[0-9]+" if signed else r"[0-9]+", value),
            "Missing/nonexact decimal field: " + name)
    result = int(value)
    require(-(2**63) <= result < 2**63 if signed else 0 <= result < 2**64,
            "Out-of-range decimal field: " + name)
    require(not positive or result > 0, "Nonpositive field: " + name)
    return result


def uint32(value, name):
    require(type(value) is int and 0 <= value <= 0xffffffff, "Invalid uint32: " + name)
    return value


def tick(value, name):
    require(type(value) is int and 0 < value < 2**63, "Positive integer QPC ticks required: " + name)
    return value


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def write_new_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def normalized_identity(value):
    require(isinstance(value, dict), "Identity must be an exact handle-verified record")
    pid = value.get("pid")
    created = value.get("creation_time_100ns")
    image = value.get("executable")
    require(type(pid) is int and 0 < pid <= 0xffffffff and type(created) is int and created > 0,
            "Identity requires exact PID and creation FILETIME")
    require(isinstance(image, str) and ntpath.isabs(image) and "\0" not in image,
            "Identity requires an absolute executable")
    return dict(pid=pid, creation_time_100ns=created,
                executable=ntpath.normcase(ntpath.normpath(image)))


def normalized_proxy(value):
    """Compare provider births without relabelling them as native handle proof."""
    if isinstance(value, dict) and value.get("schema") == "halogen.gpu-pdh.proxy-cim-birth.v1":
        pid, name, host = value.get("pid"), value.get("name"), value.get("host")
        require(type(pid) is int and 0 < pid <= 0xffffffff and pid != 4,
                "Invalid provider proxy PID")
        require(isinstance(name, str) and name.casefold() in
                {"vmwp.exe", "vmmemwsl", "vmmemwsl.exe", "wslhost.exe"}, "Unexpected provider proxy name")
        require(isinstance(host, str) and host.casefold() == socket.gethostname().casefold(),
                "Provider census must belong to this local host")
        require(value.get("provider") == "CIMWin32.Win32_Process" and
                value.get("executable") is None and value.get("native_handle_verified") is False and
                value.get("image_verified") is False and
                value.get("continuity") == "provider_birth_observed_at_boundaries",
                "Provider birth limits must remain explicit")
        lower, upper = tick(value.get("census_qpc_before"), "provider census before"), tick(
            value.get("census_qpc_after"), "provider census after")
        require(lower <= upper, "Provider census bracket regresses")
        raw = value.get("creation_date")
        require(isinstance(raw, str), "Raw provider timestamp must remain text")
        match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\.(\d{6})([+-])(\d{3})", raw or "")
        require(match is not None, "Complete non-wildcard DMTF provider birth required")
        offset = int(match[9]) * (1 if match[8] == "+" else -1)
        created = datetime(*(int(match[index]) for index in range(1, 8)),
                           tzinfo=timezone(timedelta(minutes=offset)))
        return dict(schema=value["schema"], pid=pid, name=name.casefold(), host=host.casefold(),
                    provider=value["provider"], creation_date_utc=created.astimezone(timezone.utc).isoformat(),
                    precision="provider_DMTF_microseconds", executable=None,
                    native_handle_verified=False, image_verified=False,
                    continuity="provider_birth_observed_at_boundaries")
    return normalized_identity(value)


def qpc_now(expected_frequency):
    """Read exact Windows ticks at runtime; no float seconds conversion."""
    require(os.name == "nt", "The native owned window requires Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    for name in ("QueryPerformanceCounter", "QueryPerformanceFrequency"):
        function = getattr(api, name)
        function.argtypes = [ctypes.POINTER(ctypes.c_int64)]
        function.restype = ctypes.c_int
    value, frequency = ctypes.c_int64(), ctypes.c_int64()
    require(api.QueryPerformanceFrequency(ctypes.byref(frequency)) and
            frequency.value == expected_frequency and
            api.QueryPerformanceCounter(ctypes.byref(value)), "QPC clock/frequency proof failed")
    return tick(value.value, "runtime QPC")


class PdhWindow:
    def __init__(self, *, warmup_completion_qpc, admitted_wsl_proxies=(), seconds=120,
                 baseline_timeout=10.0, stop_timeout=10.0):
        require(isinstance(warmup_completion_qpc, (tuple, list)) and len(warmup_completion_qpc) == 2,
                "Supply the proven warmup completion QPC bracket")
        self.warmup = tuple(tick(x, "warmup completion") for x in warmup_completion_qpc)
        require(self.warmup[0] <= self.warmup[1], "Warmup bracket regresses")
        require(type(seconds) is int and 1 <= seconds <= 120, "Native duration must be 1..120 seconds")
        require(all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                    and 0 < x <= 30 for x in (baseline_timeout, stop_timeout)), "Bounded waits required")
        self.seconds, self.baseline_timeout, self.stop_timeout = seconds, baseline_timeout, stop_timeout
        self.admitted = sorted((normalized_proxy(x) for x in admitted_wsl_proxies), key=lambda x: x["pid"])
        self.admitted_initial_evidence = list(admitted_wsl_proxies)
        require(len({x["pid"] for x in self.admitted}) == len(self.admitted), "Duplicate admitted PID")
        require(all(x["pid"] != 4 for x in self.admitted), "PID4/System is never admitted")
        self.admitted_pids = {x["pid"] for x in self.admitted}
        self.child = self.reader = self.identity_callback = None
        self.recovery_owner = None
        self.run_dir = self.raw_path = self.stderr_path = self.stop_path = None
        self.executable = self.pinned_sha = self.identity = None
        self.qpc_frequency = self.baseline_ack_qpc = None
        self.baseline = self.previous = self.final_snapshot = self.terminal = None
        self.counter_type = self.timebase = None
        self.counter_registry = None
        self.request_brackets, self.identity_checks, self.violations, self.errors = [], [], [], []
        self.error_count = self.samples = self.lines = self.raw_bytes_read = self.unresolved_total = 0
        self.stop_requested = self.closed = self.finished = self.final_seen = False
        self.result = None
        self.finish_attempts = 0
        self.native_exit_code = None
        self.started_monotonic = None

    def _error(self, error):
        self.error_count += 1
        if len(self.errors) < 32:
            self.errors.append(str(error))

    def _verify_proxies(self):
        # Root supplies fresh native handle proof OR the explicitly weaker local
        # Win32_Process provider-birth schema. A cached PID list is insufficient.
        observed = self.identity_callback()
        require(isinstance(observed, (list, tuple)), "Identity callback must return fresh verified proxy identities")
        current = sorted((normalized_proxy(x) for x in observed), key=lambda x: x["pid"])
        require(current == self.admitted, "Admitted WSL proxy identities changed or are unresolved")
        return list(observed)

    def _verify_owned_live(self, *, verify_pin=True):
        require(self.child is not None and not self.closed and self.child.poll() is None,
                "Owned sampler exited prematurely; no restart")
        live = self.child.owner.verify_live_identity()
        require(normalized_identity(live) == normalized_identity(self.identity), "Owned sampler identity changed")
        if verify_pin:
            require(sha256_file(self.executable) == self.pinned_sha, "Pinned native executable changed")
        return live

    def _sync_raw(self):
        # The native fflush makes complete records visible; a separate writable
        # descriptor fsync commits that same file before ACK or final hashing.
        require(self.raw_path is not None and self.raw_path.is_file(), "Owned raw file unavailable for durable flush")
        with self.raw_path.open("r+b", buffering=0) as output:
            os.fsync(output.fileno())

    def start_after_warmup(self, out_dir, exe, pinned_sha, callback_identities):
        require(self.child is None and self.run_dir is None, "Window may be started only once")
        require(callable(callback_identities), "A fresh retained-handle identity callback is required")
        directory, executable = Path(out_dir), Path(exe)
        require(directory.is_absolute() and executable.is_absolute(), "Output directory/executable must be absolute")
        directory, executable = directory.resolve(strict=True), executable.resolve(strict=True)
        require(directory.is_dir() and executable.is_file(), "Existing directory/native executable required")
        require(isinstance(pinned_sha, str) and re.fullmatch(r"[0-9a-fA-F]{64}", pinned_sha), "Exact reviewed SHA256 required")
        self.pinned_sha, self.executable = pinned_sha.lower(), executable
        require(sha256_file(executable) == self.pinned_sha, "Native executable differs from reviewed pin")
        self.identity_callback = callback_identities
        self._verify_proxies()
        self.run_dir = directory / ("gpu-pdh-window-" + uuid.uuid4().hex)
        self.run_dir.mkdir()
        self.raw_path, self.stderr_path = self.run_dir / "gpu-pdh.jsonl", self.run_dir / "stderr.log"
        self.stop_path = self.run_dir / "owned.stop"
        require(not self.stop_path.exists(), "Stop marker must be new and absent")
        command = [str(executable), "--stop", str(self.stop_path), "--seconds", str(self.seconds)]
        self.started_monotonic = time.monotonic()
        try:
            self.child = JobChild(command, cwd=ROOT, env=os.environ.copy(),
                                  stdout_path=self.raw_path, stderr_path=self.stderr_path)
            self.identity = self.child.owner.verify_live_identity()
            require(normalized_identity(self.identity)["executable"] ==
                    ntpath.normcase(ntpath.normpath(str(executable))), "Actual native image differs")
            write_new_json(self.run_dir / "owned-start.json", dict(
                schema="halogen.gpu-pdh.owned-start.v1", command=command,
                windows_identity=self.identity, executable_sha256=self.pinned_sha,
                stop_marker=str(self.stop_path), raw_path=str(self.raw_path),
                warmup_completion_qpc=list(self.warmup), admitted_wsl_proxies=self.admitted,
                attribution_qualified=False, speed_claim=False))
            self.reader = self.raw_path.open("rb")
            deadline = time.monotonic() + self.baseline_timeout
            while self.baseline is None:
                self._drain()
                require(self.child.poll() is None, "Native closed before baseline acknowledgement")
                require(time.monotonic() < deadline, "Flushed baseline wait expired; no restart")
                if self.baseline is None:
                    self.child.owner.wait(50)
            live = self._verify_owned_live()
            proxies = self._verify_proxies()
            self._sync_raw()
            self.baseline_ack_qpc = qpc_now(self.qpc_frequency)
            require(self.baseline_ack_qpc >= decimal(self.baseline["collection"]["qpc_after"], "baseline end"),
                    "Baseline acknowledgement precedes baseline")
            self.identity_checks.append(dict(qpc=self.baseline_ack_qpc, windows_identity=live,
                                             admitted_wsl_proxies=proxies, phase="baseline_ack"))
            ready = dict(schema="halogen.gpu-pdh.ready.v1", windows_identity=self.identity,
                         qpc_frequency=self.qpc_frequency, baseline_ack_qpc=self.baseline_ack_qpc,
                         baseline=self.baseline, raw_path=str(self.raw_path),
                         warmup_completion_qpc=list(self.warmup), attribution_qualified=False)
            write_new_json(self.run_dir / "ready.json", ready)
            return ready
        except BaseException as error:
            self.recovery_owner = getattr(error, "owner", None)
            self._error(error)
            try:
                self.abort("start_or_baseline_failed")
            except BaseException as cleanup:
                self._error("Owned abort unconfirmed: " + str(cleanup))
                error.cleanup_error = cleanup
            raise

    @staticmethod
    def _mark(mark, name):
        require(isinstance(mark, dict), "Missing UTC/QPC mark: " + name)
        before = decimal(mark.get("qpc_before"), name + ".qpc_before", positive=True)
        after = decimal(mark.get("qpc_after"), name + ".qpc_after", positive=True)
        require(before <= after, "UTC/QPC mark regresses: " + name)
        decimal(mark.get("utc_filetime_100ns"), name + ".utc_filetime_100ns", positive=True)
        require(isinstance(mark.get("utc"), str) and mark["utc"].endswith("Z"), "Missing precise UTC text")
        return before, after

    def _snapshot(self, snapshot):
        require(isinstance(snapshot, dict) and snapshot.get("raw_available") is True, "Raw snapshot unavailable")
        for name in ("query_code", "raw_array_code", "metadata_code", "timebase_code"):
            require(uint32(snapshot.get(name), name) == 0, "PDH API failed: " + name)
        counter_type = uint32(snapshot.get("counter_type"), "counter_type")
        timebase = decimal(snapshot.get("timebase"), "timebase", signed=True, positive=True)
        query_time = decimal(snapshot.get("query_filetime_100ns"), "original query timestamp", signed=True, positive=True)
        collection = snapshot.get("collection")
        require(isinstance(collection, dict), "Missing collection QPC endpoints")
        before = decimal(collection.get("qpc_before"), "collection before", positive=True)
        after = decimal(collection.get("qpc_after"), "collection after", positive=True)
        require(before <= after, "Collection bracket regresses")
        utc_before = self._mark(collection.get("utc_before"), "utc_before")
        utc_after = self._mark(collection.get("utc_after"), "utc_after")
        require(utc_before[1] <= before <= after <= utc_after[0], "Collection/UTC QPC ordering is ambiguous")
        require(counter_type == self.counter_type and timebase == self.timebase, "Counter type/timebase changed")
        raw = snapshot.get("raw")
        require(isinstance(raw, list) and 0 < len(raw) <= 4096, "Empty/oversized raw instance array")
        for item in raw:
            require(isinstance(item, dict) and isinstance(item.get("instance"), str) and
                    INSTANCE.fullmatch(item["instance"]), "Unparsed GPU instance identity")
            require(uint32(item.get("status"), "raw status") in VALID_STATUSES, "Invalid raw PDH status")
            decimal(item.get("filetime_100ns"), "original raw timestamp", positive=True)
            decimal(item.get("first"), "raw first", signed=True)
            decimal(item.get("second"), "raw second", signed=True)
            uint32(item.get("multi_count"), "raw MultiCount")
        return before, after, query_time

    def _pairs(self, row, previous, current, *, baseline):
        pairs = row.get("pairs")
        require(isinstance(pairs, list), "Full pair union missing")
        old, new = [] if previous is None else previous["raw"], current["raw"]
        old_counts = Counter(x["instance"] for x in old)
        new_counts = Counter(x["instance"] for x in new)
        names = set(old_counts) | set(new_counts)
        require(len(pairs) == len(names) and {p.get("instance") for p in pairs if isinstance(p, dict)} == names,
                "Pair union drops or duplicates an instance")
        require(type(row.get("unresolved_pairs")) is int and row["unresolved_pairs"] == 0,
                "Unresolved native instance pairs")
        for pair in pairs:
            name = pair["instance"]
            require(pair.get("previous_matches") == old_counts[name] and
                    pair.get("current_matches") == new_counts[name] == 1 and
                    old_counts[name] == (0 if baseline else 1), "Missing/duplicate instance endpoint")
            current_index = pair.get("current_index")
            previous_index = pair.get("previous_index")
            require(type(current_index) is int and 0 <= current_index < len(new) and
                    new[current_index]["instance"] == name, "Current pair index is not exact")
            if baseline:
                require(previous_index is None and pair.get("status") == "baseline" and pair.get("cooked") is None,
                        "Baseline must be the first raw point, never a cooked interval")
                continue
            require(type(previous_index) is int and 0 <= previous_index < len(old) and
                    old[previous_index]["instance"] == name and pair.get("status") == "paired",
                    "Unresolved arithmetic pair")
            older, newer = old[previous_index], new[current_index]
            require(decimal(newer["filetime_100ns"], "new raw timestamp") >
                    decimal(older["filetime_100ns"], "old raw timestamp") and
                    decimal(newer["second"], "new raw second", signed=True) >
                    decimal(older["second"], "old raw second", signed=True) and
                    decimal(newer["first"], "new busy time", signed=True) >=
                    decimal(older["first"], "old busy time", signed=True) and
                    newer["multi_count"] == older["multi_count"], "Repeated timestamp/nonpositive denominator/reset")
            require(uint32(pair.get("calculate_code"), "calculate status") == 0 and
                    uint32(pair.get("cooked_status"), "cooked status") in VALID_STATUSES,
                    "Invalid calculation/cooked status")
            value = pair.get("cooked")
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                    "Invalid/negative cooked value")
            matched = INSTANCE.fullmatch(name)
            pid, engine_type = int(matched[1]), matched[5].casefold()
            threshold = 2.0 if engine_type == "copy" else 1.0
            if value > threshold and pid not in self.admitted_pids:
                if len(self.violations) < 32:
                    self.violations.append(dict(index=row["index"], instance=name, pid=pid,
                                                cooked=value, threshold=threshold,
                                                scope="unresolved_foreign_pid"))
                raise PdhWindowError("Unresolved foreign GPU activity: " + name + " > " + str(threshold) + "%")

    def _point(self, row):
        event = row["event"]
        require(event != "collection_error", "Native reported a failed collection attempt")
        baseline = event == "baseline"
        frequency = decimal(row.get("qpc_frequency"), "QPC frequency", signed=True, positive=True)
        require(row.get("counter_path") == COUNTER_PATH and row.get("sample_gap_valid") is True and
                row.get("raw_timestamp_semantics") == "provider_FILETIME_preserved", "Counter/time boundary metadata differs")
        require(row.get("pair_continuity_only") is True and row.get("instance_generation_verified") is False,
                "Native continuity/identity limits must stay explicit")
        require(row.get("acceptance") is False and row.get("attribution_qualified") is False,
                "Native output must not assign acceptance/ownership")
        require(type(row.get("index")) is int and row["index"] == (0 if baseline else self.samples),
                "Native sample index gap/regression")
        previous, current = row.get("previous"), row.get("current")
        if baseline:
            require(self.baseline is None and self.samples == 0 and previous is None and
                    row.get("final_sample") is False and row.get("stop_kind") == "none", "Invalid/duplicate baseline")
            require(isinstance(current, dict), "Baseline snapshot missing")
            self.qpc_frequency = frequency
            self.counter_type = uint32(current.get("counter_type"), "counter_type")
            self.timebase = decimal(current.get("timebase"), "timebase", signed=True, positive=True)
        else:
            require(self.baseline is not None and frequency == self.qpc_frequency and
                    isinstance(previous, dict) and previous == self.previous, "Skipped/changed preceding raw snapshot")
        bounds = self._snapshot(current)
        if baseline:
            require(bounds[0] > self.warmup[1], "Baseline was not strictly after proven warmup completion")
            require(decimal(row.get("sample_gap_qpc"), "baseline sample gap", signed=True) == 0, "Baseline gap is not zero")
        else:
            prior = self._snapshot(previous)
            require(bounds[0] >= prior[1] and bounds[2] > prior[2], "Acquisition/timestamp continuity regresses")
            gap = bounds[1] - prior[1]
            require(0 < gap <= self.qpc_frequency * 1500 // 1000 and
                    decimal(row.get("sample_gap_qpc"), "sample gap", signed=True) == gap,
                    "Premature/late/missing acquisition interval")
        require(row.get("final_sample") is False or row.get("final_sample") is True, "Missing final-sample flag")
        if row["final_sample"]:
            require(not self.final_seen and self.stop_requested and row.get("stop_kind") == "marker",
                    "Premature final sample/deadline/foreign stop")
            self.final_seen = True
            self.final_snapshot = self._snapshot_receipt(current)
        else:
            require(not self.final_seen and row.get("stop_kind") == "none", "Sampling continued after final point")
        self._pairs(row, previous, current, baseline=baseline)
        if baseline:
            self.baseline = self._snapshot_receipt(current)

    @staticmethod
    def _snapshot_receipt(snapshot):
        return {key: value for key, value in snapshot.items() if key != "raw"} | {
            "raw_instance_count": len(snapshot["raw"])}

    def _terminal(self, row):
        require(row.get("status") == "complete" and row.get("success") is True and row.get("reason") == "none" and
                row.get("stop_kind") == "marker" and self.stop_requested and self.final_seen,
                "Native terminal is incomplete, premature or not the owned marker")
        require(ntpath.normcase(ntpath.normpath(row.get("stop", ""))) ==
                ntpath.normcase(ntpath.normpath(str(self.stop_path))) and row.get("seconds") == self.seconds,
                "Terminal belongs to another native run")
        require(row.get("baseline_emitted") is True and row.get("samples") == self.samples and self.samples > 0,
                "Terminal/baseline/sample count differs")
        require(decimal(row.get("unresolved_pairs_total"), "unresolved pair total") == 0,
                "Native terminal reports unresolved pairs")
        require(decimal(row.get("qpc_frequency"), "terminal QPC frequency", signed=True, positive=True) == self.qpc_frequency,
                "Terminal QPC frequency changed")
        for key in ("query_open_code", "counter_add_code", "query_close_code", "marker_code"):
            require(uint32(row.get(key), key) == 0, "Native terminal API failed: " + key)
        require(row.get("query_closed") is True and row.get("pdh_query_called") is True and
                row.get("acceptance") is False and row.get("attribution_qualified") is False and
                row.get("pair_continuity_only") is True and row.get("instance_generation_verified") is False,
                "Terminal cleanup/continuity qualification differs")

    def _decode_point(self, row):
        """Expand fixed registry references; retain the unmodified raw JSONL."""
        encoding = row.get("counter_encoding")
        if encoding is None:
            require(self.counter_registry is None, "Compact encoding disappeared mid-epoch")
            return
        require(encoding == "explicit-registry-v1", "Unknown counter reference encoding")
        if row.get("event") == "baseline" or (row.get("event") == "collection_error" and row.get("index") == 0):
            require(self.counter_registry is None, "Counter registry may appear only once")
            registry = row.get("counter_registry")
            require(isinstance(registry, list) and 0 < len(registry) <= 4096,
                    "Missing or oversized explicit counter registry")
            keys = {"counter_index", "instance", "path", "parsed_instance", "provider_instance_index"}
            for position, entry in enumerate(registry):
                require(isinstance(entry, dict) and set(entry) == keys,
                        "Explicit registry fields differ")
                require(type(entry["counter_index"]) is int and entry["counter_index"] == position,
                        "Explicit counter registry index is not fixed")
                require(all(isinstance(entry[key], str) and 0 < len(entry[key]) < 4096 and
                            "\0" not in entry[key] for key in
                            {"instance", "path", "parsed_instance"}),
                        "Invalid explicit counter registry text")
                provider_index = uint32(entry["provider_instance_index"], "provider index")
                match = INSTANCE.fullmatch(entry["instance"])
                require(match is not None and match[6] is not None and
                        int(match[6]) == provider_index and
                        entry["instance"] == entry["parsed_instance"] + "#" + str(provider_index),
                        "Explicit instance/index registry identity differs")
            require(len({entry["instance"] for entry in registry}) == len(registry) and
                    len({entry["path"] for entry in registry}) == len(registry),
                    "Duplicate explicit counter registry identity")
            self.counter_registry = registry
        else:
            require("counter_registry" not in row and self.counter_registry is not None,
                    "Counter registry changed or unavailable")
        registry = self.counter_registry
        complete = set(range(len(registry)))

        def complete_references(indices, name):
            require(len(indices) == len(registry) and all(type(index) is int for index in indices) and
                    set(indices) == complete, "Incomplete or duplicate fixed registry coverage: " + name)

        def reference(index):
            require(type(index) is int and 0 <= index < len(registry),
                    "Unmapped or invalid explicit counter reference")
            return registry[index]

        for key in ("previous", "current"):
            snapshot = row.get(key)
            if snapshot is None:
                continue
            require(isinstance(snapshot, dict), "Compact snapshot missing")
            for topology_key in ("topology_before", "topology_after"):
                topology = snapshot.get(topology_key)
                require(isinstance(topology, dict) and "paths" not in topology and
                        isinstance(topology.get("path_indices"), list) and
                        topology.get("unmapped_paths") == [],
                        "Compact provider topology missing or ambiguous")
                indices = topology["path_indices"]
                require(len(indices) <= 4096 and topology.get("path_count") == len(indices) and
                        len(set(index for index in indices if type(index) is int)) == len(indices),
                        "Duplicate or incomplete compact provider topology")
                complete_references(indices, topology_key)
                topology["paths"] = [reference(index)["path"] for index in indices]
            raw = snapshot.get("raw")
            require(isinstance(raw, list) and len(raw) <= 4096, "Compact raw array unavailable")
            require(all(isinstance(item, dict) for item in raw), "Invalid compact raw entry")
            complete_references([item.get("counter_index") for item in raw], key + ".raw")
            for item in raw:
                require(isinstance(item, dict) and not any(key in item for key in
                        ("instance", "path", "parsed_instance", "provider_instance_index")),
                        "Ambiguous compact raw counter identity")
                item.update(reference(item.get("counter_index")))
        pairs = row.get("pairs")
        require(isinstance(pairs, list) and len(pairs) <= 4096, "Compact counter pairs unavailable")
        require(all(isinstance(pair, dict) for pair in pairs), "Invalid compact pair entry")
        complete_references([pair.get("counter_index") for pair in pairs], "pairs")
        for pair in pairs:
            require(isinstance(pair, dict) and "instance" not in pair and "path" not in pair,
                    "Ambiguous compact pair identity")
            entry = reference(pair.get("counter_index"))
            pair.update(instance=entry["instance"], path=entry["path"])

    def _drain(self, *, final=False, strict=True):
        if self.reader is None:
            return
        start_errors = self.error_count
        while True:
            position = self.reader.tell()
            line = self.reader.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if not line.endswith(b"\n") and not final and len(line) <= MAX_LINE_BYTES:
                self.reader.seek(position)  # Partial writes are not acknowledged.
                break
            self.lines += 1
            self.raw_bytes_read += len(line)
            try:
                require(len(line) <= MAX_LINE_BYTES and line.endswith(b"\n") and
                        self.raw_bytes_read <= MAX_RAW_BYTES, "Oversized/incomplete raw JSONL output")
                row = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                require(isinstance(row, dict) and row.get("schema") == SCHEMA and self.terminal is None,
                        "Unexpected JSONL schema or rows after terminal")
                event = row.get("event")
                require(event in ("baseline", "sample", "collection_error", "terminal"), "Unknown native event")
                if event == "terminal":
                    self.terminal = row
                    self._terminal(row)
                else:
                    self._decode_point(row)
                    if event != "baseline":
                        self.samples += 1
                    try:
                        self._point(row)
                    finally:
                        # Preserve the immediately preceding raw point even when
                        # invalid, so later retained intervals are still checked.
                        self.previous = row.get("current")
            except (PdhWindowError, ValueError, TypeError, KeyError) as error:
                self._error("Raw line " + str(self.lines) + ": " + str(error))
                if len(line) > MAX_LINE_BYTES:
                    break
        if strict and self.error_count != start_errors:
            raise PdhWindowError(self.errors[-1])

    def assert_live(self):
        require(self.baseline_ack_qpc is not None and not self.stop_requested and not self.finished,
                "A ready, still-measuring epoch is required")
        self._drain()
        require(not self.errors and not self.final_seen and self.terminal is None, "Epoch already invalid/closed")
        live = self._verify_owned_live()
        proxies = self._verify_proxies()
        proof_qpc = qpc_now(self.qpc_frequency)
        self.identity_checks.append(dict(qpc=proof_qpc, windows_identity=live, admitted_wsl_proxies=proxies))
        return dict(qpc=proof_qpc, windows_identity=live, admitted_wsl_proxies=proxies)

    def add_request_bracket(self, before_qpc, after_qpc):
        require(not self.stop_requested and len(self.request_brackets) < 3, "Exactly three measured brackets are permitted")
        before, after = tick(before_qpc, "request lower"), tick(after_qpc, "request upper")
        require(before <= after and self.baseline_ack_qpc is not None and self.baseline_ack_qpc < before,
                "Baseline acknowledgement does not precede conservative measured bracket")
        self.request_brackets.append(dict(index=len(self.request_brackets), before=before, after=after))
        # No intermediate acquisition-bracket exclusion or per-request filtering.

    def _request_stop(self, end_qpc, *, cleanup=False):
        if self.stop_requested:
            return
        require(self.child is not None and not self.closed, "No retained owned child for stop")
        if self.child.poll() is not None:
            self._drain(final=True, strict=False)
            raise PdhWindowError("Owned sampler closed before its stop marker")
        # Cleanup still proves the retained process identity. A changed on-disk
        # pin invalidates qualification but must not prevent its owned marker.
        self._verify_owned_live(verify_pin=not cleanup)
        require(not self.stop_path.exists(), "Exact owned stop marker unexpectedly exists")
        with self.stop_path.open("xb", buffering=0) as marker:
            marker.write((str(end_qpc) + "\n").encode("ascii"))
            os.fsync(marker.fileno())
        self.stop_requested = True

    def _await_terminal(self):
        deadline = time.monotonic() + self.stop_timeout
        while self.child.poll() is None:
            self._drain(strict=False)
            if time.monotonic() >= deadline:
                self._error("Owned marker/terminal wait expired; no restart")
                break
            self.child.owner.wait(50)
        self.native_exit_code = self.child.poll()
        if self.native_exit_code is not None:
            self._drain(final=True, strict=False)
        require(self.native_exit_code == 0 and self.terminal is not None, "Native exit/terminal not successfully confirmed")

    def stop_after_measurements(self, end_qpc):
        require(not self.finished and len(self.request_brackets) == 3, "Three fully validated measured brackets required")
        end = tick(end_qpc, "final measured upper")
        require(end >= max(row["after"] for row in self.request_brackets), "Final end does not cover all measured rows")
        try:
            self.assert_live()
            self._request_stop(end)
            self._await_terminal()
            proxies = self._verify_proxies()
            self.identity_checks.append(dict(qpc=qpc_now(self.qpc_frequency),
                                             admitted_wsl_proxies=proxies, phase="final_collection"))
            require(self.final_snapshot is not None and
                    decimal(self.final_snapshot["collection"]["qpc_before"], "final collection before", positive=True) > end,
                    "Final collection does not start strictly after conservative measured end")
            require(not self.errors, "At least one full-epoch interval or identity proof failed")
            return self._finish(passed=True, end_qpc=end)
        except BaseException as error:
            self._error(error)
            try:
                self.abort("measurement_or_terminal_validation_failed")
            except BaseException as cleanup:
                error.cleanup_error = cleanup
            raise

    def _finish(self, *, passed, end_qpc=None):
        if self.finished and self.closed:
            return self.result
        self.finish_attempts += 1
        closed = False
        try:
            if self.child is not None:
                self.child.close()  # Only this JobChild's owned job/handle.
            if self.recovery_owner is not None:
                self.recovery_owner.close()
            closed = True
        except BaseException as error:
            self._error("Owned job close unconfirmed: " + str(error))
        self.closed = closed
        if closed and self.reader is not None:
            self._drain(final=True, strict=False)
            self.reader.close()
            self.reader = None
        raw_exists = self.raw_path is not None and self.raw_path.exists()
        if raw_exists:
            try:
                self._sync_raw()
            except BaseException as error:
                self._error("Raw output durable flush failed: " + str(error))
        result = dict(schema="halogen.gpu-pdh.coverage.v1", passed=bool(passed and closed and not self.errors),
                      errors=self.errors, error_count=self.error_count, windows_identity=self.identity,
                      executable=str(self.executable), executable_sha256=self.pinned_sha,
                      raw_path=str(self.raw_path), raw_sha256=sha256_file(self.raw_path) if raw_exists else None,
                      raw_bytes=self.raw_path.stat().st_size if raw_exists else 0, stderr_path=str(self.stderr_path),
                      stop_marker=str(self.stop_path), stop_requested=self.stop_requested,
                      native_exit_code=self.native_exit_code, owned_job_closed=closed,
                      qpc_frequency=self.qpc_frequency, warmup_completion_qpc=list(self.warmup),
                      baseline=self.baseline, baseline_ack_qpc=self.baseline_ack_qpc,
                      request_qpc_brackets=self.request_brackets, measured_end_qpc=end_qpc,
                      final_snapshot=self.final_snapshot, sample_count=self.samples,
                      parsed_line_count=self.lines, raw_bytes_read=self.raw_bytes_read,
                      identity_checks=self.identity_checks, admitted_wsl_proxies=self.admitted,
                      counter_registry=self.counter_registry,
                      admitted_initial_evidence=self.admitted_initial_evidence,
                      unresolved_foreign_violations=self.violations, terminal=self.terminal,
                      policy="Gate every interval of baseline-through-final epoch, including idle margins",
                      thresholds_percent=dict(copy=2.0, other=1.0), no_pid4_whitelist=True,
                      raw_arrays_and_pairs_preserved=True, raw_output_retained_without_filtering=True,
                      full_epoch_validation_passed=bool(passed and closed and not self.errors),
                      pair_continuity_only=True, instance_generation_verified=False,
                      attribution_qualified=False, speed_claim=False,
                      elapsed_seconds=None if self.started_monotonic is None else time.monotonic() - self.started_monotonic)
        self.result = result
        if self.run_dir is not None:
            # A failed close or partial receipt remains evidence. A retry writes
            # a new file and never overwrites the original coverage receipt.
            name = "coverage.json" if self.finish_attempts == 1 else "coverage-retry-%03d.json" % self.finish_attempts
            result["receipt_path"] = str(self.run_dir / name)
            try:
                write_new_json(self.run_dir / name, result)
            except BaseException as error:
                self._error("Coverage receipt write failed: " + str(error))
                result["passed"] = result["full_epoch_validation_passed"] = False
                result["error_count"] = self.error_count
                raise
        self.finished = closed
        if passed:
            require(result["passed"], "Owned cleanup/receipt did not qualify the epoch")
        return result

    def abort(self, reason="coordinator_failed"):
        """Bounded owned-marker cleanup; never requires three request rows."""
        if self.finished:
            return self.result
        self._error("Coordinator abort: " + str(reason))
        if self.child is not None and not self.closed:
            try:
                # Abort needs no measurement end. Native ignores marker contents,
                # so a broken QPC proof cannot prevent the owned stop attempt.
                self._request_stop(0, cleanup=True)
                self._await_terminal()
            except BaseException as error:
                self._error("Owned marker cleanup: " + str(error))
        return self._finish(passed=False)

    def close(self):
        if not self.finished:
            return self.abort("closed_before_validated_measurement_end")
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


# Importable only; there is deliberately no CLI that starts a sampler by default.
