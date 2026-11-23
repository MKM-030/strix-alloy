"""Observe one local NTFS file generation without reading its payload."""

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import struct
import subprocess
from typing import NamedTuple


GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
FILE_SHARE_DELETE = 0x4
OPEN_EXISTING = 3
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_TYPE_DISK = 1
FILE_BASIC_INFO = 0
FILE_ID_INFO = 18
VOLUME_NAME_GUID = 1
FSCTL_READ_FILE_USN_DATA = 0x000900EB
FSCTL_QUERY_USN_JOURNAL = 0x000900F4
JOURNAL_QUERY_FALLBACK = frozenset((1, 5, 50, 87))
INVALID_HANDLE = ctypes.c_void_p(-1).value
VOLUME_GUID = re.compile(
    r'\\\\\?\\Volume\{[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}\\', re.IGNORECASE
)


class NtfsGenerationUnavailable(RuntimeError):
    """The native witness cannot authorize reuse of a content-check receipt."""


class _BasicInfo(ctypes.Structure):
    _fields_ = [
        ('created', ctypes.c_int64), ('accessed', ctypes.c_int64),
        ('written', ctypes.c_int64), ('changed', ctypes.c_int64),
        ('attributes', ctypes.c_uint32),
    ]


class _FileIdInfo(ctypes.Structure):
    _fields_ = [('serial', ctypes.c_uint64), ('file_id', ctypes.c_ubyte * 16)]


class _Journal(NamedTuple):
    identifier: int
    first: int
    next: int
    lowest_valid: int


def _checked_path(path):
    raw = os.fspath(path)
    if not isinstance(raw, str):
        raise NtfsGenerationUnavailable('Expected a native Windows filename')
    value = PureWindowsPath(raw)
    if (not value.is_absolute() or not re.fullmatch(r'[a-zA-Z]:', value.drive)
            or len(value.parts) < 2 or str(value) != raw):
        raise NtfsGenerationUnavailable('Expected a canonical local Windows drive path')
    for name in value.parts[1:]:
        if (name.endswith(('.', ' ')) or any(ord(char) < 32 or char in '<>:"|?*' for char in name)
                or PureWindowsPath(name).is_reserved()):
            raise NtfsGenerationUnavailable('Ambiguous filename or alternate stream')
    return value


