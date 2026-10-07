"""Offline regressions for captured ownership; never starts a trace or GPU work."""
import importlib.util
from pathlib import Path
import unittest

TARGET = Path(__file__).with_name("halogen_gpu_copy_attribution.py")


def prop(name, value, kind=16, label=None):
    if kind == 1:
        raw = (value + "\0").encode("utf-16-le")
    elif kind == 15:
        import uuid
        raw = uuid.UUID(value).bytes_le
    else:
        raw = value.to_bytes(4 if kind == 8 else 8, "little")
    return dict(name=name, in_type=kind, out_type=19, flags=0, count=1,
                count_property_index=None, length=len(raw), length_property_index=None,
                map_name="test" if label else None, bytes=len(raw), raw_hex=raw.hex(),
                status="materialized", tdh_status=0, formatted=label,
                map_status=0 if label else 1168, format_status=0 if label else 50)


def event(eid, qpc, **fields):
    versions = {27: 2, 28: 2, 29: 2, 33: 3, 34: 3, 35: 3, 36: 2, 37: 2, 38: 2,
                175: 1, 176: 0, 110: 1}
    return dict(type="event", provider="802ec45a-1e99-4b83-9920-87c98277ba9d",
                id=eid, version=versions.get(eid, 0), opcode=0, ordinal=str(qpc),
                qpc=str(qpc), header_pid=4, status="materialized", properties_complete=True,
                properties=[prop(name, *value) if isinstance(value, tuple) else prop(name, value)
                            for name, value in fields.items()])


def fixture():
    return [
        dict(type="trace_header", input="C:\\fixture\\owned.etl", input_bytes="1024", clock=dict(type="QPC", perf_freq="10000000"),
             header_statistics=dict(events_lost=0, buffers_lost=0)),
        event(474, 100, DxgVirtualMachine=10, VmGuid=("12345678-1234-1234-1234-123456789abc", 15)),
        event(472, 110, DxgProcess=20, ProcessIdInVm=707, DxgProcessInVm=21,
              DxgVirtualMachine=10, ProcessNameInVm=("controlled-copy", 1)),
        event(110, 115, pDxgAdapter=50, AdapterLuid=0x11884),
        event(250, 116, pDxgAdapter=50, NodeOrdinal=(1, 8), EngineType=(6, 8),
              FriendlyName=("Copy", 1)),
        event(27, 120, hDevice=30, pDxgAdapter=50, DxgProcess=20),
        event(30, 130, hDevice=30, hContext=40, NodeOrdinal=(1, 8)),
        event(175, 150, hContext=40, ulQueueSubmitSequence=(3, 8), pDmaBuffer=60,
              PacketType=(0, 8)),
        event(176, 160, hContext=40, ulQueueSubmitSequence=(3, 8), PacketType=(0, 8), bPreempted=(0, 8)),
        event(31, 170, hContext=40),
        event(28, 180, hDevice=30, pDxgAdapter=50),
        event(477, 190, DxgProcess=20),
        dict(type="summary", decode_success=True, dxg_events_seen="11", dxg_events_written="11",
             unresolved_events="0", events_not_written="0", unresolved_properties="0"),
    ]


def receipt():
    return dict(event="recorder_receipt", mode="capture", success=True,
                owned_session_closed=True, owned_session_may_remain=False,
                start_code=0, enable_code=0, stop_code=0, capture_state_requested=True,
                output="C:\\fixture\\owned.etl", file_bytes=1024,
                capture_state_code=0, qpc_frequency=10000000,
                enabled=dict(qpc_before=90, qpc_after=91), stop_begin=dict(qpc_before=200, qpc_after=201),
                final_stats=dict(statistics_available=True, events_lost=0, log_buffers_lost=0,
                                 realtime_buffers_lost=0))


class AttributionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("copy_attribution", TARGET)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def analyze(self, records=None, capture=None, identities=None, pdh=None, native_nodes=(), namespaces=None):
        identity = dict(label="standalone-control", process_id_in_vm=707,
                        process_name_in_vm="controlled-copy",
                        vm_guid="12345678-1234-1234-1234-123456789abc",
                        qpc_before=140, qpc_after=165,
                        linux_task_evidence=dict(initial_namespace_tid=707, start_ticks=1234,
                                                 boot_id="fixture-boot", executable="/tmp/controlled-copy"))
        return self.module.analyze_records(iter(records or fixture()), capture or receipt(),
                                           [identity] if identities is None else identities,
                                           engine_type_receipt=dict(copy_value=6, source="installed-sdk", sha256="a" * 64),
                                           pdh_intervals=pdh, native_node_metadata=native_nodes,
                                           namespace_bindings=namespaces)

    def test_new_guest_lifecycle_resolves_system_header_packet(self):
        result = self.analyze()
        self.assertEqual(result["packets"][0]["owner"]["label"], "standalone-control")
        self.assertEqual(result["packets"][0]["owner"]["process_id_in_vm"], 707)
        self.assertEqual(result["packets"][0]["engine"]["class"], "copy")
        self.assertTrue(result["captured_copy_packet_owners_resolved"])
        self.assertIsNone(result["pdh_exclusive_ownership_qualified"])
        self.assertEqual(result["pdh_evaluation"]["status"], "not-requested")

    def test_pid4_header_alone_never_resolves(self):
        rows = [r for r in fixture() if r.get("id") not in {27, 30, 472, 474}]
        result = self.analyze(rows)
        self.assertIsNone(result["packets"][0]["owner"])
        self.assertFalse(result["captured_copy_packet_owners_resolved"])

    def test_host_process_cannot_replace_guest_process_schema(self):
        rows = fixture()
        rows[2] = event(471, 110, DxgProcess=20, ProcessId=707)
        self.assertIsNone(self.analyze(rows)["packets"][0]["owner"])

    def test_trace_loss_rejects_even_complete_guest_chain(self):
        cap = receipt()
        cap["final_stats"]["events_lost"] = 1
        result = self.analyze(capture=cap)
        self.assertFalse(result["trace_integrity"]["qualified"])
        self.assertFalse(result["captured_copy_packet_owners_resolved"])

    def test_loss_receipt_for_another_trace_is_rejected(self):
        cap = receipt()
        cap["output"] = "C:\\fixture\\other.etl"
        self.assertFalse(self.analyze(capture=cap)["trace_integrity"]["qualified"])

    def test_context_stop_prevents_handle_reuse_attribution(self):
        rows = fixture()
        rows.insert(7, event(31, 145, hContext=40))
        self.assertIsNone(self.analyze(rows)["packets"][0]["owner"])

    def test_guest_stop_during_packet_prevents_owner_attribution(self):
        rows = fixture()
        rows.insert(8, event(477, 155, DxgProcess=20))
        self.assertIsNone(self.analyze(rows)["packets"][0]["owner"])

    def test_packet_outside_enabled_window_is_unqualified(self):
        cap = receipt()
        cap["enabled"]["qpc_after"] = 155
        result = self.analyze(capture=cap)
        self.assertFalse(result["captured_copy_packet_owners_resolved"])
        self.assertNotEqual(result["packets"][0]["status"], "resolved")

    def test_packet_type_mismatch_cannot_pair_completion(self):
        rows = fixture()
        rows[8]["properties"] = [p for p in rows[8]["properties"] if p["name"] != "PacketType"] + [prop("PacketType", 1, 8)]
        self.assertNotEqual(self.analyze(rows)["packets"][0]["status"], "resolved")

    def test_child_cannot_join_reused_parent_process(self):
        rows = fixture()
        rows.insert(7, event(477, 140, DxgProcess=20))
        rows.insert(8, event(472, 145, DxgProcess=20, ProcessIdInVm=808, DxgProcessInVm=22,
                             DxgVirtualMachine=10, ProcessNameInVm=("other-process", 1)))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        result = self.analyze(rows)
        self.assertIsNone(result["packets"][0]["owner"])
        self.assertFalse(result["captured_copy_packet_owners_resolved"])

    def test_child_cannot_join_reused_parent_device(self):
        rows = fixture()
        rows.insert(7, event(28, 140, hDevice=30, pDxgAdapter=50))
        rows.insert(8, event(27, 145, hDevice=30, pDxgAdapter=50, DxgProcess=20))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        self.assertIsNone(self.analyze(rows)["packets"][0]["owner"])

    def test_same_tick_later_context_does_not_retroactively_own_packet(self):
        rows = fixture()
        context = rows.pop(6)
        context.update(qpc="150", ordinal="150")
        rows.insert(7, context)
        self.assertIsNone(self.analyze(rows)["packets"][0]["owner"])

    def test_hardware_queue_packet_joins_captured_guest_context(self):
        rows = fixture()
        rows.insert(7, event(422, 140, hHwQueue=70, ParentDxgHwQueue=80, hContext=40))
        rows.insert(8, event(450, 145, hHwQueue=80, pDmaBuffer=60, ProgressFenceValue=3))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        result = self.analyze(rows)
        self.assertEqual(result["hardware_packets"][0]["owner"]["process_id_in_vm"], 707)
        self.assertEqual(result["hardware_packets"][0]["engine"]["class"], "copy")

    def test_pdh_interval_evaluates_missing_physical_mapping(self):
        interval = dict(instance="pid_4_luid_0x00000000_0x00011884_phys_0_eng_1_engtype_copy",
                        start_qpc=140, end_qpc=165, raw_pair_valid=True,
                        admitted_labels=["standalone-control"])
        result = self.analyze(pdh=[interval])
        self.assertEqual(result["pdh_evaluation"]["status"], "evaluated")
        self.assertFalse(result["pdh_exclusive_ownership_qualified"])
        self.assertGreater(len(result["pdh_evaluation"]["intervals"][0]["reasons"]), 0)

    def complete_pdh_interval(self):
        instance = "pid_4_luid_0x00000000_0x00011884_phys_0_eng_1_engtype_copy"
        return dict(instance=instance, start_qpc=140, end_qpc=165, raw_pair_valid=True,
                    admitted_labels=["standalone-control"],
                    native_node_metadata=dict(schema="halogen.gpu-node-metadata.v1", success=True,
                        api="D3DKMTQueryAdapterInfo", type="KMTQAITYPE_NODEMETADATA", status=0,
                        open_adapter_status=0, physical_count_status=0, close_adapter_status=0,
                        instance=instance, input_pdh_pid=4, adapter_luid="0x0000000000011884",
                        physical_index=0, node_ordinal=1, physical_adapter_count=1,
                        NodeOrdinalAndAdapterIndex=1, EngineType=6, qpc_frequency=10000000,
                        qpc_before=130, qpc_after=135, native_executable_sha256="c" * 64),
                    execution_timing_binding=dict(provider=self.module.PROVIDER, start_descriptor="175/v1",
                        stop_descriptor="176/v0", semantics="GPU-execution", pdh_timebase=10000000,
                        primary_source_sha256="b" * 64),
                    instance_generation_continuity="captured-adapter-node-lifetime")

    def test_complete_native_node_mapping_is_evaluated(self):
        result = self.analyze(pdh=[self.complete_pdh_interval()])
        self.assertTrue(result["pdh_exclusive_ownership_qualified"])

    def test_failed_or_other_instance_native_mapping_never_qualifies(self):
        for changed in ({"success": False}, {"close_adapter_status": 0xc0000001},
                        {"instance": "pid_999_luid_0x0_0x11884_phys_0_eng_1_engtype_copy"},
                        {"physical_adapter_count": 0}, {"qpc_after": 129}, {"input_pdh_pid": 999}):
            with self.subTest(changed=changed):
                interval = self.complete_pdh_interval()
                interval["native_node_metadata"].update(changed)
                result = self.analyze(pdh=[interval])
                self.assertFalse(result["pdh_exclusive_ownership_qualified"])

    def test_native_metadata_binds_physical_node_without_attesting_pdh_pid(self):
        mapping = self.complete_pdh_interval()["native_node_metadata"]
        result = self.analyze(identities=[], native_nodes=[mapping])
        self.assertEqual(result["physical_node_metadata_bound_packet_count"], 1)
        self.assertEqual(result["packets"][0]["engine"]["physical_index"], 0)
        self.assertIsNone(result["packets"][0]["owner"]["label"])
        self.assertIsNone(result["pdh_exclusive_ownership_qualified"])

    def test_linked_adapter_requires_context_physical_index(self):
        interval = self.complete_pdh_interval()
        interval["native_node_metadata"]["physical_adapter_count"] = 2
        result = self.analyze(pdh=[interval], native_nodes=[interval["native_node_metadata"]])
        self.assertEqual(result["physical_node_metadata_bound_packet_count"], 0)
        self.assertFalse(result["pdh_exclusive_ownership_qualified"])

    def test_native_receipts_are_deduplicated_and_count_bounded(self):
        mapping = self.complete_pdh_interval()["native_node_metadata"]
        result = self.analyze(native_nodes=[mapping] * 2)
        self.assertEqual(result["native_node_metadata_input_count"], 2)
        self.assertEqual(len(result["native_node_metadata_receipts"]), 1)
        with self.assertRaises(self.module.AttributionError):
            self.analyze(native_nodes=[mapping] * 33)

    def allocation_fixture(self):
        rows = fixture()
        rows[7:7] = [
            event(33, 132, hDevice=30, pDxgAdapter=50, hVidMmGlobalAlloc=90, hDxgGlobalAlloc=91,
                  hDxgSharedResource=0, allocSize=(4096, 10), PhysicalAdapterIndex=(0, 8)),
            event(36, 133, hDevice=30, pDxgAdapter=50, hVidMmAlloc=92, hVidMmGlobalAlloc=90),
            event(50, 145, hAllocationGlobalHandle=90, pDmaBuffer=60),
        ]
        rows[12:12] = [event(37, 162, pDxgAdapter=50, hVidMmAlloc=92),
                       event(34, 163, pDxgAdapter=50, hVidMmGlobalAlloc=90)]
        rows[-1].update(dxg_events_seen="16", dxg_events_written="16")
        return rows

    def test_transfer_global_association_preserves_full_lifetimes_without_alias_qualification(self):
        result = self.analyze(self.allocation_fixture())
        association = result["observed_transfer_global_associations"][0]
        self.assertEqual(association["global_allocation_lifetime"]["end"], 163)
        self.assertEqual(association["active_local_allocation_references"][0]["end"], 162)
        self.assertEqual(association["guest_origin_candidate"]["process_id_in_vm"], 707)
        self.assertEqual(association["first_subsequent_same_named_pDmaBuffer_match"]["start"]["qpc"], 150)
        self.assertFalse(association["global_namespace_alias_verified"])
        self.assertFalse(association["beneficiary_ownership_qualified"])

    def test_transfer_cannot_use_expired_global_allocation(self):
        rows = self.allocation_fixture()
        closed = rows.pop(13)
        closed.update(qpc="140", ordinal="140")
        rows.insert(9, closed)
        association = self.analyze(rows)["observed_transfer_global_associations"][0]
        self.assertNotIn("guest_origin_candidate", association)
        self.assertTrue(association["reasons"])

    def namespace_fixture(self):
        return dict(schema="halogen.dxg-field-namespace-bindings.v1", provider=self.module.PROVIDER,
                    images_hash_verified=True, bindings=[
            dict(kind="global-allocation", from_descriptor="50/v0", from_field="hAllocationGlobalHandle",
                 to_descriptors=["33/v3", "35/v3"], to_field="hVidMmGlobalAlloc",
                 object_type="VIDMM_GLOBAL_ALLOC*", verified=True, proof=["typed producer", "writer slot"]),
            dict(kind="hardware-parent-queue", from_descriptor="450/v0", from_field="hHwQueue",
                 to_descriptors=["422/v0", "424/v0"], to_field="ParentDxgHwQueue",
                 object_type="DXGHWQUEUE*", verified=True, proof=["typed scheduler parent", "writer slot"]),
        ])

    def test_scoped_namespace_proof_qualifies_origin_and_host_parent_edge(self):
        result = self.analyze(self.allocation_fixture(), namespaces=self.namespace_fixture())
        association = result["observed_transfer_global_associations"][0]
        self.assertTrue(association["global_namespace_alias_verified"])
        self.assertTrue(association["allocation_origin_qualified"])
        self.assertFalse(association["beneficiary_ownership_qualified"])
        rows = fixture()
        rows.insert(7, event(422, 140, hHwQueue=70, ParentDxgHwQueue=80, hContext=40))
        rows.insert(8, event(450, 145, hHwQueue=80, pDmaBuffer=60, ProgressFenceValue=3))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        packet = self.analyze(rows, namespaces=self.namespace_fixture())["hardware_packets"][0]
        self.assertEqual(packet["status"], "resolved")
        self.assertTrue(packet["hardware_queue_binding"]["namespace_semantics_verified"])

    def test_unpinned_namespace_claim_cannot_qualify_alias(self):
        namespaces = self.namespace_fixture()
        namespaces["images_hash_verified"] = False
        association = self.analyze(self.allocation_fixture(), namespaces=namespaces)["observed_transfer_global_associations"][0]
        self.assertFalse(association["global_namespace_alias_verified"])
        self.assertFalse(association["allocation_origin_qualified"])

    def test_allocation_origin_requires_trace_integrity_and_enabled_window(self):
        capture = receipt()
        capture["final_stats"]["events_lost"] = 1
        result = self.analyze(self.allocation_fixture(), capture=capture, namespaces=self.namespace_fixture())
        self.assertFalse(result["trace_integrity"]["qualified"])
        self.assertFalse(result["observed_transfer_global_associations"][0]["allocation_origin_qualified"])
        capture = receipt()
        capture["enabled"]["qpc_after"] = 146
        association = self.analyze(self.allocation_fixture(), capture=capture,
                                   namespaces=self.namespace_fixture())["observed_transfer_global_associations"][0]
        self.assertFalse(association["within_enabled_capture_window"])
        self.assertFalse(association["allocation_origin_qualified"])

    def test_native_parent_or_scheduler_proof_never_uses_local_handle_fallback(self):
        namespaces = self.namespace_fixture()
        namespaces["bindings"][1]["object_type"] = "DXGHWQUEUE* when parent is present; VIDSCH_HW_QUEUE* when parent is null"
        rows = fixture()
        rows.insert(7, event(422, 140, hHwQueue=70, ParentDxgHwQueue=80, hContext=40))
        rows.insert(8, event(450, 145, hHwQueue=80, pDmaBuffer=60, ProgressFenceValue=3))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        packet = self.analyze(rows, namespaces=namespaces)["hardware_packets"][0]
        self.assertEqual(packet["status"], "resolved")
        self.assertTrue(packet["hardware_queue_binding"]["namespace_semantics_verified"])
        rows[7] = event(422, 140, hHwQueue=70, ParentDxgHwQueue=0, hContext=40)
        rows[8] = event(450, 145, hHwQueue=70, pDmaBuffer=60, ProgressFenceValue=3)
        self.assertIsNone(self.analyze(rows, namespaces=namespaces)["hardware_packets"][0]["owner"])

    def test_event53_cannot_inherit_event50_global_namespace_proof(self):
        rows = self.allocation_fixture()
        rows[9] = event(53, 145, hAllocationGlobalHandle=90, pDmaBuffer=60)
        association = self.analyze(rows, namespaces=self.namespace_fixture())["observed_transfer_global_associations"][0]
        self.assertFalse(association["global_namespace_alias_verified"])
        self.assertFalse(association["allocation_origin_qualified"])

    def test_namespace_proof_with_wrong_descriptor_or_object_type_is_rejected(self):
        for key, value in (("from_descriptor", "53/v0"), ("object_type", "void*"),
                           ("to_field", "hHwQueue"), ("to_descriptors", ["422/v0"])):
            with self.subTest(key=key):
                namespaces = self.namespace_fixture()
                namespaces["bindings"][1][key] = value
                self.assertNotIn("hardware-parent-queue", self.module.verified_namespace_kinds(namespaces))

    def test_guest_tid_needs_exact_vm_and_task_evidence(self):
        self.assertIsNone(self.analyze(identities=[])["packets"][0]["owner"]["label"])
        bad = dict(label="wrong-vm", process_id_in_vm=707, process_name_in_vm="controlled-copy",
                   vm_guid="00000000-0000-0000-0000-000000000000", qpc_before=140, qpc_after=165)
        self.assertIsNone(self.analyze(identities=[bad])["packets"][0]["owner"]["label"])

    def test_sequence_reuse_without_completion_is_ambiguous(self):
        rows = fixture()
        rows.insert(8, event(175, 155, hContext=40, ulQueueSubmitSequence=(3, 8), pDmaBuffer=61,
                             PacketType=(0, 8)))
        result = self.analyze(rows)
        self.assertTrue(all(p["status"] != "resolved" for p in result["packets"]))

    def test_unknown_engine_number_does_not_become_copy(self):
        rows = fixture()
        rows[4] = event(250, 116, pDxgAdapter=50, NodeOrdinal=(1, 8), EngineType=(99, 8),
                        FriendlyName=("3D", 1))
        self.assertEqual(self.analyze(rows)["packets"][0]["engine"]["class"], "other")

    def test_null_device_owner_is_schema_valid_and_unresolved(self):
        rows = fixture()
        rows[5] = event(27, 120, hDevice=30, pDxgAdapter=50, DxgProcess=0)
        result = self.analyze(rows)
        self.assertTrue(result["trace_integrity"]["qualified"])
        self.assertEqual(result["malformed_schemas"], [])
        self.assertIsNone(result["packets"][0]["owner"])
        self.assertEqual(result["packets"][0]["engine"]["class"], "copy")

    def test_null_hardware_queue_never_forms_object_identity(self):
        rows = fixture()
        rows.insert(7, event(424, 140, hHwQueue=0, ParentDxgHwQueue=0, hContext=40))
        rows.insert(8, event(450, 145, hHwQueue=0, pDmaBuffer=0, ProgressFenceValue=3))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        result = self.analyze(rows)
        self.assertTrue(result["trace_integrity"]["qualified"])
        self.assertEqual(result["unjoinable_object_record_count"], 1)
        self.assertIsNone(result["hardware_packets"][0]["owner"])
        self.assertFalse(result["captured_copy_packet_owners_resolved"])

    def test_null_local_queue_handle_preserves_captured_host_parent_edge(self):
        rows = fixture()
        rows.insert(7, event(422, 140, hHwQueue=0, ParentDxgHwQueue=80, hContext=40))
        rows.insert(8, event(450, 145, hHwQueue=80, pDmaBuffer=0, ProgressFenceValue=3))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        result = self.analyze(rows)
        self.assertTrue(result["trace_integrity"]["qualified"])
        self.assertEqual(result["hardware_packets"][0]["owner"]["process_id_in_vm"], 707)
        self.assertEqual(result["hardware_packets"][0]["hardware_queue_binding"]["local_handle"], 0)

    def test_local_queue_handle_never_substitutes_for_host_parent(self):
        rows = fixture()
        rows.insert(7, event(422, 140, hHwQueue=70, ParentDxgHwQueue=80, hContext=40))
        rows.insert(8, event(450, 145, hHwQueue=70, pDmaBuffer=60, ProgressFenceValue=3))
        rows[-1].update(dxg_events_seen="13", dxg_events_written="13")
        self.assertIsNone(self.analyze(rows)["hardware_packets"][0]["owner"])

    def test_null_dma_pointer_does_not_alias_null_allocation_provenance(self):
        rows = fixture()
        rows.insert(7, event(50, 140, pDmaBuffer=0))
        rows[8] = event(175, 150, hContext=40, ulQueueSubmitSequence=(3, 8), pDmaBuffer=0,
                        PacketType=(0, 8))
        rows[-1].update(dxg_events_seen="12", dxg_events_written="12")
        result = self.analyze(rows)
        self.assertTrue(result["trace_integrity"]["qualified"])
        self.assertEqual(result["packets"][0]["owner"]["process_id_in_vm"], 707)
        self.assertEqual(result["packets"][0]["allocation_provenance_candidates"], [])

    def test_null_packet_context_is_retained_and_unresolved(self):
        rows = fixture()
        rows[7] = event(175, 150, hContext=0, ulQueueSubmitSequence=(3, 8), pDmaBuffer=0,
                        PacketType=(0, 8))
        rows[8] = event(176, 160, hContext=0, ulQueueSubmitSequence=(3, 8),
                        PacketType=(0, 8), bPreempted=(0, 8))
        result = self.analyze(rows)
        self.assertTrue(result["trace_integrity"]["qualified"])
        self.assertEqual(len(result["packets"]), 1)
        self.assertIsNone(result["packets"][0]["owner"])
        self.assertFalse(result["captured_copy_packet_owners_resolved"])


if __name__ == "__main__":
    unittest.main()
