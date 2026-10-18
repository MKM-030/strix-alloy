"""Credential checks, speech endpoints and stale-audio fencing (no network)."""
from array import array
from collections import deque
import ipaddress
import math
import re
import secrets


def authorized_agents(data, required):
    if not isinstance(data, dict) or data.get('error'):
        return False
    result = data.get('result')
    return (isinstance(result, list) and bool(result) and
            all(isinstance(x, str) and re.fullmatch('[0-9a-f]{32}', x) for x in result)
            and required in result)


def local_auth(supplied, expected, remote):
    try:
        loopback = ipaddress.ip_address(remote).is_loopback
    except ValueError:
        return False
    return bool(loopback and len(expected) >= 32 and supplied and
                secrets.compare_digest(supplied, expected))


class PlaybackBuffer:
    def __init__(self):
        self.generation = 0
        self.data = bytearray()

    def interrupt(self):
        self.generation += 1
        self.data.clear()
        return self.generation

    def put(self, pcm, generation):
        if generation != self.generation:
            return False
        self.data.extend(pcm)
        return True

    def read(self, size):
        count = min(size, len(self.data)) // 2 * 2
        result = bytes(self.data[:count])
        del self.data[:count]
        return result + bytes(size - len(result))


class EndpointGate:
    """Bounded PCM16 energy VAD; browser acoustic echo cancellation is required.

    Samples must be mono and fed in roughly 20 ms frames. This intentionally
    simple detector has an adjustable floor for the demo microphone. It does
    not claim neural VAD or native Omni full-duplex inference.
    """
    def __init__(self, sample_rate=16000, threshold=450, onset_ms=100,
                 silence_ms=550, minimum_ms=120, maximum_ms=20000):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.onset = sample_rate * onset_ms // 1000
        self.silence = sample_rate * silence_ms // 1000
        self.minimum = sample_rate * minimum_ms // 1000
        self.maximum = sample_rate * maximum_ms // 1000
        self.preroll = deque(maxlen=15)
        self.active = False
        self.voiced = self.quiet = self.run = 0
        self.audio = bytearray()

    def feed(self, pcm):
        values = array('h', pcm)
        n = len(values)
        rms = math.sqrt(sum(x*x for x in values) / max(1, n))
        loud = rms >= self.threshold
        began = False
        if not self.active:
            self.preroll.append(pcm)
            self.run = self.run + n if loud else 0
            if self.run < self.onset:
                return False, None
            self.active = True
            began = True
            self.audio = bytearray(b''.join(self.preroll))
            self.voiced = self.run
            self.quiet = 0
            self.preroll.clear()
        else:
            self.audio.extend(pcm)
            if loud:
                self.voiced += n
                self.quiet = 0
            else:
                self.quiet += n
        if self.quiet >= self.silence or len(self.audio) // 2 >= self.maximum:
            return began, self.finish()
        return began, None

    def finish(self):
        """Finish once using only recorded PCM; no fabricated silence or speech.

        A transport may suppress quiet frames. Its wall-clock endpoint can use
        this same minimum-speech check without waiting for sample-count silence.
        """
        if not self.active:
            return None
        result = bytes(self.audio) if self.voiced >= self.minimum else None
        self.active = False
        self.audio.clear()
        self.voiced = self.quiet = self.run = 0
        self.preroll.clear()
        return result
