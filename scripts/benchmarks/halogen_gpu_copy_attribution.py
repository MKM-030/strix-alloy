"""Stream native DxgKrnl materialization into schema-supported ownership joins.

This is an offline analyzer and capture command builder. It never starts ETW,
changes a server, or launches GPU work. A packet's header PID is not its owner.
Only captured hContext -> hDevice -> DxgProcess -> DxgVirtualMachine links are
used. The result distinguishes a captured guest owner from an attested Linux
task and never qualifies a PDH aggregate or allocation beneficiaries by itself.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import ntpath
from pathlib import Path
import re
import uuid

PROVIDER = "802ec45a-1e99-4b83-9920-87c98277ba9d"
KEYWORDS = 0x04900845
MAX_INPUT_BYTES = 256 * 1024**2
MAX_LINE_BYTES = 1024**2
MAX_OBJECTS = 20000
MAX_PACKETS = 20000
MAX_NATIVE_NODE_RECEIPTS = 32
SDK_HEADER = Path(r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\shared\d3dkmdt.h")
PDH_COPY_INSTANCE = re.compile(r"pid_(\d+)_luid_0x([0-9a-f]{1,8})_0x([0-9a-f]{1,8})_phys_(\d+)_eng_(\d+)_engtype_copy(?:#\d+)?", re.I)
VERSIONS = {27: 2, 28: 2, 29: 2, 30: 0, 31: 0, 32: 0, 33: 3, 34: 3, 35: 3,
            36: 2, 37: 2, 38: 2, 43: 0, 50: 0, 53: 0, 76: 0, 77: 0, 110: 1,
            175: 1, 176: 0, 177: 1, 178: 1, 179: 0, 180: 1, 250: 0, 288: 0,
            422: 0, 423: 0, 424: 0, 450: 0, 471: 0, 472: 0, 473: 0, 474: 0,
            475: 0, 477: 0, 491: 0, 492: 0, 493: 0}


class AttributionError(RuntimeError):
    pass


def exact_int(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise AttributionError("Exact unsigned integer required")


def stream_jsonl(path):
    path = Path(path).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_INPUT_BYTES:
        raise AttributionError("Input must be a nonempty file of at most256MiB")
    with path.open("rb") as source:
        while raw := source.readline(MAX_LINE_BYTES + 1):
            if len(raw) > MAX_LINE_BYTES or not raw.endswith(b"\n"):
                raise AttributionError("Oversized or incomplete JSONL row")
            yield json.loads(raw)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while block := source.read(1024**2):
            digest.update(block)
    return digest.hexdigest()


def installed_engine_type_receipt(path=SDK_HEADER):
    """Read the exact primary SDK enum instead of guessing numeric EngineType."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    match = re.search(r"typedef\s+enum\s*\{([^}]*DXGK_ENGINE_TYPE_COPY[^}]*)\}\s*DXGK_ENGINE_TYPE", text)
    if not match:
        raise AttributionError("Installed SDK DXGK_ENGINE_TYPE enum is missing")
    names = []
    for entry in match[1].split(","):
        name = entry.strip()
        if not re.fullmatch(r"DXGK_ENGINE_TYPE_[A-Z0-9_]+", name):
            raise AttributionError("SDK enum changed; explicit values require reviewed parsing")
        names.append(name)
    return dict(source="installed-sdk", path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                symbol="DXGK_ENGINE_TYPE_COPY", copy_value=names.index("DXGK_ENGINE_TYPE_COPY"),
                enumerants=names,
                documentation="https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmdt/ne-d3dkmdt-dxgk_engine_type")


def load_namespace_bindings(path):
    """Load reviewed producer dataflow proof scoped to exact installed images.

    This reads and hashes images/PDBs only; it does not load drivers or run code.
    The proof supplies reviewed pointer origins, not inferred raw-value aliases.
    """
    receipt = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if (receipt.get("schema") != "halogen.dxg-field-namespace-bindings.v1" or
        receipt.get("provider") != PROVIDER or not 1 <= len(receipt.get("images", [])) <= 4):
        raise AttributionError("Reviewed namespace binding receipt schema missing")
    names = set()
    for item in receipt["images"]:
        binary, pdb = Path(item["path"]), Path(item["pdb_path"])
        if (not binary.is_absolute() or binary.name.lower() not in {"dxgmms2.sys", "dxgkrnl.sys"} or
            not pdb.is_absolute() or not binary.is_file() or not pdb.is_file() or
            not 0 < binary.stat().st_size <= 64 * 1024**2 or not 0 < pdb.stat().st_size <= 64 * 1024**2 or
            sha256_file(binary).lower() != str(item["sha256"]).lower() or
            sha256_file(pdb).lower() != str(item["pdb_sha256"]).lower() or
            exact_int(item["pdb_dbi_age"]) <= 0 or not item.get("version")):
            raise AttributionError("Namespace binding image/PDB pin does not match local evidence")
        uuid.UUID(item["pdb_guid"])
        names.add(binary.name.lower())
    if "dxgmms2.sys" not in names:
        raise AttributionError("Dxgmms2 producer image proof missing")
    return dict(receipt, images_hash_verified=True)


def verified_namespace_kinds(receipt):
    if (not receipt or receipt.get("schema") != "halogen.dxg-field-namespace-bindings.v1" or
        receipt.get("images_hash_verified") is not True or receipt.get("provider") != PROVIDER):
        return set()
    expected = {
        "global-allocation": ("50/v0", "hAllocationGlobalHandle", {"33/v3", "35/v3"}, "hVidMmGlobalAlloc", {"VIDMM_GLOBAL_ALLOC*"}),
        "hardware-parent-queue": ("450/v0", "hHwQueue", {"422/v0", "424/v0"}, "ParentDxgHwQueue",
                                  {"DXGHWQUEUE*", "DXGHWQUEUE* when parent is present; VIDSCH_HW_QUEUE* when parent is null"}),
    }
    valid = set()
    for binding in receipt.get("bindings", []):
        kind = binding.get("kind")
        if kind not in expected:
            continue
        descriptor, field, targets, target_field, object_types = expected[kind]
        if (binding.get("verified") is True and binding.get("from_descriptor") == descriptor and
            binding.get("from_field") == field and set(binding.get("to_descriptors", [])) == targets and
            binding.get("to_field") == target_field and binding.get("object_type") in object_types and
            isinstance(binding.get("proof"), list) and len(binding["proof"]) >= 2):
            valid.add(kind)
    return valid


