"""Supervise one startup-only cache worker independently of HTTP readiness."""
import json
import subprocess
import threading
import time


class StartupMonitor:
    def __init__(self, wsl, cid, attempt, run_id, seconds, publish, log):
        self.attempt, self.run_id = attempt, run_id
        self.publish, self.log = publish, log
        self.failure, self.last_record = None, None
        self.last_seen = time.monotonic()
        self.process = subprocess.Popen(wsl + ['docker', 'exec', cid, 'python3', '-u',
            '/candidate/startup_cache.py', '--run-id', run_id, '--seconds', str(seconds)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.log.info(line.rstrip('\r\n'))
                # Preserve the first error and drain the raw stream to EOF.
                # A later JSON line cannot turn a failed worker into progress.
                if self.failure is not None:
                    continue
                try:
                    record = json.loads(line)
                    if record.get('run_id') != self.run_id:
                        raise ValueError('Startup-cache diagnostic has wrong run ID')
                except Exception as exc:
                    self.failure = str(exc)
                    continue
                self.last_record, self.last_seen = record, time.monotonic()
        except Exception as exc:
            if self.failure is None:
                self.failure = str(exc)

    def check(self):
        if self.failure or self.process.poll() is not None:
            raise RuntimeError('Startup-cache worker failed: ' + str(self.failure or self.process.returncode))
        if time.monotonic() - self.last_seen > 15:
            raise RuntimeError('Startup-cache worker made no measured progress for 15 seconds')

    def stop(self):
        self.publish(self.attempt/'cache-stop.json', {'run_id': self.run_id})
        code = self.process.wait(timeout=12)
        self.thread.join(timeout=3)
        if self.thread.is_alive() or self.failure or code != 0:
            raise RuntimeError('Startup-cache shutdown not clean: ' + str(self.failure or code))
        if not self.last_record or self.last_record.get('event') != 'stopped':
            raise RuntimeError('Startup-cache shutdown acknowledgement missing')

    def close(self):
        # Called after the owned container is stopped, or after stop() succeeded.
        self.process.wait(timeout=5)
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError('Startup-cache reader did not terminate')
        self.process.stdout.close()
        for handler in self.log.handlers[:]:
            handler.close()
            self.log.removeHandler(handler)
