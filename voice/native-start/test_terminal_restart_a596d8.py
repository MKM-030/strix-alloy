import importlib.util,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
p=Path(__file__).with_name('model_restart_a596d8.py')
spec=importlib.util.spec_from_file_location('exact_incident_recovery',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class GuardedRecovery(unittest.TestCase):
 def receipt(self,**changes):
  return dict(schema=1,mode='verify',phase='verified',run=m.RUN,outer_run=m.OUTER,archived=False,
   requested_restart_gate_passed=True,admission_policy_sha256=m.POLICY_SHA,historical_recovery=False,protected_hashes=m.PINS,source_pins=m.SOURCE_PINS,
   source_sha256=m.sha(p),verified_unix=time.time(),final_sample_monotonic=time.monotonic(),**changes)
 def old(self,root,receipt):
  q=Path(root)/'verified.json';q.write_text(json.dumps(receipt));return q
 def test_low_memory_failure_never_archives(self):
  with patch.object(m,'verify',side_effect=ValueError('Requested restart below floor')),patch.object(m,'archive_lock') as rename:
   with self.assertRaises(ValueError):m.reconcile('verify',None)
   rename.assert_not_called()
 def test_archive_requires_verified_receipt(self):
  with patch.object(m,'verify') as verify,patch.object(m,'archive_lock') as rename:
   with self.assertRaises(ValueError):m.reconcile('archive',None)
   verify.assert_not_called();rename.assert_not_called()
 def test_archive_preflight_receipt_is_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   receipt=self.receipt();receipt['mode']='archive'
   with patch.object(m,'verify') as verify,patch.object(m,'archive_lock') as rename:
    with self.assertRaises(ValueError):m.reconcile('archive',self.old(root,receipt))
    verify.assert_not_called();rename.assert_not_called()
 def test_stale_receipt_is_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   receipt=self.receipt();receipt['verified_unix']-=181
   with patch.object(m,'verify') as verify,patch.object(m,'archive_lock') as rename:
    with self.assertRaises(ValueError):m.reconcile('archive',self.old(root,receipt))
    verify.assert_not_called();rename.assert_not_called()
 def test_final_memory_age_rejects_before_rename(self):
  with tempfile.TemporaryDirectory() as root:
   prior=self.receipt();current=self.receipt();current['final_sample_monotonic']-=3
   with patch.object(m,'OUT',Path(root)),patch.object(m,'verify',return_value=current),patch.object(m,'archive_lock') as rename:
    with self.assertRaises(ValueError):m.reconcile('archive',self.old(root,prior))
    rename.assert_not_called()
 def test_fresh_pin_drift_rejects_before_rename(self):
  with tempfile.TemporaryDirectory() as root:
   prior=self.receipt();current=self.receipt();current['protected_hashes']={**m.PINS,'unexpected':'drift'}
   with patch.object(m,'OUT',Path(root)),patch.object(m,'verify',return_value=current),patch.object(m,'archive_lock') as rename:
    with self.assertRaises(ValueError):m.reconcile('archive',self.old(root,prior))
    rename.assert_not_called()
 def test_verify_produces_immutable_receipt_without_rename(self):
  with tempfile.TemporaryDirectory() as root:
   with patch.object(m,'OUT',Path(root)),patch.object(m,'verify',return_value=self.receipt()),patch.object(m,'archive_lock') as rename:
    result=m.reconcile('verify',None)
    self.assertFalse(result['archived']);self.assertTrue(Path(result['receipt']).exists());rename.assert_not_called()
if __name__=='__main__':unittest.main()
