"""Build an explicitly derived, fresh-instance-only, no-delete Update Set XML.

This reads an actual native export. It never calls ServiceNow or executes stored
scripts. Native received-import/preview compatibility remains a separate check.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET
from xml.parsers import expat


ROOT_NAME = "Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028"
OUTPUT_NAME = "Custom-LLM-Platform-2.2-Fresh-Instance-NO-DELETE-20261028.xml"
EXPECTED_INPUT = "16bd719d2ed1edc4ed28a8f87e4ac76db7504eb4e7252c519514ccfa58159e8d"
EXPECTED_OVERLAY = "a858632bcabecab810dccb6ffc82fb16c60827cdb9e37557f9e1ed8f0298e37f"
OVERLAY_NAME = "sys_script_include_6bf331459344d7905c8132d47aba1008"
OVERLAY_SCRIPT = "669a30b84d69c826827fb32d21dd628cf216fb1db69e415c58945b99fd7a5426"
GLOBAL_DELTA = "0d6fda3b9388db545c8132d47aba10e4"
GENAI_BRANCH = "7e0a05ed9308df905c8132d47aba10db"
GENAI_SCOPE = "7cc4ec81533121106b38ddeeff7b12ee"
FRESH_DESCRIPTION = (
    "Derived delivery for FRESH INSTANCES ONLY. This 36-set batch contains exactly "
    "809 unique INSERT_OR_UPDATE records, with zero outer DELETE Customer Updates, "
    "zero embedded delete/delete_multiple transport actions and no insert/delete "
    "name conflicts. It is a reviewed derivation of unchanged native source exports, "
    "not an original native export. Configure ACT governance, credentials, endpoints, "
    "operational bindings and the four custom_llm.prompt_mirror properties locally "
    "on the target: default_model, automation_enabled, apply_enabled and "
    "serialized_execution_verified. Execution gates require target qualification. "
    "Compatible applications, licenses, schemas, native parent configurations and "
    "all other prerequisites must be verified separately. Native received-import "
    "and preview validation are separate checks; no target commit, runtime acceptance "
    "or universal portability is claimed. Original wrapper descriptions and lineage "
    "are preserved in the external derived-delivery manifest."
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_exact(text: str) -> ET.Element:
    if "\ue000" in text or re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
        raise ValueError("Unsupported XML declaration or reserved CR sentinel")
    root = ET.fromstring(text.replace("\r", "\ue000"))
    for node in root.iter():
        if node.text:
            node.text = node.text.replace("\ue000", "\r")
        if node.tail:
            node.tail = node.tail.replace("\ue000", "\r")
    return root


def value(node: ET.Element, name: str) -> str:
    return node.findtext(name) or ""


def field_contract(node: ET.Element):
    """All retained attributes and decoded field text; formatting tails excluded."""
    text = node.text or ""
    if len(node) and not text.strip():
        text = ""
    return [node.tag, sorted(node.attrib.items()), text,
            [field_contract(child) for child in node]]


def contract_hash(node: ET.Element) -> str:
    return digest(json.dumps(field_contract(node), ensure_ascii=True,
                             separators=(",", ":")).encode("utf-8"))


def identity(cu: ET.Element, payload: ET.Element):
    name = value(cu, "name")
    match = re.fullmatch(r"([a-z][a-z0-9_]*)_([0-9a-f]{32})", name)
    table = match.group(1) if match else next(
        (t for t in ("sys_documentation", "sys_dictionary", "sys_index")
         if name.startswith(t + "_")), payload.attrib.get("table"))
    record_id = match.group(2) if match else None
    owners = [node for node in payload.iter()
              if node.tag == table and (not record_id or value(node, "sys_id") == record_id)
              and not any(child.tag == table for child in node)]
    if len(owners) != 1:
        raise ValueError(f"Ambiguous primary record: {name}")
    primary = owners[0]
    fields = {child.tag: child.text or "" for child in primary}
    return table, record_id or fields.get("sys_id"), primary, fields


def destructive_nodes(root: ET.Element):
    return [node for node in root.iter()
            if "delete" in node.attrib.get("action", "").lower()]


def strip_destructive_payload_nodes(payload: str):
    """Use parser byte offsets: every retained original UTF-8 byte stays intact."""
    raw = payload.encode("utf-8")
    parser = expat.ParserCreate()
    stack = []
    removals = []

    def tag_end(start):
        quote = None
        for pos in range(start, len(raw)):
            char = raw[pos]
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in (34, 39):
                quote = char
            elif char == 62:
                return pos + 1
        raise ValueError("Unclosed XML token")

    def start(name, attrs):
        begin = parser.CurrentByteIndex
        end = tag_end(begin)
        stack.append({"tag": name, "attrs": attrs, "begin": begin, "startEnd": end,
                      "selfClosing": raw[begin:end].rstrip().endswith(b"/>"),
                      "remove": "delete" in attrs.get("action", "").lower()})

    def finish(name):
        frame = stack.pop()
        if frame["tag"] != name:
            raise ValueError("Unexpected XML parser stack")
        if frame["remove"]:
            end = frame["startEnd"] if frame["selfClosing"] else tag_end(parser.CurrentByteIndex)
            node_bytes = raw[frame["begin"]:end]
            removals.append({"tag": name, "action": frame["attrs"].get("action"),
                             "attributes": frame["attrs"], "byteStart": frame["begin"],
                             "byteEnd": end, "bytes": len(node_bytes),
                             "sha256": digest(node_bytes), "originalNodeXml": node_bytes.decode("utf-8")})

    parser.StartElementHandler = start
    parser.EndElementHandler = finish
    parser.Parse(raw, True)
    removals.sort(key=lambda row: (row["byteStart"], -row["byteEnd"]))
    spans = []
    for row in removals:
        start, end = row["byteStart"], row["byteEnd"]
        if spans and start < spans[-1][1]:
            if end <= spans[-1][1]:
                continue
            raise ValueError("Overlapping destructive XML ranges")
        spans.append((start, end))
    chunks, cursor = [], 0
    for start, end in spans:
        chunks.append(raw[cursor:start])
        cursor = end
    chunks.append(raw[cursor:])
    output = b"".join(chunks).decode("utf-8")
    if destructive_nodes(parse_exact(output)):
        raise ValueError("Destructive payload action survived removal")
    return output, removals


def prune_tree(root: ET.Element):
    clone = copy.deepcopy(root)
    for parent in clone.iter():
        for child in list(parent):
            if "delete" in child.attrib.get("action", "").lower():
                parent.remove(child)
    return clone


def fresh_id(kind: str, old_id: str, input_hash: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL,
                      f"urn:byollm:{ROOT_NAME}:{input_hash}:{kind}:{old_id}").hex


def set_text(node, name, text):
    field = node.find(name)
    if field is None:
        field = ET.SubElement(node, name)
    field.text = text


def serialize_wrapper(node: ET.Element, payload: str | None = None) -> bytes:
    clone = copy.deepcopy(node)
    marker = None
    if payload is not None:
        marker = "BYOLLM_PAYLOAD_" + value(clone, "sys_id")
        if marker in payload:
            raise ValueError("Payload marker collision")
        clone.find("payload").text = marker
    wire = ET.tostring(clone, encoding="unicode", short_empty_elements=True)
    wire = wire.replace("\r", "&#13;")
    if marker:
        cdata = "<![CDATA[" + payload.replace("]]>", "]]]]><![CDATA[>") + "]]>"
        if wire.count(marker) != 1:
            raise ValueError("Unexpected payload marker count")
        wire = wire.replace(marker, cdata)
    return wire.encode("utf-8")


def build(input_path: Path, output_dir: Path, source_manifest: Path, overlay_path: Path):
    input_bytes = input_path.read_bytes()
    input_hash = digest(input_bytes)
    if input_hash != EXPECTED_INPUT or len(input_bytes) != 5600083:
        raise ValueError("Input is not the pinned actual 868-CU native export")
    source = parse_exact(input_bytes.decode("utf-8-sig"))
    if source.tag != "unload" or any(n.tag not in {"sys_remote_update_set", "sys_update_xml"} for n in source):
        raise ValueError("Unsupported native export structure")
    headers = {}
    for header in source.findall("sys_remote_update_set"):
        key = value(header, "sys_id")
        if key in headers and field_contract(headers[key]) != field_contract(header):
            raise ValueError("Conflicting duplicated native header")
        headers[key] = header
    original_to_remote = {value(h, "remote_sys_id"): key for key, h in headers.items()}
    roots = [key for key, h in headers.items() if not value(h, "parent")]
    cus = source.findall("sys_update_xml")
    if len(headers) != 36 or len(cus) != 868 or len(roots) != 1:
        raise ValueError("Unexpected input counts/hierarchy")
    root_remote = roots[0]
    groups = defaultdict(list)
    app_ids = set()
    for cu in cus:
        payload = value(cu, "payload")
        parsed = parse_exact(payload)
        table, record_id, primary, fields = identity(cu, parsed)
        app_ids.update(value(n, "sys_id") for n in parsed.iter() if n.find("sys_id") is not None)
        header_id = value(cu, "remote_update_set")
        if header_id not in headers:
            raise ValueError("CU has an unknown header")
        own_scope = fields.get("sys_scope") or value(cu, "application")
        revision = fields.get("sys_mod_count", "")
        groups[value(cu, "name")].append({"cu": cu, "payload": payload, "parsed": parsed,
            "table": table, "id": record_id, "primary": primary, "fields": fields,
            "scope": own_scope, "revision": int(revision) if revision.isdigit() else -1,
            "updated": fields.get("sys_updated_on", ""), "header": header_id,
            "scopeMatch": own_scope == value(cu, "application") == value(headers[header_id], "application")})
    deleted = {name for name, rows in groups.items() if any(value(r["cu"], "action") == "DELETE" for r in rows)}
    if len(groups) != 818 or len(deleted) != 9:
        raise ValueError("Unexpected input identity/tombstone counts")
    selection = []
    excluded = []
    discarded = []
    for name, rows in sorted(groups.items()):
        if name in deleted:
            excluded.extend({"name": name, "sourceExportCustomerUpdateId": value(r["cu"], "sys_id"),
                             "action": value(r["cu"], "action"), "sourcePayloadSHA256": digest(r["payload"].encode("utf-8"))}
                            for r in rows)
            continue
        if any(value(r["cu"], "action") != "INSERT_OR_UPDATE" for r in rows):
            raise ValueError("Unknown action in a retained identity")
        highest = max((r["revision"], r["updated"]) for r in rows)
        tied = [r for r in rows if (r["revision"], r["updated"]) == highest]
        signatures = {contract_hash(prune_tree(r["parsed"])) for r in tied}
        if len(signatures) > 1:
            raise ValueError(f"Unresolved same-revision retained-field conflict: {name}")
        selected = max(tied, key=lambda r: (r["scopeMatch"], value(r["cu"], "sys_updated_on"),
                                            value(r["cu"], "sys_id")))
        selected["name"] = name
        selection.append(selected)
        discarded.extend({"name": name, "sourceExportCustomerUpdateId": value(r["cu"], "sys_id"),
                          "revision": r["revision"], "sourceUpdatedOnUtc": r["updated"],
                          "sourcePayloadSHA256": digest(r["payload"].encode("utf-8"))}
                         for r in rows if r is not selected)
    if len(selection) != 809 or len(excluded) != 10 or len(discarded) != 49:
        raise ValueError("Unexpected one-current-version selection counts")
    # One explicit native overlay supersedes an existing base identity. The base
    # capture remains the stable wrapper-ID seed and destination branch; the
    # complete newer native CU supplies all source wrapper and payload fields.
    overlay_bytes = overlay_path.read_bytes()
    if digest(overlay_bytes) != EXPECTED_OVERLAY or len(overlay_bytes) != 20950:
        raise ValueError("Overlay is not the pinned native notice-language export")
    overlay = parse_exact(overlay_bytes.decode("utf-8-sig"))
    overlay_headers = overlay.findall("sys_remote_update_set")
    overlay_cus = overlay.findall("sys_update_xml")
    if (overlay.tag != "unload" or len(overlay) != 2 or
            len(overlay_headers) != 1 or len(overlay_cus) != 1):
        raise ValueError("Expected exactly one native overlay header and CU")
    overlay_header, overlay_cu = overlay_headers[0], overlay_cus[0]
    overlay_payload = value(overlay_cu, "payload")
    overlay_parsed = parse_exact(overlay_payload)
    overlay_table, overlay_id, overlay_primary, overlay_fields = identity(overlay_cu, overlay_parsed)
    base = next(row for row in selection if row["name"] == OVERLAY_NAME)
    if (value(overlay_cu, "name") != OVERLAY_NAME or
            value(overlay_cu, "action") != "INSERT_OR_UPDATE" or
            value(overlay_cu, "remote_update_set") != value(overlay_header, "sys_id") or
            overlay_table != base["table"] or overlay_id != base["id"] or
            overlay_fields.get("sys_scope") != base["scope"] or
            value(overlay_cu, "application") != base["scope"] or
            value(overlay_header, "application") != base["scope"] or
            overlay_fields.get("sys_mod_count") != "4" or
            overlay_fields.get("sys_updated_on") != "2026-10-19 16:40:11" or
            digest(overlay_fields.get("script", "").encode("utf-8")) != OVERLAY_SCRIPT or
            destructive_nodes(overlay_parsed)):
        raise ValueError("Native overlay identity/scope/revision/field contract mismatch")
    changed_fields = sorted(key for key in set(base["fields"]) | set(overlay_fields)
                            if base["fields"].get(key) != overlay_fields.get(key))
    if changed_fields != ["script", "sys_mod_count", "sys_updated_on"]:
        raise ValueError("Native overlay changes unexpected application fields")
    overlay_provenance = {
        "file": str(overlay_path), "bytes": len(overlay_bytes), "sha256": digest(overlay_bytes),
        "customerUpdates": 1, "customerUpdateName": OVERLAY_NAME,
        "sourceExportCustomerUpdateId": value(overlay_cu, "sys_id"),
        "sourceHeaderFields": {field.tag: field.text or "" for field in overlay_header},
        "sourceOriginalSetId": value(overlay_header, "remote_sys_id"),
        "supersededBaseCustomerUpdateId": value(base["cu"], "sys_id"),
        "supersededBasePayloadSHA256": digest(base["payload"].encode("utf-8")),
        "supersededBaseRevision": base["revision"], "supersededBaseUpdatedOnUtc": base["updated"],
        "supersededBasePrimaryFieldContractSHA256": contract_hash(base["primary"]),
        "changedNativeApplicationFields": changed_fields,
        "existingDestinationOriginalSetId": value(headers[base["header"]], "remote_sys_id"),
        "extraOverlayHeaderAdded": False, "wrapperIdentitySeedUnchanged": True,
        "nativeApplicationRecordFieldsEdited": False,
    }
    replacement = {**base, "cu": overlay_cu, "payload": overlay_payload, "parsed": overlay_parsed,
                   "primary": overlay_primary, "fields": overlay_fields, "revision": 4,
                   "updated": overlay_fields["sys_updated_on"], "nativeOverlay": True,
                   "baseWrapperIdentitySeed": value(base["cu"], "sys_id"),
                   "sourceOriginalSetId": value(overlay_header, "remote_sys_id")}
    selection[selection.index(base)] = replacement
    remote_ids = {key: fresh_id("remote-set", key, input_hash) for key in headers}
    source_ids = {old: fresh_id("source-set-wrapper", old, input_hash) for old in original_to_remote}
    cu_ids = {value(r["cu"], "sys_id"): fresh_id("remote-cu", r.get("baseWrapperIdentitySeed", value(r["cu"], "sys_id")), input_hash)
              for r in selection}
    new_ids = set(remote_ids.values()) | set(source_ids.values()) | set(cu_ids.values())
    original_cu_ids = {value(cu, "sys_id") for cu in cus}
    if len(new_ids) != 36 + 36 + 809 or new_ids & (app_ids | set(headers) | set(original_to_remote) | original_cu_ids):
        raise ValueError("Fresh delivery wrapper identity collision")
    header_lineage, output_headers = [], []
    for old_id, original in headers.items():
        header = copy.deepcopy(original)
        source_original = value(original, "remote_sys_id")
        changes = []
        for field in ("sys_id", "remote_sys_id", "origin_sys_id", "parent", "remote_parent_id", "remote_base_update_set", "update_set"):
            old = value(header, field)
            new = remote_ids.get(old, source_ids.get(old, old))
            if field == "sys_id":
                new = remote_ids[old_id]
            elif field == "remote_sys_id":
                new = source_ids[source_original]
            if new != old:
                set_text(header, field, new)
                changes.append({"field": field, "source": old, "derived": new})
        if old_id == root_remote:
            changes.append({"field": "name", "source": value(header, "name"), "derived": ROOT_NAME})
            set_text(header, "name", ROOT_NAME)
        changes.append({"field": "description", "source": value(header, "description"),
                        "derived": FRESH_DESCRIPTION})
        set_text(header, "description", FRESH_DESCRIPTION)
        output_headers.append(header)
        header_lineage.append({"sourceExportRemoteSetId": old_id, "sourceOriginalNativeSetId": source_original,
                               "sourceName": value(original, "name"), "application": value(original, "application"),
                               "freshRemoteSetId": remote_ids[old_id], "freshSourceSetWrapperId": source_ids[source_original],
                               "sourceHeaderFields": {field.tag: field.text or "" for field in original},
                               "wrapperChanges": changes})
    output_cus = []
    records, removed_nodes, removed_hash_fields, reroutes = [], [], [], []
    selected_by_identity = {}
    for row in selection:
        cu = copy.deepcopy(row["cu"])
        old_cu_id = value(cu, "sys_id")
        set_text(cu, "sys_id", cu_ids[old_cu_id])
        destination = row["header"]
        if not row["scopeMatch"]:
            allowed = GENAI_BRANCH if row["scope"] == GENAI_SCOPE else GLOBAL_DELTA if row["scope"] == "global" else None
            if allowed is None or allowed not in original_to_remote:
                raise ValueError("No approved scope-correct destination")
            destination = original_to_remote[allowed]
            reroutes.append({"name": row["name"], "sourceOriginalSetId": value(headers[row["header"]], "remote_sys_id"),
                             "derivedOriginalBranchId": allowed, "scope": row["scope"], "applicationRecordFieldsChanged": False})
        if value(headers[destination], "application") != row["scope"] or value(cu, "application") != row["scope"]:
            raise ValueError("Scope/capture application mismatch")
        set_text(cu, "remote_update_set", remote_ids[destination])
        old_update_set = value(cu, "update_set")
        if old_update_set in remote_ids or old_update_set in source_ids:
            set_text(cu, "update_set", remote_ids.get(old_update_set, source_ids.get(old_update_set)))
        output_payload, removed = strip_destructive_payload_nodes(row["payload"])
        expected = prune_tree(row["parsed"])
        parsed_output = parse_exact(output_payload)
        if field_contract(expected) != field_contract(parsed_output):
            raise ValueError("Retained payload tree/fields changed")
        _, _, primary_after, _ = identity(cu, parsed_output)
        if field_contract(row["primary"]) != field_contract(primary_after):
            raise ValueError("Primary record fields changed")
        changed = output_payload != row["payload"]
        if changed:
            for field in ("payload_hash", "update_guid", "update_guid_history"):
                old = cu.find(field)
                if old is not None:
                    removed_hash_fields.append({"name": row["name"], "field": field, "originalValue": old.text or "",
                                                "reason": "Payload changed; native hash/guid algorithm is not guessed"})
                    cu.remove(old)
        removed_nodes.extend({"ownerName": row["name"], "sourceExportCustomerUpdateId": old_cu_id, **node} for node in removed)
        output_cus.append((cu, output_payload))
        record = {"name": row["name"], "table": row["table"], "applicationRecordId": row["id"], "scope": row["scope"],
                  "sourceRevision": row["revision"] if row["revision"] >= 0 else None,
                  "sourceUpdatedOnUtc": row["updated"] or None,
                  "sourceExportCustomerUpdateId": old_cu_id, "freshCustomerUpdateWrapperId": cu_ids[old_cu_id],
                  "sourceCustomerUpdateWrapperFields": {field.tag: field.text or "" for field in row["cu"] if field.tag != "payload"},
                  "sourceOriginalSetId": row.get("sourceOriginalSetId", value(headers[row["header"]], "remote_sys_id")),
                  "freshRemoteSetId": remote_ids[destination], "primaryFieldContractSHA256": contract_hash(row["primary"]),
                  "primaryFieldsUnchanged": True, "sourcePayloadSHA256": digest(row["payload"].encode("utf-8")),
                  "derivedPayloadSHA256": digest(output_payload.encode("utf-8")), "payloadChanged": changed,
                  "removedDestructiveNodeCount": len(removed)}
        if row.get("nativeOverlay"):
            record.update({"sourceInput": "native_notice_language_overlay",
                           "baseWrapperIdentitySeed": row["baseWrapperIdentitySeed"],
                           "existingDestinationOriginalSetId": value(headers[destination], "remote_sys_id")})
        records.append(record)
        selected_by_identity[(row["table"], row["id"])] = parsed_output
    if len(reroutes) != 5 or len(removed_nodes) != 95:
        raise ValueError("Unexpected routing/destructive-node counts")
    root_open = ET.Element(source.tag, source.attrib)
    opening = ET.tostring(root_open, encoding="unicode", short_empty_elements=False)
    opening = opening[:opening.index(">") + 1]
    chunks = [b'<?xml version="1.0" encoding="UTF-8"?>\n', opening.encode("utf-8"), b"\n"]
    chunks.extend(serialize_wrapper(header) + b"\n" for header in output_headers)
    chunks.extend(serialize_wrapper(cu, payload) + b"\n" for cu, payload in output_cus)
    chunks.append(b"</unload>\n")
    output_bytes = b"".join(chunks)
    reparsed = parse_exact(output_bytes.decode("utf-8"))
    out_headers = {value(h, "sys_id"): h for h in reparsed.findall("sys_remote_update_set")}
    out_cus = reparsed.findall("sys_update_xml")
    if len(out_headers) != 36 or len(out_cus) != 809 or len({value(c, "name") for c in out_cus}) != 809:
        raise ValueError("Derived XML identity/count verification failed")
    if any(value(c, "action") != "INSERT_OR_UPDATE" or value(c, "name") in deleted for c in out_cus):
        raise ValueError("Destructive/tombstoned CU survived")
    out_by_identity = {}
    original_by_name = {r["name"]: r for r in selection}
    retained_data_counts = Counter()
    for cu in out_cus:
        payload = parse_exact(value(cu, "payload"))
        if destructive_nodes(payload):
            raise ValueError("Embedded destructive action survived output XML")
        table, rid, primary, _ = identity(cu, payload)
        before = original_by_name[value(cu, "name")]
        if field_contract(primary) != field_contract(before["primary"]):
            raise ValueError("Reparsed primary record fields differ")
        if field_contract(payload) != field_contract(prune_tree(before["parsed"])):
            raise ValueError("Reparsed retained payload fields/inserts differ")
        if value(cu, "remote_update_set") not in out_headers:
            raise ValueError("Broken derived CU/set reference")
        out_by_identity[(table, rid)] = payload
        retained_data_counts.update(node.tag for node in payload.iter()
                                    if node.tag in {"sys_translated_text", "fx_price"})
    for header in out_headers.values():
        if value(header, "description") != FRESH_DESCRIPTION:
            raise ValueError("Historical wrapper description survived")
        if value(header, "parent") and value(header, "parent") not in out_headers:
            raise ValueError("Broken derived parent reference")
        if value(header, "remote_base_update_set") != remote_ids[root_remote]:
            raise ValueError("Broken derived batch base")
    current = json.loads(source_manifest.read_text(encoding="utf-8"))
    code_checks = []
    for pin in current["entries"]:
        key = (pin["table"], pin["recordId"])
        if key not in out_by_identity:
            raise ValueError("Current native source record missing")
        owner = next(node for node in out_by_identity[key].iter()
                     if node.tag == key[0] and value(node, "sys_id") == key[1])
        actual = digest(value(owner, pin["field"]).encode("utf-8"))
        if actual != pin["sha256"]:
            raise ValueError("Current seven-field source hash mismatch")
        code_checks.append({"table": key[0], "id": key[1], "field": pin["field"], "sha256": actual, "equal": True})
    if len(code_checks) != 7 or len({(r["table"], r["id"], r["field"]) for r in code_checks}) != 7:
        raise ValueError("Expected seven distinct current code-field pins")
    deleted_ids = {row["id"] for name in deleted for row in groups[name] if row["id"]}
    direct_refs_to_deleted = []
    for cu in out_cus:
        payload = parse_exact(value(cu, "payload"))
        for node in payload.iter():
            if not len(node) and (node.text or "") in deleted_ids:
                direct_refs_to_deleted.append({"ownerName": value(cu, "name"), "field": node.tag, "excludedId": node.text})
    if direct_refs_to_deleted:
        raise ValueError("Retained direct reference to a deleted source identity")
    manifest = {"schemaVersion": 1, "kind": "derived_fresh_instance_no_delete_transport",
        "rootName": ROOT_NAME, "notOriginalNativeExport": True, "freshInstancesOnly": True,
        "builder": {"file": str(Path(__file__).resolve()), "sha256": digest(Path(__file__).read_bytes())},
        "input": {"file": str(input_path), "bytes": len(input_bytes), "sha256": input_hash, "customerUpdateVersions": 868,
                  "uniqueNames": 818, "uniqueSets": 36, "serializedHeaders": 37},
        "output": {"file": OUTPUT_NAME, "bytes": len(output_bytes), "sha256": digest(output_bytes),
                   "customerUpdates": 809, "distinctNames": 809, "uniqueSets": 36, "serializedHeaders": 36,
                   "outerDeleteActions": 0, "embeddedDeleteActions": 0, "insertDeleteNameConflicts": 0},
        "nativeOverlays": [overlay_provenance],
        "selectionPolicy": "Base: highest captured native source revision, then source updated time; equal-revision/time retained-field conflicts fail. Scope-correct tie, then capture metadata. One pinned same-identity newer native notice-language overlay supersedes its base capture, preserving the base wrapper ID seed and destination. Fresh current seven-field pins independently verified.",
        "excludedDeletedIdentityNames": sorted(deleted), "excludedVersionsForDeletedIdentities": excluded,
        "discardedOlderOrDuplicateInsertVersions": discarded, "setWrapperLineage": header_lineage,
        "recordLineageAndFieldChecks": records, "scopeOnlyWrapperReroutes": reroutes,
        "removedDestructivePayloadNodes": removed_nodes, "removedStaleOuterHashGuidFields": removed_hash_fields,
        "retainedTranslationAndPriceElementCounts": dict(retained_data_counts),
        "currentCodeFieldChecks": code_checks,
        "sourceFieldManifest": {"path": str(source_manifest), "sha256": digest(source_manifest.read_bytes())},
        "validation": {"all809PrimaryFieldContractsUnchanged": True, "allRetainedPayloadElementsAndFieldsUnchanged": True,
                       "allNondestructiveTranslationAndPriceInsertsRetained": True, "currentSevenFieldHashesEqual": True,
                       "applicationRecordIdentitiesRemapped": False, "unresolvedSameRevisionFieldConflicts": 0,
                       "directReferencesToDeletedIdentities": 0, "wrapperReferenceIntegrity": True,
                       "allSelectedCapturesHaveScopeCorrectDestination": True, "inputNativeExportUnchanged": True,
                       "inputNativeOverlayUnchanged": True, "all809WrapperIdentitySeedsUnchanged": True},
        "wrapperDescriptionPolicy": {"all36HeadersDescribeFreshDerivedDelivery": True,
                                     "originalDescriptionsPreservedInSetWrapperLineage": True,
                                     "metadataDatesChanged": False},
        "nativeHashPolicy": "Changed payloads omit payload_hash/update_guid/update_guid_history; no native numeric hash algorithm is guessed. SHA-256 values in this manifest are external audit hashes only.",
        "prerequisites": {"compatibleNativeAppsLicensesSchemaAndProtectedFactoryRecords": True,
            "actGovernanceConfiguredSeparately": True, "actRoutingPolicyRowSynthesized": False,
            "retainedControlSettingMetadataFlagIsNotRoutingPolicy": True,
            "targetLocalMirrorPropertiesNotSynthesizedOrTransported": ["custom_llm.prompt_mirror.default_model",
                "custom_llm.prompt_mirror.automation_enabled", "custom_llm.prompt_mirror.apply_enabled",
                "custom_llm.prompt_mirror.serialized_execution_verified"],
            "localConnectionsCredentialsEndpointsAndOperationalMappings": "Configure privately on the target",
            "nativeParentConfigsAndAllRemainingReferences": "Resolve through native preview; no complete target closure claimed"},
        "nativeReceivedImportValidated": False, "nativePreviewValidated": False, "targetCommitPerformed": False,
        "nativeSchemaCompatibilityProven": False, "targetRuntimeAccepted": False, "universalApplyProven": False,
        "protectedOpaqueXMLRead": False, "modelOrInstanceActions": False}
    if input_path.read_bytes() != input_bytes:
        raise ValueError("Input export changed during build")
    if overlay_path.read_bytes() != overlay_bytes:
        raise ValueError("Input overlay changed during build")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_NAME
    output_path.write_bytes(output_bytes)
    manifest_path = output_dir / "DERIVED-FRESH-INSTANCE-MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = {"status": "passed", "failures": [], "outputSHA256": digest(output_path.read_bytes()),
                  "manifestSHA256": digest(manifest_path.read_bytes()), "inputSHA256": input_hash,
                  "nativeOverlaySHA256": digest(overlay_bytes), "primaryRecordsVerified": 809,
                  "currentCodeFieldsVerified": 7, "nativeOverlayRecordsVerified": 1,
                  "removedPayloadDeleteNodes": len(removed_nodes),
                  "deletedIdentitiesExcluded": 9, "olderInsertVersionsDiscarded": 49, "scopeWrapperReroutes": 5,
                  "nativeReceivedImportValidated": False, "nativePreviewValidated": False, "targetCommitPerformed": False}
    (output_dir / "DERIVED-FRESH-INSTANCE-VERIFICATION.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    return output_path, validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-field-manifest", type=Path, required=True)
    parser.add_argument("--native-overlay", type=Path, required=True)
    args = parser.parse_args()
    output, report = build(args.input, args.output_dir, args.source_field_manifest, args.native_overlay)
    print(json.dumps({"output": str(output), **report}, indent=2))


if __name__ == "__main__":
    main()
