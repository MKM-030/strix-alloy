"""Offline ABI and HTTP behavior; the DLL boundary never loads real weights."""
import ctypes
import importlib
import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

def repository_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "voice/native_qwen_asr.py").is_file() and (parent / "voice/native-start/start_current_voice.py").is_file():
            return parent
    raise RuntimeError("Cannot find the repository Voice sources")

sys.path.insert(0, str(repository_root() / "voice"))
import audio_service as service


class Function:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


class FakeCRT:
    def __init__(self):
        self.environment = {b"CRISPASR_SESSION_CHUNK_SECONDS": b"5",
                            b"CRISPASR_SESSION_AUTOCHUNK": b"0"}
        self.error = 0
        self._putenv_s = Function(self.putenv)
        self.getenv = Function(lambda name: self.environment.get(name))

    def putenv(self, name, value):
        if not self.error:
            self.environment[name] = value
        return self.error


def install_dll_boundary(monkeypatch, dll):
    import os
    crt = FakeCRT()
    loads = []
    def load(path):
        loads.append(path)
        if path == "ucrtbase.dll":
            return crt
        dll.load_environment = {key: os.environ.get(key) for key in (
            "CRISPASR_SESSION_CHUNK_SECONDS", "CRISPASR_SESSION_AUTOCHUNK")}
        dll.crt_load_environment = dict(crt.environment)
        return dll
    monkeypatch.setattr(ctypes, "CDLL", load)
    return crt, loads


