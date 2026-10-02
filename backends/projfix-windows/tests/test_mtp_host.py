import pathlib, re, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from profile import command

class MtpHostTests(unittest.TestCase):
    def candidate(self):
        try:
            return command('runtime', 'target.gguf', 'draft.gguf', 262144, 'mtp-host')
        except ValueError as exc:
            self.fail('Explicit mixed-placement MTP mode is missing: ' + str(exc))

    def test_explicit_single_gpu_split_and_real_draft(self):
        args = self.candidate()
        self.assertEqual(args[args.index('--tensor-split') + 1], '1')
        self.assertEqual(args[args.index('-md') + 1], 'draft.gguf')
        self.assertEqual(args[args.index('--spec-type') + 1], 'draft-mtp')
        self.assertEqual(args[args.index('--spec-draft-device') + 1], 'ROCm0')

    def test_target_placement_matches_fast_serial(self):
        args = self.candidate()
        control = command('runtime', 'target.gguf', 'draft.gguf', 262144)
        self.assertEqual(args[args.index('-ot') + 1], control[control.index('-ot') + 1])
        self.assertEqual(args[args.index('-ub') + 1], '512')

    def test_old_mtp_stays_explicit_and_unchanged(self):
        args = command('runtime', 'target.gguf', 'draft.gguf', 262144, 'mtp')
        self.assertNotIn('-ot', args)
        self.assertNotIn('--tensor-split', args)

    def test_mtp_host_uses_the_measured_shallow_draft(self):
        args = self.candidate()
        self.assertEqual(args[args.index('--spec-draft-n-max') + 1], '1')
