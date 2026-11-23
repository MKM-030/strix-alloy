"""Test N-Gram hash reuse, mount binding, and owned startup refusal offline."""

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import checkpoint_integrity as ci
import lease_supervisor as supervisor
import ngram_ntfs
import ntfs_file_generation
import service


MACHINE = {'distro': 'fixture', 'user': 'fixture', 'ngram_source': '/mnt/c/models/source.hgn'}
SOURCE = MACHINE['ngram_source']
WINDOWS_PATH, MOUNT = ngram_ntfs.drvfs_path(SOURCE)
ORIGINAL = dict(device=19, inode=23, size=ci.NGRAM_SIZE, mtime_ns=1234, ctime_ns=5678)
CURRENT = dict(ORIGINAL, device=42)
GENERATION = dict(eof=ci.NGRAM_SIZE, file_usn=12)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.local = Path(folder)
        self.enterContext(patch.object(ngram_ntfs.portable, 'LOCAL', self.local))
        self.legacy = self.local / 'ngram-integrity.json'
        self.native = self.local / ngram_ntfs.RECEIPT_NAME
        self.lease = Mock()
        self.lease.snapshot.return_value = GENERATION.copy()
        self.releases = 0

        @contextmanager
        def open_fixture(path):
            self.assertEqual(path, WINDOWS_PATH)
            try:
                yield self.lease
            finally:
                self.releases += 1

        self.observe = self.enterContext(patch.object(ngram_ntfs, 'observe', return_value=CURRENT.copy()))
        self.open = self.enterContext(patch.object(ntfs_file_generation, 'open_read_lease', side_effect=open_fixture))
        self.full_hash = self.enterContext(patch.object(ci, '_verify_hash', return_value={
            'source': SOURCE, 'sha256': ci.NGRAM_SHA, 'identity': CURRENT.copy(),
        }))

    def prior(self):
        self.native.write_text(json.dumps({
            'schema': 1, 'source': SOURCE, 'sha256': ci.NGRAM_SHA,
            'identity': ORIGINAL, 'mount': MOUNT, 'ntfs': GENERATION,
        }), encoding='utf-8')

    def test_native_receipt_reuses_digest_and_binds_current_dev_under_lease(self):
        self.prior()
        prior_bytes = self.native.read_bytes()
        with ExitStack() as leases:
            result = ci.verify_ngram(MACHINE, self.local, startup_leases=leases)
            self.assertEqual(result['ntfs_mount_binding'],
                             dict(source=SOURCE, identity=CURRENT, mode='ntfs_receipt'))
            self.assertEqual(self.releases, 0)
        self.assertEqual(self.releases, 1)
        self.assertEqual(self.native.read_bytes(), prior_bytes)
        self.assertFalse(self.legacy.exists())
        self.full_hash.assert_not_called()

    def test_stable_legacy_receipt_does_not_require_a_new_full_read(self):
        legacy = {'source': SOURCE, 'sha256': ci.NGRAM_SHA, 'identity': CURRENT}
        self.legacy.write_text(json.dumps(legacy), encoding='utf-8')
        with ExitStack() as leases:
            self.assertEqual(ci.verify_ngram(MACHINE, self.local, startup_leases=leases), legacy)
        self.open.assert_not_called()
        self.full_hash.assert_not_called()
        self.assertFalse(self.native.exists())

    def test_changed_ntfs_generation_forces_full_read_even_if_guest_stats_match(self):
        self.prior()
        self.observe.return_value = ORIGINAL
        self.full_hash.return_value['identity'] = ORIGINAL
        self.lease.snapshot.return_value = dict(GENERATION, file_usn=13)
        with ExitStack() as leases:
            result = ci.verify_ngram(MACHINE, self.local, startup_leases=leases)
            self.assertEqual(result['ntfs_mount_binding']['mode'], 'full_sha256')
            self.assertEqual(self.releases, 0)
        self.full_hash.assert_called_once_with(MACHINE, SOURCE, ORIGINAL, ci.NGRAM_SIZE,
                                               ci.NGRAM_SHA, 'N-gram source', SOURCE)
        self.assertEqual(json.loads(self.native.read_bytes())['ntfs']['file_usn'], 13)
        self.assertEqual(json.loads(self.legacy.read_bytes())['identity'], ORIGINAL)

    def test_generation_change_after_hash_refuses_to_publish_or_hold_lease(self):
        self.lease.snapshot.side_effect = [GENERATION, dict(GENERATION, file_usn=14)]
        with ExitStack() as leases, self.assertRaisesRegex(ValueError, 'generation changed'):
            ci.verify_ngram(MACHINE, self.local, startup_leases=leases)
        self.assertEqual(self.releases, 1)
        self.assertFalse(self.native.exists())
        self.assertFalse(self.legacy.exists())

    def test_missing_ntfs_information_uses_the_original_verifier(self):
        self.open.side_effect = ntfs_file_generation.NtfsGenerationUnavailable('fixture')
        with ExitStack() as leases, patch.object(ci, '_verify_file', return_value={'mode': 'fallback'}) as stock:
            self.assertEqual(ci.verify_ngram(MACHINE, self.local, startup_leases=leases), {'mode': 'fallback'})
        stock.assert_called_once_with(MACHINE, self.local, SOURCE, 'ngram-integrity.json',
                                      ci.NGRAM_SIZE, ci.NGRAM_SHA, 'N-gram source', bind_source=True, force_hash=False)
        self.full_hash.assert_not_called()

    def test_native_receipt_without_journal_proof_requires_a_full_read(self):
        self.prior()
        self.open.side_effect = ntfs_file_generation.NtfsGenerationUnavailable('no journal')
        with ExitStack() as leases, patch.object(ci, '_verify_file', return_value={}) as stock:
            ci.verify_ngram(MACHINE, self.local, startup_leases=leases)
        self.assertIs(stock.call_args.kwargs['force_hash'], True)

    def test_active_writer_refuses_without_legacy_fallback(self):
        self.prior()
        locked = OSError('file sharing violation')
        locked.winerror = 32
        error = ntfs_file_generation.NtfsGenerationUnavailable('file is locked')
        error.__cause__ = locked
        self.open.side_effect = error
        with ExitStack() as leases, patch.object(ci, '_verify_file') as stock:
            with self.assertRaisesRegex(ValueError, 'open for writing or locked'):
                ci.verify_ngram(MACHINE, self.local, startup_leases=leases)
        stock.assert_not_called()


