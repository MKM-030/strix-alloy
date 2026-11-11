"""CPU regression executing the actual startup ownership-inspection block."""
import ast
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'backends/halogen-wsl2-0.20.1/scripts/service.py'


def startup_block(source):
    tree = ast.parse(source.read_text(encoding='utf-8'))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'serve')
    loop = next(node for node in ast.walk(main) if isinstance(node, ast.While)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.comparators[0], ast.Name)
        and node.test.comparators[0].id == 'deadline'
        and any(isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
                and isinstance(item.func.value, ast.Name) and item.func.value.id == 'cache_worker'
                for item in ast.walk(node)))
    block = []
    for node in loop.body:
        block.append(node)
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == 'cache_worker'
                and node.value.func.attr == 'check'):
            break
    else:
        raise AssertionError('Actual startup block has no cache worker check')
    assignments = [node for node in ast.walk(main) if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'deadline' for target in node.targets)
        and isinstance(node.value, ast.BinOp) and isinstance(node.value.right, ast.Attribute)
        and node.value.right.attr == 'startup_timeout']
    if len(assignments) != 1:
        raise AssertionError('Original startup deadline is missing or ambiguous')
    timeout = next(node for node in ast.walk(main) if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == 'ready'
        and any(isinstance(item, ast.Constant) and item.value == 'Startup timeout; model was not ready'
                for item in ast.walk(node)))
    truncated_loop = ast.While(test=loop.test, body=block + [ast.Return(value=ast.Name(id='info', ctx=ast.Load()))], orelse=[])
    fixture = ast.FunctionDef(name='exercise_actual_startup_block', args=ast.arguments(
        posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=[assignments[0], truncated_loop, timeout], decorator_list=[])
    return ast.fix_missing_locations(ast.Module(body=[fixture], type_ignores=[]))


class StartupInspectTests(unittest.TestCase):
    def run_block(self, observations, *, seconds=25, ownership_error=None, worker_error=None):
        events = []
        clock = SimpleNamespace(now=0.0)
        clock.monotonic = lambda: clock.now
        def sleep(seconds):
            clock.now += seconds
            events.append(('sleep', seconds))
        clock.sleep = sleep
        queue = iter(observations)
        def inspect(cid):
            events.append(('inspect', cid))
            value = next(queue)
            if isinstance(value, BaseException):
                clock.now += 10
                raise value
            return value
        def owned(info, cid, manifest, **options):
            events.append(('owned', cid))
            if ownership_error:
                raise ownership_error
        def worker_check():
            events.append(('worker_check',))
            if worker_error:
                raise worker_error
        scope = dict(time=clock, subprocess=subprocess,
            r=SimpleNamespace(inspect=inspect), cid='same-owned-cid', m={},
            cancelled=lambda: False, keepalive=SimpleNamespace(check=lambda: events.append(('keepalive',))),
            guard_proc=object(), attempt=Path('fixture'),
            guard_alive=lambda *args: events.append(('guard',)),
            owned=owned, cache_worker=SimpleNamespace(check=worker_check),
            log=SimpleNamespace(warning=lambda *args: events.append(('warning',))),
            o=SimpleNamespace(startup_timeout=seconds), ready=False,
            startup_exit_error=lambda attempt: RuntimeError('Actual engine exited'))
        exec(compile(startup_block(SOURCE), str(SOURCE), 'exec'), scope)
        return scope['exercise_actual_startup_block'], events, clock

    def test_transient_timeout_continues_same_cid_and_checks_worker_before_success(self):
        execute, events, clock = self.run_block([
            subprocess.TimeoutExpired('fixture-inspect', 10), dict(State=dict(Running=True))])
        try:
            info = execute()
        except subprocess.TimeoutExpired:
            self.fail('The startup block promoted a transient inspect observation timeout to fatal')
        self.assertTrue(info['State']['Running'])
        self.assertEqual([event for event in events if event[0] == 'inspect'],
                         [('inspect', 'same-owned-cid'), ('inspect', 'same-owned-cid')])
        self.assertEqual(events.count(('worker_check',)), 2)
        self.assertEqual(events.count(('guard',)), 2)
        self.assertEqual(events.count(('keepalive',)), 2)
        self.assertLess(clock.now, 25)

    def test_repeated_timeouts_do_not_extend_original_startup_deadline(self):
        execute, events, clock = self.run_block([subprocess.TimeoutExpired('fixture-inspect', 10)] * 3)
        with self.assertRaisesRegex(TimeoutError, 'Startup timeout; model was not ready'):
            execute()
        self.assertEqual(events.count(('inspect', 'same-owned-cid')), 3)
        self.assertEqual(events.count(('worker_check',)), 3)
        self.assertEqual(clock.now, 33)

    def test_changed_ownership_remains_fatal(self):
        execute, events, _ = self.run_block([dict(State=dict(Running=True))],
                                          ownership_error=ValueError('Ownership changed'))
        with self.assertRaisesRegex(ValueError, 'Ownership changed'):
            execute()
        self.assertEqual(events.count(('inspect', 'same-owned-cid')), 1)
        self.assertNotIn(('worker_check',), events)

    def test_malformed_inspection_remains_fatal(self):
        execute, events, _ = self.run_block([{}])
        with self.assertRaises(KeyError):
            execute()
        self.assertEqual(events.count(('inspect', 'same-owned-cid')), 1)

    def test_failed_inspect_command_remains_fatal(self):
        execute, events, _ = self.run_block([subprocess.CalledProcessError(1, 'fixture-inspect')])
        with self.assertRaises(subprocess.CalledProcessError):
            execute()
        self.assertEqual(events.count(('inspect', 'same-owned-cid')), 1)

    def test_cache_worker_failure_during_timeout_remains_fatal(self):
        execute, events, _ = self.run_block([subprocess.TimeoutExpired('fixture-inspect', 10)],
                                          worker_error=RuntimeError('Worker failed'))
        with self.assertRaisesRegex(RuntimeError, 'Worker failed'):
            execute()
        self.assertEqual(events.count(('inspect', 'same-owned-cid')), 1)

    def test_observed_engine_exit_remains_fatal(self):
        execute, events, _ = self.run_block([dict(State=dict(Running=False))])
        with self.assertRaisesRegex(RuntimeError, 'Actual engine exited'):
            execute()
        self.assertEqual(events.count(('inspect', 'same-owned-cid')), 1)


if __name__ == '__main__':
    unittest.main()
