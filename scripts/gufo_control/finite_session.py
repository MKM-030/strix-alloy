"""One in-process finite HTTP worker graph; importing does no I/O."""
from dataclasses import asdict
import threading
import time

from .finite_ledger import Ledger
from .finite_transport import FiniteTransport
from .finite_startup import ListeningHint
from .finite_workload import WORKLOAD_SHA256
from . import finite_phase as phase


class FiniteSession:
    def __init__(self, workload, index, run_dir, *, api_key, resumed_at,
                 startup_deadline, lifetime_deadline, cancel, committed,
                 parent_live):
        if (type(index) is not int or index not in (1, 2) or
                startup_deadline != resumed_at + 480 or
                lifetime_deadline != resumed_at + (3600 if index == 1 else 900)):
            raise ValueError('finite_session_deadline')
        self.cancel, self.committed, self.parent_live = cancel, committed, parent_live
        self.done = threading.Event()  # readiness notification, not worker termination
        self.ledger = Ledger(run_dir/'ledger', workload, index, run_dir.name,
                             resumed_at, create=True)
        self.transport = FiniteTransport(self.ledger, workload, api_key, cancel=cancel)
        self.readiness = None
        self.readiness_sha256 = None
        self.certificate = None
        self.phase_started = False
        self.failure = None
        self._ready_result = dict(success=False, error='finite_not_ready')
        self.thread = threading.Thread(target=self._work,
            args=(workload, run_dir, startup_deadline, lifetime_deadline),
            daemon=True, name='gufo-finite-session')
        self.thread.start()

    def _work(self, workload, run_dir, startup_deadline, lifetime_deadline):
        try:
            self.readiness = phase.start_readiness(workload, self.ledger,
                self.transport, ListeningHint(run_dir),
                startup_deadline=startup_deadline, lifetime_deadline=lifetime_deadline)
            while self.readiness.thread.is_alive():
                self.readiness.thread.join(.01)
                if self.cancel.is_set() or not self.parent_live.is_set():
                    self.cancel.set()
                if time.monotonic() >= startup_deadline:
                    self.cancel.set()
                    raise ValueError('finite_readiness_join_deadline')
            self.readiness.thread.join(0)
            self.readiness_sha256 = phase.readiness_digest(
                self.readiness, self.ledger, self.transport)
            self._ready_result = dict(self.readiness.result)
            self.done.set()
            while not self.committed.wait(.01):
                if (self.cancel.is_set() or not self.parent_live.is_set() or
                        time.monotonic() >= lifetime_deadline):
                    raise ValueError('finite_handoff_interrupted')
            if (self.cancel.is_set() or not self.parent_live.is_set() or
                    time.monotonic() >= lifetime_deadline):
                raise ValueError('finite_handoff_interrupted')
            counts = self.ledger.snapshot()['counts']
            handoff = phase.VerifiedHandoff(self.ledger.header['run_id'],
                WORKLOAD_SHA256, self.readiness_sha256, counts['ready'],
                counts['models'], counts['post'], True, True)
            self.phase_started = True
            self.certificate = phase.run_remaining(workload, self.ledger,
                self.transport, handoff, stop_event=self.cancel,
                parent_alive=self.parent_live.is_set)
            if not self.certificate.complete:
                self.failure = self.certificate.failure or 'finite_coverage_incomplete'
        except BaseException as error:
            self.failure = type(error).__name__ + ':' + str(error)
            self.cancel.set()
        finally:
            self.done.set()

    def terminal(self):
        # Join actual threads; done events do not establish termination.
        if self.thread.ident is not None:
            self.thread.join(0)
        if self.readiness is not None:
            self.readiness.thread.join(0)
            if self.readiness.thread.is_alive():
                return False
        if self.thread.is_alive():
            return False
        # An unexpected exception after entering the phase cannot establish
        # whether it left inner wave workers alive. Fail closed indefinitely.
        return (not self.phase_started or (self.certificate is not None and
                                          self.certificate.workers_terminal is True))

    def complete(self):
        return (self.terminal() and self.certificate is not None and
                self.certificate.complete is True and self.failure is None)

    @property
    def result(self):
        if self.failure is not None:
            return dict(success=False, error=self.failure)
        if self.phase_started and not self.thread.is_alive():
            return dict(success=self.complete(), error=None if self.complete()
                        else 'finite_workers_unconfirmed')
        return dict(self._ready_result)

    def status(self):
        complete = self.complete()
        return dict(finite_complete=complete, finite_workers_terminal=self.terminal(),
            finite_readiness_sha256=self.readiness_sha256,
            finite_post_count=(self.certificate.post_count if self.certificate else None),
            finite_state=('complete_awaiting_stop' if complete else
                          'failed' if self.failure else
                          'continuation' if self.phase_started else 'readiness_or_handoff'),
            finite_acceptance='structural_only')

    def coverage(self):
        return asdict(self.certificate) if self.certificate is not None else None
