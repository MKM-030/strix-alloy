"""Synthetic scope and failure fixtures for the read-only Windows snapshot."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import unittest
from unittest.mock import patch

from gufo_control.telemetry import TelemetryError, collect_snapshot, normalize_snapshot
from gufo_control import telemetry
from gufo_control.operator_policy import Frame, _frame_reasons

G = 1 << 30
NOW = datetime(2026, 9, 26, 12, 0, 1, tzinfo=timezone.utc)
STAMP = "2026-09-26T12:00:00Z"
LUID = "0x00000000_0x000111c1"
INSTANCE = "luid_" + LUID + "_phys_0"


def owned_fixture():
    request = dict(pid=42, creation_time_100ns=123456, executable='C:\\test\\engine.exe', adapter_luid=LUID)
    rows = []
    for luid, value in ((LUID, 123), ('0x00000000_0x00014fe1', 999)):
        instance = 'pid_42_luid_'+luid+'_phys_0'
        for label in ('dedicated usage', 'shared usage', 'total committed'):
            rows.append(dict(path='\\\\host\\gpu process memory('+instance+')\\'+label,
                instance=instance, raw_value=value, cooked_value=value, status=0, timestamp_utc=STAMP))
    raw = dict(available=True, identity_before=dict(request), identity_after=dict(request),
        working_set_bytes=500, private_bytes=700, host_timestamp_utc=STAMP, counters=rows)
    return request, raw


class OwnedTelemetryTests(unittest.TestCase):
    def normalize(self, owned_raw, request):
        raw = fixture()
        raw['owned'] = owned_raw
        self.assertIn('owned', __import__('inspect').signature(normalize_snapshot).parameters,
                      'optional owned normalization missing')
        return normalize_snapshot(raw, captured_monotonic=100, now_monotonic=101,
            now_utc=NOW, owned=request)

    def test_same_pid_two_adapters_selects_only_exact_identity_and_luid(self):
        request, owned = owned_fixture()
        result = self.normalize(owned, request)
        diagnostic = result['owned_counters']
        self.assertTrue(diagnostic['available'], diagnostic)
        self.assertEqual(diagnostic['gpu_scope'], 'owned_process_target_adapter')
        self.assertEqual(diagnostic['process_dedicated_bytes'], 123)
        self.assertEqual(diagnostic['working_set_bytes'], 500)
        self.assertEqual(diagnostic['private_bytes'], 700)
        self.assertEqual(result['adapter_dedicated_bytes'], G)

    def test_optional_identity_missing_stale_ambiguous_or_null_stays_unavailable(self):
        edits = [lambda o: o['identity_after'].update(creation_time_100ns=456),
            lambda o: o['identity_before'].update(pid=99),
            lambda o: o['identity_after'].update(executable='C:\\other.exe'),
            lambda o: o.update(counters=[]), lambda o: o.update(working_set_bytes=None),
            lambda o: o['counters'][0].update(timestamp_utc='2020-01-01T00:00:00Z'),
            lambda o: o['counters'].append(dict(o['counters'][0])),
            lambda o: o['counters'][0].update(raw_value=None),
            lambda o: o.update(available=False, reason='process_exited'),
            lambda o: o.update(host_timestamp_utc='2020-01-01T00:00:00Z')]
        for edit in edits:
            with self.subTest(edit=edit):
                request, owned = owned_fixture()
                edit(owned)
                result = self.normalize(owned, request)
                self.assertTrue(result['telemetry_ok'])
                self.assertFalse(result['owned_counters']['available'])
                self.assertIsNone(result['owned_counters']['process_dedicated_bytes'])
                self.assertTrue(result['owned_counters']['reason'])

    def test_wrong_target_luid_is_unavailable_without_weakening_aggregate(self):
        request, owned = owned_fixture()
        request['adapter_luid'] = '0x00000000_0x00014fe1'
        result = self.normalize(owned, request)
        self.assertFalse(result['owned_counters']['available'])
        self.assertEqual(result['adapter_dedicated_bytes'], G)

    @unittest.skipUnless(os.name == 'nt', 'retained process handle requires Windows')
    def test_retained_current_process_handle_and_fake_pdh_sample(self):
        from gufo_control import service_ipc
        request = dict(service_ipc._process_identity(os.getpid()), adapter_luid=LUID)
        raw = fixture()
        raw['provider'] = telemetry.PROVIDER
        _, optional = owned_fixture()
        for row in optional['counters']:
            row['path'] = row['path'].replace('pid_42_', 'pid_'+str(os.getpid())+'_')
            row['instance'] = row['instance'].replace('pid_42_', 'pid_'+str(os.getpid())+'_')
        raw['owned'] = optional
        now = datetime.now(timezone.utc)
        for row in raw['counters']+optional['counters']: row['timestamp_utc'] = now.isoformat()
        peers = []
        original = service_ipc._Peer
        def retain(pid):
            peer = original(pid)
            peers.append(peer)
            return peer
        with patch.object(service_ipc, '_Peer', side_effect=retain), patch.object(
                telemetry.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, json.dumps(raw).encode(), b'')) as probe:
            sample = collect_snapshot(owned=request)
        diagnostic = sample['owned_counters']
        self.assertTrue(diagnostic['available'], diagnostic)
        self.assertGreater(diagnostic['working_set_bytes'], 0)
        self.assertEqual(diagnostic['identity']['creation_time_100ns'], request['creation_time_100ns'])
        self.assertTrue(all(peer.handle is None for peer in peers))
        self.assertEqual(probe.call_count, 1)
        self.assertIn('-OwnedPid', probe.call_args.args[0])
        self.assertLessEqual(probe.call_args.kwargs['timeout'], 5)

    def test_failed_optional_handle_and_exit_preserve_aggregate(self):
        from gufo_control import service_ipc
        from unittest.mock import Mock
        request, optional = owned_fixture()
        now = datetime.now(timezone.utc)
        raw = fixture()
        raw['provider'] = telemetry.PROVIDER
        raw['owned'] = optional
        for row in raw['counters']+optional['counters']: row['timestamp_utc'] = now.isoformat()
        for kind in ('open_failure', 'reuse', 'exit'):
            peer = Mock(identity=dict(request), alive=lambda: False)
            if kind == 'reuse': peer.identity['creation_time_100ns'] += 1
            with patch.object(service_ipc, '_Peer', side_effect=OSError() if kind == 'open_failure' else None,
                              return_value=peer), patch.object(telemetry.subprocess, 'run',
                return_value=subprocess.CompletedProcess([], 0, json.dumps(raw).encode(), b'')) as probe:
                result = collect_snapshot(owned=request)
            self.assertTrue(result['telemetry_ok'])
            self.assertFalse(result['owned_counters']['available'])
            self.assertIsNone(result['owned_counters']['private_bytes'])
            if kind != 'open_failure': peer.close.assert_called_once()
            if kind in ('open_failure', 'reuse'): self.assertNotIn('-OwnedPid', probe.call_args.args[0])

    def test_no_instance_is_not_a_measured_zero_or_process_exit(self):
        request, optional = owned_fixture()
        optional['counters'] = []
        result = self.normalize(optional, request)['owned_counters']
        self.assertEqual(result['reason'], 'owned_instance_missing')
        self.assertIsNone(result['process_dedicated_bytes'])
        optional.update(available=False, reason='process_exited')
        result = self.normalize(optional, request)['owned_counters']
        self.assertEqual(result['reason'], 'process_exited')

    def test_malformed_optional_reply_does_not_fail_aggregate_and_identity_time_is_bounded(self):
        from gufo_control import service_ipc
        from unittest.mock import Mock
        request, _ = owned_fixture()
        raw = fixture()
        raw['provider'] = telemetry.PROVIDER
        now = datetime.now(timezone.utc)
        for row in raw['counters']: row['timestamp_utc'] = now.isoformat()
        raw['owned'] = None
        peer = Mock(identity=dict(request), alive=lambda: True)
        with patch.object(service_ipc, '_Peer', return_value=peer), patch.object(
            telemetry, '_host_process_memory', return_value=dict(working_set_bytes=1,private_bytes=2)), patch.object(
            telemetry.time, 'monotonic', side_effect=[100.,100.5,101.]), patch.object(
            telemetry.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,json.dumps(raw).encode(),b'')) as probe:
            try:
                result = collect_snapshot(owned=request)
            except AttributeError as error:
                self.fail('optional malformed reply escaped aggregate isolation: '+str(error))
        self.assertTrue(result['telemetry_ok'])
        self.assertFalse(result['owned_counters']['available'])
        self.assertEqual(probe.call_args.kwargs['timeout'], 4.5)
        peer.close.assert_called_once()


def fixture():
    rows = []
    for label, value in (("available bytes", 53 * G), ("committed bytes", 15 * G), ("commit limit", 224 * G)):
        rows.append(dict(path="\\\\host\\memory\\" + label, instance=None, raw_value=value,
                         cooked_value=value, status=0, timestamp_utc=STAMP))
    for label, value in (("dedicated usage", G), ("shared usage", G // 4), ("total committed", 2 * G)):
        rows.append(dict(path="\\\\host\\gpu adapter memory(" + INSTANCE + ")\\" + label,
                         instance=INSTANCE, raw_value=value, cooked_value=value,
                         status=0, timestamp_utc=STAMP))
    return dict(schema=1, provider="PDH/Get-Counter;DXGI/EnumAdapters1",
                adapters=[dict(luid=LUID, vendor_id=0x1002, device_id=0x1586,
                               subsystem_id=0x801d2014, flags=0,
                               description="AMD Radeon(TM) 8060S Graphics",
                               dedicated_video_memory=64 * G)], counters=rows, processes=[])


class TelemetryTests(unittest.TestCase):
    def test_native_provider_normalizes_without_relabeling(self):
        raw = fixture()
        raw["provider"] = "PDH/native-gauges;DXGI/EnumAdapters1"
        normalized = self.normalize(raw)
        self.assertEqual(normalized["provider"], raw["provider"])
        self.assertEqual(normalized["raw"]["provider"], raw["provider"])

    def test_policy_accepts_explicit_historical_and_native_providers(self):
        for provider in ("PDH/Get-Counter;DXGI/EnumAdapters1",
                         "PDH/native-gauges;DXGI/EnumAdapters1"):
            with self.subTest(provider=provider):
                raw = fixture()
                raw["provider"] = provider
                snapshot = self.normalize(raw)
                self.assertEqual(_frame_reasons(Frame(snapshot, 100., 101., NOW)), [])
        raw["provider"] = "other"
        with self.assertRaises(TelemetryError):
            self.normalize(raw)

    @patch("gufo_control.telemetry.os.name", "nt")
    @patch("gufo_control.telemetry.subprocess.run")
    def test_collect_rejects_historical_subprocess_provider(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(fixture()).encode(), b"")
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(NOW.timestamp(), tz)
        with patch("gufo_control.telemetry.datetime", FrozenDatetime):
            with self.assertRaisesRegex(TelemetryError, "provider"):
                collect_snapshot()

    def normalize(self, raw, **kw):
        args = dict(captured_monotonic=100., now_monotonic=101., now_utc=NOW)
        args.update(kw)
        return normalize_snapshot(raw, **args)

    def rejects(self, edit):
        raw = fixture()
        edit(raw)
        with self.assertRaises(TelemetryError):
            self.normalize(raw)

    def test_exact_scopes_and_independent_committed_value(self):
        raw = fixture()
        original = copy.deepcopy(raw)
        result = self.normalize(raw)
        self.assertEqual(raw, original)
        self.assertEqual(result["adapter_luid"], LUID)
        self.assertEqual(result["gpu_scope"], "adapter_aggregate")
        self.assertEqual(result["host_scope"], "host_global")
        self.assertEqual(result["inventory_scope"], "known_engine_and_guest_names")
        self.assertEqual(result["available_physical_bytes"], 53 * G)
        self.assertEqual(result["commit_headroom_bytes"], 209 * G)
        self.assertEqual(result["adapter_total_committed_bytes"], 2 * G)
        self.assertNotEqual(result["adapter_total_committed_bytes"], result["adapter_dedicated_bytes"] + result["adapter_shared_bytes"])
        self.assertEqual(result["sample_utc_min"], NOW.replace(second=0).isoformat())
        self.assertEqual(result["sample_utc_max"], NOW.replace(second=0).isoformat())
        self.assertEqual(result["raw"], raw)

    def test_other_adapter_is_not_summed(self):
        raw = fixture()
        for row in list(raw["counters"][3:]):
            row = dict(row)
            row["path"] = row["path"].replace("0x000111c1", "0x00014fe1")
            row["instance"] = row["instance"].replace("0x000111c1", "0x00014fe1")
            row["raw_value"] = row["cooked_value"] = 10 * G
            raw["counters"].append(row)
        self.assertEqual(self.normalize(raw)["adapter_dedicated_bytes"], G)

    def test_other_adapter_rows_must_be_healthy_complete_and_fresh(self):
        for change in (
            lambda row: row.pop("raw_value"),
            lambda row: row.update(raw_value=-1, cooked_value=-1),
            lambda row: row.update(cooked_value=float("nan")),
            lambda row: row.update(status=0xc0000bc6),
            lambda row: row.pop("timestamp_utc"),
            lambda row: row.update(timestamp_utc="2026-09-26T11:59:55Z"),
        ):
            raw = fixture()
            row = copy.deepcopy(raw["counters"][3])
            row["path"] = row["path"].replace("0x000111c1", "0x00014fe1")
            row["instance"] = row["instance"].replace("0x000111c1", "0x00014fe1")
            change(row)
            raw["counters"].append(row)
            with self.subTest(change=change), self.assertRaises(TelemetryError):
                self.normalize(raw)

    def test_duplicate_luid_across_distinct_adapter_descriptors_rejected(self):
        raw = fixture()
        other = copy.deepcopy(raw["adapters"][0])
        other.update(vendor_id=0x1234, device_id=0x5678, description="Other GPU")
        other["luid"] = other["luid"].upper().replace("0X", "0x")
        raw["adapters"].append(other)
        with self.assertRaises(TelemetryError):
            self.normalize(raw)

    def test_valid_radeon_with_alternate_subsystem_and_description(self):
        raw = fixture()
        raw["adapters"][0].update(subsystem_id=0x12345678, description="OEM Radeon 8060S")
        self.assertEqual(self.normalize(raw)["adapter_luid"], LUID)

    def test_adapter_identity_rejections(self):
        for edit in (
            lambda r: r["adapters"].append(copy.deepcopy(r["adapters"][0])),
            lambda r: r["adapters"][0].update(device_id=1),
            lambda r: r["adapters"][0].update(vendor_id=True),
            lambda r: r["adapters"][0].update(flags=2),
            lambda r: r["adapters"][0].update(description=" "),
            lambda r: r["adapters"][0].update(subsystem_id=-1),
            lambda r: r["adapters"][0].update(subsystem_id=True),
            lambda r: r["adapters"].append(None),
            lambda r: r["adapters"][0].update(luid="bad"),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_counter_identity_rejections(self):
        for edit in (
            lambda r: r["counters"].append(copy.deepcopy(r["counters"][3])),
            lambda r: r["counters"].pop(3),
            lambda r: r["counters"][3].update(instance="luid_0x00000000_0x000111c1_phys_1"),
            lambda r: r["counters"][3].update(path=r["counters"][3]["path"].replace("phys_0", "phys_1"), instance=INSTANCE.replace("phys_0", "phys_1")),
            lambda r: r["counters"][0].update(instance=INSTANCE),
            lambda r: r["counters"][3].update(path="\\\\host\\gpu adapter memory(bad)\\dedicated usage"),
            lambda r: r["counters"][0].update(path="\\\\host\\memory\\unknown"),
            lambda r: r["counters"].append(None),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_counter_health_and_value_rejections(self):
        for edit in (
            lambda r: r["counters"][3].update(status=0xc0000bc6),
            lambda r: r["counters"][3].update(raw_value=-1),
            lambda r: r["counters"][3].update(raw_value=True),
            lambda r: r["counters"][3].update(raw_value=1 << 64),
            lambda r: r["counters"][3].update(cooked_value=1.5),
            lambda r: r["counters"][3].update(cooked_value=1 << 10000),
            lambda r: r["counters"][3].update(cooked_value=float("nan")),
            lambda r: r["counters"][3].update(cooked_value=True),
            lambda r: r["counters"][0].update(timestamp_utc="2026-09-26T11:59:55Z"),
            lambda r: r["counters"][0].update(timestamp_utc="2026-09-26T12:00:02Z"),
            lambda r: r["counters"][0].update(timestamp_utc="bad"),
            lambda r: r["counters"][1].update(raw_value=225 * G, cooked_value=225 * G),
            lambda r: r["counters"][3].update(raw_value=65 * G, cooked_value=65 * G),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_schema_time_and_collection_bounds(self):
        for edit in (
            lambda r: r.update(schema=True),
            lambda r: r.update(provider="other"),
            lambda r: r.update(provider=[]),
            lambda r: r.update(counters=[]),
            lambda r: r.update(processes=None),
            lambda r: r.update(adapters="bad"),
        ):
            with self.subTest(edit=edit): self.rejects(edit)
        for args in (dict(captured_monotonic=1 << 10000), dict(now_monotonic=float("inf")),
                     dict(now_monotonic=99.), dict(now_monotonic=106.),
                     dict(now_utc=NOW.replace(tzinfo=None))):
            with self.subTest(args=args), self.assertRaises(TelemetryError):
                self.normalize(fixture(), **args)

    def test_inventory_exact_names_and_integrity(self):
        raw = fixture()
        raw["processes"] = [dict(pid=123, name="vmmemWSL"), dict(pid=456, name="notepad"),
                            dict(pid=789, name="LM Studio"), dict(pid=321, name="gufo"),
                            dict(pid=0, name="Idle")]
        self.assertEqual(self.normalize(raw)["other_inference_pids"], [123, 321, 789])
        for edit in (
            lambda r: r["processes"].append(dict(pid=True, name="gufo")),
            lambda r: r["processes"].append(dict(pid=0, name="gufo")),
            lambda r: r["processes"].extend((dict(pid=123, name="gufo"), dict(pid=123, name="notepad"))),
            lambda r: r["processes"].append(dict(pid=777, name=" ")),
            lambda r: r["processes"].append(None),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_counter_order_does_not_matter(self):
        raw = fixture()
        raw["counters"].reverse()
        self.assertEqual(self.normalize(raw)["adapter_total_committed_bytes"], 2 * G)

    @patch("gufo_control.telemetry.os.name", "nt")
    @patch("gufo_control.telemetry.subprocess.run")
    @patch("gufo_control.telemetry.time.monotonic", side_effect=[100., 101.])
    def test_collect_normalizes_real_subprocess_boundary(self, monotonic, run):
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(NOW.timestamp(), tz)
        raw = fixture()
        raw["provider"] = "PDH/native-gauges;DXGI/EnumAdapters1"
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(raw).encode(), b"")
        with patch("gufo_control.telemetry.datetime", FrozenDatetime):
            self.assertEqual(collect_snapshot()["adapter_luid"], LUID)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)

    @patch("gufo_control.telemetry.os.name", "nt")
    @patch("gufo_control.telemetry.subprocess.run")
    def test_collect_fails_closed_at_process_boundary(self, run):
        failures = (subprocess.CompletedProcess([], 1, b"{}", b"failure"),
                    subprocess.CompletedProcess([], 0, b"\xff", b""),
                    subprocess.CompletedProcess([], 0, b"{", b""),
                    subprocess.CompletedProcess([], 0, b"x" * (2 * 1024 * 1024 + 1), b""))
        for value in failures:
            run.return_value = value
            with self.subTest(value=len(value.stdout)), self.assertRaises(TelemetryError):
                collect_snapshot()
        run.side_effect = subprocess.TimeoutExpired("powershell", 5)
        with self.assertRaises(TelemetryError): collect_snapshot()

    @patch("gufo_control.telemetry.os.name", "nt")
    @patch("gufo_control.telemetry.struct.calcsize", return_value=4)
    def test_collect_rejects_32_bit_python(self, calcsize):
        with self.assertRaises(TelemetryError):
            collect_snapshot()


if __name__ == "__main__":
    unittest.main()