class ContainerBindingTests(unittest.TestCase):
    def test_selected_manifest_mount_and_env_must_match_the_receipt(self):
        plan = {'checkpoint': 'v2', 'mounts': {ngram_ntfs.MOUNT: SOURCE},
                'environment': {'HALOGEN_NGRAM_TABLE': ngram_ntfs.MOUNT},
                'ngram_ntfs_binding': dict(source=SOURCE, identity=CURRENT, mode='ntfs_receipt')}
        self.assertEqual(ngram_ntfs.binding_identity(plan), CURRENT)
        for change in ({'mounts': {ngram_ntfs.MOUNT: '/mnt/c/other.hgn'}},
                       {'environment': {'HALOGEN_NGRAM_TABLE': '/candidate/ngram.hgn'}},
                       {'lookup_tuning': {}}, {'checkpoint': 'w4b'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                ngram_ntfs.binding_identity(dict(plan, **change))

    def test_supervisor_refuses_before_starting_child(self):
        with patch.object(supervisor, 'verify_ngram_mount', side_effect=ValueError('mismatch')), \
                patch.object(supervisor, 'read_record'), patch.object(supervisor, 'ProgressLease') as tracker, \
                patch.object(supervisor.subprocess, 'Popen') as launch, patch.object(supervisor.signal, 'signal'):
            tracker.return_value.observe.return_value = True
            tracker.return_value.is_fresh.return_value = True
            result = supervisor.main(['--lease', '/fixture/lease.json', '--run-id', 'frozen',
                                      '--ngram-identity', '1,2,3,4,5', '/bin/false'])
        self.assertEqual(result, 2)
        launch.assert_not_called()

    def test_supervisor_checks_the_engine_selected_path_before_open(self):
        with patch.dict(os.environ, {'HALOGEN_NGRAM_TABLE': '/other.hgn'}), patch.object(supervisor.os, 'open') as opened:
            with self.assertRaisesRegex(ValueError, 'configured to open another'):
                supervisor.verify_ngram_mount('1,2,3,4,5')
        opened.assert_not_called()

    def test_command_passes_current_generation_before_child_arguments(self):
        plan = {'run_id': 'a' * 32, 'checkpoint': 'v2', 'mounts': {ngram_ntfs.MOUNT: SOURCE},
                'environment': {'HALOGEN_NGRAM_TABLE': ngram_ntfs.MOUNT},
                'ngram_ntfs_binding': dict(source=SOURCE, identity=CURRENT, mode='ntfs_receipt')}
        with patch.object(service, 'reject_unqualified_manifest_overrides', return_value=None):
            args = service.command(plan)
        self.assertIn(f'type=bind,src={SOURCE},dst={ngram_ntfs.MOUNT},readonly', args)
        at = args.index('--ngram-identity')
        self.assertEqual(args[at + 1], f"42,23,{ci.NGRAM_SIZE},1234,5678")
        self.assertEqual(args[at + 2], '/bin/bash')