def capture_command(recorder, etl, stop_file, *, seconds=30, session=None):
    if type(seconds) is not int or not 1 <= seconds <= 30:
        raise AttributionError("Capture duration must be1..30seconds")
    session = session or "StrixAlloy-GpuCopy-" + uuid.uuid4().hex
    if not re.fullmatch(r"StrixAlloy-GpuCopy-[a-fA-F0-9-]{1,44}", session):
        raise AttributionError("Unique recorder session name required")
    etl, stop_file = Path(etl).resolve(), Path(stop_file).resolve()
    if etl.suffix.lower() != ".etl" or etl == stop_file or etl.exists() or stop_file.exists():
        raise AttributionError("Capture outputs and stop marker must be fresh, distinct paths")
    return [str(Path(recorder).resolve()), "--output", str(etl), "--seconds", str(seconds),
            "--keywords", "0x04900845", "--capture-state", "--session", session,
            "--stop-file", str(stop_file)]


def properties(record):
    result = {}
    for prop in record.get("properties", []):
        name = prop.get("name")
        if not isinstance(name, str) or name in result or prop.get("status") != "materialized":
            raise AttributionError("Property name duplicate/missing or not materialized")
        raw = prop.get("raw_hex")
        if not isinstance(raw, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2})*", raw):
            raise AttributionError("Property raw bytes missing")
        value = bytes.fromhex(raw)
        if len(value) != prop.get("bytes"):
            raise AttributionError("Property byte count mismatch")
        result[name] = dict(prop, raw_bytes=value)
    return result


def numeric(fields, name, *, pointer=False, nonzero=False):
    prop = fields.get(name)
    if not prop:
        raise AttributionError("Missing field:" + name)
    kind, raw = prop.get("in_type"), prop["raw_bytes"]
    sizes = {4: 1, 6: 2, 8: 4, 10: 8, 13: 4, 16: len(raw), 20: 4, 21: 8}
    if kind not in sizes or len(raw) != sizes[kind] or len(raw) not in {1, 2, 4, 8}:
        raise AttributionError("Unsupported numeric schema:" + name)
    if pointer and (kind != 16 or len(raw) not in {4, 8}):
        raise AttributionError("Captured pointer schema required:" + name)
    if prop.get("count_property_index") is not None or prop.get("count") != 1:
        raise AttributionError("Scalar schema required:" + name)
    value = int.from_bytes(raw, "little")
    if nonzero and not value:
        raise AttributionError("Null object field:" + name)
    return value


def text_value(fields, name):
    prop = fields.get(name)
    if not prop or prop.get("in_type") != 1:
        raise AttributionError("Unicode schema required:" + name)
    raw = prop["raw_bytes"]
    if len(raw) % 2 or not raw.endswith(b"\0\0"):
        raise AttributionError("Incomplete Unicode field:" + name)
    return raw.decode("utf-16-le").rstrip("\0")


def guid_value(fields, name):
    prop = fields.get(name)
    if not prop or prop.get("in_type") != 15 or len(prop["raw_bytes"]) != 16:
        raise AttributionError("GUID schema required:" + name)
    return str(uuid.UUID(bytes_le=prop["raw_bytes"]))


class LifetimeIndex:
    def __init__(self):
        self.objects = defaultdict(list)
        self.by_field = defaultdict(list)
        self.by_key = defaultdict(list)
        self.ends_by_field = defaultdict(list)
        self.count = 0
        self.end_count = 0

    def begin(self, kind, key, tick, fields, record, rundown=False):
        active = [item for item in self.by_key[kind, key] if item["end"] is None]
        if rundown and len(active) == 1 and active[0]["fields"] == fields:
            active[0]["evidence"].append(record)
            return
        self.count += 1
        if self.count > MAX_OBJECTS:
            raise AttributionError("Bounded lifetime count exceeded")
        item = dict(key=key, begin=tick, end=None, fields=fields, evidence=[record],
                    begin_point=(tick, record["source_line"]), end_point=None,
                    origin="rundown" if rundown else "start", ambiguous=bool(active))
        for previous in active:
            previous["ambiguous"] = True
        self.objects[kind].append(item)
        self.by_key[kind, key].append(item)
        for name, value in fields.items():
            self.by_field[kind, name, value].append(item)

    def end(self, kind, tick, match, record):
        # A stop before this object's first rundown observation is still a
        # generation barrier. Keep it even when no captured lifetime is active.
        self.end_count += 1
        if self.end_count > MAX_OBJECTS:
            raise AttributionError("Bounded lifetime stop count exceeded")
        tombstone = dict(point=(tick, record["source_line"]), match=match)
        for name, value in match.items():
            self.ends_by_field[kind, name, value].append(tombstone)
        source = min((self.by_field[kind, name, value] for name, value in match.items()), key=len)
        active = [item for item in source if item["end"] is None and
                  all(item["fields"].get(name) == value for name, value in match.items())]
        for item in active:
            item["end"] = tick
            item["end_point"] = tick, record["source_line"]
            item["evidence"].append(record)
            if len(active) != 1:
                item["ambiguous"] = True

    def resolve(self, kind, point, **match):
        source = min((self.by_field[kind, name, value] for name, value in match.items()), key=len)
        candidates = [item for item in source if item["begin_point"] <= point and
                      (item["end_point"] is None or point < item["end_point"]) and
                      all(item["fields"].get(name) == value for name, value in match.items())]
        if len(candidates) != 1 or candidates[0]["ambiguous"]:
            raise AttributionError("Missing or ambiguous " + kind + " lifetime")
        return candidates[0]


    def parent(self, child, kind, work_point, **match):
        try:
            return self.resolve(kind, child["begin_point"], **match)
        except AttributionError:
            if child["origin"] != "rundown":
                raise
        # DC_Start is a state observation, not a birth event. Enumeration may
        # observe a child before its parent. Only later work may use that parent;
        # a true creation event must retain the exact parent-at-birth rule.
        parent = self.resolve(kind, work_point, **match)
        if (parent["origin"] != "rundown" or
            not child["begin_point"] < parent["begin_point"] < work_point):
            raise AttributionError("Missing parent at child birth or rundown observation")
        stops = min((self.ends_by_field[kind, name, value] for name, value in match.items()), key=len)
        if any(child["begin_point"] < stop["point"] <= parent["begin_point"] and
               all(parent["fields"].get(name) == value for name, value in stop["match"].items())
               for stop in stops):
            raise AttributionError("Parent teardown separates rundown observations")
        return parent


def require_prior_rundown(items, work_point):
    if any(item is not None and item["origin"] == "rundown" and
           work_point[0] <= item["begin_point"][0] for item in items):
        raise AttributionError("Work is not strictly after required rundown observations")


