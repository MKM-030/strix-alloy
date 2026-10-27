"""Local protocol and native Windows security tests; no model execution."""
import importlib
import importlib.util
import gc
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid
import weakref
from contextlib import contextmanager


def _native_guardian_helper(descriptor_path):
    """Only this test module injects harmless ownership and synthetic telemetry."""
    from contextlib import ExitStack
    from types import SimpleNamespace
    from test_smoke_guard import Harness
    from gufo_control import service_ipc as ipc, service_lifecycle, service_store
    from gufo_control import smoke_guard as guard, operator_store, operator_probe
    from gufo_control.winjob import OwnedProcess
    descriptor_path = Path(descriptor_path)
    root = descriptor_path.parent
    descriptor = json.loads(descriptor_path.read_text())
    h = Harness(root/'evidence')
    h.manifest['installed_profile'] = {'fixture': 'harmless-native'}
    h.store.BUILD = root
    actual_sleep = time.sleep
    clock_sleep = h.clock.sleep
    def sleep(seconds):
        actual_sleep(.003)
        clock_sleep(seconds)
    h.clock.sleep = sleep
    def owned(argv, **kwargs):
        child = OwnedProcess(argv, **kwargs)
        h.children.append(child)
        # Readiness telemetry/module proof are synthetic; Job ownership is real.
        child.inspect_modules = lambda **_: SimpleNamespace(snapshot=lambda **_: dict(
            status='verified', terminal=True, duplicate_handle_closed=True),
            deadline=h.clock.monotonic()+2, done=SimpleNamespace(is_set=lambda: True),
            duplicate_closed=SimpleNamespace(is_set=lambda: True))
        return child
    with ExitStack() as stack:
        stack.enter_context(patch.object(guard, 'time', h.clock))
        stack.enter_context(patch.object(operator_probe, 'time', h.clock))
        stack.enter_context(patch.object(guard, 'utcnow', h.clock.utcnow))
        stack.enter_context(patch.object(operator_store, 'EVIDENCE', root/'operator'))
        stack.enter_context(patch.object(service_lifecycle, '_qualified_deadline', lambda _, now: now+600))
        h.guard = guard._Guardian(store=h.store, owned_factory=owned, query_factory=h.query,
            http_start=h.http, collect=lambda: None, port_check=h.port,
            argv_builder=lambda key: [sys.executable, '-c', 'import time; time.sleep(60)', '--api-key', key])
        result = ipc._run_guardian(h.guard, descriptor)
    operator_store.atomic_json(root/'helper-result.json', result)


def _native_launcher_helper(descriptor_path):
    from gufo_control import service_ipc as ipc, service_store, operator_store
    root = Path(descriptor_path).parent
    descriptor = dict(parent=ipc._process_identity(os.getpid()),
        profile_digest=service_store._digest({'fixture': 'harmless-native'}),
        record_path=str(root/'endpoint.json'))
    operator_store.atomic_json(descriptor_path, descriptor)
    real_popen = subprocess.Popen
    def private_test_entry(argv, **kwargs):
        assert argv[1:3] == ['-m', 'gufo_control.service']
        # A Windows venv redirector has a different PID from the interpreter
        # serving the pipe. This fixture must launch the actual guardian image.
        argv = [getattr(sys, '_base_executable', argv[0]), '-m',
                'test_service_ipc', '_native_guardian', str(descriptor_path)]
        # Only the test entry needs this private helper module; production fixes
        # its module path to scripts without inheriting arbitrary PYTHONPATH.
        kwargs['env'] = dict(kwargs['env'], PYTHONPATH=kwargs['env']['PYTHONPATH']+
                             os.pathsep+str(Path(__file__).resolve().parent))
        return real_popen(argv, **kwargs)
    process = None
    try:
        with patch.object(ipc.subprocess, 'Popen', private_test_entry):
            process = ipc._launch_hidden(Path(descriptor_path))
        operator_store.atomic_json(root/'guardian.json', ipc._process_identity(process.pid))
        until = time.monotonic()+15
        while not (root/'endpoint.json').exists():
            if process.poll() is not None or time.monotonic() > until:
                raise RuntimeError('native_guardian_not_ready')
            time.sleep(.005)
        record = json.loads((root/'endpoint.json').read_text())
        ipc._match_identity(record['guardian'], ipc._process_identity(process.pid))
        result = ipc.control_request(record, 'handoff', timeout_seconds=10)
        operator_store.atomic_json(root/'launcher-result.json', result)
        if result['state'] != 'committed':
            raise RuntimeError('native_handoff_unconfirmed')
        # Parent test retains a handle before allowing this launcher to exit.
        while not (root/'exit-launcher').exists() and time.monotonic() < until:
            time.sleep(.005)
        if not (root/'exit-launcher').exists():
            raise RuntimeError('native_test_parent_timeout')
        process = None
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)


