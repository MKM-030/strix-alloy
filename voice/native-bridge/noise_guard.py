"""Speech qualification after native echo/noise suppression; no audio storage."""
import math


class SpeechNoiseGuard:
    """Require sustained, confident near-end speech before interrupting TTS.

    This does not remove acoustic noise. The native WebRTC path does that;
    this gate prevents residual noise from becoming an interruption/ASR turn.
    EndpointGate retains its existing preroll, so qualifying speech is retained.
    """
    def __init__(self):
        self.noise_rms = 30.0
        self.barge_ms = 0.0
        self.confident_ms = 0.0
        self.confident_gap_ms = 0.0

    def reset(self):
        self.barge_ms = 0.0
        self.confident_ms = 0.0
        self.confident_gap_ms = 0.0

    def qualify(self, probability, rms, milliseconds, *, speaking=False, utterance_active=False):
        if (type(probability) not in (int, float) or not math.isfinite(probability)
                or not 0 <= probability <= 1 or type(rms) not in (int, float)
                or not math.isfinite(rms) or rms < 0
                or type(milliseconds) not in (int, float)
                or not math.isfinite(milliseconds) or not 0 < milliseconds <= 1000):
            self.reset()
            return False
        if probability < .2 and not utterance_active:
            weight = min(.12, milliseconds / 1000)
            self.noise_rms += weight * (rms - self.noise_rms)
        if utterance_active:
            # Do not clip soft syllables after a genuine onset was admitted.
            self.reset()
            return probability >= .45
        if not speaking:
            self.reset()
            return probability >= .6
        confident = probability >= .85 and rms >= max(40.0, self.noise_rms * 1.6)
        self.barge_ms = self.barge_ms + milliseconds if confident else 0.0
        # Strong neural speech can be quieter than residual background energy.
        # Count only confident speech, retaining credit through phonetic gaps.
        if probability >= .95:
            self.confident_ms += milliseconds
            self.confident_gap_ms = 0.0
        else:
            self.confident_gap_ms += milliseconds
            if self.confident_gap_ms > 60.0:
                self.confident_ms = 0.0
        return (self.barge_ms >= 220.0 or
                self.confident_ms >= 240.0 and probability >= .45)


def accepted_transcript(data):
    """Keep original text; reject only an explicit all-nonspeech ASR result."""
    text = data.get('text') if isinstance(data, dict) else None
    if not isinstance(text, str) or len(text) > 4000:
        raise ValueError('Invalid transcription')
    segments = data.get('segments')
    if isinstance(segments, list) and 0 < len(segments) <= 256:
        def nonspeech(segment):
            if not isinstance(segment, dict):
                return False
            silence, likelihood = segment.get('no_speech_prob'), segment.get('avg_logprob')
            return (type(silence) in (int, float) and math.isfinite(silence)
                    and .6 <= silence <= 1 and type(likelihood) in (int, float)
                    and math.isfinite(likelihood) and -1000 <= likelihood < -1)
        if all(nonspeech(segment) for segment in segments):
            return ''
    return text.strip()
