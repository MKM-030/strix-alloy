"""Real local VAD regressions; public/synthetic fixtures only, no services."""
import ctypes
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import wave

import av
import numpy as np

try:
    from speech_activity import (SpeechActivityConfiguration,
        StreamingSpeechActivity, load_speech_activity_file)
except ModuleNotFoundError:
    SpeechActivityConfiguration = StreamingSpeechActivity = load_speech_activity_file = None

HERE = Path(__file__).resolve().parent
LIBRARY = Path(r'C:\AI\build\whisper.cpp\build\bin\whisper.dll')
MODEL = Path(r'C:\AI\build\whisper.cpp\models\for-tests-silero-v6.2.0-ggml.bin')
SPEECH = Path(r'C:\Projects\strix-alloy-scc-voice\voice\assets\scc-demo\reference.wav')
LIBRARY_SHA = 'a64bc7d6914a96694e3c1ffabb82c7551c4eedb331590044983bfe7b4c76fd8b'
MODEL_SHA = '2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987'


def profile(**changes):
    value = {'version':1, 'library_file':str(LIBRARY), 'library_sha256':LIBRARY_SHA,
             'model_file':str(MODEL), 'model_sha256':MODEL_SHA, 'threshold':.5}
    value.update(changes)
    return value


def fixture_pcm(gain=1):
    with wave.open(str(SPEECH),'rb') as wav:
        frame = av.AudioFrame.from_ndarray(np.frombuffer(wav.readframes(wav.getnframes()),dtype=np.int16).reshape(1,-1),format='s16',layout='mono')
        frame.sample_rate=wav.getframerate()
    converter=av.AudioResampler(format='s16',layout='mono',rate=16000)
    values=np.concatenate([f.to_ndarray().reshape(-1) for f in converter.resample(frame)+converter.resample(None)])
    return (values.astype(np.float32)*gain).astype(np.int16).tobytes()


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(load_speech_activity_file,'speech-aware input classifier is missing')
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'profile.json'

    def load(self,value):
        self.path.write_text(json.dumps(value),encoding='utf-8')
        return load_speech_activity_file(self.path)

    def test_default_configuration_cannot_construct_detector(self):
        configuration=SpeechActivityConfiguration()
        self.assertFalse(configuration.enabled)
        with self.assertRaises(ValueError): StreamingSpeechActivity(configuration)

    def test_valid_pinned_profile_is_immutable_and_repr_omits_paths(self):
        configuration=self.load(profile())
        self.assertTrue(configuration.enabled)
        self.assertNotIn(str(MODEL),repr(configuration))
        with self.assertRaises(FrozenInstanceError): configuration.threshold=.7

    def test_changed_pin_rejects_model_before_native_loading(self):
        for key in ('model_sha256','library_sha256'):
            with self.subTest(key=key),self.assertRaises(ValueError): self.load(profile(**{key:'0'*64}))

    def test_missing_or_changed_asset_rejected_without_sensitive_error(self):
        arbitrary=Path(self.temp.name)/'untrusted-private-token-file.bin'
        arbitrary.write_bytes(b'invalid neural model')
        for path in (arbitrary,arbitrary.with_name('missing-secret-file.bin')):
            with self.assertRaises(ValueError) as caught: self.load(profile(model_file=str(path)))
            self.assertNotIn('secret',str(caught.exception))
            self.assertNotIn('private',str(caught.exception))

    def test_valid_profile_cannot_authorize_model_changed_before_call(self):
        copy=Path(self.temp.name)/'copy.bin'
        copy.write_bytes(MODEL.read_bytes())
        configuration=self.load(profile(model_file=str(copy)))
        copy.write_bytes(b'changed after startup validation')
        with self.assertRaises(ValueError): StreamingSpeechActivity(configuration)

    def test_relative_asset_paths_are_resolved_from_profile_directory(self):
        relative=__import__('os').path.relpath(str(MODEL),str(self.path.parent))
        configuration=self.load(profile(model_file=relative))
        self.assertEqual(configuration.model_file,MODEL.resolve())

    def test_unc_or_url_asset_paths_are_rejected(self):
        for location in ('\\\\server\\share\\model.bin','https://example.com/model.bin','//server/share/model.bin'):
            with self.subTest(location=location),self.assertRaises(ValueError): self.load(profile(model_file=location))

    def test_strict_schema_rejects_extra_missing_and_invalid_fields(self):
        invalid=[]
        for key in profile():
            value=profile();del value[key];invalid.append(value)
        invalid += [profile(extra=True),profile(version=True),profile(version=2),profile(threshold=True),profile(threshold=.75),profile(model_file=''),profile(library_sha256=LIBRARY_SHA.upper()),[],None]
        for value in invalid:
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError): self.load(value)

    def test_oversized_duplicate_and_nonfinite_json_rejected(self):
        for value in (' '*9000, '{"version":1,"version":1}',json.dumps(profile()).replace('0.5','NaN')):
            self.path.write_text(value,encoding='utf-8')
            with self.assertRaises(ValueError): load_speech_activity_file(self.path)


class NativeDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if load_speech_activity_file is not None:
            cls.configuration=load_speech_activity_file(HERE/'speech-activity.profile.json')
            cls.speech=fixture_pcm()

    def setUp(self):
        self.assertIsNotNone(StreamingSpeechActivity,'speech-aware input classifier is missing')
        self.detector=StreamingSpeechActivity(self.configuration)
        self.addCleanup(self.detector.close)

    def feed_frames(self,pcm,size=640):
        return [self.detector.feed(pcm[i:i+size]) for i in range(0,len(pcm),size)]

    def test_steady_noise_and_hum_never_trigger_speech(self):
        rng=random.Random(20261023)
        signals=[np.asarray([rng.randint(-1200,1200) for _ in range(32000)],dtype=np.int16),np.asarray([int(1000*math.sin(2*math.pi*1000*i/16000)) for i in range(32000)],dtype=np.int16)]
        for signal in signals:
            self.detector.reset()
            self.assertFalse(any(self.feed_frames(signal.tobytes())))

    def test_100ms_noise_burst_does_not_cut_output(self):
        rng=random.Random(20261023)
        burst=np.asarray([rng.randint(-1200,1200) for _ in range(1600)],dtype=np.int16).tobytes()+bytes(64000)
        self.assertFalse(any(self.feed_frames(burst)))

    def test_real_german_speech_and_quiet_speech_are_accepted_promptly(self):
        for gain in (1,.1):
            self.detector.reset()
            flags=self.feed_frames(fixture_pcm(gain)[:640*25])
            first=next((i for i,x in enumerate(flags) if x),None)
            self.assertIsNotNone(first)
            self.assertLessEqual((first+1)*20,160)

    def test_reset_discards_carry_probability_and_previous_speech_state(self):
        self.assertTrue(any(self.feed_frames(self.speech[:32000])))
        self.detector.feed(b'\xff\x7f'*37)
        self.detector.reset()
        self.assertEqual(self.detector.probability,0)
        self.assertFalse(self.detector.feed(bytes(640)))
        self.assertFalse(any(self.feed_frames(bytes(64000))))

    def test_per_call_contexts_do_not_leak_speech_to_other_caller(self):
        other=StreamingSpeechActivity(self.configuration)
        self.addCleanup(other.close)
        for i in range(0,32000,640):
            self.detector.feed(self.speech[i:i+640])
            self.assertFalse(other.feed(bytes(640)))
        self.assertGreater(self.detector.probability,.5)
        self.assertLess(other.probability,.1)

    def test_partial_frames_keep_sample_order_and_same_final_probability(self):
        pcm=self.speech[:16384]
        self.feed_frames(pcm,640)
        expected=self.detector.probability
        self.detector.reset()
        self.feed_frames(pcm,74)
        self.assertAlmostEqual(self.detector.probability,expected,places=7)

    def test_invalid_input_cannot_be_loaded_or_corrupt_state(self):
        for invalid in (b'\x00',b'\x00'*32002,'private forbidden sample',None):
            with self.subTest(input_type=type(invalid).__name__),self.assertRaises(ValueError): self.detector.feed(invalid)
        self.assertFalse(self.detector.feed(bytes(1024)))

    def test_close_is_idempotent_and_blocks_future_native_calls(self):
        self.detector.close();self.detector.close()
        with self.assertRaises(ValueError): self.detector.feed(bytes(640))
        with self.assertRaises(ValueError): self.detector.reset()

    def test_native_failure_rejects_future_audio_without_energy_fallback(self):
        # A real native inference failure cannot be induced safely; only that
        # boundary is replaced. The detector cleanup and next feed remain real.
        with patch.object(self.detector._runtime.library,'whisper_vad_detect_speech_no_reset',side_effect=OSError('private-token-and-caller-data')):
            with self.assertRaises(ValueError) as caught: self.detector.feed(bytes(1024))
        self.assertNotIn('private',str(caught.exception))
        with self.assertRaises(ValueError): self.detector.feed(b'\xff\x7f'*320)

    def test_native_reset_failure_is_sanitized_and_closes_detector(self):
        with patch.object(self.detector._runtime.library,'whisper_vad_reset_state',side_effect=OSError('private-reset-data')):
            with self.assertRaises(ValueError) as caught: self.detector.reset()
        self.assertNotIn('private',str(caught.exception))
        with self.assertRaises(ValueError): self.detector.feed(bytes(640))


if __name__=='__main__': unittest.main()