class ProtocolTests(unittest.TestCase):
    def test_handoff_outcome_survives_unconfirmed_client_cleanup(self):
        from types import SimpleNamespace
        ipc = importlib.import_module('gufo_control.service_ipc')
        record = dict(run_id='exact-run', profile_digest='a'*64,
                      guardian={'pid': 1}, child={'pid': 2}, run='exact-directory')
        for acknowledged in (True, False):
            with self.subTest(acknowledged=acknowledged):
                channel = ipc._Channel(None)
                ready = ipc._envelope(record, channel.challenge, state='ready',
                    guardian=record['guardian'], child=record['child'], run=record['run'])
                ack = ipc._envelope(record, channel.challenge, state='committed')
                responses = ['sent', ready, 'sent', ack if acknowledged else TimeoutError('lost_ack')]
                clock = SimpleNamespace(monotonic=iter([0, 0, 3]).__next__, sleep=lambda _: None)
                try:
                    with patch.object(ipc, '_connect', return_value=channel), \
                            patch.object(ipc, '_process_identity', return_value={'pid': 3}), \
                            patch.object(channel, 'send'), patch.object(channel, 'receive'), \
                            patch.object(ipc, '_wait_channel', side_effect=responses), \
                            patch.object(channel, 'retire', return_value=False), \
                            patch.object(ipc, 'time', clock):
                        try:
                            result = ipc.control_request(record, 'handoff', timeout_seconds=1)
                        except RuntimeError as error:
                            self.fail(f'cleanup erased the handoff outcome: {error}')
                    self.assertEqual(result['state'], 'committed' if acknowledged else 'indeterminate')
                    self.assertEqual(result['run_id'], record['run_id'])
                    self.assertEqual(result['cleanup_error'], 'control_cleanup_incomplete')
                    if not acknowledged:
                        self.assertTrue(result['requires_status'])
                    self.assertIn(channel, ipc._RETAINED_CLEANUP)
                finally:
                    ipc._close_client(channel)
                self.assertNotIn(channel, ipc._RETAINED_CLEANUP)

    def test_envelope_binds_run_digest_version_and_challenge(self):
        ipc = importlib.import_module('gufo_control.service_ipc')
        record = dict(run_id='run', profile_digest='a'*64)
        good = ipc._envelope(record, 'challenge', command='status')
        for key, wrong in (('run_id', 'other'), ('profile_digest', 'b'*64),
                           ('schema_version', 2), ('schema_version', True), ('challenge', 'stolen')):
            with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                ipc._validate_envelope(dict(good, **{key: wrong}), record, 'challenge')

    def test_framing_rejects_malformed_oversized_and_non_object(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.service_ipc'),
                             'authenticated IPC transport is missing')
        ipc = importlib.import_module('gufo_control.service_ipc')
        self.assertEqual(ipc._decode(ipc._encode({'x': 'ü'})[4:]), {'x': 'ü'})
        for value in (b'[]', b'{', b'\xff', b'{"x":NaN}', b'{"x":1e999}', b'{"x":1,"x":2}', b'x'*65537):
            with self.subTest(value=value[:12]), self.assertRaises(ValueError):
                ipc._decode(value)
        with self.assertRaises(ValueError):
            ipc._encode({'x': 'x'*65536})

    def test_identity_checks_every_binding(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.service_ipc'))
        ipc = importlib.import_module('gufo_control.service_ipc')
        expected = dict(pid=42, creation_time_100ns=123, executable=r'C:\Python\python.exe', user_sid='S-1-5-21-1')
        ipc._match_identity(expected, dict(expected, executable=r'c:\python\PYTHON.exe'))
        for invalid in (None, 42, [], 'invalid'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ipc._match_identity(invalid, expected)
        for key, wrong in (('pid', 43), ('creation_time_100ns', 124),
                           ('executable', r'C:\bad.exe'), ('user_sid', 'S-1-5-21-2')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                ipc._match_identity(expected, dict(expected, **{key: wrong}))

    def test_existing_guardian_generates_fresh_keys_and_redacts_all_evidence(self):
        from test_smoke_guard import Harness
        observed = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                result = h.run()
                key = h.http_tasks[0].args['api_key']
                observed.append(key)
                self.assertGreaterEqual(len(key), 32)
                self.assertNotIn(key, json.dumps(result))
                for path in Path(root).rglob('*'):
                    if path.is_file():
                        self.assertNotIn(key.encode(), path.read_bytes(), str(path))
        self.assertNotEqual(*observed)


@unittest.skipUnless(os.name == 'nt', 'native Windows IPC')
class NativeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.service_ipc'))
        self.ipc = importlib.import_module('gufo_control.service_ipc')

    @contextmanager
    def parent_session(self):
        ipc = self.ipc
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            descriptor = dict(parent=ipc._process_identity(os.getpid()), profile_digest='a'*64,
                              record_path=str(root/'endpoint.json'))
            life = ipc._IpcLifecycle(descriptor, lambda now: now+60)
            results = []
            def connect():
                try:
                    until = time.monotonic()+3
                    while not (root/'endpoint.json').exists() and time.monotonic() < until:
                        time.sleep(.002)
                    record = json.loads((root/'endpoint.json').read_text())
                    channel = ipc._connect(record, until)
                    channel.send(ipc._envelope(record, channel.challenge, command='handoff',
                        client=ipc._process_identity(os.getpid())), 'request')
                    ipc._wait_channel(channel, until)
                    results.append(channel)
                except Exception as error:
                    results.append(error)
            thread = threading.Thread(target=connect)
            thread.start()
            try:
                life.on_started(root, dict(pid=123, creation_time_100ns=456, executable='harmless'), 'secret-token')
                thread.join(4)
                self.assertFalse(thread.is_alive())
                self.assertNotIsInstance(results[0], Exception)
                yield life, results[0], root
            finally:
                life.close()
                thread.join(4)
                if results and not isinstance(results[0], Exception):
                    ipc._close_client(results[0])

    def test_disconnect_before_commit_and_expired_handoff_fail(self):
        with self.parent_session() as (life, channel, root):
            self.ipc._close_client(channel)
            until = time.monotonic()+2
            request = None
            while request is None and time.monotonic() < until:
                request = life.poll(time.monotonic())
            self.assertEqual(request, 'handoff_failed')
            self.assertFalse((root/'handoff.json').exists())
        with self.parent_session() as (life, channel, root):
            life.handoff_deadline = time.monotonic()-1
            self.assertEqual(life.poll(time.monotonic()), 'handoff_failed')
            self.assertFalse((root/'handoff.json').exists())

    def test_status_disconnect_is_not_original_parent_disconnect_and_stop_startup(self):
        ipc = self.ipc
        with self.parent_session() as (life, channel, root):
            life.status_provider = lambda: dict(phase='unknown/stale', ready=None,
                aggregate_sample=None, owned_counters=None)
            for command in ('status', 'stop', 'stop'):
                results = []
                def request():
                    try:
                        results.append(ipc.control_request(life.record, command, timeout_seconds=2))
                    except Exception as error:
                        results.append(type(error).__name__)
                thread = threading.Thread(target=request)
                thread.start()
                try:
                    until = time.monotonic()+3
                    while thread.is_alive() and time.monotonic() < until:
                        value = life.poll(time.monotonic())
                        self.assertNotEqual(value, 'handoff_failed')
                        time.sleep(.002)
                finally:
                    thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertIsInstance(results[0], dict, results)
                if command == 'status':
                    self.assertEqual(results[0]['phase'], 'unknown/stale')
                    self.assertIsNone(results[0]['aggregate_sample'])
                    self.assertEqual(results[0]['guardian'], life.record['guardian'])
                    self.assertEqual(results[0]['child'], life.record['child'])
                    self.assertFalse(results[0]['handoff_confirmed'])
            self.assertEqual(life.poll(time.monotonic()), 'stop')
            self.assertFalse((root/'handoff.json').exists())
            with self.assertRaises(ValueError):
                life.on_ready(dict(run=str(root), identity=life.record['child']))

    def test_wrong_run_challenge_user_and_pid_reuse_reject_client(self):
        ipc = self.ipc
        for mutate in (
            lambda msg: msg.update(run_id='wrong'),
            lambda msg: msg.update(challenge='wrong'),
            lambda msg: msg['client'].update(user_sid='S-1-5-18'),
            lambda msg: msg['client'].update(creation_time_100ns=1)):
            with self.parent_session() as (life, channel, root):
                message = ipc._envelope(life.record, channel.challenge, command='commit',
                    client=ipc._process_identity(os.getpid()))
                mutate(message)
                channel.send(message, 'request')
                ipc._wait_channel(channel, time.monotonic()+1)
                until = time.monotonic()+2
                outcome = None
                while outcome is None and time.monotonic() < until:
                    outcome = life.poll(time.monotonic())
                self.assertEqual(outcome, 'handoff_failed')
                self.assertFalse((root/'handoff.json').exists())

    def test_native_inherited_pipe_handle_is_denied(self):
        ipc = self.ipc
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        helper = None
        try:
            handle = server._slots[0].handle
            self.assertFalse(ipc._inherited(handle))  # Also proves parent handle validity.
            query = ipc._api().GetNamedPipeInfo
            query.argtypes = [ipc.W.HANDLE] + [ipc.C.POINTER(ipc.W.DWORD)]*4
            query.restype = ipc.W.BOOL
            self.assertTrue(query(handle, None, None, None, None))
            # Python may reuse a noninherited numeric handle. Query the actual
            # pipe object, with the same idle pipe explicitly inherited as control.
            code = ('import ctypes as C,sys; a=C.WinDLL("kernel32",use_last_error=True); '
                'a.GetNamedPipeInfo.argtypes=[C.c_void_p]+[C.POINTER(C.c_ulong)]*4; '
                'valid=bool(a.GetNamedPipeInfo(int(sys.argv[1]),None,None,None,None)); '
                'sys.exit(0 if valid==bool(int(sys.argv[2])) else 1)')
            for inherited in (False, True):
                os.set_handle_inheritable(handle, inherited)
                helper = subprocess.Popen([sys.executable, '-c', code, str(handle), str(int(inherited))],
                    close_fds=False, creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.assertEqual(helper.wait(timeout=5), 0, f'inheritance={inherited}')
        finally:
            if helper is not None:
                if helper.poll() is None:
                    helper.terminate()
                helper.wait(timeout=5)
            os.set_handle_inheritable(server._slots[0].handle, False)
            server.close()

    def test_absent_and_busy_endpoint_have_bounded_connection_timeout(self):
        ipc = self.ipc
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        occupied = None
        try:
            occupied = ipc._api().CreateFileW(server.record['endpoint'], 0x12019b, 0, None, 3, 0x40000000, None)
            self.assertNotEqual(occupied, ipc._INVALID)
            missing_id = uuid.uuid4().hex
            absent = dict(server.record, run_id=missing_id, endpoint='\\\\.\\pipe\\gufo-'+missing_id)
            for record in (absent, server.record):
                with self.subTest(endpoint=record['endpoint']):
                    started = time.monotonic()
                    try:
                        with self.assertRaisesRegex(TimeoutError, 'control_connect_timeout'):
                            ipc._connect(record, started+.02)
                    except UnboundLocalError as error:
                        self.fail(f'connection timeout accessed a nonexistent channel: {error}')
                    self.assertLess(time.monotonic()-started, 1)
        finally:
            if occupied not in (None, ipc._INVALID):
                ipc.winjob._check(ipc._api().CloseHandle(occupied))
            server.close()

    def test_client_cancellation_owner_survives_discarded_exception_and_collection(self):
        ipc = self.ipc
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        channel = operation = None
        owner = None
        handle = None
        try:
            handle = ipc._api().CreateFileW(server.record['endpoint'], 0x12019b, 0, None, 3, 0x40000000, None)
            self.assertNotEqual(handle, ipc._INVALID)
            channel = ipc._Channel(handle)
            channel.receive()
            operation = channel.operation
            owner = weakref.ref(channel)
            now = time.monotonic()
            with patch.object(operation, 'poll', return_value=None), \
                    patch.object(ipc.time, 'monotonic', side_effect=[now, now, now+3]):
                try:
                    ipc._close_client(channel)
                except RuntimeError as error:
                    self.assertEqual(str(error), 'pending_io_retained')
                else:
                    self.fail('unconfirmed client retirement did not fail')
            del channel
            gc.collect()
            self.assertIsNotNone(owner(), 'discarding the exception freed the pending client channel')
            self.assertIn(owner(), ipc._RETAINED_CLEANUP)
            self.assertIs(owner().operation, operation)
            ipc._close_client(owner())
            self.assertIsNone(owner(), 'confirmed retirement did not release registry ownership')
        finally:
            # Keep native operation storage alive even on the pre-fix RED path.
            channel = owner() if owner else channel
            if channel is None and operation is not None and operation.overlapped.event:
                channel = ipc._Channel(handle)
                channel.operation = operation
            if channel is not None:
                ipc._close_client(channel)
            server.close()

    def test_replaced_endpoint_cannot_be_joined_after_all_old_handles_close(self):
        ipc = self.ipc
        identity = dict(ipc._process_identity(os.getpid()), profile_digest='a'*64)
        server = ipc.ControlServer(uuid.uuid4().hex, identity)
        server.close()
        replacement = ipc.ControlServer(server.run_id, identity)
        try:
            with self.assertRaises(OSError):
                server._listen()
        finally:
            server.close()
            replacement.close()

    def test_unconfirmed_cancellation_retains_owner_even_if_exception_is_discarded(self):
        ipc = self.ipc
        self.assertTrue(hasattr(ipc, '_RETAINED_CLEANUP'), 'unconfirmed cancellation lacks durable Python ownership')
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        operation = server._slots[0].operation
        now = time.monotonic()
        try:
            with patch.object(operation, 'poll', return_value=None), patch.object(ipc.time, 'monotonic', side_effect=[now, now, now+3]):
                with self.assertRaisesRegex(RuntimeError, 'pending_io_retained'):
                    server.close()
            self.assertIn(server, ipc._RETAINED_CLEANUP)
            self.assertIsNotNone(operation.buffer)
            server.close()
            self.assertNotIn(server, ipc._RETAINED_CLEANUP)
        finally:
            server.close()

    def test_unconfirmed_retired_io_fails_serving_with_bounded_retention(self):
        ipc = self.ipc
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        slot = server._slots[0]
        operation = slot.operation
        server._drop(slot)
        now = time.monotonic()
        try:
            with patch.object(operation, 'poll', return_value=None), patch.object(ipc.time, 'monotonic', return_value=now):
                server.poll()
            with patch.object(operation, 'poll', return_value=None), patch.object(ipc.time, 'monotonic', return_value=now+3):
                with self.assertRaisesRegex(RuntimeError, 'pipe_cancellation_unconfirmed'):
                    server.poll()
            self.assertIn(server, ipc._RETAINED_CLEANUP)
            self.assertLessEqual(len(server._slots)+len(server._retired), 4)
        finally:
            server.close()
        self.assertNotIn(server, ipc._RETAINED_CLEANUP)

    def test_lost_final_ack_is_indeterminate_and_commit_is_durable(self):
        ipc = self.ipc
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            life = ipc._IpcLifecycle(dict(parent=ipc._process_identity(os.getpid()),
                profile_digest='a'*64, record_path=str(root/'endpoint.json')), lambda now: now+60)
            outcomes = []
            def request():
                try:
                    until = time.monotonic()+3
                    while not (root/'endpoint.json').exists() and time.monotonic() < until:
                        time.sleep(.002)
                    outcomes.append(ipc.control_request(json.loads((root/'endpoint.json').read_text()), 'handoff', timeout_seconds=3))
                except Exception as error:
                    outcomes.append(type(error).__name__)
            thread = threading.Thread(target=request)
            thread.start()
            try:
                life.on_started(root, dict(pid=1, creation_time_100ns=2, executable='harmless'), 'secret-token')
                original_reply = life.server.reply
                def lose_ack(event, value, **kwargs):
                    if value['state'] == 'committed':
                        life.server._drop(event['channel'])
                    else:
                        original_reply(event, value, **kwargs)
                life.server.reply = lose_ack
                life.on_ready(dict(run=str(root), identity=life.record['child']))
                until = time.monotonic()+4
                while thread.is_alive() and time.monotonic() < until:
                    life.poll(time.monotonic())
                    time.sleep(.002)
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(outcomes[0]['state'], 'indeterminate')
                self.assertTrue(outcomes[0]['requires_status'])
                self.assertTrue(life.committed)
                self.assertTrue((root/'handoff.json').exists())
                self.assertIsNone(life.poll(time.monotonic()))
            finally:
                life.close()
                thread.join(4)

    def test_parent_cannot_commit_early_during_startup(self):
        ipc = self.ipc
        with self.parent_session() as (life, channel, root):
            channel.send(ipc._envelope(life.record, channel.challenge, command='commit',
                client=ipc._process_identity(os.getpid())), 'request')
            ipc._wait_channel(channel, time.monotonic()+1)
            until = time.monotonic()+2
            outcome = None
            while outcome is None and time.monotonic() < until:
                outcome = life.poll(time.monotonic())
                time.sleep(.002)
            self.assertEqual(outcome, 'handoff_failed')
            self.assertFalse((root/'handoff.json').exists())

    def test_readiness_run_mismatch_never_sends_commit(self):
        ipc = self.ipc
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            life = ipc._IpcLifecycle(dict(parent=ipc._process_identity(os.getpid()),
                profile_digest='a'*64, record_path=str(root/'endpoint.json')), lambda now: now+60)
            outcomes = []
            def request():
                try:
                    until = time.monotonic()+3
                    while not (root/'endpoint.json').exists() and time.monotonic() < until:
                        time.sleep(.002)
                    outcomes.append(ipc.control_request(json.loads((root/'endpoint.json').read_text()), 'handoff', timeout_seconds=3))
                except Exception as error:
                    outcomes.append(str(error))
            thread = threading.Thread(target=request)
            thread.start()
            try:
                life.on_started(root, dict(pid=1, creation_time_100ns=2, executable='harmless'), 'secret-token')
                original_reply = life.server.reply
                def wrong_run(event, value, **kwargs):
                    if value['state'] == 'ready':
                        value = dict(value, run=str(root/'wrong'))
                    original_reply(event, value, **kwargs)
                life.server.reply = wrong_run
                life.on_ready(dict(run=str(root), identity=life.record['child']))
                until = time.monotonic()+4
                while thread.is_alive() and time.monotonic() < until:
                    life.poll(time.monotonic())
                    time.sleep(.002)
                thread.join(1)
                self.assertEqual(outcomes[0], 'ready_identity_mismatch')
                self.assertFalse((root/'handoff.json').exists())
            finally:
                life.close()
                thread.join(4)

    def test_native_status_stop_identity_acl_and_exclusivity(self):
        ipc = self.ipc
        identity = dict(ipc._process_identity(os.getpid()), profile_digest='a'*64)
        server = ipc.ControlServer(uuid.uuid4().hex, identity)
        try:
            self.assertEqual(ipc._acl_sids(server._slots[0].handle), {identity['user_sid'], 'S-1-5-18'})
            self.assertFalse(ipc._inherited(server._slots[0].handle))
            self.assertTrue(server._pipe_mode & 8)
            with self.assertRaises(OSError):
                ipc.ControlServer(server.run_id, identity)
            for command in ('status', 'stop', 'stop'):
                results = []
                thread = threading.Thread(target=lambda: results.append(ipc.control_request(server.record, command, timeout_seconds=2)))
                thread.start()
                until = time.monotonic()+3
                while thread.is_alive() and time.monotonic() < until:
                    for event in server.poll():
                        server.reply(event, {'state': 'stopping' if command == 'stop' else 'starting'})
                    time.sleep(.002)
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(results[0]['state'], 'stopping' if command == 'stop' else 'starting')
        finally:
            server.close()

    def test_stalled_client_does_not_block_poll_and_cancellation_retains_storage(self):
        ipc = self.ipc
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        channel = None
        try:
            handle = ipc._api().CreateFileW(server.record['endpoint'], 0x12019b, 0, None, 3, 0x40000000, None)
            self.assertNotEqual(handle, ipc._INVALID)
            channel = ipc._Channel(handle)
            for _ in range(20):
                start = time.monotonic()
                server.poll()
                self.assertLess(time.monotonic()-start, .2)
                time.sleep(.002)
            slot = next(s for s in server._slots if s.state != 'connect')
            operation = slot.operation
            self.assertIsNotNone(operation)
            with self.assertRaisesRegex(RuntimeError, 'pending_io_retained'):
                operation.close()
            self.assertIsNotNone(operation.buffer)
            operation.cancel()
            until = time.monotonic()+2
            while not operation.terminal and time.monotonic() < until:
                try:
                    operation.poll()
                except OSError:
                    pass
            self.assertTrue(operation.terminal)
            operation.close()
            slot.operation = None
        finally:
            if channel:
                ipc._close_client(channel)
            server.close()

    def test_listener_waiting_longer_than_client_deadline_still_accepts(self):
        ipc = self.ipc
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        thread = None
        try:
            server._slots[0].deadline = time.monotonic()-10
            results = []
            def request():
                try:
                    results.append(ipc.control_request(server.record, 'status', timeout_seconds=1))
                except Exception as error:
                    results.append(type(error).__name__)
            thread = threading.Thread(target=request)
            thread.start()
            until = time.monotonic()+2
            while thread.is_alive() and time.monotonic() < until:
                for event in server.poll():
                    if event['command'] == 'status':
                        server.reply(event, {'state': 'starting'})
                time.sleep(.002)
            thread.join(1)
            self.assertEqual(results[0].get('state') if isinstance(results[0], dict) else results[0], 'starting')
        finally:
            server.close()
            if thread:
                thread.join(2)

    def test_wrong_server_identity_and_reparse_refused(self):
        ipc = self.ipc
        server = ipc.ControlServer(uuid.uuid4().hex, dict(ipc._process_identity(os.getpid()), profile_digest='a'*64))
        try:
            for key, wrong in (('pid', os.getpid()+1), ('creation_time_100ns', 1), ('user_sid', 'S-1-5-18')):
                record = dict(server.record, guardian=dict(server.record['guardian'], **{key: wrong}))
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'peer_identity_mismatch'):
                    ipc._connect(record, time.monotonic()+1)
                server.poll()
        finally:
            server.close()
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)/'target'
            target.mkdir()
            junction = Path(root)/'private'
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(target)], capture_output=True, check=True)
            try:
                with self.assertRaisesRegex(ValueError, 'credential_path_untrusted'):
                    ipc.write_client_credentials(Path(root), 'never-written')
                self.assertEqual(list(target.iterdir()), [])
            finally:
                junction.rmdir()

    def test_credentials_exclusive_protected_and_no_write_on_acl_failure(self):
        ipc = self.ipc
        with tempfile.TemporaryDirectory() as root:
            path = ipc.write_client_credentials(Path(root), 'secret-value')
            self.assertEqual(json.loads(path.read_text())['api_key'], 'secret-value')
            self.assertEqual(ipc._path_acl_sids(path), {ipc._process_identity(os.getpid())['user_sid']})
            with self.assertRaises(OSError):
                ipc.write_client_credentials(Path(root), 'different-secret')
            self.assertNotIn('different-secret', path.read_text())
        with tempfile.TemporaryDirectory() as root:
            with patch.object(ipc, '_verify_acl', side_effect=ValueError('acl_rejected')):
                with self.assertRaises(ValueError):
                    ipc.write_client_credentials(Path(root), 'never-written')
            self.assertFalse(any(p.is_file() and b'never-written' in p.read_bytes() for p in Path(root).rglob('*')))
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'private').mkdir()  # Inherited ordinary ACL is not accepted.
            with self.assertRaisesRegex(ValueError, 'acl_unprotected|acl_mismatch'):
                ipc.write_client_credentials(Path(root), 'never-written')
            self.assertEqual(list((Path(root)/'private').iterdir()), [])

    def test_lifecycle_retains_original_parent_and_commits_durably(self):
        ipc = self.ipc
        self.assertTrue(hasattr(ipc, '_IpcLifecycle'), 'missing lifecycle adapter')
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            descriptor = dict(parent=ipc._process_identity(os.getpid()), profile_digest='a'*64,
                              record_path=str(root/'endpoint.json'))
            life = ipc._IpcLifecycle(descriptor, lambda now: now+60)
            outcomes = []
            def request():
                until = time.monotonic()+3
                while not (root/'endpoint.json').exists() and time.monotonic() < until:
                    time.sleep(.002)
                record = json.loads((root/'endpoint.json').read_text())
                outcomes.append(ipc.control_request(record, 'handoff', timeout_seconds=3))
            thread = threading.Thread(target=request)
            thread.start()
            try:
                life.on_started(root, {'pid': 123, 'creation_time_100ns': 456, 'executable': 'harmless'}, 'secret-token')
                self.assertFalse((root/'handoff.json').exists())
                life.on_ready(dict(run=str(root), profile='fixture', identity=life.record['child'], runtime_samples=1))
                until = time.monotonic()+4
                while thread.is_alive() and time.monotonic() < until:
                    self.assertIsNone(life.poll(time.monotonic()))
                    time.sleep(.002)
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(outcomes[0]['state'], 'committed')
                self.assertEqual(json.loads((root/'handoff.json').read_text())['state'], 'committed')
                for _ in range(10):
                    self.assertIsNone(life.poll(time.monotonic()))
                self.assertNotIn('secret-token', json.dumps(life.record))
                life.on_result(dict(success=False, failure='secret-token', api_key='secret-token'))
                self.assertNotIn('secret-token', json.dumps(life.status))
            finally:
                life.close()
                thread.join(4)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '_native_guardian':
        _native_guardian_helper(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == '_native_launcher':
        _native_launcher_helper(sys.argv[2])
    else:
        unittest.main()
