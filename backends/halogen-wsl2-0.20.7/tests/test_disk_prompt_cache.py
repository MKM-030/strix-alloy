"""Offline coverage for the managed cache and its owned-container lifecycle."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import disk_prompt_cache as cache
import service
import startup_guard as guard


DIRECTORY = dict(path='/home/test/' + cache.DIRECTORY, uid=1000, gid=1000, dev=17, ino=23)
MACHINE = dict(distro='fixture', user='test')
CACHE_ARGS = ['--checkpoint', 'v2', '--context-size', '32768', '--disable-vision',
              '--prompt-cache', 'Flexible', '--prefill-chunk', '8192', '--max-prefill-tokens', '8192']


def manifest():
    return {
        'run_id': '1' * 32, 'checkpoint': 'v2', 'context': 32768, 'slots': 1,
        'environment': {
            'HALOGEN_CTX': '32768', 'HALOGEN_KV_SLOTS': '1', 'HALOGEN_KV_POOL_POSITIONS': '32768',
            'HALOGEN_PROMPT_CACHE': '2', 'HALOGEN_PREFILL_CHUNK': '8192', 'HALOGEN_MAX_TOK': '8192',
        },
        'mounts': {'/models': '/home/test/models', '/service-state': '/mnt/c/state'},
    }


class DiskPromptCacheTests(unittest.TestCase):
    def test_default_has_no_writable_mount_environment_or_wsl_probe(self):
        plan = manifest()
        with patch.object(cache, '_observe', side_effect=AssertionError('Unexpected WSL probe')):
            cache.revalidate(plan, MACHINE)
            args = service.command(plan)
        binds = [args[i + 1] for i, arg in enumerate(args) if arg == '--mount']
        self.assertEqual(len(binds), 2)
        self.assertTrue(all(bind.endswith(',readonly') for bind in binds))
        self.assertFalse(any(arg.split('=', 1)[0] in cache.ENVIRONMENT for arg in args))

    def test_option_requires_exact_reviewed_scope(self):
        self.assertFalse(service.options(CACHE_ARGS).persist_prompt_cache)
        self.assertTrue(service.options(CACHE_ARGS + ['--persist-prompt-cache']).persist_prompt_cache)
        for option, value in (('--context-size', '65536'), ('--checkpoint', 'w4b'),
                              ('--prompt-cache', 'Off'), ('--max-prefill-tokens', '16384')):
            args = CACHE_ARGS.copy()
            args[args.index(option) + 1] = value
            with self.subTest(option=option), self.assertRaises(ValueError):
                service.options(args + ['--persist-prompt-cache'])
        with self.assertRaises(ValueError):
            service.options([arg for arg in CACHE_ARGS if arg != '--disable-vision'] + ['--persist-prompt-cache'])

    def test_opt_in_has_exactly_one_nonrecursive_writable_mount(self):
        plan = manifest()
        with patch.object(cache, '_observe', return_value=DIRECTORY) as observe:
            cache.bind(plan, MACHINE)
        observe.assert_called_once_with(MACHINE, prepare=True)
        args = service.command(plan)
        binds = [args[i + 1] for i, arg in enumerate(args) if arg == '--mount']
        self.assertEqual(sum(bind.endswith(',readonly') for bind in binds), 2)
        self.assertEqual(len(binds), 3)
        self.assertIn(f"type=bind,src={DIRECTORY['path']},dst={cache.DESTINATION},bind-recursive=disabled", binds)
        for key, value in cache.ENVIRONMENT.items():
            self.assertEqual(args.count(f'{key}={value}'), 1)
        plan['mounts']['/other'] = DIRECTORY['path'].rsplit('/', 1)[0]
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            service.command(plan)

    def test_host_and_container_directory_replacement_are_rejected(self):
        plan = manifest()
        with patch.object(cache, '_observe', side_effect=[DIRECTORY, {**DIRECTORY, 'ino': 99}]):
            cache.bind(plan, MACHINE)
            with self.assertRaisesRegex(ValueError, 'directory identity changed'):
                cache.revalidate(plan, MACHINE)
        bound = {key: DIRECTORY[key] for key in ('uid', 'gid', 'dev', 'ino')}
        with patch.object(service.r, 'docker', return_value=json.dumps(bound)) as docker:
            cache.verify_binding(plan, docker, 'a'*64)
            self.assertEqual(docker.call_args.args[-1], cache.DESTINATION)
            docker.return_value = json.dumps({**bound, 'dev': 99})
            with self.assertRaisesRegex(ValueError, 'Bound prompt cache directory identity changed'):
                cache.verify_binding(plan, docker, 'a'*64)

    def test_mount_refusal_does_not_prevent_owned_stop(self):
        plan = manifest()
        with patch.object(cache, '_observe', return_value=DIRECTORY):
            cache.bind(plan, MACHINE)
        good = [{'Source': source, 'Destination': destination, 'Type': 'bind', 'RW': False}
                for destination, source in plan['mounts'].items()]
        good.append({'Source': DIRECTORY['path'], 'Destination': cache.DESTINATION,
                     'Type': 'bind', 'RW': True, 'Propagation': 'rprivate'})
        accepted = {'Mounts': good, 'HostConfig': {'Mounts': [
            {'Target': cache.DESTINATION, 'BindOptions': {'NonRecursive': True}},
        ]}}
        guard.validate_mounts(accepted, plan['mounts'], DIRECTORY['path'])
        with self.assertRaisesRegex(ValueError, 'nonrecursive binding'):
            guard.validate_mounts({'Mounts': good}, plan['mounts'], DIRECTORY['path'])
        running = {'State': {'Running': True}, 'Mounts': good[:-1]}
        terminal = {'State': {'Running': False}, 'Mounts': good[:-1]}
        cid = 'a' * 64
        with patch.object(service.r, 'owned') as owned, \
                patch.object(service.r, 'inspect', side_effect=[running, terminal]), \
                patch.object(service.r, 'docker') as docker, patch.object(service.r, 'validate_terminal'):
            with self.assertRaises(ValueError):
                service.validate_created_container(running, cid, plan)
            self.assertIs(service.stop_owned(cid, plan), terminal)
            docker.assert_called_once_with('stop', '-t', '10', cid, timeout=45)
            self.assertEqual(owned.call_count, 3)

    def test_native_cache_readiness_is_bound_to_active_budget_and_path(self):
        stats = {'cache_root': cache.DESTINATION + '/d9ee1961438b12d6',
                 'disk': {'on': True, 'budget_bytes': 1 << 30}}
        self.assertEqual(cache.check_cache_stats(stats), stats)
        for actual in ({}, {**stats, 'disk': {'on': False, 'budget_bytes': 1 << 30}},
                       {**stats, 'disk': {'on': True, 'budget_bytes': 1 << 29}},
                       {**stats, 'cache_root': '/cache/elsewhere'},
                       {**stats, 'cache_root': cache.DESTINATION + '/..'}):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                cache.check_cache_stats(actual)