class FakeDLL:
    def __init__(self):
        self.events = []
        self.segments = [b"Marcel", "KÃ¤fke".encode()]
        self.result = 202
        self.open_result = 101
        self.setter_result = 0
        self.backend = b"qwen3"
        self.entered = self.release = None
        for name in ("open_with_params", "backend", "set_max_new_tokens", "transcribe_lang",
                     "result_n_segments", "result_segment_text", "result_free", "close"):
            setattr(self, "crispasr_session_" + name, Function(getattr(self, "_" + name)))

    def _open_with_params(self, model, backend, parameters):
        values = list(ctypes.cast(parameters, ctypes.POINTER(ctypes.c_int * 12)).contents)
        assert backend == b"qwen3"
        assert values == [2, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.events.append(("open", model))
        return self.open_result

    def _backend(self, session):
        assert session == 101
        return self.backend

    def _set_max_new_tokens(self, session, limit):
        assert (session, limit) == (101, 256)
        self.events.append(("limit", limit))
        return self.setter_result

    def _transcribe_lang(self, session, pointer, count, language):
        assert session == 101
        self.received = np.ctypeslib.as_array(pointer, shape=(count,)).copy()
        self.events.append(("transcribe", count, language))
        if self.entered:
            self.entered.set()
            assert self.release.wait(5)
        return self.result

    def _result_n_segments(self, result):
        assert result == 202
        return len(self.segments)

    def _result_segment_text(self, result, index):
        assert result == 202
        return self.segments[index]

    def _result_free(self, result):
        assert result == 202
        self.events.append(("result_free", result))
        self.segments = [b"borrowed memory invalidated"]

    def _close(self, session):
        assert session == 101
        self.events.append(("close", session))


@pytest.fixture
def executor_module():
    assert importlib.util.find_spec("native_qwen_asr") is not None, "Native executor is not implemented"
    return importlib.import_module("native_qwen_asr")


@pytest.fixture
def native(monkeypatch, tmp_path, executor_module):
    library, model = tmp_path / "crispasr.dll", tmp_path / "qwen06-q4.gguf"
    library.write_bytes(b"fake ABI boundary")
    model.write_bytes(b"fake local model, never loaded")
    dll = FakeDLL()
    install_dll_boundary(monkeypatch, dll)
    backend = executor_module.NativeQwenASR(model, library, 6)
    yield backend, dll, model, library
    backend.close()


def test_native_copies_utf8_result_and_frees_exactly_once(native):
    backend, dll, _, _ = native
    pcm = np.linspace(-.25, .25, 320000, dtype=np.float32)
    assert backend.transcribe(pcm, 16000, "German") == "Marcel KÃ¤fke"
    np.testing.assert_array_equal(dll.received, pcm)
    assert dll.events[-2:] == [("transcribe", 320000, b"de"), ("result_free", 202)]
    backend.close()
    backend.close()
    assert dll.events.count(("close", 101)) == 1
    with pytest.raises(RuntimeError, match="closed"):
        backend.transcribe(pcm, 16000, "German")


def test_native_declares_exact_c_abi(native):
    backend, dll, _, _ = native
    assert dll.crispasr_session_open_with_params.restype is ctypes.c_void_p
    assert dll.crispasr_session_transcribe_lang.argtypes == [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_char_p]
    assert dll.crispasr_session_result_segment_text.restype is ctypes.c_char_p
    assert dll.crispasr_session_result_free.restype is None
    assert backend.runtime == "crispasr" and backend.dtype == "mixed-gguf"


def test_worker_pins_60_second_window_before_dll_load_in_both_environments(
        monkeypatch, tmp_path, executor_module):
    monkeypatch.setenv("CRISPASR_SESSION_CHUNK_SECONDS", "5")
    monkeypatch.setenv("CRISPASR_SESSION_AUTOCHUNK", "0")
    dll = FakeDLL()
    crt, loads = install_dll_boundary(monkeypatch, dll)
    model, library = tmp_path / "qwen.gguf", tmp_path / "crispasr.dll"
    model.touch()
    library.touch()
    backend = executor_module.NativeQwenASR(model, library, 6)
    try:
        assert dll.load_environment == {
            "CRISPASR_SESSION_CHUNK_SECONDS": "60", "CRISPASR_SESSION_AUTOCHUNK": "1"}
        assert dll.crt_load_environment == {
            b"CRISPASR_SESSION_CHUNK_SECONDS": b"60", b"CRISPASR_SESSION_AUTOCHUNK": b"1"}
        assert loads == ["ucrtbase.dll", str(library)]
    finally:
        backend.close()


def test_worker_rejects_crt_environment_failure_before_model_dll(
        monkeypatch, tmp_path, executor_module):
    crt, loads = install_dll_boundary(monkeypatch, FakeDLL())
    crt.error = 22
    model, library = tmp_path / "qwen.gguf", tmp_path / "crispasr.dll"
    model.touch()
    library.touch()
    with pytest.raises(RuntimeError, match="environment"):
        executor_module.NativeQwenASR(model, library, 6)
    assert loads == ["ucrtbase.dll"]


@pytest.mark.parametrize("segments,expected", [
    (["Guten Morgen", "Marcel KÃ¤fke"], "Guten Morgen Marcel KÃ¤fke"),
    ([" Guten Morgen ", " Marcel  KÃ¤fke "], "Guten Morgen Marcel  KÃ¤fke"),
    (["", "  ", "M A  R C E L", "", "K Ã„ F K E"], "M A  R C E L K Ã„ F K E"),
    (["", " \t "], ""),
])
def test_independent_trimmed_segments_keep_word_and_spelling_boundaries(native, segments, expected):
    backend, dll, _, _ = native
    dll.segments = [text.encode("utf-8") for text in segments]
    assert backend.transcribe(np.zeros(1600, np.float32), 16000, "German") == expected
    assert dll.events[-1] == ("result_free", 202)


@pytest.mark.parametrize("rate,count,want", [(8000, 480000, 960000), (48000, 960000, 320000)])
def test_resampling_keeps_complete_60_or_20_second_audio(native, rate, count, want):
    backend, dll, _, _ = native
    pcm = np.zeros(count, dtype=np.float32)
    pcm[:100] = .2
    pcm[-100:] = -.2
    backend.transcribe(pcm, rate, "English")
    assert dll.received.shape == (want,)
    assert np.any(dll.received[:200] > .05)
    assert np.any(dll.received[-200:] < -.05)
    assert dll.events[-2] == ("transcribe", want, b"en")


def test_auto_language_is_passed_to_the_existing_native_session(native):
    backend, dll, _, _ = native
    assert backend.transcribe(np.zeros(1600, np.float32), 16000, None) == "Marcel KÃ¤fke"
    assert dll.events[-2] == ("transcribe", 1600, b"auto")


def test_native_result_cleanup_on_bad_utf8_and_null_result(native):
    backend, dll, _, _ = native
    dll.segments = [b"\xff"]
    with pytest.raises(UnicodeDecodeError):
        backend.transcribe(np.zeros(1600, np.float32), 16000, "German")
    assert dll.events[-1] == ("result_free", 202)
    dll.result = None
    with pytest.raises(RuntimeError):
        backend.transcribe(np.zeros(1600, np.float32), 16000, "German")
    assert dll.events.count(("result_free", 202)) == 1


@pytest.mark.parametrize("failure", ["load", "backend", "limit"])
def test_initialization_failure_closes_only_created_session(monkeypatch, tmp_path, executor_module, failure):
    dll = FakeDLL()
    if failure == "load":
        dll.open_result = None
    elif failure == "backend":
        dll.backend = b"whisper"
    else:
        dll.setter_result = -1
    library, model = tmp_path / "crispasr.dll", tmp_path / "qwen.gguf"
    library.touch()
    model.touch()
    install_dll_boundary(monkeypatch, dll)
    with pytest.raises(RuntimeError):
        executor_module.NativeQwenASR(model, library, 6)
    assert dll.events.count(("close", 101)) == (0 if failure == "load" else 1)


def wav(seconds=.1, rate=16000):
    output = io.BytesIO()
    sf.write(output, np.zeros(int(rate * seconds), np.float32), rate, format="WAV", subtype="PCM_16")
    return output.getvalue()


AUTH = {"Authorization": "Bearer test-secret"}
DATA = {"model": "qwen3-asr-0.6b", "language": "de", "response_format": "json"}


def send(client, audio):
    return client.post("/v1/audio/transcriptions", headers=AUTH, data=DATA,
                       files={"file": ("speech.wav", audio, "audio/wav")})


def test_http_native_health_auth_duration_and_request_reserve(native, monkeypatch):
    backend, dll, _, _ = native
    from types import SimpleNamespace
    import psutil
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=30 * 1024**3))
    with TestClient(service.create_app("asr", "test-secret", backend)) as client:
        assert client.get("/health").status_code == 401
        health = client.get("/health", headers=AUTH).json()
        assert health["runtime"] == "crispasr" and health["dtype"] == "mixed-gguf"
        assert health["model"] == "Qwen/Qwen3-ASR-0.6B" and health["device"] == "cpu"
        assert health["busy"] is False and health["max_parallel"] == 1
        assert send(client, wav(60.01)).status_code == 413
        assert not any(event[0] == "transcribe" for event in dll.events)
        monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=18 * 1024**3 - 1))
        assert send(client, wav()).status_code == 503
        assert not any(event[0] == "transcribe" for event in dll.events)


