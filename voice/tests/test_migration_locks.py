"""Exercise real startup lock orchestration using only owned temp OS locks."""
import ast
from contextlib import contextmanager, redirect_stdout
import contextlib
import io
import msvcrt
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

def repository_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "voice/native_qwen_asr.py").is_file() and (parent / "voice/native-start/start_current_voice.py").is_file():
            return parent
    raise RuntimeError("Cannot find the repository Voice sources")

ROOT = repository_root()
HERE = Path(__file__).resolve().parent
STARTER = ROOT / 'voice/native-start/start_current_voice.py'


def actual_run(services, speech_services, body):
    tree = ast.parse(STARTER.read_bytes())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ('startup_locks', 'run')]
    noop = lambda *args, **kwargs: None
    scope = dict(contextlib=contextlib, Path=Path, services=services,
                 speech_services=speech_services, validate_profile=lambda: {},
                 preflight=body, conversation_stage=noop, omni_stage=noop,
                 speech_stage=noop, model_start=noop, gateway_start=noop,
                 funnel_check=noop, health=noop, BOT_CONFIG=Path('inert-bot.json'),
                 NATIVE_CONFIG=Path('inert-native.json'))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(STARTER), 'exec'), scope)
    with redirect_stdout(io.StringIO()):
        return scope['run'](False)


def service(runtime, label, events, active):
    @contextmanager
    def startup_lock():
        runtime.mkdir(parents=True, exist_ok=True)
        with (runtime / 'startup.lock').open('a+b') as handle:
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            events.append('attempt-' + label)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('Actual non-reentrant OS lock rejected ' + label) from None
            events.append('enter-' + label)
            active.add(label)
            try:
                yield
            finally:
                active.remove(label)
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                events.append('exit-' + label)
    return SimpleNamespace(RUNTIME=runtime, startup_lock=startup_lock,
                           voice_start=lambda *args, **kwargs: None)


class MigrationLockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='migration-lock-', dir=HERE)
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(HERE.resolve()))
        self.events, self.active = [], set()

    def tearDown(self):
        self.temporary.cleanup()

    def test_same_resolved_runtime_takes_one_real_os_lock(self):
        # Removing deduplication makes the second handle fail in the actual OS.
        first = service(self.root / 'runtime', 'first', self.events, self.active)
        second = service(self.root / 'runtime/../runtime', 'second', self.events, self.active)
        seen = []
        def body(profile):
            seen.append(set(self.active))
        try:
            result = actual_run(first, second, body)
        except RuntimeError as error:
            self.fail('Shared runtime was reacquired through a second OS handle: ' + str(error))
        self.assertEqual(result, 0)
        self.assertEqual(seen, [{'first'}])
        self.assertEqual(self.events, ['attempt-first', 'enter-first', 'exit-first'])
        self.assertFalse(self.active)

    def test_distinct_runtimes_keep_both_locks_and_reverse_release_order(self):
        # Deduplicating by module type rather than resolved runtime loses a lock.
        first = service(self.root / 'product', 'first', self.events, self.active)
        second = service(self.root / 'primary', 'second', self.events, self.active)
        seen = []
        actual_run(first, second, lambda profile: seen.append(set(self.active)))
        self.assertEqual(seen, [{'first', 'second'}])
        self.assertEqual(self.events, ['attempt-first', 'enter-first', 'attempt-second',
                                       'enter-second', 'exit-second', 'exit-first'])
        self.assertFalse(self.active)

    def test_second_lock_failure_releases_first_before_propagating(self):
        # Losing ExitStack cleanup leaves the first file locked after failure.
        first = service(self.root / 'product', 'first', self.events, self.active)
        second = service(self.root / 'primary', 'second', self.events, self.active)
        holder = service(self.root / 'primary', 'holder', [], set())
        seen = []
        with holder.startup_lock():
            with self.assertRaisesRegex(RuntimeError, 'rejected second'):
                actual_run(first, second, lambda profile: seen.append('body'))
            self.assertFalse(self.active)
            # A fresh real handle can acquire the formerly held first lock.
            with first.startup_lock():
                self.assertEqual(self.active, {'first'})
        self.assertEqual(seen, [])
        self.assertFalse(self.active)


if __name__ == '__main__':
    unittest.main(verbosity=2)
