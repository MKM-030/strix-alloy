"""Pinned local Silero speech classification for 16 kHz mono PCM16.

Each detector owns its native recurrent state. Audio stays in a bounded RAM
carry buffer; this module performs no service calls or audio persistence.
"""
from array import array
import ctypes
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading


_LIBRARY_SHA256 = 'a64bc7d6914a96694e3c1ffabb82c7551c4eedb331590044983bfe7b4c76fd8b'
_MODEL_SHA256 = '2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987'
_PROFILE_LIMIT = 8192
_ASSET_LIMIT = 16 * 1024 * 1024
_WINDOW_SAMPLES = 512
_WINDOW_BYTES = _WINDOW_SAMPLES * 2
_MAX_PCM_BYTES = 32000
_RUNTIMES = {}
_RUNTIME_LOCK = threading.Lock()


@dataclass(frozen=True, repr=False)
class SpeechActivityConfiguration:
    library_file: Path | None = None
    library_sha256: str = ''
    model_file: Path | None = None
    model_sha256: str = ''
    threshold: float = .5
    sample_rate: int = 16000
    window_samples: int = _WINDOW_SAMPLES

    def __post_init__(self):
        if (type(self.threshold) not in (float, int) or self.threshold != .5
                or type(self.sample_rate) is not int or self.sample_rate != 16000
                or type(self.window_samples) is not int or self.window_samples != _WINDOW_SAMPLES):
            raise ValueError('Unsupported speech activity parameters')
        if self.library_file is None and self.model_file is None:
            if self.library_sha256 or self.model_sha256:
                raise ValueError('Incomplete speech activity configuration')
            return
        if (self.library_file is None or self.model_file is None
                or self.library_sha256 != _LIBRARY_SHA256
                or self.model_sha256 != _MODEL_SHA256):
            raise ValueError('Unapproved speech activity assets')
        object.__setattr__(self, 'library_file', _local_path(self.library_file))
        object.__setattr__(self, 'model_file', _local_path(self.model_file))

    @property
    def enabled(self):
        return self.library_file is not None and self.model_file is not None


def _local_path(value, base=None):
    if not isinstance(value, (str, Path)):
        raise ValueError('Invalid speech activity asset path')
    raw = str(value)
    if not raw or '\x00' in raw or '://' in raw or raw.startswith(('\\\\', '//')):
        raise ValueError('Invalid speech activity asset path')
    try:
        path = Path(raw)
        if not path.is_absolute():
            path = (base if base is not None else Path.cwd()) / path
        path = path.resolve()
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Invalid speech activity asset path')
        return path
    except (OSError, RuntimeError, ValueError):
        raise ValueError('Invalid speech activity asset path') from None


def _check_asset(path, expected):
    try:
        if not path.is_file() or not 1 <= path.stat().st_size <= _ASSET_LIMIT:
            raise ValueError('Invalid speech activity asset')
        digest = hashlib.sha256()
        with path.open('rb') as source:
            size = 0
            while block := source.read(65536):
                size += len(block)
                if size > _ASSET_LIMIT:
                    raise ValueError('Invalid speech activity asset')
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError('Speech activity asset verification failed')
    except (OSError, ValueError):
        raise ValueError('Speech activity asset verification failed') from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate speech activity field')
        result[key] = value
    return result


def load_speech_activity_file(path):
    """Load an explicit, bounded profile; absence never silently enables VAD."""
    try:
        path = _local_path(path)
        with path.open('rb') as source:
            raw = source.read(_PROFILE_LIMIT + 1)
        if len(raw) > _PROFILE_LIMIT:
            raise ValueError('Speech activity profile is oversized')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        keys = {'version', 'library_file', 'library_sha256', 'model_file', 'model_sha256', 'threshold'}
        if (type(value) is not dict or set(value) != keys
                or type(value['version']) is not int or value['version'] != 1
                or not isinstance(value['library_file'], str)
                or not isinstance(value['model_file'], str)
                or type(value['threshold']) not in (int, float) or value['threshold'] != .5):
            raise ValueError('Invalid speech activity profile')
        for key, approved in (('library_sha256', _LIBRARY_SHA256), ('model_sha256', _MODEL_SHA256)):
            if (not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{64}', value[key])
                    or value[key] != approved):
                raise ValueError('Unapproved speech activity assets')
        configuration = SpeechActivityConfiguration(
            library_file=_local_path(value['library_file'], path.parent),
            library_sha256=value['library_sha256'],
            model_file=_local_path(value['model_file'], path.parent),
            model_sha256=value['model_sha256'], threshold=value['threshold'])
        _check_asset(configuration.library_file, configuration.library_sha256)
        _check_asset(configuration.model_file, configuration.model_sha256)
        return configuration
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError):
        raise ValueError('Speech activity profile validation failed') from None


class _ContextParameters(ctypes.Structure):
    _fields_ = [('n_threads', ctypes.c_int), ('use_gpu', ctypes.c_bool), ('gpu_device', ctypes.c_int)]


