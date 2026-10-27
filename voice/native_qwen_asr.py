"""Pinned local Qwen0.6 GGUF execution through CrispASR's batch C ABI.

The starter must qualify and pin the DLL, dependencies and converted model
before selecting this executor. This module never selects or downloads models.
"""
import ctypes
import math
import os
from pathlib import Path
import threading


class OpenParamsV2(ctypes.Structure):
    # crispasr_open_params_v1, aac7798 src/crispasr_c_api.cpp:4564.
    _fields_ = [(name, ctypes.c_int) for name in (
        "abi_version", "n_threads", "use_gpu", "verbosity", "flash_attn", "n_gpu_layers")]
    _fields_.append(("reserved", ctypes.c_int * 6))


class NativeQwenASR:
    model_id = "Qwen/Qwen3-ASR-0.6B"
    runtime = "crispasr"
    dtype = "mixed-gguf"
    voice_name = None

    def __init__(self, model_file, library_file, threads=6):
        self._lock = threading.RLock()
        self._session = self._dll_directory = None
        model, library = Path(model_file), Path(library_file)
        if (not model.is_absolute() or not library.is_absolute()
                or not model.is_file() or not library.is_file()):
            raise ValueError("Native ASR requires qualified absolute local model and DLL paths")
        if type(threads) is not int or not 1 <= threads <= 8:
            raise ValueError("Native ASR requires 1 to 8 CPU threads")
        try:
            self._configure_worker_chunking()
            if os.name == "nt":
                self._dll_directory = os.add_dll_directory(str(library.parent))
            self._dll = ctypes.CDLL(str(library))
            self._bind()
            parameters = OpenParamsV2(2, threads, 0, 0, 0, 0)
            self._session = self._dll.crispasr_session_open_with_params(
                os.fsencode(model), b"qwen3", ctypes.byref(parameters))
            if not self._session:
                raise RuntimeError("Native Qwen ASR could not load the qualified model")
            if self._dll.crispasr_session_backend(self._session) != b"qwen3":
                raise RuntimeError("Native ASR loaded an unexpected backend")
            if self._dll.crispasr_session_set_max_new_tokens(self._session, 256) != 0:
                raise RuntimeError("Native ASR rejected the 256-token output bound")
        except BaseException:
            self.close()
            raise

    def _configure_worker_chunking(self):
        # This dedicated worker already rejects audio over 60 seconds. Keep
        # the original single 256-token budget instead of the upstream 30s split.
        options = {"CRISPASR_SESSION_CHUNK_SECONDS": "60", "CRISPASR_SESSION_AUTOCHUNK": "1"}
        os.environ.update(options)
        if os.name == "nt":
            # The qualified MSVC DLL uses dynamic UCRT. Set its narrow getenv
            # view explicitly as well as Python's process environment.
            self._crt = ctypes.CDLL("ucrtbase.dll")
            putenv, getenv = self._crt._putenv_s, self._crt.getenv
            putenv.argtypes, putenv.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
            getenv.argtypes, getenv.restype = [ctypes.c_char_p], ctypes.c_char_p
            for name, value in options.items():
                key, encoded = name.encode("ascii"), value.encode("ascii")
                if putenv(key, encoded) != 0 or getenv(key) != encoded:
                    raise RuntimeError("Native ASR could not pin its 60-second process environment")

    def _bind(self):
        pointer = ctypes.c_void_p
        definitions = {
            "open_with_params": ([ctypes.c_char_p, ctypes.c_char_p, ctypes.POINTER(OpenParamsV2)], pointer),
            "backend": ([pointer], ctypes.c_char_p),
            "set_max_new_tokens": ([pointer, ctypes.c_int], ctypes.c_int),
            "transcribe_lang": ([pointer, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_char_p], pointer),
            "result_n_segments": ([pointer], ctypes.c_int),
            "result_segment_text": ([pointer, ctypes.c_int], ctypes.c_char_p),
            "result_free": ([pointer], None),
            "close": ([pointer], None),
        }
        for name, (arguments, result) in definitions.items():
            function = getattr(self._dll, "crispasr_session_" + name)
            function.argtypes, function.restype = arguments, result

    def transcribe(self, audio, sample_rate, language):
        import numpy as np
        languages = {"German": b"de", "English": b"en", None: b"auto",
                     "de": b"de", "en": b"en", "auto": b"auto"}
        if language not in languages:
            raise ValueError("Native ASR language must be German, English, or auto")
        if type(sample_rate) is not int or not 8000 <= sample_rate <= 192000:
            raise ValueError("Invalid native ASR sample rate")
        samples = np.asarray(audio, dtype=np.float32)
        if (samples.ndim != 1 or not 0 < samples.size <= sample_rate * 60
                or not np.isfinite(samples).all()):
            raise ValueError("Native ASR requires finite mono audio of at most 60 seconds")
        if sample_rate != 16000:
            from scipy.signal import resample_poly
            divisor = math.gcd(sample_rate, 16000)
            samples = resample_poly(samples, 16000 // divisor, sample_rate // divisor)
        samples = np.ascontiguousarray(samples, dtype=np.float32)
        with self._lock:
            if not self._session:
                raise RuntimeError("Native ASR executor is closed")
            result = self._dll.crispasr_session_transcribe_lang(
                self._session, samples.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                samples.size, languages[language])
            if not result:
                raise RuntimeError("Native Qwen ASR transcription failed")
            try:
                count = self._dll.crispasr_session_result_n_segments(result)
                if not 0 <= count <= 4096:
                    raise RuntimeError("Native ASR returned an invalid segment count")
                text = []
                for index in range(count):
                    segment = self._dll.crispasr_session_result_segment_text(result, index)
                    if segment is None:
                        raise RuntimeError("Native ASR returned an invalid text segment")
                    # c_char_p copies each borrowed C string before result_free.
                    text.append(segment.decode("utf-8", errors="strict"))
                # Batch chunks are independent trimmed spans, not token deltas.
                return " ".join(part.strip() for part in text if part.strip())
            finally:
                self._dll.crispasr_session_result_free(result)

    def close(self):
        with self._lock:
            session, self._session = self._session, None
            try:
                if session:
                    self._dll.crispasr_session_close(session)
            finally:
                directory, self._dll_directory = self._dll_directory, None
                if directory is not None:
                    directory.close()
