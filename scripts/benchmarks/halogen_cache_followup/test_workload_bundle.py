import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE=Path(__file__).with_name('workload_bundle.py')


class WorkloadTests(unittest.TestCase):
    def module(self):
        if not MODULE.exists():self.fail('The frozen follow-up workload builder is not implemented')
        spec=importlib.util.spec_from_file_location('cache_workload_under_test',MODULE)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_distinct_cold_pairs_reuse_only_their_own_stable_prefix(self):
        value=self.module().build('A document with several people and different observations.')
        pairs=value['pairs'];self.assertEqual(len(pairs),4)
        self.assertEqual([p['phase'] for p in pairs],['warmup_excluded','measured','measured','measured'])
        systems=[]
        for pair in pairs:
            a,b=pair['requests']
            self.assertEqual(a['body']['messages'][:2],b['body']['messages'][:2])
            self.assertNotEqual(a['body']['messages'][-1],b['body']['messages'][-1])
            systems.append(a['body']['messages'][0]['content'])
            for row in (a,b):
                body=row['body'];self.assertTrue(body['stream'])
                self.assertEqual(body['stream_options'],{'include_usage':True})
                self.assertEqual(body['prompt_cache_policy'],'default')
                self.assertNotIn('cache_prompt',body)
                self.assertIsNone(row['actual_input_tokens'])
                self.assertEqual(body['max_tokens'],128)
        self.assertEqual(len(set(systems)),4)
        self.assertFalse(value['runtime_qualified'])

    def test_interleaved_isolation_has_different_ground_truths(self):
        value=self.module().build('Document context.')
        rows=value['isolation_requests']
        self.assertEqual([r['conversation'] for r in rows],['A','B','A','B'])
        self.assertEqual(rows[0]['expected_text'],rows[2]['expected_text'])
        self.assertEqual(rows[1]['expected_text'],rows[3]['expected_text'])
        self.assertNotEqual(rows[0]['expected_text'],rows[1]['expected_text'])
        self.assertTrue(all(r['phase']=='isolation_only' for r in rows))

    def test_bundle_is_frozen_without_overwriting_or_inventing_token_counts(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'bundle'
            m.write_bundle(output,'A small artificial fixture.',{'kind':'artificial_test_fixture'})
            paths=list(output.glob('*.request.json'));self.assertEqual(len(paths),12)
            manifest=json.loads((output/'manifest.json').read_bytes())
            self.assertEqual(manifest['requests_sent'],0)
            self.assertEqual(manifest['provenance'],{'kind':'artificial_test_fixture'})
            self.assertTrue(all(r['actual_input_tokens'] is None for r in manifest['request_files']))
            before={p.name:p.read_bytes() for p in output.iterdir()}
            with self.assertRaises(FileExistsError):m.write_bundle(output,'Changed',{})
            self.assertEqual(before,{p.name:p.read_bytes() for p in output.iterdir()})

    def test_empty_or_nontext_document_is_rejected(self):
        m=self.module()
        for document in ('','  ',None,[],{}):
            with self.subTest(document=document):
                with self.assertRaises(ValueError):m.build(document)


if __name__=='__main__':unittest.main()