def test_http_native_rejects_overlap_without_second_dll_call(native, monkeypatch):
    backend, dll, _, _ = native
    monkeypatch.setattr(service, "ensure_memory_reserve", lambda: None)
    dll.entered, dll.release = threading.Event(), threading.Event()
    with TestClient(service.create_app("asr", "test-secret", backend)) as client, ThreadPoolExecutor(1) as pool:
        first = pool.submit(send, client, wav())
        assert dll.entered.wait(5)
        try:
            second = send(client, wav())
            assert second.status_code == 503 and second.headers["Retry-After"] == "1"
            assert client.get("/health", headers=AUTH).json()["busy"] is True
        finally:
            dll.release.set()
        assert first.result().json() == {"text": "Marcel KÃ¤fke"}
    assert len([event for event in dll.events if event[0] == "transcribe"]) == 1


def test_native_factory_never_imports_torch_and_closes_on_postload_reserve(native, monkeypatch):
    backend, dll, model, library = native
    factory = getattr(service, "create_backend", None)
    assert callable(factory), "Explicit native executor selection is missing"
    import builtins
    real_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        assert name.split(".")[0] not in {"torch", "transformers", "qwen_asr"}
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    checks = []
    def reserve():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("reserve")
    monkeypatch.setattr(service, "ensure_memory_reserve", reserve)
    with pytest.raises(RuntimeError, match="reserve"):
        factory("asr", 6, "mixed-gguf", None, "crispasr", model, library)
    assert checks == [True, True]
    assert dll.events.count(("close", 101)) == 1


def test_native_factory_rejects_missing_assets_and_tts_without_torch(monkeypatch):
    factory = getattr(service, "create_backend", None)
    assert callable(factory), "Explicit native executor selection is missing"
    monkeypatch.setattr(service, "ensure_memory_reserve", lambda: None)
    with pytest.raises(ValueError):
        factory("asr", 6, "float32", None, "crispasr", None, None)
    with pytest.raises(ValueError):
        factory("tts", 6, "mixed-gguf", None, "crispasr", None, None)


@pytest.mark.parametrize("audio,rate,language", [
    (np.zeros(1, np.float32), 16000, "French"),
    (np.zeros((2, 2), np.float32), 16000, "German"),
    (np.array([np.nan], np.float32), 16000, "German"),
    (np.zeros(0, np.float32), 16000, "German"),
    (np.zeros(960001, np.float32), 16000, "German"),
    (np.zeros(1, np.float32), 7999, "German"),
])
def test_invalid_native_audio_never_enters_dll(native, audio, rate, language):
    backend, dll, _, _ = native
    with pytest.raises(ValueError):
        backend.transcribe(audio, rate, language)
    assert not any(event[0] == "transcribe" for event in dll.events)


def test_reserve_failure_before_load_never_calls_dll(native, monkeypatch):
    _, dll, model, library = native
    opens = len(dll.events)
    def reject():
        raise RuntimeError("reserve")
    monkeypatch.setattr(service, "ensure_memory_reserve", reject)
    with pytest.raises(RuntimeError, match="reserve"):
        service.create_backend("asr", 6, "mixed-gguf", None, "crispasr", model, library)
    assert len(dll.events) == opens


def test_main_passes_explicit_native_selection_and_closes_on_server_error(tmp_path, monkeypatch):
    from types import SimpleNamespace
    token = tmp_path / "token.txt"
    token.write_text("test-secret")
    closed = []
    backend = SimpleNamespace(close=lambda: closed.append(True))
    def factory(mode, threads, dtype, voice, runtime, model, library):
        assert (mode, threads, dtype, voice, runtime, model, library) == (
            "asr", 6, "mixed-gguf", None, "crispasr", "qualified.gguf", "qualified.dll")
        return backend
    def run(app, **options):
        assert options["host"] == "127.0.0.1" and options["port"] == 8851
        raise RuntimeError("server ended")
    monkeypatch.setattr(service, "create_backend", factory, raising=False)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=run))
    monkeypatch.setattr(sys, "argv", ["audio_service.py", "--mode", "asr", "--asr-runtime", "crispasr",
        "--dtype", "mixed-gguf", "--asr-model", "qualified.gguf", "--asr-library", "qualified.dll",
        "--token-file", str(token)])
    with pytest.raises(RuntimeError, match="server ended"):
        service.main()
    assert closed == [True]