def packet_context(index, packet):
    point = packet["start"]["qpc"], packet["start"]["source_line"]
    queue = index.resolve("hwqueue", point, ParentDxgHwQueue=packet["hHwQueue"]) if packet["kind"] == "hardware_info" else None
    context = (index.parent(queue, "context", point, hContext=queue["fields"]["hContext"]) if queue else
               index.resolve("context", point, hContext=packet["hContext"]))
    device = index.parent(context, "device", point, hDevice=context["fields"]["hDevice"])
    require_prior_rundown((queue, context, device), point)
    return queue, context, device


def reference(record):
    return dict(id=record["id"], version=record["version"], qpc=exact_int(record["qpc"]),
                ordinal=record.get("ordinal"), source_line=record.get("source_line"))


def normalize_identities(identities):
    valid = []
    for identity in identities:
        try:
            evidence = identity["linux_task_evidence"]
            pid = exact_int(identity["process_id_in_vm"])
            if (pid <= 0 or exact_int(evidence["initial_namespace_tid"]) != pid or
                exact_int(evidence["start_ticks"]) <= 0 or
                not isinstance(evidence["boot_id"], str) or not evidence["boot_id"] or
                not str(evidence["executable"]).startswith("/") or
                not isinstance(identity["label"], str) or not identity["label"] or
                not isinstance(identity["process_name_in_vm"], str) or not identity["process_name_in_vm"]):
                continue
            lower, upper = exact_int(identity["qpc_before"]), exact_int(identity["qpc_after"])
            if lower > upper:
                continue
            valid.append(dict(identity, vm_guid=str(uuid.UUID(identity["vm_guid"])),
                              process_id_in_vm=pid, qpc_before=lower, qpc_after=upper))
        except (KeyError, TypeError, ValueError, AttributionError):
            continue
    return valid


def trace_integrity(header, summary, recorder, event_count, malformed):
    reasons = []
    if not header or header.get("clock", {}).get("type") != "QPC":
        reasons.append("QPC header missing")
    if not summary or summary.get("decode_success") is not True:
        reasons.append("Complete successful native decode missing")
    else:
        for name in ("dxg_events_seen", "dxg_events_written"):
            if exact_int(summary.get(name)) != event_count:
                reasons.append("Decoder event count mismatch:" + name)
    if malformed:
        reasons.append("Malformed or unsupported attribution schemas")
    if (recorder.get("mode") != "capture" or recorder.get("success") is not True or
        recorder.get("owned_session_closed") is not True or recorder.get("owned_session_may_remain") is not False or
        any(recorder.get(name) != 0 for name in ("start_code", "enable_code", "stop_code"))):
        reasons.append("Completed owned recorder receipt missing")
    stats = recorder.get("final_stats")
    if not stats or stats.get("statistics_available") is not True or any(
            stats.get(name) != 0 for name in ("events_lost", "log_buffers_lost", "realtime_buffers_lost")):
        reasons.append("Final zero loss counters missing or nonzero")
    if header:
        input_path, output_path = header.get("input"), recorder.get("output")
        if (not isinstance(input_path, str) or not isinstance(output_path, str) or
            not ntpath.isabs(input_path) or not ntpath.isabs(output_path) or
            ntpath.normcase(ntpath.normpath(input_path)) != ntpath.normcase(ntpath.normpath(output_path))):
            reasons.append("Recorder loss receipt belongs to a different or unidentified ETL")
        try:
            if exact_int(header.get("input_bytes")) != exact_int(recorder.get("file_bytes")):
                reasons.append("Recorder/decoded ETL file size mismatch")
        except AttributionError:
            reasons.append("Recorder/decoded ETL file size binding missing")
        if any(header.get("header_statistics", {}).get(name) != 0 for name in ("events_lost", "buffers_lost")):
            reasons.append("ETL header loss counters missing or nonzero")
        if exact_int(header.get("clock", {}).get("perf_freq")) != recorder.get("qpc_frequency"):
            reasons.append("Recorder/ETL QPC frequency mismatch")
    return dict(qualified=not reasons, reasons=reasons,
                zero_loss_scope="enabled/emitted records only; coverage is independently observed")


def valid_native_node_metadata(mapping, *, instance=None, qpc_frequency=None):
    """Validate an actual collector receipt, including owned-handle cleanup.

    The metadata query is a point observation. It does not attest the PDH PID or
    establish adapter/node generation continuity over an integration interval.
    """
    if not isinstance(mapping, dict):
        return False
    try:
        match = PDH_COPY_INSTANCE.fullmatch(mapping.get("instance", ""))
        if not match or (instance is not None and mapping["instance"] != instance):
            return False
        luid = (int(match[2], 16) << 32) | int(match[3], 16)
        physical, node = int(match[4]), int(match[5])
        return (
            physical <= 65535 and node <= 65535 and 0 < int(match[1]) <= 0xffffffff and
            mapping.get("schema") == "halogen.gpu-node-metadata.v1" and
            mapping.get("success") is True and mapping.get("api") == "D3DKMTQueryAdapterInfo" and
            mapping.get("type") == "KMTQAITYPE_NODEMETADATA" and
            all(exact_int(mapping.get(field)) == 0 for field in
                ("status", "open_adapter_status", "physical_count_status", "close_adapter_status")) and
            exact_int(mapping.get("input_pdh_pid")) == int(match[1]) and
            mapping.get("adapter_luid") == f"0x{luid:016x}" and
            exact_int(mapping.get("physical_index")) == physical and
            exact_int(mapping.get("node_ordinal")) == node and
            exact_int(mapping.get("physical_adapter_count")) > physical and
            exact_int(mapping.get("NodeOrdinalAndAdapterIndex")) == (physical << 16) | node and
            exact_int(mapping.get("EngineType")) == 6 and
            exact_int(mapping.get("qpc_frequency")) > 0 and
            (qpc_frequency is None or exact_int(mapping.get("qpc_frequency")) == qpc_frequency) and
            0 < exact_int(mapping.get("qpc_before")) <= exact_int(mapping.get("qpc_after")) and
            bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(mapping.get("native_executable_sha256", "")))))
    except (AttributionError, TypeError):
        return False