class _Runtime:
    """Keep DLL search handle and quiet callback alive as long as native code."""
    def __init__(self, library_file):
        if os.name != 'nt' or ctypes.sizeof(_ContextParameters) != 12:
            raise ValueError('Unsupported speech activity runtime')
        self.directory = None
        try:
            self.directory = os.add_dll_directory(str(library_file.parent))
            self.library = ctypes.CDLL(str(library_file), winmode=0x00001100)
            callback_type = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
            self.log_callback = callback_type(lambda level, message, user: None)
            dll = self.library
            dll.whisper_log_set.argtypes = [callback_type, ctypes.c_void_p]
            dll.whisper_log_set.restype = None
            dll.whisper_vad_default_context_params.argtypes = []
            dll.whisper_vad_default_context_params.restype = _ContextParameters
            dll.whisper_vad_init_from_file_with_params.argtypes = [ctypes.c_char_p, _ContextParameters]
            dll.whisper_vad_init_from_file_with_params.restype = ctypes.c_void_p
            dll.whisper_vad_detect_speech_no_reset.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int]
            dll.whisper_vad_detect_speech_no_reset.restype = ctypes.c_bool
            dll.whisper_vad_reset_state.argtypes = [ctypes.c_void_p]
            dll.whisper_vad_reset_state.restype = None
            dll.whisper_vad_n_probs.argtypes = [ctypes.c_void_p]
            dll.whisper_vad_n_probs.restype = ctypes.c_int
            dll.whisper_vad_probs.argtypes = [ctypes.c_void_p]
            dll.whisper_vad_probs.restype = ctypes.POINTER(ctypes.c_float)
            dll.whisper_vad_free.argtypes = [ctypes.c_void_p]
            dll.whisper_vad_free.restype = None
            # Register only after the complete ABI is usable. A failed runtime
            # must never leave a native callback pointing at collected Python.
            dll.whisper_log_set(self.log_callback, None)
        except (OSError, AttributeError, TypeError, ValueError):
            if self.directory is not None:
                self.directory.close()
            raise ValueError('Speech activity runtime initialization failed') from None


def _get_runtime(configuration):
    key = (str(configuration.library_file), configuration.library_sha256)
    with _RUNTIME_LOCK:
        runtime = _RUNTIMES.get(key)
        if runtime is None:
            runtime = _Runtime(configuration.library_file)
            _RUNTIMES[key] = runtime
        return runtime


class StreamingSpeechActivity:
    """Classify bounded PCM chunks using a private, streaming native context."""
    def __init__(self, configuration):
        if not isinstance(configuration, SpeechActivityConfiguration) or not configuration.enabled:
            raise ValueError('Speech activity is not configured')
        # A previously loaded profile is not permission to load changed files.
        _check_asset(configuration.library_file, configuration.library_sha256)
        _check_asset(configuration.model_file, configuration.model_sha256)
        self.configuration = configuration
        self._runtime = _get_runtime(configuration)
        self._carry = bytearray()
        self._lock = threading.RLock()
        self._context = None
        self.probability = 0.0
        try:
            dll = self._runtime.library
            params = dll.whisper_vad_default_context_params()
            params.n_threads = 1
            params.use_gpu = False
            params.gpu_device = 0
            self._context = dll.whisper_vad_init_from_file_with_params(
                str(configuration.model_file).encode('utf-8'), params)
            if not self._context:
                raise ValueError('Speech activity model initialization failed')
            dll.whisper_vad_reset_state(self._context)
        except (OSError, AttributeError, TypeError, ValueError):
            self.close()
            raise ValueError('Speech activity model initialization failed') from None

    def feed(self, pcm):
        if not isinstance(pcm, (bytes, bytearray)) or len(pcm) % 2 or len(pcm) > _MAX_PCM_BYTES:
            raise ValueError('Invalid speech activity PCM')
        with self._lock:
            if self._context is None:
                raise ValueError('Speech activity detector is closed')
            if not pcm:
                return False
            self._carry.extend(pcm)
            dll = self._runtime.library
            try:
                while len(self._carry) >= _WINDOW_BYTES:
                    raw = bytes(self._carry[:_WINDOW_BYTES])
                    del self._carry[:_WINDOW_BYTES]
                    values = (ctypes.c_float * _WINDOW_SAMPLES)(*(x / 32768 for x in array('h', raw)))
                    if (not dll.whisper_vad_detect_speech_no_reset(self._context, values, _WINDOW_SAMPLES)
                            or dll.whisper_vad_n_probs(self._context) != 1):
                        raise ValueError('Speech activity inference failed')
                    probability = float(dll.whisper_vad_probs(self._context)[0])
                    if not math.isfinite(probability) or not 0 <= probability <= 1:
                        raise ValueError('Speech activity inference failed')
                    self.probability = probability
            except (OSError, AttributeError, TypeError, ValueError):
                self.close()
                raise ValueError('Speech activity inference failed') from None
            return self.probability >= self.configuration.threshold

    def reset(self):
        with self._lock:
            if self._context is None:
                raise ValueError('Speech activity detector is closed')
            try:
                self._runtime.library.whisper_vad_reset_state(self._context)
            except (OSError, AttributeError, TypeError, ValueError):
                self.close()
                raise ValueError('Speech activity reset failed') from None
            self._carry.clear()
            self.probability = 0.0

    def close(self):
        with self._lock:
            if self._context is not None:
                context, self._context = self._context, None
                self._runtime.library.whisper_vad_free(context)
            self._carry.clear()
            self.probability = 0.0
