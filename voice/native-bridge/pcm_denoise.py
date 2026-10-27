"""Streaming RNNoise for PCM16/mono/16k, before both VAD and ASR.

The pinned pyrnnoise wheel supplies its C library; importing its high-level
package is unnecessary. Each stream owns one RNNoise state and two resamplers.
RNNoise's 960-sample (20ms) lookahead is removed; internal drain padding is never
returned as caller audio. No audio IO, model request, or storage occurs here.
"""
import ctypes
from fractions import Fraction
from importlib.metadata import distribution

import av
import numpy as np

RATE = 16000
RN_RATE = 48000
RN_FRAME = 480
CHUNK_BYTES = 640
DELAY_SAMPLES = 320
MAX_PENDING_SAMPLES = 1600


class _RNNoise:
    def __init__(self):
        wheel = distribution('pyrnnoise')
        if wheel.version != '0.4.5':
            raise RuntimeError('Unverified RNNoise wheel version')
        self._lib = ctypes.CDLL(str(wheel.locate_file('pyrnnoise/rnnoise.dll')))
        self._lib.rnnoise_create.argtypes = [ctypes.c_void_p]
        self._lib.rnnoise_create.restype = ctypes.c_void_p
        self._lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        self._lib.rnnoise_destroy.restype = None
        self._lib.rnnoise_get_frame_size.argtypes = []
        self._lib.rnnoise_get_frame_size.restype = ctypes.c_int
        self._lib.rnnoise_process_frame.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float)]
        self._lib.rnnoise_process_frame.restype = ctypes.c_float
        self._state = None
        if self._lib.rnnoise_get_frame_size() != RN_FRAME:
            raise RuntimeError('Unexpected RNNoise frame size')
        self._state = self._lib.rnnoise_create(None)
        if not self._state:
            raise RuntimeError('RNNoise state unavailable')

    def process(self, frame):
        data = np.ascontiguousarray(frame, dtype=np.float32)
        if len(data) != RN_FRAME or not np.isfinite(data).all():
            raise ValueError('Unexpected RNNoise input frame')
        pointer = data.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        # The returned speech probability is deliberately not used as a VAD.
        self._lib.rnnoise_process_frame(self._state, pointer, pointer)
        if not np.isfinite(data).all():
            raise ValueError('Invalid RNNoise output')
        return data

    def close(self):
        if self._state:
            self._lib.rnnoise_destroy(self._state)
            self._state = None


def _make_backend():
    return _RNNoise()


