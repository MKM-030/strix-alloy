"""Bounded reads of atomically replaced Windows state; never renew a lease."""
import errno
import json
import os
from pathlib import Path
import time


def read_json(path, *, budget=1.0, clock=time.monotonic, sleep=time.sleep,
              load=None, windows=None):
    if not 0 <= budget <= 2.0:
        raise ValueError('State-read retry budget must be 0..2 seconds')
    if windows is None:
        windows = os.name == 'nt'
    if load is None:
        load = lambda: Path(path).read_text(encoding='utf-8-sig')
    deadline = clock() + budget
    while True:
        try:
            return json.loads(load())
        except OSError as exc:
            transient = windows and (getattr(exc, 'winerror', None) in (5, 32, 33)
                                     or exc.errno == errno.EACCES)
            remaining = deadline - clock()
            if not transient or remaining <= 0:
                raise
            sleep(min(0.025, remaining))