def evaluate_pdh_intervals(packets, integrity, recorder, intervals, *, transfer_count,
                           reference_count, hardware_packet_count):
    """Evaluate supplied prospective PDH evidence; absence is not a false axiom.

    The native node query receipt must explicitly bind physical adapter/index.
    Allocation-namespace or GPU execution timing gaps are tested separately;
    equality of raw handles and event durations cannot close them.
    """
    if intervals is None:
        return dict(status="not-requested", qualified=None, intervals=[])
    evaluations = []
    for interval in intervals:
        reasons = []
        try:
            start, end = exact_int(interval["start_qpc"]), exact_int(interval["end_qpc"])
            match = PDH_COPY_INSTANCE.fullmatch(interval["instance"])
            if not match or start >= end or interval.get("raw_pair_valid") is not True:
                raise AttributionError("Exact valid PDH raw interval and Copy instance required")
            luid = (int(match[2], 16) << 32) | int(match[3], 16)
            physical, node = int(match[4]), int(match[5])
            mapping = interval.get("native_node_metadata", {})
            if not valid_native_node_metadata(mapping, instance=interval["instance"], qpc_frequency=recorder.get("qpc_frequency")):
                reasons.append("Native adapter LUID/physical index/node metadata receipt missing")
            elif mapping["physical_adapter_count"] != 1 or physical != 0:
                reasons.append("Captured context physical adapter index is missing for a linked adapter")
            if not integrity["qualified"]:
                reasons.append("Trace integrity is not qualified")
            if not (exact_int(recorder["enabled"]["qpc_after"]) <= start < end <=
                    exact_int(recorder["stop_begin"]["qpc_before"])):
                reasons.append("PDH integration interval is not enclosed by capture")
            relevant = [packet for packet in packets if packet["start"]["qpc"] <= end and
                        (packet["end"] is None or packet["end"]["qpc"] >= start)]
            unknown = [packet for packet in relevant if not packet["engine"]]
            engine_packets = [packet for packet in relevant if packet["engine"] and
                              packet["engine"]["AdapterLuid"] == f"0x{luid:016x}" and
                              packet["engine"]["NodeOrdinal"] == node and packet["engine"]["class"] == "copy"]
            labels = set(interval.get("admitted_labels", []))
            if unknown or not engine_packets or any(packet["status"] != "resolved" or not packet["owner"] or
                    packet["owner"]["label"] not in labels for packet in engine_packets):
                reasons.append("Copy execution packets are missing, unresolved, foreign or unattested")
            if transfer_count or reference_count:
                reasons.append("Captured allocation references/transfers require beneficiary namespace/lifetime joins")
            if hardware_packet_count:
                reasons.append("Hardware-queue packet execution/coverage must be joined to the PDH interval")
            # Current primary GPUView documentation distinguishes HW queue time,
            # GPU start, ISR completion and DPC completion.175/176 alone do not
            # establish which interval the counter integrates. Test the supplied
            # exact event-field binding receipt, not an untyped bool override.
            timing = interval.get("execution_timing_binding", {})
            if (timing.get("provider") != PROVIDER or timing.get("start_descriptor") != "175/v1" or
                timing.get("stop_descriptor") != "176/v0" or timing.get("semantics") != "GPU-execution" or
                timing.get("pdh_timebase") != recorder.get("qpc_frequency") or
                not re.fullmatch(r"[0-9a-fA-F]{64}", str(timing.get("primary_source_sha256", "")))):
                reasons.append("Exact GPU execution/PDH integration semantics binding missing")
            if interval.get("instance_generation_continuity") != "captured-adapter-node-lifetime":
                reasons.append("PDH instance generation continuity missing")
            evaluations.append(dict(instance=interval["instance"], start_qpc=start, end_qpc=end,
                                    qualified=not reasons, reasons=reasons,
                                    captured_engine_packets=len(engine_packets)))
        except (KeyError, TypeError, ValueError, AttributionError) as error:
            evaluations.append(dict(qualified=False, reasons=[str(error)]))
    return dict(status="evaluated", qualified=bool(evaluations and all(item["qualified"] for item in evaluations)),
                intervals=evaluations)