def _reject_reparse(path):
    for component in (*reversed(path.parents), path):
        try:
            info = os.lstat(component)
        except OSError as error:
            raise NtfsGenerationUnavailable('Could not inspect local Windows path') from error
        if stat.S_ISLNK(info.st_mode) or (
                getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise NtfsGenerationUnavailable('Native file path has a reparse point')


def _journal_range(identifier, first, next_usn, lowest_valid):
    if not (0 < identifier < 2**64
            and 0 <= first <= next_usn < 2**63 and 0 <= lowest_valid <= next_usn):
        raise NtfsGenerationUnavailable('Invalid USN journal range')
    return _Journal(identifier, first, next_usn, lowest_valid)


def _parse_journal(data):
    # USN_JOURNAL_DATA_V0 is the unchanged prefix of later returned structures.
    if len(data) < struct.calcsize('<QqqqqQQ'):
        raise NtfsGenerationUnavailable('Truncated USN journal response')
    return _journal_range(*struct.unpack_from('<Qqqq', data))


def _parse_fsutil(data):
    if len(data) > 16384:
        raise NtfsGenerationUnavailable('Oversized USN journal command output')
    values = []
    for label in (b'Usn Journal ID', b'First Usn', b'Next Usn', b'Lowest Valid Usn'):
        matches = re.findall(rb'(?m)^' + label + rb'[ \t]*:[ \t]*(0x[0-9a-fA-F]{1,16})[ \t\r]*$', data)
        if len(matches) != 1:
            raise NtfsGenerationUnavailable('Unsupported or ambiguous USN journal command output')
        values.append(int(matches[0], 16))
    return _journal_range(*values)


def _parse_file_usn(data, file_id):
    if len(data) < 8:
        raise NtfsGenerationUnavailable('Truncated file USN response')
    length, major, minor = struct.unpack_from('<IHH', data)
    if major == 2 and minor == 0:
        minimum, usn_offset, width = 60, 24, 8
    elif major == 3 and minor == 0:
        minimum, usn_offset, width = 76, 40, 16
    else:
        raise NtfsGenerationUnavailable('Unsupported file USN record version')
    if not minimum <= length <= len(data):
        raise NtfsGenerationUnavailable('Truncated file USN record')
    reference = data[8:8+width].ljust(16, b'\x00')
    last_usn, = struct.unpack_from('<q', data, usn_offset)
    if len(file_id) != 16 or reference != file_id or last_usn < 0:
        raise NtfsGenerationUnavailable('File USN record does not match the opened NTFS file')
    return last_usn, major


class _Win32:
    def __init__(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        w = wintypes
        for name, parameters, result in (
            ('CreateFileW', (w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE), w.HANDLE),
            ('CloseHandle', (w.HANDLE,), w.BOOL),
            ('GetFileType', (w.HANDLE,), w.DWORD),
            ('GetFileInformationByHandleEx', (w.HANDLE, w.INT, w.LPVOID, w.DWORD), w.BOOL),
            ('GetFileSizeEx', (w.HANDLE, ctypes.POINTER(ctypes.c_int64)), w.BOOL),
            ('GetFinalPathNameByHandleW', (w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD), w.DWORD),
            ('GetVolumeNameForVolumeMountPointW', (w.LPCWSTR, w.LPWSTR, w.DWORD), w.BOOL),
            ('GetVolumeInformationByHandleW', (w.HANDLE, w.LPWSTR, w.DWORD, w.LPVOID, w.LPVOID,
                                               w.LPVOID, w.LPWSTR, w.DWORD), w.BOOL),
            ('DeviceIoControl', (w.HANDLE, w.DWORD, w.LPVOID, w.DWORD, w.LPVOID, w.DWORD,
                                 ctypes.POINTER(w.DWORD), w.LPVOID), w.BOOL),
            ('GetSystemDirectoryW', (w.LPWSTR, w.UINT), w.UINT),
        ):
            function = getattr(kernel, name)
            function.argtypes = parameters
            function.restype = result
        self.kernel = kernel

    @staticmethod
    def check(ok, operation):
        if not ok:
            error = ctypes.WinError(ctypes.get_last_error())
            raise NtfsGenerationUnavailable(f'{operation} failed: {error}') from error

    @contextmanager
    def open_existing(self, path, access, share, flags=0):
        handle = self.kernel.CreateFileW(str(path), access, share, None, OPEN_EXISTING, flags, None)
        self.check(handle not in (None, INVALID_HANDLE), 'CreateFileW')
        try:
            yield handle
        finally:
            self.kernel.CloseHandle(handle)

    def volume_guid(self, anchor):
        buffer = ctypes.create_unicode_buffer(256)
        self.check(self.kernel.GetVolumeNameForVolumeMountPointW(anchor, buffer, len(buffer)),
                   'GetVolumeNameForVolumeMountPointW')
        if not VOLUME_GUID.fullmatch(buffer.value):
            raise NtfsGenerationUnavailable('Local drive has no canonical volume GUID')
        return buffer.value

    def require_canonical(self, handle, path, volume_guid):
        if self.kernel.GetFileType(handle) != FILE_TYPE_DISK:
            raise NtfsGenerationUnavailable('Opened object is not a local disk file')
        if self.volume_guid(path.anchor).casefold() != volume_guid.casefold():
            raise NtfsGenerationUnavailable('Drive now refers to another volume')
        buffer = ctypes.create_unicode_buffer(32768)
        count = self.kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), VOLUME_NAME_GUID)
        self.check(count, 'GetFinalPathNameByHandleW')
        relative = str(path)[len(path.anchor):]
        if (count >= len(buffer) or buffer.value[:len(volume_guid)].casefold() != volume_guid.casefold()
                or buffer.value[len(volume_guid):] != relative):
            raise NtfsGenerationUnavailable('Native file handle resolves through an alias')

    def require_ntfs(self, handle):
        filesystem = ctypes.create_unicode_buffer(32)
        self.check(self.kernel.GetVolumeInformationByHandleW(
            handle, None, 0, None, None, None, filesystem, len(filesystem)),
            'GetVolumeInformationByHandleW')
        if filesystem.value != 'NTFS':
            raise NtfsGenerationUnavailable('Local drive does not use NTFS')

    def metadata(self, handle):
        identity, basic, size = _FileIdInfo(), _BasicInfo(), ctypes.c_int64()
        for kind, value in ((FILE_ID_INFO, identity), (FILE_BASIC_INFO, basic)):
            self.check(self.kernel.GetFileInformationByHandleEx(
                handle, kind, ctypes.byref(value), ctypes.sizeof(value)), 'GetFileInformationByHandleEx')
        self.check(self.kernel.GetFileSizeEx(handle, ctypes.byref(size)), 'GetFileSizeEx')
        if basic.attributes & (stat.FILE_ATTRIBUTE_REPARSE_POINT | stat.FILE_ATTRIBUTE_DIRECTORY):
            raise NtfsGenerationUnavailable('Opened object is a directory or reparse point')
        file_id = bytes(identity.file_id)
        if not any(file_id) or min(basic.created, basic.written, basic.changed, size.value) < 0:
            raise NtfsGenerationUnavailable('Invalid native file generation fields')
        return {
            'volume_serial': identity.serial, 'file_id': file_id.hex(), 'eof': size.value,
            'created_100ns': basic.created, 'written_100ns': basic.written, 'changed_100ns': basic.changed,
        }

    def ioctl(self, handle, code, request=b''):
        incoming = ctypes.create_string_buffer(request) if request else None
        outgoing = ctypes.create_string_buffer(4096)
        returned = wintypes.DWORD()
        self.check(self.kernel.DeviceIoControl(handle, code, incoming, len(request), outgoing,
                                               len(outgoing), ctypes.byref(returned), None), 'DeviceIoControl')
        if returned.value > len(outgoing):
            raise NtfsGenerationUnavailable('Oversized USN control response')
        return outgoing.raw[:returned.value]

    def direct_journal(self, volume_guid):
        share = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
        with self.open_existing(volume_guid.rstrip('\\'), 0, share) as volume:
            return _parse_journal(self.ioctl(volume, FSCTL_QUERY_USN_JOURNAL))

    def system_journal(self, drive):
        directory = ctypes.create_unicode_buffer(32768)
        count = self.kernel.GetSystemDirectoryW(directory, len(directory))
        self.check(count, 'GetSystemDirectoryW')
        if count >= len(directory):
            raise NtfsGenerationUnavailable('Windows system directory could not be resolved')
        program = Path(directory.value) / 'fsutil.exe'
        _checked_path(program)
        _reject_reparse(program)
        try:
            done = subprocess.run(
                [str(program), 'usn', 'queryjournal', drive],
                check=True, capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise NtfsGenerationUnavailable('System USN journal query is unavailable') from error
        return _parse_fsutil(done.stdout)


class _NtfsReadLease:
    def __init__(self, api, handle, path, volume_guid):
        self._api = api
        self._handle = handle
        self._path = path
        self._volume_guid = volume_guid
        self._use_system_journal = False

    def _journal(self):
        if not self._use_system_journal:
            try:
                return self._api.direct_journal(self._volume_guid)
            except NtfsGenerationUnavailable as error:
                if getattr(error.__cause__, 'winerror', None) not in JOURNAL_QUERY_FALLBACK:
                    raise
                self._use_system_journal = True
        if self._api.volume_guid(self._path.anchor).casefold() != self._volume_guid.casefold():
            raise NtfsGenerationUnavailable('Drive changed before the system USN query')
        journal = self._api.system_journal(self._path.drive)
        if self._api.volume_guid(self._path.anchor).casefold() != self._volume_guid.casefold():
            raise NtfsGenerationUnavailable('Drive changed during the system USN query')
        return journal

    def _file_record(self):
        metadata = self._api.metadata(self._handle)
        file_id = bytes.fromhex(metadata['file_id'])
        raw = self._api.ioctl(self._handle, FSCTL_READ_FILE_USN_DATA, struct.pack('<HH', 2, 3))
        last_usn, version = _parse_file_usn(raw, file_id)
        return dict(metadata, file_usn=last_usn, record_version=version)

    def snapshot(self):
        """Return stable JSON-safe metadata from this exact read-leased handle."""
        if self._handle is None:
            raise NtfsGenerationUnavailable('NTFS read lease is already closed')
        self._api.require_canonical(self._handle, self._path, self._volume_guid)
        before = self._journal()
        first = self._file_record()
        last = self._file_record()
        after = self._journal()
        self._api.require_canonical(self._handle, self._path, self._volume_guid)
        if (first != last or before.identifier != after.identifier or before.next > after.next
                or not max(before.lowest_valid, after.lowest_valid) <= last['file_usn'] < after.next):
            raise NtfsGenerationUnavailable('NTFS file or journal generation changed during observation')
        return dict(last, volume_guid=self._volume_guid.casefold(), journal_id=after.identifier)


@contextmanager
def open_read_lease(path):
    """Hold a local NTFS file open for reads while denying write and delete sharing."""
    if os.name != 'nt':
        raise NtfsGenerationUnavailable('The NTFS file witness requires native Windows')
    named = _checked_path(path)
    _reject_reparse(named)
    try:
        api = _Win32()
    except (OSError, AttributeError) as error:
        raise NtfsGenerationUnavailable('Required Win32 file APIs are unavailable') from error
    volume_guid = api.volume_guid(named.anchor)
    with api.open_existing(named, GENERIC_READ, FILE_SHARE_READ, FILE_FLAG_OPEN_REPARSE_POINT) as handle:
        api.require_canonical(handle, named, volume_guid)
        api.require_ntfs(handle)
        lease = _NtfsReadLease(api, handle, named, volume_guid)
        try:
            yield lease
        finally:
            lease._handle = None
