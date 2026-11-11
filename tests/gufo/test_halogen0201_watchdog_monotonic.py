"""Execute the actual saved Bash watchdog with CPU-only clock/process stubs.

No WSL, network, model, GPU or NPU access. Every signal/stop is a recorded
fixture operation against the two fixed fake process identifiers below.
"""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKEND = ROOT / 'backends/halogen-wsl2-0.20.1'
UPSTREAM = BACKEND / '.local/entrypoint-upstream.sh'
BASH = Path('C:/Program Files/Git/bin/bash.exe')
spec = importlib.util.spec_from_file_location('private_watchdog_adapter', BACKEND / 'scripts/entrypoint_adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def function(source, name):
    marker = name + '() {\n'
    start = source.index(marker)
    return source[start:source.index('\n}\n', start) + 3]


def event(round_, *, pong=False, state='S', compact=0, wall_shift=0):
    return dict(mono=1000 + 15 * round_, wall=1000 + 15 * round_ + wall_shift,
                pong=int(pong), state=state, compact=compact)


class WatchdogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not UPSTREAM.is_file():
            raise unittest.SkipTest('Pinned installed upstream entrypoint required')
        if not BASH.is_file():
            raise unittest.SkipTest('Native Git Bash CPU fixtures require Git for Windows')
        cls.original = UPSTREAM.read_bytes()
        cls.candidate = adapter.transform(cls.original).decode()
        cls.old = cls.original.decode()

    def fixture(self, events, *, original=False, limit=120, defer=900):
        self.assertTrue(BASH.is_file(), 'Explicit native Git Bash is required; never fall back to WSL bash')
        source = self.old if original else self.candidate
        pieces = [function(source, name) for name in ('stop_clean', 'all_takedown', 'engine_watchdog')]
        if 'wd_uptime_s() {\n' in source:
            pieces.insert(0, function(source, 'wd_uptime_s'))
        records = [event(0), *events]
        for record in records:
            self.assertEqual(set(record), {'mono', 'wall', 'pong', 'state', 'compact'})
            self.assertTrue(all(type(record[k]) is int for k in ('mono', 'wall', 'pong', 'compact')))
            self.assertIn(record['state'], ('S', 'D'))
        arrays = '\n'.join(key + '=(' + ' '.join(str(record[key]) for record in records) + ')'
                           for key in ('mono', 'wall', 'pong', 'state', 'compact'))
        temporary = tempfile.TemporaryDirectory(prefix='cpu-watchdog-', dir=HERE)
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name).resolve()
        self.assertTrue(directory.is_relative_to(HERE))
        (directory / 'proc').mkdir()
        (directory / 'proc/uptime').write_text('1000.00 0.00\n', encoding='ascii')
        script = '\n'.join(pieces) + '\n' + arrays + r'''
round_=0
ENGINE_PID=2222; API_PID=1111; WATCHDOG_PID=""; NPU_PID=""; HG_STOP=0
_hg_proc="$PWD/proc"
date() { printf 'DATE_USED\n' >> events; printf '%s\n' "${wall[$round_]}"; }
sleep() {
  [[ "$1" == 15 ]] || { printf 'UNEXPECTED_SLEEP\n'; return 2; }
  round_=$((round_ + 1))
  printf '%s.00 0.00\n' "${mono[$round_]}" > "$_hg_proc/uptime"
}
kill() {
  if [[ "$1" == -0 && "$2" == 2222 ]]; then
    ((round_ < ${#mono[@]} - 1)); return
  fi
  if [[ "$1" == -TERM && "$2" == 1111 && $# == 2 ]]; then
    printf 'SIGNAL_OWNED_API %s\n' "$2"; return 0
  fi
  printf 'UNEXPECTED_SIGNAL %s\n' "$*"; return 2
}
engine_pong() { [[ "${pong[$round_]}" == 1 ]]; }
wd_state() { printf '%s\n' "${state[$round_]}"; }
wd_compact() { printf '%s\n' "${compact[$round_]}"; }
wd_gtt_gib() { printf '?\n'; }
stop_engine() {
  [[ "$1" == 2222 ]] || { printf 'UNEXPECTED_STOP %s\n' "$1"; return 2; }
  printf 'STOP_OWNED_ENGINE %s\n' "$1"
}
wait() { :; }
npu_fclk_release() { :; }
wd_gtt_after_exit() { :; }
engine_watchdog 8730 "$ENGINE_PID"
result=$?
printf 'WATCHDOG_RETURN %s\n' "$result"
if [[ "$result" != 0 ]]; then all_takedown "$result"; fi
exit "$result"
'''
        completed = subprocess.run([str(BASH), '--noprofile', '--norc', '-s'],
                                   input=script, text=True, capture_output=True,
                                   # The 61-step virtual D-state case spawns Bash
                                   # subshells; allow host scheduling during model load.
                                   # This bounds the fixture, not the watchdog policy.
                                   cwd=directory, timeout=30,
                                   env={'PATH': 'C:/Program Files/Git/usr/bin;C:/Windows/System32',
                                        'HALOGEN_ENGINE_WATCHDOG_S': str(limit),
                                        'HALOGEN_ENGINE_WATCHDOG_DEFER_S': str(defer)})
        self.assertNotIn('UNEXPECTED_', completed.stdout + completed.stderr)
        return completed, (directory / 'events').read_text() if (directory / 'events').exists() else ''

    def test_original_forward_wall_jump_reproduces_false_owned_shutdown(self):
        result, calls = self.fixture([event(1, wall_shift=136), event(2, pong=True)], original=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PING for 151s', result.stderr)
        self.assertIn('STOP_OWNED_ENGINE 2222', result.stdout)
        self.assertIn('DATE_USED', calls)

    def test_forward_wall_jump_does_not_kill(self):
        result, calls = self.fixture([event(1, wall_shift=136), event(2, pong=True)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PING for 15s', result.stderr)
        self.assertNotIn('STOP_OWNED_ENGINE', result.stdout)
        self.assertNotIn('DATE_USED', calls)

    def test_backward_wall_jump_does_not_delay_real_timeout(self):
        events = [event(i, wall_shift=-500) for i in range(1, 9)]
        result, calls = self.fixture(events)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PING for 120s', result.stderr)
        self.assertIn('STOP_OWNED_ENGINE 2222', result.stdout)
        self.assertNotIn('DATE_USED', calls)

    def test_real_elapsed_timeout_still_stops_only_fixture_owned_processes(self):
        result, _ = self.fixture([event(i) for i in range(1, 9)])
        self.assertEqual(result.returncode, 1)
        self.assertIn('PING for 120s', result.stderr)
        self.assertEqual(result.stdout.count('STOP_OWNED_ENGINE 2222'), 1)
        self.assertEqual(result.stdout.count('SIGNAL_OWNED_API 1111'), 1)

    def test_successful_PONG_resets_last_success_time(self):
        events = [event(i, pong=i == 8) for i in range(1, 16)]
        result, _ = self.fixture(events)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('STOP_OWNED_ENGINE', result.stdout)
        self.assertIn('PING for 105s', result.stderr)
        events.append(event(16))
        result, _ = self.fixture(events)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PING for 120s', result.stderr)

    def test_D_state_stays_deferred_even_at_defer_limit(self):
        result, _ = self.fixture([event(i, state='D') for i in range(1, 62)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PING for 915s: a thread is in uninterruptible sleep', result.stderr)
        self.assertNotIn('STOP_OWNED_ENGINE', result.stdout)

    def test_compaction_still_defers_until_original_900_seconds(self):
        result, _ = self.fixture([event(i, compact=i) for i in range(1, 61)])
        self.assertEqual(result.returncode, 1)
        self.assertIn('past HALOGEN_ENGINE_WATCHDOG_DEFER_S=900', result.stderr)
        self.assertIn('nothing for 900s', result.stderr)

    def test_end_of_compaction_starts_original_grace_window(self):
        events = [event(i, compact=min(i, 3)) for i in range(1, 12)]
        result, _ = self.fixture(events)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('compaction stopped after 45s', result.stderr)
        events.append(event(12, compact=3))
        result, _ = self.fixture(events)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PING for 120s', result.stderr)

    def test_PONG_clears_deferred_state(self):
        events = [event(i, state='D' if i <= 3 else 'S', pong=i == 4) for i in range(1, 12)]
        result, _ = self.fixture(events)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('answered PING again after 60s of silence (45s of it deferred', result.stderr)
        self.assertNotIn('compaction stopped', result.stderr)

    def test_disabled_watchdog_preserves_original_off_mode(self):
        result, calls = self.fixture([event(1)], limit=0)
        self.assertEqual(result.returncode, 0)
        self.assertIn('watchdog OFF', result.stdout)
        self.assertNotIn('DATE_USED', calls)

    def test_unknown_upstream_bytes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            adapter.transform(self.original + b'\n')

    def clock_helper(self, contents):
        temporary = tempfile.TemporaryDirectory(prefix='cpu-clock-', dir=HERE)
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name).resolve()
        self.assertTrue(directory.is_relative_to(HERE))
        (directory / 'proc').mkdir()
        if contents is not None:
            (directory / 'proc/uptime').write_text(contents, encoding='ascii')
        script = function(self.candidate, 'wd_uptime_s') + '\n_hg_proc="$PWD/proc"\nwd_uptime_s\n'
        return subprocess.run([str(BASH), '--noprofile', '--norc', '-s'],
                              input=script, text=True, capture_output=True, cwd=directory, timeout=10)

    def test_uptime_parser_uses_integer_seconds_and_explicit_decimal(self):
        for value, expected in (('1234.99 0.00\n', '1234\n'),
                                ('0008.56 0.00\n', '8\n'), ('0.00 0.00\n', '0\n'),
                                ('321 0\n', '321\n')):
            with self.subTest(value=value):
                result = self.clock_helper(value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_uptime_unreadable_or_invalid_never_uses_wall_clock(self):
        for value in (None, '', 'NaN 0\n', '-1.00 0\n', '1e3 0\n',
                      '123.4x 0\n', '9999999999999999999.00 0\n'):
            with self.subTest(value=value):
                result = self.clock_helper(value)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertIn('watchdog uptime clock', result.stderr)

    def test_clock_only_change_leaves_every_other_watchdog_instruction_exact(self):
        original = function(self.old, 'engine_watchdog')
        changed = function(self.candidate, 'engine_watchdog')
        normalized = changed.replace('$(wd_uptime_s) || return 1', '$(date +%s)')
        self.assertEqual(normalized, original)
        self.assertEqual(changed.count('$(wd_uptime_s) || return 1'), 3)
        self.assertNotIn('date +%s', changed)
        self.assertIn('local limit="${HALOGEN_ENGINE_WATCHDOG_S:-180}" step=15 silent=0', changed)
        self.assertEqual(function(self.candidate, 'engine_pong'), function(self.old, 'engine_pong'))
        self.assertEqual(function(self.candidate, 'all_takedown'), function(self.old, 'all_takedown'))

    def test_candidate_diff_is_only_clock_helper_and_clock_calls_after_WSL_transform(self):
        normalized = self.candidate.replace(adapter.UPTIME_HELPER.decode(), '', 1)
        normalized = normalized.replace(function(normalized, 'engine_watchdog'),
                                        function(self.old, 'engine_watchdog'), 1)
        self.assertEqual(hashlib.sha256(normalized.encode()).hexdigest(), adapter.ORIGINAL_WSL_SHA256)
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            adapter.adapt_watchdog(normalized.encode() + b'\n')

    def test_actual_candidate_has_valid_Bash_syntax_without_execution(self):
        result = subprocess.run([str(BASH), '--noprofile', '--norc', '-n'],
                                input=self.candidate, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
