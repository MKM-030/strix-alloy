"""Private Windows control transport. No process ownership or policy lives here.

The current engine receives its API key on argv. Same-user/administrator process
inspection can expose it; this transport does not claim that threat boundary.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import math
import ntpath
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import time
import uuid

from . import winjob

MAX_MESSAGE = 65536
_INVALID = C.c_void_p(-1).value
# A caller dropping an exception must never free memory still used by Windows.
# Explicit close retries remove an owner only after terminal I/O is confirmed.
_RETAINED_CLEANUP = []


class _Security(C.Structure):
    _fields_ = [('length', W.DWORD), ('descriptor', C.c_void_p), ('inherit', W.BOOL)]


class _Overlapped(C.Structure):
    _fields_ = [('internal', C.c_size_t), ('internal_high', C.c_size_t),
                ('offset', W.DWORD), ('offset_high', W.DWORD), ('event', W.HANDLE)]


def _api():
    api = winjob._api()
    definitions = {
        'OpenProcess': ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
        'CreateNamedPipeW': ([W.LPCWSTR, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, C.c_void_p], W.HANDLE),
        'CreateFileW': ([W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE),
        'CreateDirectoryW': ([W.LPCWSTR, C.c_void_p], W.BOOL),
        'GetFileAttributesW': ([W.LPCWSTR], W.DWORD),
        'GetHandleInformation': ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
        'GetNamedPipeClientProcessId': ([W.HANDLE, C.POINTER(W.ULONG)], W.BOOL),
        'GetNamedPipeServerProcessId': ([W.HANDLE, C.POINTER(W.ULONG)], W.BOOL),
        'CreateEventW': ([C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR], W.HANDLE),
        'ConnectNamedPipe': ([W.HANDLE, C.c_void_p], W.BOOL),
        'ReadFile': ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
        'WriteFile': ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
        'GetOverlappedResult': ([W.HANDLE, C.c_void_p, C.POINTER(W.DWORD), W.BOOL], W.BOOL),
        'CancelIoEx': ([W.HANDLE, C.c_void_p], W.BOOL),
        'LocalFree': ([C.c_void_p], C.c_void_p),
    }
    for name, (args, result) in definitions.items():
        fn = getattr(api, name)
        fn.argtypes, fn.restype = args, result
    return api


def _security_api():
    api = C.WinDLL('advapi32', use_last_error=True)
    definitions = {
        'OpenProcessToken': ([W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], W.BOOL),
        'GetTokenInformation': ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
        'ConvertSidToStringSidW': ([C.c_void_p, C.POINTER(W.LPWSTR)], W.BOOL),
        'ConvertStringSecurityDescriptorToSecurityDescriptorW': ([W.LPCWSTR, W.DWORD, C.POINTER(C.c_void_p), C.POINTER(W.DWORD)], W.BOOL),
        'GetSecurityInfo': ([W.HANDLE, C.c_int, W.DWORD, C.c_void_p, C.c_void_p, C.POINTER(C.c_void_p), C.c_void_p, C.POINTER(C.c_void_p)], W.DWORD),
        'GetAce': ([C.c_void_p, W.DWORD, C.POINTER(C.c_void_p)], W.BOOL),
        'GetSecurityDescriptorControl': ([C.c_void_p, C.POINTER(W.WORD), C.POINTER(W.DWORD)], W.BOOL),
    }
    for name, (args, result) in definitions.items():
        fn = getattr(api, name)
        fn.argtypes, fn.restype = args, result
    return api


def _sid_string(pointer):
    value = W.LPWSTR()
    winjob._check(_security_api().ConvertSidToStringSidW(pointer, C.byref(value)))
    try:
        return value.value
    finally:
        _api().LocalFree(C.cast(value, C.c_void_p))


class _Peer:
    """Retained query/synchronize handle, never terminate/Job access."""
    def __init__(self, pid):
        self.api = api = _api()
        self.handle = winjob._check(api.OpenProcess(0x101000, False, pid))
        try:
            if api.WaitForSingleObject(self.handle, 0) != 258:
                raise ValueError('peer_not_live')
            times = [W.FILETIME() for _ in range(4)]
            winjob._check(api.GetProcessTimes(self.handle, *(C.byref(t) for t in times)))
            path, length = C.create_unicode_buffer(32768), W.DWORD(32768)
            winjob._check(api.QueryFullProcessImageNameW(self.handle, 0, path, C.byref(length)))
            security, token = _security_api(), W.HANDLE()
            winjob._check(security.OpenProcessToken(self.handle, 8, C.byref(token)))
            try:
                size = W.DWORD()
                security.GetTokenInformation(token, 1, None, 0, C.byref(size))
                if not 0 < size.value <= 65536:
                    raise ValueError('token_size_invalid')
                buffer = C.create_string_buffer(size.value)
                winjob._check(security.GetTokenInformation(token, 1, buffer, size, C.byref(size)))
                sid = _sid_string(C.cast(buffer, C.POINTER(C.c_void_p))[0])
            finally:
                api.CloseHandle(token)
            self.identity = dict(pid=int(api.GetProcessId(self.handle)),
                creation_time_100ns=times[0].dwHighDateTime << 32 | times[0].dwLowDateTime,
                executable=path.value, user_sid=sid)
        except BaseException:
            self.close()
            raise

    def alive(self):
        return self.api.WaitForSingleObject(self.handle, 0) == 258

    def close(self):
        if self.handle:
            winjob._check(self.api.CloseHandle(self.handle))
            self.handle = None


def _process_identity(pid):
    peer = _Peer(pid)
    try:
        return dict(peer.identity)
    finally:
        peer.close()


def _match_identity(expected, actual):
    if (not isinstance(expected, dict) or not isinstance(actual, dict)
            or any(type(expected.get(k)) is not int or expected[k] != actual.get(k)
            for k in ('pid', 'creation_time_100ns'))
            or expected.get('user_sid') != actual.get('user_sid')
            or not isinstance(expected.get('executable'), str)
            or ntpath.normcase(expected['executable']) != ntpath.normcase(actual.get('executable', ''))):
        raise ValueError('peer_identity_mismatch')


class _Descriptor:
    def __init__(self, sid, *, pipe=False):
        self.pointer = C.c_void_p()
        # The same user must create additional server instances. Windows DACLs
        # cannot distinguish this guardian from other processes of that user.
        # Clients request only 0x12019b, excluding CREATE_PIPE_INSTANCE.
        rights = 'FA'
        sddl = f'D:P(A;;{rights};;;{sid})' + ('(A;;FA;;;SY)' if pipe else '')
        winjob._check(_security_api().ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, C.byref(self.pointer), None))
        self.attributes = _Security(C.sizeof(_Security), self.pointer, False)

    def close(self):
        _api().LocalFree(self.pointer)


def _acl_sids(handle):
    api, acl, descriptor = _security_api(), C.c_void_p(), C.c_void_p()
    code = api.GetSecurityInfo(handle, 1, 4, None, None, C.byref(acl), None, C.byref(descriptor))
    if code:
        raise OSError(code, 'acl_query_failed')
    try:
        control, revision = W.WORD(), W.DWORD()
        winjob._check(api.GetSecurityDescriptorControl(descriptor, C.byref(control), C.byref(revision)))
        if not acl.value or not control.value & 0x1000:
            raise ValueError('acl_unprotected')
        count = C.c_ushort.from_address(acl.value+4).value
        sids = set()
        for index in range(count):
            ace = C.c_void_p()
            winjob._check(api.GetAce(acl, index, C.byref(ace)))
            if C.c_ubyte.from_address(ace.value).value != 0:
                raise ValueError('acl_unexpected_ace')
            sids.add(_sid_string(ace.value+8))
        if count != len(sids):
            raise ValueError('acl_duplicate_ace')
        return sids
    finally:
        _api().LocalFree(descriptor)


def _verify_acl(handle, sids):
    if _acl_sids(handle) != sids:
        raise ValueError('acl_mismatch')


def _inherited(handle):
    flags = W.DWORD()
    winjob._check(_api().GetHandleInformation(handle, C.byref(flags)))
    return bool(flags.value & 1)


def _open_path(path):
    handle = _api().CreateFileW(str(path), 0x20000, 7, None, 3, 0x02200000, None)
    if handle == _INVALID:
        raise C.WinError(C.get_last_error())
    return handle


def _path_acl_sids(path):
    handle = _open_path(path)
    try:
        return _acl_sids(handle)
    finally:
        _api().CloseHandle(handle)


def _reject_reparse(path):
    for item in (path, *path.parents):
        attributes = _api().GetFileAttributesW(str(item))
        if attributes == 0xffffffff or attributes & 0x400:
            raise ValueError('credential_path_untrusted')


def write_client_credentials(run_dir: Path, api_key: str) -> Path:
    """Exclusive selected-client file; verify ACL before writing any secret."""
    api = _api()
    run_dir = Path(os.path.abspath(run_dir))
    _reject_reparse(run_dir)
    directory = run_dir/'private'
    sid = _process_identity(os.getpid())['user_sid']
    descriptor = _Descriptor(sid)
    directory_handle = file_handle = None
    try:
        if not api.CreateDirectoryW(str(directory), C.byref(descriptor.attributes)) and C.get_last_error() != 183:
            raise C.WinError(C.get_last_error())
        _reject_reparse(directory)
        directory_handle = _open_path(directory)
        _verify_acl(directory_handle, {sid})
        path = directory/'client-api-key.json'
        file_handle = api.CreateFileW(str(path), 0x40020000, 0, C.byref(descriptor.attributes), 1, 0x00200000, None)
        if file_handle == _INVALID:
            file_handle = None
            raise C.WinError(C.get_last_error())
        _verify_acl(file_handle, {sid})
        data = json.dumps(dict(api_key=api_key), ensure_ascii=False).encode('utf-8')
        written = W.DWORD()
        winjob._check(api.WriteFile(file_handle, data, len(data), C.byref(written), None))
        if written.value != len(data):
            raise OSError('credential_write_incomplete')
        return path
    finally:
        for handle in (file_handle, directory_handle):
            if handle:
                api.CloseHandle(handle)
        descriptor.close()


def _encode(value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if not isinstance(value, dict) or not 0 < len(data) <= MAX_MESSAGE:
        raise ValueError('message_size_invalid')
    return struct.pack('<I', len(data))+data


def _decode(data):
    if not 0 < len(data) <= MAX_MESSAGE:
        raise ValueError('message_size_invalid')
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate_field')
                result[key] = value
            return result
        def finite(value):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError('nonfinite_number')
            return number
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique, parse_float=finite,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('message_malformed') from None
    if not isinstance(value, dict):
        raise ValueError('message_not_object')
    return value


class _Operation:
    """Buffer, event and OVERLAPPED remain owned until terminal completion."""
    def __init__(self, handle, kind, value=0):
        self.api, self.handle, self.kind = _api(), handle, kind
        self.buffer = C.create_string_buffer(value if kind == 'write' else max(1, value))
        self.overlapped = _Overlapped()
        self.overlapped.event = winjob._check(self.api.CreateEventW(None, True, False, None))
        self.terminal = False
        self.count = W.DWORD()
        if kind == 'connect':
            ok = self.api.ConnectNamedPipe(handle, C.byref(self.overlapped))
        else:
            fn = self.api.WriteFile if kind == 'write' else self.api.ReadFile
            ok = fn(handle, self.buffer, len(value) if kind == 'write' else value,
                    None, C.byref(self.overlapped))
        error = C.get_last_error()
        if not ok and error not in (997, 535 if kind == 'connect' else 997):
            self.api.CloseHandle(self.overlapped.event)
            self.overlapped.event = None
            raise OSError(error, 'pipe_io_failed')
        self.connected = kind == 'connect' and not ok and error == 535

    def poll(self):
        if self.connected:
            self.terminal = True
            return b''
        ok = self.api.GetOverlappedResult(self.handle, C.byref(self.overlapped), C.byref(self.count), False)
        if not ok:
            error = C.get_last_error()
            if error == 996:
                return None
            self.terminal = True
            raise OSError(error, 'pipe_io_failed')
        self.terminal = True
        return self.buffer.raw[:self.count.value]

    def cancel(self):
        if not self.terminal:
            self.api.CancelIoEx(self.handle, C.byref(self.overlapped))

    def close(self):
        if not self.terminal:
            raise RuntimeError('pending_io_retained')
        if self.overlapped.event:
            winjob._check(self.api.CloseHandle(self.overlapped.event))
            self.overlapped.event = None


class _Channel:
    def __init__(self, handle):
        self.handle, self.operation, self.peer = handle, None, None
        self.state, self.data, self.needed = '', b'', 0
        self.deadline = time.monotonic()+2
        self.challenge = secrets.token_hex(32)
        self.retained = False
        self.queued_send = None
        self.retirement_started = None

    def send(self, value, after):
        if self.operation is not None:
            if self.state != 'header' or self.data or self.queued_send:
                raise ValueError('unexpected_pending_message')
            self.queued_send = (value, after)
            self.operation.cancel()
            return
        self.data = _encode(value)
        self.state, self.after = 'write', after
        self.operation = _Operation(self.handle, 'write', self.data)

    def receive(self):
        self.state, self.data, self.needed = 'header', b'', 4
        self.operation = _Operation(self.handle, 'read', 4)

    def advance(self):
        if self.operation is None:
            return None
        if self.queued_send is not None:
            try:
                value = self.operation.poll()
                if value is None:
                    return None
                raise ValueError('premature_parent_message')
            except OSError as error:
                if error.errno != 995:
                    raise
            self.operation.close()
            self.operation = None
            value, after = self.queued_send
            self.queued_send = None
            self.send(value, after)
            return None
        value = self.operation.poll()
        if value is None:
            return None
        self.operation.close()
        self.operation = None
        if self.state == 'connect':
            return 'connected'
        if self.state == 'write':
            if not value:
                raise ValueError('pipe_disconnected')
            self.data = self.data[len(value):]
            if self.data:
                self.operation = _Operation(self.handle, 'write', self.data)
            else:
                self.state = self.after
                return 'sent'
            return None
        if not value:
            raise ValueError('pipe_disconnected')
        self.data += value
        if len(self.data) < self.needed:
            self.operation = _Operation(self.handle, 'read', self.needed-len(self.data))
            return None
        if self.state == 'header':
            self.needed = struct.unpack('<I', self.data)[0]
            if not 0 < self.needed <= MAX_MESSAGE:
                raise ValueError('message_size_invalid')
            self.data, self.state = b'', 'body'
            self.operation = _Operation(self.handle, 'read', self.needed)
            return None
        self.state = 'received'
        return _decode(self.data)

    def retire(self):
        if self.retirement_started is None:
            self.retirement_started = time.monotonic()
        if self.operation:
            self.operation.cancel()
            try:
                if self.operation.poll() is None:
                    return False
            except OSError:
                pass
            self.operation.close()
            self.operation = None
        if self.peer:
            self.peer.close()
            self.peer = None
        if self.handle:
            winjob._check(_api().CloseHandle(self.handle))
            self.handle = None
        return True


def _envelope(record, challenge, **body):
    return dict(schema_version=1, run_id=record['run_id'], profile_digest=record['profile_digest'],
                challenge=challenge, **body)


def _validate_envelope(value, record, challenge):
    if type(value.get('schema_version')) is not int or any(value.get(key) != wanted for key, wanted in (
            ('schema_version', 1), ('run_id', record['run_id']),
            ('profile_digest', record['profile_digest']), ('challenge', challenge))):
        raise ValueError('protocol_binding_mismatch')


class ControlServer:
    def __init__(self, run_id: str, guardian_identity: dict):
        if not isinstance(run_id, str) or not run_id or any(c not in '0123456789abcdef-' for c in run_id):
            raise ValueError('run_id_invalid')
        digest = guardian_identity.get('profile_digest', '')
        if len(digest) != 64 or any(c not in '0123456789abcdefABCDEF' for c in digest):
            raise ValueError('profile_digest_invalid')
        _match_identity(guardian_identity, _process_identity(os.getpid()))
        self.run_id, self._slots, self._retired = run_id, [], []
        self._closed, self._pipe_mode = False, 8  # byte mode, remote clients rejected
        self.record = dict(run_id=run_id, profile_digest=digest,
            endpoint='\\\\.\\pipe\\gufo-'+run_id, guardian=dict(guardian_identity))
        self._listen(first=True)

    def _listen(self, *, first=False):
        first = first or not (self._slots or self._retired)
        descriptor = _Descriptor(self.record['guardian']['user_sid'], pipe=True)
        try:
            handle = _api().CreateNamedPipeW(self.record['endpoint'], 3 | 0x40000000 | (0x80000 if first else 0),
                self._pipe_mode, 4, MAX_MESSAGE+4, MAX_MESSAGE+4, 0, C.byref(descriptor.attributes))
            if handle == _INVALID:
                raise C.WinError(C.get_last_error())
            slot = _Channel(handle)
            try:
                _verify_acl(handle, {self.record['guardian']['user_sid'], 'S-1-5-18'})
                if _inherited(handle):
                    raise ValueError('pipe_inheritable')
                slot.state = 'connect'
                slot.operation = _Operation(handle, 'connect')
                self._slots.append(slot)
            except BaseException:
                self._retired.append(slot)
                self.close()
                raise
        finally:
            descriptor.close()

    def _drop(self, slot):
        self._slots.remove(slot)
        self._retired.append(slot)

    def poll(self):
        events = []
        self._retired[:] = [slot for slot in self._retired if not slot.retire()]
        if any(time.monotonic()-slot.retirement_started > 2 for slot in self._retired):
            if self not in _RETAINED_CLEANUP:
                _RETAINED_CLEANUP.append(self)
            error = RuntimeError('pipe_cancellation_unconfirmed')
            error.owner = self
            raise error  # Existing guardian performs owned shutdown/recovery.
        for slot in list(self._slots):
            try:
                if slot.state != 'connect' and (not slot.retained and time.monotonic() > slot.deadline):
                    raise TimeoutError('client_timeout')
                value = slot.advance()
                if value == 'connected':
                    slot.deadline = time.monotonic()+2
                    pid = W.ULONG()
                    winjob._check(_api().GetNamedPipeClientProcessId(slot.handle, C.byref(pid)))
                    slot.peer = _Peer(pid.value)
                    if slot.peer.identity['user_sid'] != self.record['guardian']['user_sid']:
                        raise ValueError('client_user_mismatch')
                    slot.send(_envelope(self.record, slot.challenge, kind='challenge'), 'request')
                elif value == 'sent':
                    if slot.state in ('request', 'commit'):
                        slot.receive()
                    elif slot.state == 'close':
                        self._drop(slot)
                elif isinstance(value, dict):
                    _validate_envelope(value, self.record, slot.challenge)
                    _match_identity(value.get('client', {}), slot.peer.identity)
                    if not slot.peer.alive() or value.get('command') not in ('status', 'stop', 'handoff', 'commit'):
                        raise ValueError('request_invalid')
                    events.append(dict(channel=slot, command=value['command'], message=value,
                                       peer=dict(slot.peer.identity)))
            except (OSError, ValueError, TimeoutError):
                events.append(dict(channel=slot, command='disconnect'))
                self._drop(slot)
        if not self._closed and len(self._slots)+len(self._retired) < 4 and not any(s.state == 'connect' for s in self._slots):
            self._listen()
        return events

    def reply(self, event, value, *, retain=False):
        slot = event['channel']
        slot.retained = retain
        slot.send(_envelope(self.record, slot.challenge, **value), 'commit' if retain else 'close')

    def close(self):
        self._closed = True
        self._retired.extend(self._slots)
        self._slots = []
        deadline = time.monotonic()+2
        while self._retired:
            self._retired[:] = [s for s in self._retired if not s.retire()]
            if self._retired and time.monotonic() >= deadline:
                if self not in _RETAINED_CLEANUP:
                    _RETAINED_CLEANUP.append(self)
                error = RuntimeError('pending_io_retained')
                error.owner = self
                raise error
            if self._retired:
                time.sleep(.001)
        if self in _RETAINED_CLEANUP:
            _RETAINED_CLEANUP.remove(self)


def _wait_channel(channel, deadline):
    while time.monotonic() < deadline:
        value = channel.advance()
        if value is not None:
            return value
        time.sleep(.002)
    raise TimeoutError('control_timeout')


def _connect(record, deadline):
    expected = '\\\\.\\pipe\\gufo-'+record['run_id']
    if record.get('endpoint') != expected:
        raise ValueError('endpoint_invalid')
    while True:
        handle = _api().CreateFileW(expected, 0x12019b, 0, None, 3, 0x40000000 | 0x100000, None)
        if handle != _INVALID:
            break
        if time.monotonic() >= deadline:
            if channel not in _RETAINED_CLEANUP:
                _RETAINED_CLEANUP.append(channel)
            raise TimeoutError('control_connect_timeout')
        time.sleep(.005)
    channel = _Channel(handle)
    try:
        pid = W.ULONG()
        winjob._check(_api().GetNamedPipeServerProcessId(handle, C.byref(pid)))
        channel.peer = _Peer(pid.value)
        _match_identity(record['guardian'], channel.peer.identity)
        channel.receive()
        greeting = _wait_channel(channel, deadline)
        challenge = greeting.get('challenge')
        if not isinstance(challenge, str) or len(challenge) != 64 or greeting.get('kind') != 'challenge':
            raise ValueError('challenge_invalid')
        _validate_envelope(greeting, record, challenge)
        channel.challenge = challenge
        return channel
    except BaseException:
        _close_client(channel)
        raise


def _close_client(channel):
    deadline = time.monotonic()+2
    while not channel.retire():
        if time.monotonic() >= deadline:
            error = RuntimeError('pending_io_retained')
            error.owner = channel
            raise error
        time.sleep(.001)
    if channel in _RETAINED_CLEANUP:
        _RETAINED_CLEANUP.remove(channel)


def control_request(record: dict, command: str, *, timeout_seconds: float) -> dict:
    if command not in ('status', 'stop', 'handoff'):
        raise ValueError('command_invalid')
    if type(timeout_seconds) not in (float, int) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 600:
        raise ValueError('timeout_invalid')
    deadline = time.monotonic()+timeout_seconds
    channel = _connect(record, deadline)
    committed = False
    try:
        identity = _process_identity(os.getpid())
        channel.send(_envelope(record, channel.challenge, command=command, client=identity), 'request')
        _wait_channel(channel, deadline)
        channel.receive()
        response = _wait_channel(channel, deadline)
        _validate_envelope(response, record, channel.challenge)
        if command == 'handoff':
            if (response.get('state') != 'ready' or response.get('guardian') != record['guardian']
                    or response.get('child') != record.get('child') or response.get('run') != record.get('run')):
                raise ValueError('ready_identity_mismatch')
            channel.send(_envelope(record, channel.challenge, command='commit', client=identity), 'request')
            committed = True  # Sending may succeed even if its completion/ACK is lost.
            _wait_channel(channel, deadline)
            channel.receive()
            response = _wait_channel(channel, deadline)
            _validate_envelope(response, record, channel.challenge)
            if response.get('state') != 'committed':
                raise ValueError('commit_ack_invalid')
        return response
    except (OSError, ValueError, TimeoutError):
        if committed:
            return dict(state='indeterminate', run_id=record['run_id'], requires_status=True)
        raise
    finally:
        _close_client(channel)


def _validate_descriptor(descriptor):
    if set(descriptor) != {'parent', 'profile_digest', 'record_path'}:
        raise ValueError('bootstrap_fields_invalid')
    digest = descriptor['profile_digest']
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdefABCDEF' for c in digest):
        raise ValueError('profile_digest_invalid')
    path = Path(descriptor['record_path'])
    if not path.is_absolute() or path.name != 'endpoint.json' or path.exists():
        raise ValueError('bootstrap_record_path_invalid')
    _reject_reparse(path.parent)
    peer = _Peer(descriptor['parent']['pid'])
    try:
        _match_identity(descriptor['parent'], peer.identity)
        if peer.identity['user_sid'] != _process_identity(os.getpid())['user_sid']:
            raise ValueError('bootstrap_user_mismatch')
    except BaseException:
        peer.close()
        raise
    return peer


class _IpcLifecycle:
    """Five-method adapter; all post-start pipe work is nonblocking."""
    def __init__(self, descriptor, deadline_provider, *, profile_validator=None):
        self.parent = _validate_descriptor(descriptor)
        self.descriptor, self.deadline_provider = dict(descriptor), deadline_provider
        self.profile_validator = profile_validator
        self.server = self.parent_event = None
        self.record = self.run_dir = None
        self.status = dict(state='starting', api_key='[REDACTED]')
        self.secret, self.committed, self.stopping = '', False, False
        self.failed = False
        self.handoff_deadline = time.monotonic()+490

    def deadline(self, resumed_at):
        return self.deadline_provider(resumed_at)

    def on_started(self, run_dir, child_identity, api_key):
        from . import operator_store
        if self.profile_validator:
            self.profile_validator()
        self.run_dir, self.secret = Path(run_dir), api_key
        credentials = write_client_credentials(self.run_dir, api_key)
        identity = dict(_process_identity(os.getpid()), profile_digest=self.descriptor['profile_digest'])
        self.server = ControlServer(uuid.uuid4().hex, identity)
        self.record = dict(self.server.record, child=dict(child_identity), run=str(self.run_dir),
                           credentials=str(credentials), api_key='[REDACTED]')
        operator_store.atomic_json(self.run_dir/'control.json', self.record)
        operator_store.atomic_json(Path(self.descriptor['record_path']), self.record)
        until = time.monotonic()+10
        while self.parent_event is None:
            result = self.poll(time.monotonic())
            if result is not None or time.monotonic() >= until:
                raise ValueError('parent_handshake_failed')
            time.sleep(.002)

    def on_ready(self, snapshot):
        if self.parent_event is None or self.failed or self.stopping:
            raise ValueError('parent_handshake_failed')
        if snapshot.get('run') != str(self.run_dir) or snapshot.get('identity') != self.record['child']:
            raise ValueError('readiness_binding_mismatch')
        self.status.update(state='ready')
        self.server.reply(self.parent_event, dict(state='ready', guardian=self.record['guardian'],
            child=self.record['child'], run=self.record['run']), retain=True)

    def poll(self, now):
        from . import operator_store
        if not self.committed and (not self.parent.alive() or time.monotonic() > self.handoff_deadline):
            self.failed = True
        if self.server:
            for event in self.server.poll():
                command = event['command']
                original = self.parent_event and event['channel'] is self.parent_event['channel']
                if command == 'disconnect':
                    if original and not self.committed:
                        self.failed = True
                elif original and command in ('status', 'handoff') and not self.committed:
                    self.failed = True
                    self.server.reply(event, dict(state='refused'))
                elif command == 'handoff':
                    try:
                        _match_identity(self.descriptor['parent'], event['peer'])
                        if self.parent_event is not None or self.committed:
                            raise ValueError('handoff_already_started')
                        self.parent_event = event
                        event['channel'].retained = True
                        # Observe disconnect during startup with an outstanding read.
                        event['channel'].receive()
                    except ValueError:
                        self.server.reply(event, dict(state='refused'))
                elif command == 'commit':
                    if not original or self.status['state'] != 'ready' or self.committed or self.stopping or self.failed:
                        if original and not self.committed:
                            self.failed = True
                        self.server.reply(event, dict(state='refused'))
                        continue
                    operator_store.atomic_json(self.run_dir/'handoff.json', dict(self.record, state='committed'))
                    self.committed = True
                    self.status.update(state='running')
                    self.server.reply(event, dict(state='committed'))
                elif command == 'stop':
                    self.stopping = True
                    self.status.update(state='stopping')
                    self.server.reply(event, dict(state='stopping'))
                elif command == 'status':
                    self.server.reply(event, dict(self.status))
        if self.failed:
            return 'handoff_failed'
        if self.stopping:
            return 'stop'

    def on_result(self, result):
        from .smoke_guard import _redact
        self.status = _redact(dict(state='stopped', success=result.get('success', False),
            failure=result.get('failure'), run_id=self.record['run_id'] if self.record else None,
            api_key='[REDACTED]'), self.secret)

    def close(self):
        if self.server:
            self.server.close()
        self.parent.close()


def _run_guardian(guardian, descriptor):
    """Private bootstrap seam. Production guardian qualification stays in force."""
    from .service_lifecycle import _qualified_deadline
    from . import service_store
    def verify_profile():
        if service_store._digest(guardian.manifest['installed_profile']) != descriptor['profile_digest']:
            raise ValueError('bootstrap_profile_mismatch')
    lifecycle = _IpcLifecycle(descriptor,
        lambda resumed_at: _qualified_deadline(guardian.manifest, resumed_at), profile_validator=verify_profile)
    guardian.lifecycle = lifecycle
    try:
        return guardian.run()
    finally:
        lifecycle.close()


def _launch_hidden(descriptor_path):
    """Fixed future service entry point; no key, model or module override."""
    from .service_store import PROFILE_ID
    path = Path(descriptor_path)
    if not path.is_absolute() or path.name != 'bootstrap.json':
        raise ValueError('bootstrap_path_invalid')
    _reject_reparse(path)
    descriptor = _decode(path.read_bytes())
    peer = _validate_descriptor(descriptor)
    try:
        _match_identity(descriptor['parent'], _process_identity(os.getpid()))
    finally:
        peer.close()
    return subprocess.Popen([sys.executable, '-m', 'gufo_control.service', '_guardian',
        '--profile', PROFILE_ID, '--bootstrap', str(path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