def analyze_records(records, recorder, identities=(), *, engine_type_receipt=None, pdh_intervals=None,
                    native_node_metadata=(), namespace_bindings=None):
    index, pending, packets = LifetimeIndex(), defaultdict(list), []
    allocation_records, reference_elements = [], 0
    counts, schema_counts = Counter(), Counter()
    malformed, unjoinable, header, summary, event_count, last_tick = [], [], None, None, 0, None
    unjoinable_count = 0
    identities = normalize_identities(identities)
    namespace_kinds = verified_namespace_kinds(namespace_bindings)
    native_nodes, native_node_keys, native_node_record_count = [], set(), 0
    for mapping in native_node_metadata:
        native_node_record_count += 1
        if native_node_record_count > MAX_NATIVE_NODE_RECEIPTS:
            raise AttributionError("Bounded native node receipt count exceeded")
        if valid_native_node_metadata(mapping, qpc_frequency=recorder.get("qpc_frequency")):
            key = (mapping["adapter_luid"], mapping["physical_index"], mapping["node_ordinal"], mapping["EngineType"])
            if key not in native_node_keys:
                native_node_keys.add(key)
                native_nodes.append(mapping)
    engine_type_receipt = engine_type_receipt or {}
    engine_copy = engine_type_receipt.get("copy_value") if engine_type_receipt.get("source") == "installed-sdk" else None
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(engine_type_receipt.get("sha256", ""))):
        engine_copy = None
    for line_number, row in enumerate(records, 1):
        if not isinstance(row, dict):
            raise AttributionError("JSONL object required")
        kind = row.get("type")
        if kind == "trace_header":
            if header or event_count:
                raise AttributionError("Trace header duplicated or reordered")
            header = row
            continue
        if kind == "summary":
            if summary:
                raise AttributionError("Decoder summary duplicated")
            summary = row
            continue
        if kind != "event":
            raise AttributionError("Unknown native decoder row")
        if summary:
            raise AttributionError("Event after decoder summary")
        event_count += 1
        eid, version = row.get("id"), row.get("version")
        counts[str(eid)] += 1
        schema_counts[f"{eid}/v{version}"] += 1
        if eid not in VERSIONS:
            continue
        row = dict(row, source_line=line_number)
        try:
            if row.get("provider") != PROVIDER or version != VERSIONS[eid] or row.get("status") != "materialized" or row.get("properties_complete") is not True:
                raise AttributionError("Provider/version/materialization mismatch")
            tick = exact_int(row["qpc"])
            if last_tick is not None and tick < last_tick:
                raise AttributionError("Attribution event QPC order regresses")
            last_tick = tick
            fields, ref = properties(row), reference(row)
            pointer = lambda name: numeric(fields, name, pointer=True, nonzero=True)
            if eid in {474, 493}:
                info = dict(DxgVirtualMachine=pointer("DxgVirtualMachine"), VmGuid=guid_value(fields, "VmGuid"))
                index.begin("vm", info["DxgVirtualMachine"], tick, info, ref, eid == 493)
            elif eid == 475:
                index.end("vm", tick, dict(DxgVirtualMachine=pointer("DxgVirtualMachine")), ref)
            elif eid in {472, 492}:
                info = dict(DxgProcess=pointer("DxgProcess"), DxgVirtualMachine=pointer("DxgVirtualMachine"),
                            ProcessIdInVm=numeric(fields, "ProcessIdInVm", pointer=True, nonzero=True),
                            DxgProcessInVm=pointer("DxgProcessInVm"), ProcessNameInVm=text_value(fields, "ProcessNameInVm"))
                index.begin("guest", info["DxgProcess"], tick, info, ref, eid == 492)
            elif eid in {473, 477}:
                index.end("guest", tick, dict(DxgProcess=pointer("DxgProcess")), ref)
            elif eid in {27, 29}:
                info = dict(hDevice=pointer("hDevice"), pDxgAdapter=pointer("pDxgAdapter"),
                            DxgProcess=numeric(fields, "DxgProcess", pointer=True))
                index.begin("device", (info["pDxgAdapter"], info["hDevice"]), tick, info, ref, eid == 29)
            elif eid == 28:
                index.end("device", tick, dict(hDevice=pointer("hDevice"), pDxgAdapter=pointer("pDxgAdapter")), ref)
            elif eid in {30, 32}:
                info = dict(hContext=pointer("hContext"), hDevice=pointer("hDevice"), NodeOrdinal=numeric(fields, "NodeOrdinal"))
                index.begin("context", (info["hDevice"], info["hContext"]), tick, info, ref, eid == 32)
            elif eid == 31:
                index.end("context", tick, dict(hContext=pointer("hContext")), ref)
            elif eid == 110:
                info = dict(pDxgAdapter=pointer("pDxgAdapter"), AdapterLuid=numeric(fields, "AdapterLuid"))
                index.begin("adapter", info["pDxgAdapter"], tick, info, ref, True)
            elif eid == 250:
                info = dict(pDxgAdapter=pointer("pDxgAdapter"), NodeOrdinal=numeric(fields, "NodeOrdinal"),
                            EngineType=numeric(fields, "EngineType"), FriendlyName=text_value(fields, "FriendlyName"))
                index.begin("node", (info["pDxgAdapter"], info["NodeOrdinal"]), tick, info, ref, True)
            elif eid in {33, 34, 35, 36, 37, 38, 43, 50, 53}:
                if len(allocation_records) >= MAX_OBJECTS:
                    raise AttributionError("Bounded allocation provenance count exceeded")
                evidence = dict(event=ref, kind="allocation", fields={})
                for name in ("hDevice", "pDxgAdapter", "hVidMmAlloc", "hVidMmGlobalAlloc", "hDxgGlobalAlloc",
                             "hDxgSharedResource", "hProcessId", "hAllocationGlobalHandle", "pDmaBuffer", "hDmaBuffer", "hContext"):
                    if name in fields:
                        evidence["fields"][name] = numeric(fields, name, pointer=True)
                for name in ("offset", "size", "uiType", "allocSize", "PhysicalAdapterIndex", "Flags"):
                    if name in fields:
                        evidence["fields"][name] = numeric(fields, name)
                if eid == 43:
                    count = numeric(fields, "uiNbAllocations")
                    array = fields.get("Allocations", {})
                    width = row.get("pointer_width")
                    if (width not in {4, 8} or array.get("in_type") != 16 or
                        array.get("count_property_index") is None or
                        len(array.get("raw_bytes", b"")) != count * width):
                        raise AttributionError("Captured TDH pointer-array schema/count required for Allocations")
                    reference_elements += count
                    if reference_elements > 100000:
                        raise AttributionError("Bounded referenced allocation element count exceeded")
                    raw = array["raw_bytes"]
                    evidence.update(kind="reference", allocations=[int.from_bytes(raw[offset:offset + width], "little")
                                                                   for offset in range(0, len(raw), width)],
                                    allocation_namespace="unresolved; array schema does not name a handle namespace")
                elif eid in {50, 53}:
                    evidence["kind"] = "transfer"
                allocation_records.append(evidence)
                if eid in {33, 35}:
                    info = {name: numeric(fields, name, pointer=True) for name in
                            ("hDevice", "pDxgAdapter", "hVidMmGlobalAlloc", "hDxgGlobalAlloc", "hDxgSharedResource")}
                    if not info["pDxgAdapter"] or not info["hVidMmGlobalAlloc"]:
                        raise AttributionError("Null object field:global allocation identity")
                    info["allocSize"] = numeric(fields, "allocSize")
                    info["PhysicalAdapterIndex"] = numeric(fields, "PhysicalAdapterIndex")
                    index.begin("global_allocation", (info["pDxgAdapter"], info["hVidMmGlobalAlloc"]), tick, info, ref, eid == 35)
                elif eid == 34:
                    index.end("global_allocation", tick, {name: pointer(name) for name in
                              ("pDxgAdapter", "hVidMmGlobalAlloc")}, ref)
                elif eid in {36, 38}:
                    info = {name: numeric(fields, name, pointer=True) for name in
                            ("hDevice", "pDxgAdapter", "hVidMmAlloc", "hVidMmGlobalAlloc")}
                    if not info["pDxgAdapter"] or not info["hVidMmAlloc"]:
                        raise AttributionError("Null object field:local allocation identity")
                    index.begin("local_allocation", (info["pDxgAdapter"], info["hVidMmAlloc"]), tick, info, ref, eid == 38)
                elif eid == 37:
                    index.end("local_allocation", tick, {name: pointer(name) for name in
                              ("pDxgAdapter", "hVidMmAlloc")}, ref)
            elif eid in {422, 424}:
                # These records expose a local hHwQueue plus its captured host
                # ParentDxgHwQueue. Info450 names the parent host queue. Preserve
                # both namespaces; a null local handle does not erase its parent.
                info = dict(hHwQueue=numeric(fields, "hHwQueue", pointer=True), hContext=pointer("hContext"),
                            ParentDxgHwQueue=pointer("ParentDxgHwQueue"))
                index.begin("hwqueue", info["ParentDxgHwQueue"], tick, info, ref, eid == 424)
            elif eid == 423:
                index.end("hwqueue", tick, dict(ParentDxgHwQueue=pointer("ParentDxgHwQueue"),
                                                hContext=pointer("hContext")), ref)
            elif eid == 450:
                if len(packets) >= MAX_PACKETS:
                    raise AttributionError("Bounded packet count exceeded")
                packets.append(dict(kind="hardware_info", start=ref, end=ref,
                                    header_pid=row.get("header_pid"), hHwQueue=numeric(fields, "hHwQueue", pointer=True),
                                    hContext=None, pDmaBuffer=numeric(fields, "pDmaBuffer", pointer=True),
                                    ProgressFenceValue=numeric(fields, "ProgressFenceValue"),
                                    owner=None, engine=None, status="unresolved", reasons=[],
                                    interval_semantics="Info450 has no GPU execution duration"))
            elif eid == 175:
                if len(packets) >= MAX_PACKETS:
                    raise AttributionError("Bounded packet count exceeded")
                packet = dict(kind="dma_span", start=ref, end=None, header_pid=row.get("header_pid"),
                              hContext=numeric(fields, "hContext", pointer=True), sequence=numeric(fields, "ulQueueSubmitSequence"),
                              pDmaBuffer=numeric(fields, "pDmaBuffer", pointer=True), PacketType=numeric(fields, "PacketType"),
                              owner=None, engine=None, status="unresolved", reasons=[])
                key = packet["hContext"], packet["sequence"]
                if pending[key]:
                    packet["reasons"].append("Sequence reused before unique completion")
                    for previous in pending[key]:
                        previous["reasons"].append("Sequence reused before unique completion")
                pending[key].append(packet)
                packets.append(packet)
            elif eid == 176:
                key = numeric(fields, "hContext", pointer=True), numeric(fields, "ulQueueSubmitSequence")
                active = pending.pop(key, [])
                if len(active) == 1:
                    if numeric(fields, "PacketType") != active[0]["PacketType"]:
                        active[0]["reasons"].append("DMA Start/Stop packet type mismatch")
                    else:
                        active[0]["end"] = ref
                        active[0]["preempted"] = bool(numeric(fields, "bPreempted"))
                elif active:
                    for packet in active:
                        packet["reasons"].append("Ambiguous completion for reused sequence")
        except (AttributionError, KeyError, ValueError, UnicodeError) as error:
            if "Bounded " in str(error):
                raise
            if str(error).startswith("Null object field:"):
                # A materialized null object pointer is a semantic join gap,
                # not evidence that ETW/TDH failed to decode its schema. Never
                # place null keys in the object lifetime index.
                unjoinable_count += 1
                if len(unjoinable) < 128:
                    unjoinable.append(dict(id=eid, version=version, source_line=line_number, reason=str(error)))
            elif len(malformed) < 128:
                malformed.append(dict(id=eid, version=version, source_line=line_number, reason=str(error)))
    integrity = trace_integrity(header, summary, recorder, event_count, malformed)
    for packet in packets:
        if not packet["end"]:
            packet["reasons"].append("Unique DMA Stop176 missing")
        else:
            try:
                if not (exact_int(recorder["enabled"]["qpc_after"]) <= packet["start"]["qpc"] <=
                        packet["end"]["qpc"] <= exact_int(recorder["stop_begin"]["qpc_before"])):
                    packet["reasons"].append("Packet span outside completed enabled capture window")
            except (KeyError, TypeError, AttributionError):
                packet["reasons"].append("Exact enabled/stop QPC brackets missing")
        try:
            tick = packet["start"]["qpc"]
            packet_point = tick, packet["start"]["source_line"]
            queue, context, device = packet_context(index, packet)
            if queue:
                packet["hContext"] = queue["fields"]["hContext"]
                packet["hardware_queue_binding"] = dict(info_field="450.hHwQueue",
                    lifetime_field="422/424.ParentDxgHwQueue", host_parent=queue["fields"]["ParentDxgHwQueue"],
                    local_handle=queue["fields"]["hHwQueue"], evidence=queue["evidence"],
                    resolution="producer-origin-verified" if "hardware-parent-queue" in namespace_kinds else "observed-parent-value-match",
                    namespace_semantics_verified="hardware-parent-queue" in namespace_kinds)
                if "hardware-parent-queue" not in namespace_kinds:
                    packet["reasons"].append("Info450/ParentDxgHwQueue namespace semantics binding is not verified")
            guest = index.parent(device, "guest", packet_point, DxgProcess=device["fields"]["DxgProcess"])
            vm = index.parent(guest, "vm", packet_point, DxgVirtualMachine=guest["fields"]["DxgVirtualMachine"])
            require_prior_rundown((guest, vm), packet_point)
            end_point = (packet["end"]["qpc"], packet["end"]["source_line"]) if packet["end"] else packet_point
            if any(item["end_point"] is not None and end_point >= item["end_point"]
                   for item in ((context, device, guest, vm, queue) if queue else (context, device, guest, vm))):
                raise AttributionError("Ownership lifetime ends before packet completion")
            owner = dict(process_id_in_vm=guest["fields"]["ProcessIdInVm"],
                         process_name_in_vm=guest["fields"]["ProcessNameInVm"],
                         vm_guid=vm["fields"]["VmGuid"], label=None, linux_task_evidence=None,
                         evidence=context["evidence"] + device["evidence"] + guest["evidence"] + vm["evidence"])
            observations = [item["evidence"][0] for item in (queue, context, device, guest, vm)
                            if item is not None and item["origin"] == "rundown"]
            if observations:
                owner["required_rundown_observations"] = observations
            if queue:
                owner["evidence"] += queue["evidence"]
                if "hardware-parent-queue" not in namespace_kinds:
                    owner["resolution_scope"] = "conditional-on-Info450-host-parent-namespace"
            attestations = [identity for identity in identities if
                           identity["process_id_in_vm"] == owner["process_id_in_vm"] and
                           identity["process_name_in_vm"] == owner["process_name_in_vm"] and
                           identity["vm_guid"] == owner["vm_guid"] and
                           identity["qpc_before"] <= tick and packet["end"] and
                           packet["end"]["qpc"] <= identity["qpc_after"]]
            if len(attestations) == 1:
                owner.update(label=attestations[0]["label"], linux_task_evidence=attestations[0]["linux_task_evidence"])
            packet["owner"] = owner
        except AttributionError as error:
            packet["reasons"].append(str(error))
        try:
            packet_point = packet["start"]["qpc"], packet["start"]["source_line"]
            queue, context, device = packet_context(index, packet)
            adapter = index.resolve("adapter", packet_point, pDxgAdapter=device["fields"]["pDxgAdapter"])
            node = index.resolve("node", packet_point,
                                 pDxgAdapter=device["fields"]["pDxgAdapter"], NodeOrdinal=context["fields"]["NodeOrdinal"])
            require_prior_rundown((adapter, node), packet_point)
            packet["engine"] = dict(node["fields"], AdapterLuid=f"0x{adapter['fields']['AdapterLuid']:016x}",
                                    **{"class": "copy" if engine_copy is not None and node["fields"]["EngineType"] == engine_copy
                                       else "other" if engine_copy is not None else "unresolved"},
                                    evidence=adapter["evidence"] + node["evidence"])
        except AttributionError as error:
            packet["reasons"].append(str(error))
        if packet["engine"]:
            matches = [mapping for mapping in native_nodes if
                       mapping["adapter_luid"] == packet["engine"]["AdapterLuid"] and
                       mapping["node_ordinal"] == packet["engine"]["NodeOrdinal"] and
                       packet["engine"]["class"] == "copy" and
                       mapping["physical_adapter_count"] == 1 and mapping["physical_index"] == 0]
            if matches:
                packet["engine"].update(physical_index=0, native_node_metadata_evidence=matches,
                                        physical_mapping_scope="point-query; instance generation continuity is not established")
        if not packet["reasons"] and packet["owner"] and packet["engine"]:
            packet["status"] = "resolved" if integrity["qualified"] else "unqualified"
    hardware_packets = [packet for packet in packets if packet["kind"] == "hardware_info"]
    dma_packets = [packet for packet in packets if packet["kind"] == "dma_span"]
    copies = [packet for packet in dma_packets if packet["engine"] and packet["engine"]["class"] == "copy"]
    hardware_copies = [packet for packet in hardware_packets if packet["engine"] and packet["engine"]["class"] == "copy"]
    unresolved = [packet for packet in dma_packets if packet["status"] != "resolved"]
    unresolved_hardware = [packet for packet in hardware_packets if packet["status"] != "resolved"]
    owner_counts = Counter((packet["owner"]["label"] or "unattested-guest",
                            packet["engine"]["class"] if packet["engine"] else "unresolved-engine",
                            packet["status"])
                           for packet in packets if packet["owner"])
    provenance_by_dma = defaultdict(list)
    for record in allocation_records:
        # Same-named pDmaBuffer fields join. hDmaBuffer and global allocation
        # field names stay separate even when their values happen to coincide.
        if record["fields"].get("pDmaBuffer"):
            provenance_by_dma[record["fields"]["pDmaBuffer"]].append(record)
    previous_completion = {}
    for packet in dma_packets:
        prior = previous_completion.get(packet["pDmaBuffer"], (0, 0))
        start_point = packet["start"]["qpc"], packet["start"]["source_line"]
        packet["allocation_provenance_candidates"] = [record for record in provenance_by_dma[packet["pDmaBuffer"]]
            if prior < (record["event"]["qpc"], record["event"]["source_line"]) <= start_point] if packet["pDmaBuffer"] else []
        packet["allocation_beneficiaries_resolved"] = False if packet["allocation_provenance_candidates"] else None
        if packet["end"]:
            previous_completion[packet["pDmaBuffer"]] = packet["end"]["qpc"], packet["end"]["source_line"]
    observed_transfer_associations = []
    for transfer in allocation_records:
        if transfer["kind"] != "transfer" or not transfer["fields"].get("hAllocationGlobalHandle"):
            continue
        point = transfer["event"]["qpc"], transfer["event"]["source_line"]
        alias_verified = ("global-allocation" in namespace_kinds and transfer["event"]["id"] == 50 and
                          transfer["event"]["version"] == 0)
        association = dict(transfer=transfer, global_namespace_alias_verified=alias_verified,
                           beneficiary_ownership_qualified=False, allocation_origin_qualified=False,
                           predicates=["materialized Transfer50/53.hAllocationGlobalHandle raw value equals Allocation33/35.hVidMmGlobalAlloc",
                                       "unique allocation lifetime encloses transfer QPC and source order",
                                       "device binds at allocation creation or within a continuous rundown chain observed before transfer"], reasons=[])
        try:
            enabled_transfer = (exact_int(recorder["enabled"]["qpc_after"]) <= point[0] <=
                                exact_int(recorder["stop_begin"]["qpc_before"]))
        except (KeyError, TypeError, AttributionError):
            enabled_transfer = False
        association["within_enabled_capture_window"] = enabled_transfer
        try:
            glob = index.resolve("global_allocation", point,
                                 hVidMmGlobalAlloc=transfer["fields"]["hAllocationGlobalHandle"])
            association["global_allocation_lifetime"] = glob
            device = index.parent(glob, "device", point, hDevice=glob["fields"]["hDevice"],
                                  pDxgAdapter=glob["fields"]["pDxgAdapter"])
            guest = index.parent(device, "guest", point, DxgProcess=device["fields"]["DxgProcess"])
            vm = index.parent(guest, "vm", point, DxgVirtualMachine=guest["fields"]["DxgVirtualMachine"])
            require_prior_rundown((glob, device, guest, vm), point)
            if any(item["end_point"] is not None and point >= item["end_point"] for item in (device, guest, vm)):
                raise AttributionError("Allocation origin owner lifetime ended before transfer")
            association["guest_origin_candidate"] = dict(process_id_in_vm=guest["fields"]["ProcessIdInVm"],
                process_name_in_vm=guest["fields"]["ProcessNameInVm"], vm_guid=vm["fields"]["VmGuid"],
                evidence=device["evidence"] + guest["evidence"] + vm["evidence"])
            origin = association["guest_origin_candidate"]
            attestations = [identity for identity in identities if
                           identity["process_id_in_vm"] == origin["process_id_in_vm"] and
                           identity["process_name_in_vm"] == origin["process_name_in_vm"] and
                           identity["vm_guid"] == origin["vm_guid"] and
                           identity["qpc_before"] <= point[0] <= identity["qpc_after"]]
            if len(attestations) == 1:
                origin.update(label=attestations[0]["label"], linux_task_evidence=attestations[0]["linux_task_evidence"])
                association["allocation_origin_qualified"] = bool(alias_verified and integrity["qualified"] and enabled_transfer)
            association["active_local_allocation_references"] = [item for item in
                index.by_field["local_allocation", "hVidMmGlobalAlloc", glob["fields"]["hVidMmGlobalAlloc"]]
                if item["begin_point"] <= point and (item["end_point"] is None or point < item["end_point"]) and
                   item["fields"]["pDxgAdapter"] == glob["fields"]["pDxgAdapter"] and
                   glob["begin_point"] <= item["begin_point"] and
                   (glob["end_point"] is None or item["begin_point"] < glob["end_point"])]
        except AttributionError as error:
            association["reasons"].append(str(error))
        # This preserves an observed association, not a verified packet batch:
        # a reused pDmaBuffer may name many submissions. Retain only the first
        # succeeding same-named pointer match and do not infer execution time.
        dma = next((packet for packet in dma_packets if transfer["fields"].get("pDmaBuffer") and
                    packet["pDmaBuffer"] == transfer["fields"]["pDmaBuffer"] and
                    (packet["start"]["qpc"], packet["start"]["source_line"]) >= point), None)
        if dma:
            association["first_subsequent_same_named_pDmaBuffer_match"] = dict(start=dma["start"], end=dma["end"],
                hContext=dma["hContext"], engine=dma["engine"],
                match_scope="observed pointer and source order; DMA batch membership is not verified")
        observed_transfer_associations.append(association)
    pdh_evaluation = evaluate_pdh_intervals(packets, integrity, recorder, pdh_intervals,
                                          transfer_count=counts["50"] + counts["53"],
                                          reference_count=counts["43"], hardware_packet_count=counts["450"])
    physical_bound_count = sum(bool(packet["engine"] and packet["engine"].get("native_node_metadata_evidence"))
                               for packet in packets)
    return dict(schema="halogen.gpu-copy.attribution.v1", trace_integrity=integrity,
                event_count=event_count, event_id_counts=dict(sorted(counts.items(), key=lambda item: int(item[0]))),
                descriptor_counts=dict(sorted(schema_counts.items())), malformed_schemas=malformed,
                unjoinable_object_records=unjoinable, unjoinable_object_record_count=unjoinable_count,
                native_node_metadata_receipts=native_nodes,
                native_node_metadata_input_count=native_node_record_count,
                physical_node_metadata_bound_packet_count=physical_bound_count,
                physical_node_mapping=dict(status="point-mapping-observed" if native_nodes else "not-observed",
                    accepted_receipts=len(native_nodes), bound_packets=physical_bound_count,
                    coverage_scope="queried Copy nodes only", instance_generation_continuity=False,
                    pid_ownership_attested=False),
                allocation_provenance_records=allocation_records,
                observed_transfer_global_associations=observed_transfer_associations,
                namespace_bindings=namespace_bindings,
                verified_namespace_kinds=sorted(namespace_kinds),
                lifecycle_counts={kind: len(items) for kind, items in index.objects.items()},
                guest_bridge_observed=bool(index.objects["guest"] and index.objects["vm"]),
                capture_state_requested=recorder.get("capture_state_requested") is True,
                capture_state_code=recorder.get("capture_state_code"),
                rundown_complete=False, engine_type_receipt=engine_type_receipt,
                packets=dma_packets, hardware_packets=hardware_packets, copy_packet_count=len(copies),
                hardware_copy_packet_count=len(hardware_copies), unresolved_packet_count=len(unresolved),
                unresolved_hardware_packet_count=len(unresolved_hardware),
                captured_copy_packet_owners_resolved=bool(integrity["qualified"] and (copies or hardware_copies) and
                                                        not unresolved and not unresolved_hardware),
                attested_copy_packet_count=sum(bool(packet["owner"] and packet["owner"]["label"]) for packet in copies),
                captured_guest_packet_count=sum(bool(packet["owner"] and not packet["owner"].get("resolution_scope")) for packet in packets),
                hardware_parent_owner_candidate_count=sum(bool(packet["owner"] and packet["owner"].get("resolution_scope")) for packet in packets),
                attested_guest_packet_count=sum(bool(packet["owner"] and packet["owner"]["label"] and
                    not packet["owner"].get("resolution_scope")) for packet in packets),
                owner_summary=[dict(label=key[0], engine_class=key[1], status=key[2], packets=count)
                               for key, count in sorted(owner_counts.items())],
                pdh_exclusive_ownership_qualified=pdh_evaluation["qualified"], pdh_evaluation=pdh_evaluation, speed_gain=False,
                packet_interval_semantics="Start175/Stop176 event span paired only by hContext+ulQueueSubmitSequence; GPU occupancy/preemption accounting not inferred",
                unresolved_bridges=["PDH complete integration interval and adapter/node generation continuity" if physical_bound_count else
                                    "PDH physical-adapter/index and complete integration interval",
                                    "System paging allocation beneficiaries and sharing",
                                    "Allocations[] namespace; committed DMA batch membership and allocation sharing" if "global-allocation" in namespace_kinds else
                                    "Allocations[] namespace; global allocation and hDmaBuffer/pDmaBuffer aliases",
                                    "Unobserved records and provider rundown completeness"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument("--recorder-receipts", type=Path, required=True)
    parser.add_argument("--identities", type=Path)
    parser.add_argument("--pdh-intervals", type=Path)
    parser.add_argument("--native-node-metadata", type=Path)
    parser.add_argument("--namespace-bindings", type=Path)
    parser.add_argument("--sdk-header", type=Path, default=SDK_HEADER)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipts = [record for record in stream_jsonl(args.recorder_receipts) if record.get("event") == "recorder_receipt"]
    if len(receipts) != 1:
        raise AttributionError("Exactly one final recorder receipt is required")
    identities = json.loads(args.identities.read_text(encoding="utf-8-sig")) if args.identities else []
    result = analyze_records(stream_jsonl(args.decoded), receipts[0], identities,
                             engine_type_receipt=installed_engine_type_receipt(args.sdk_header),
                             pdh_intervals=json.loads(args.pdh_intervals.read_text(encoding="utf-8-sig")) if args.pdh_intervals else None,
                             native_node_metadata=stream_jsonl(args.native_node_metadata) if args.native_node_metadata else (),
                             namespace_bindings=load_namespace_bindings(args.namespace_bindings) if args.namespace_bindings else None)
    result["inputs"] = {str(path.resolve()): dict(sha256=sha256_file(path), bytes=path.stat().st_size)
                        for path in (Path(__file__), args.sdk_header, args.decoded, args.recorder_receipts,
                                     args.native_node_metadata, args.namespace_bindings, args.identities, args.pdh_intervals)
                        if path is not None}
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({key: result[key] for key in ("trace_integrity", "event_count", "guest_bridge_observed",
                                                 "copy_packet_count", "captured_copy_packet_owners_resolved",
                                                 "attested_copy_packet_count", "unresolved_packet_count")}))


if __name__ == "__main__":
    main()