class StreamingPCM16Denoiser:
    """feed/finish return <=20ms chunks; any failure preserves raw FIFO.

    finish drains every real input sample, then closes; it is idempotent.
    close alone is cancellation cleanup and intentionally emits nothing.
    """
    def __init__(self):
        self._backend = self._up = self._down = None
        self._raw, self._clean, self._work = bytearray(), bytearray(), bytearray()
        self._skip = DELAY_SAMPLES * 2
        self._pushed = self._processed = 0
        self.input_samples = self.output_samples = self.max_pending_samples = 0
        self.fallback_reason = None
        self._closed = False
        try:
            self._backend = _make_backend()
            self._up = av.AudioResampler(format='fltp', layout='mono', rate=RN_RATE)
            self._down = av.AudioResampler(format='s16', layout='mono', rate=RATE)
        except Exception:
            self._release()
            self.fallback_reason = 'unavailable'

    @property
    def active(self):
        return self._backend is not None

    @property
    def pending_samples(self):
        return len(self._raw) // 2

    def _release(self):
        backend, self._backend = self._backend, None
        self._up = self._down = None
        if backend is not None:
            backend.close()

    def _chunks(self, pcm):
        result = tuple(bytes(pcm[pos:pos+CHUNK_BYTES]) for pos in range(0, len(pcm), CHUNK_BYTES))
        self.output_samples += len(pcm) // 2
        return result

    def _commit(self, final=False):
        result = []
        while len(self._clean) >= CHUNK_BYTES or final and self._clean:
            size = min(CHUNK_BYTES, len(self._clean))
            result.append(bytes(self._clean[:size]))
            del self._clean[:size]
            del self._raw[:size]
            self.output_samples += size // 2
        return result

    def _fallback(self, reason):
        self.fallback_reason = reason
        self._release()
        self._clean.clear()
        self._work.clear()
        result = self._chunks(self._raw)
        self._raw.clear()
        return result

    def _accept(self, frame, final):
        if frame.format.name != 's16' or frame.layout.name != 'mono' or frame.sample_rate != RATE:
            raise ValueError('Unexpected denoiser PCM format')
        pcm = frame.to_ndarray().tobytes()
        skip = min(self._skip, len(pcm))
        self._skip -= skip
        pcm = pcm[skip:]
        remaining = len(self._raw) - len(self._clean)
        if len(pcm) > remaining and not final:
            raise ValueError('Denoiser produced unbound samples')
        self._clean.extend(pcm[:remaining])

    def _process_frames(self, final=False):
        while len(self._work) >= RN_FRAME * 4:
            data = np.frombuffer(bytes(self._work[:RN_FRAME*4]), dtype=np.float32).copy()
            del self._work[:RN_FRAME*4]
            cleaned = self._backend.process(data)
            frame = av.AudioFrame.from_ndarray((cleaned / 32768).reshape(1, -1),
                                               format='fltp', layout='mono')
            frame.sample_rate, frame.time_base, frame.pts = RN_RATE, Fraction(1, RN_RATE), self._processed
            self._processed += RN_FRAME
            for output in self._down.resample(frame):
                self._accept(output, final)

    def _upsampled(self, frames):
        for frame in frames:
            self._work.extend((frame.to_ndarray().reshape(-1) * 32768).astype(np.float32).tobytes())

    def _push(self, pcm):
        frame = av.AudioFrame.from_ndarray(np.frombuffer(pcm, dtype='<i2').reshape(1, -1),
                                           format='s16', layout='mono')
        frame.sample_rate, frame.time_base, frame.pts = RATE, Fraction(1, RATE), self._pushed
        self._pushed += frame.samples
        self._upsampled(self._up.resample(frame))
        self._process_frames()

    def feed(self, pcm):
        if self._closed:
            raise ValueError('Denoiser is closed')
        if not isinstance(pcm, (bytes, bytearray)) or len(pcm) % 2:
            raise ValueError('Expected PCM16 mono bytes')
        self.input_samples += len(pcm)//2
        if not self.active:
            return self._chunks(pcm)
        output = []
        for pos in range(0, len(pcm), CHUNK_BYTES):
            part = pcm[pos:pos+CHUNK_BYTES]
            if len(self._raw) + len(part) > MAX_PENDING_SAMPLES * 2:
                output.extend(self._fallback('buffer_limit'))
                output.extend(self._chunks(pcm[pos:]))
                break
            self._raw.extend(part)
            self.max_pending_samples = max(self.max_pending_samples, self.pending_samples)
            try:
                self._push(part)
                output.extend(self._commit(final=True))
            except Exception:
                output.extend(self._fallback('runtime_error'))
                output.extend(self._chunks(pcm[pos+len(part):]))
                break
        return tuple(output)

    def finish(self):
        if self._closed:
            return ()
        output = []
        if self.active and self._raw:
            try:
                self._upsampled(self._up.resample(None))
                # Pad the final partial 10ms frame, then drain both delayed frames.
                missing = (-len(self._work)) % (RN_FRAME * 4)
                self._work.extend(bytes(missing + RN_FRAME * 4 * 2))
                self._process_frames(final=True)
                for frame in self._down.resample(None):
                    self._accept(frame, final=True)
                output.extend(self._commit(final=True))
                if self._raw:
                    output.extend(self._fallback('short_output'))
            except Exception:
                output.extend(self._fallback('runtime_error'))
        self.close()
        return tuple(output)

    def close(self):
        self._closed = True
        self._release()
        self._raw.clear()
        self._clean.clear()
        self._work.clear()
