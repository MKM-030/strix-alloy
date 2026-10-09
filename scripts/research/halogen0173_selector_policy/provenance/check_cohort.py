"""Offline hash/ownership review for collected selector provenance; no runtime calls.

The root collector remains the trust boundary for actual loaded file snapshots and
exclusive clients. This reviewer checks the retained evidence, never creates a
qualified receipt by assigning metadata to the public decoder.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('native_ledger', ROOT / 'scripts/research/halogen0173_owned_shadow/ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def ref_bytes(ref, owner):
    require(isinstance(ref, dict) and isinstance(ref.get('path'), str), 'Missing path reference')
    require(re.fullmatch('[0-9a-f]{64}', str(ref.get('sha256', ''))) is not None, 'Missing SHA256')
    path = Path(ref['path'])
    path = path if path.is_absolute() else owner.parent / path
    path = path.resolve(strict=True)
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == ref['sha256'], 'Hash changed: ' + str(path))
    if 'bytes' in ref:
        require(len(data) == ref['bytes'], 'Byte length changed: ' + str(path))
    return path, data


def ref_json(ref, owner):
    path, data = ref_bytes(ref, owner)
    return path, json.loads(data)


def loaded_assets(ref, owner, receipt):
    path, assets = ref_json(ref, owner)
    require(assets.get('schema') == 'halogen0173.selector-loaded-assets.v1', 'Wrong loaded-assets schema')
    require(assets.get('status') != 'template-not-observed', 'Loaded-assets template cannot qualify collection')
    require(assets.get('session_nonce') == receipt['session_nonce'], 'Assets belong to another nonce')
    for key in ('controller_run_id', 'backend_run_id', 'container_id'):
        require(assets.get(key) == receipt['process_binding'][key] and bool(assets.get(key)), 'Assets process mismatch: ' + key)
    require(assets['runtime']['sha256'] == ledger.RUNTIME_SHA, 'Wrong runtime asset pin')
    for name, size, sha in (
        ('checkpoint', 66687678432, '71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687'),
        ('ngram', 124068083904, '9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6'),
    ):
        asset = assets[name]
        require(asset['bytes'] == size and asset['complete_file_sha256'] == sha, 'Wrong ' + name + ' pin')
        require(asset.get('identity_before') == asset.get('identity_after') and bool(asset.get('identity_before')), name + ' identity changed or absent')
        _, integrity = ref_json(asset['integrity_receipt'], path)
        require(integrity['sha256'] == sha and integrity['identity'] == asset['identity_before'], name + ' complete-file receipt mismatch')
        require(bool(asset.get('loaded_path_evidence')), name + ' loaded path evidence absent')
    tokenizer = assets['frontend_tokenizer']
    files = tokenizer.get('files', [])
    require(files and len({f['path'] for f in files}) == len(files), 'Tokenizer file set absent or repeated')
    require({'tokenizer.json', 'tokenizer_config.json'}.issubset({f['path'] for f in files}), 'Required frontend tokenizer files absent')
    for f in files:
        require(re.fullmatch('[0-9a-f]{64}', str(f.get('sha256', ''))) is not None and type(f.get('bytes')) is int and f['bytes'] > 0, 'Incomplete tokenizer file pin')
    canonical = json.dumps(sorted(({k: f[k] for k in ('path', 'bytes', 'sha256')} for f in files), key=lambda f: f['path']), sort_keys=True, separators=(',', ':')).encode('utf-8')
    require(tokenizer.get('asset_set_sha256') == hashlib.sha256(canonical).hexdigest(), 'Tokenizer file-set SHA mismatch')
    require(tokenizer.get('identity_before') == tokenizer.get('identity_after') and bool(tokenizer.get('identity_before')), 'Tokenizer identity changed or absent')
    require(bool(tokenizer.get('loaded_directory_evidence')), 'Actual loaded tokenizer directory not bound')
    for key in ('manifest', 'profile'):
        ref_json(assets[key], path)
    policy = assets['fixed_engine_policy']
    require(policy.get('neural_depth') == 2 and policy.get('pld') == '3,3' and policy.get('adaptive') == 0, 'Fixed stock policy not bound')
    return assets


def review(manifest_path):
    manifest_path = manifest_path.resolve(strict=True)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest.get('schema') == 'halogen0173.selector-request-cohort.v1', 'Wrong cohort schema')
    requests = manifest['requests']
    seen_requests, document_splits, seen_owners = set(), {}, set()
    results = []
    for request in requests:
        reqid = request['request_id']
        require(reqid not in seen_requests, 'Repeated request ID')
        seen_requests.add(reqid)
        split = request['split']
        require(split in ('train', 'test') and request['document_ids'], 'Missing document split')
        for docid in request['document_ids']:
            require(docid not in document_splits or document_splits[docid] == split, 'Document crossed split: ' + docid)
            document_splits[docid] = split
        _, payload = ref_json(request['payload'], manifest_path)
        _, document = ref_bytes(request['document'], manifest_path)
        require(payload['messages'] == [dict(role='user', content=document.decode('utf-8'))], 'Payload/document mismatch')
        require(all(payload.get(k) == v for k, v in {'max_tokens':128, 'temperature':0, 'seed':1, 'stream':False, 'cache_prompt':False, 'enable_thinking':False, 'drafter':'mtp'}.items()), 'Frozen request controls changed')
        provenance_path, receipt = ref_json(request['provenance'], manifest_path)
        require(receipt.get('schema') == 'halogen0173.selector-request-provenance.v1' and receipt.get('status') != 'template-not-observed', 'Unobserved provenance')
        for key in ('request_id', 'document_ids', 'split', 'session_nonce', 'wire_request_id', 'owner_birth'):
            require(receipt.get(key) == request.get(key) and receipt.get(key) is not None, 'Request binding mismatch: ' + key)
        wire, birth, nonce = receipt['wire_request_id'], receipt['owner_birth'], receipt['session_nonce']
        require(type(wire) is int and 0 <= wire < 2**64 and type(birth) is int and birth > 0, 'Native identity out of range')
        require((nonce, wire, birth) not in seen_owners, 'Native owner reused for another request')
        seen_owners.add((nonce, wire, birth))
        evidence = receipt['evidence']
        journal_path, journal = ref_bytes(evidence['journal'], provenance_path)
        _, startup = ref_json(evidence['startup'], provenance_path)
        _, close = ref_json(evidence['close'], provenance_path)
        decoded = ledger.read_ledger(io.BytesIO(journal))
        require(decoded['dataset_complete'] and decoded['header']['session_nonce'] == nonce, 'Incomplete or different journal')
        require(startup['session_nonce'] == nonce == close['session_nonce'], 'Closure nonce mismatch')
        require(startup['full_elf_verified'] and startup['native_pins_verified'] and startup['installed_sites'] == 9 and startup['capture_enabled'], 'Installer not qualified')
        require(close['closed'] and close['qualified_close'] and all(close[k] == 0 for k in ('dropped_cumulative','live_owners','pending_rounds','relay_inflight')), 'Whole journal did not close cleanly')
        require(len(journal) == 128 + 512 * close['written_events'], 'Close event count mismatch')
        interval = receipt['interval']
        before, after = interval['journal_before_bytes'], interval['journal_after_bytes']
        require(type(before) is int and type(after) is int and 128 <= before < after <= len(journal) and (before-128)%512 == (after-128)%512 == 0, 'Invalid journal watermarks')
        events = [ledger.decode_event(journal[o:o+512]) for o in range(before, after, 512)]
        births, retires = [e for e in events if e['kind']==1], [e for e in events if e['kind']==4]
        require(len(births)==len(retires)==1, 'Exclusive request interval has ambiguous lifetimes')
        require(all(e['wire_id']==wire and e['birth']==birth for e in births+retires), 'Native birth/retire identity differs')
        require(births[0]['seq']==interval['birth_seq'] and retires[0]['seq']==interval['retire_seq'], 'Birth/retire sequence differs')
        _, log = ref_bytes(evidence['engine_log'], provenance_path)
        lo, hi = interval['native_log_before_bytes'], interval['native_log_after_bytes']
        require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(log), 'Invalid native log watermarks')
        ids = sorted({int(s) % (2**64) for s in re.findall(rb'flash_serve:\s+req\s+(-?\d+)\b', log[lo:hi])})
        require(ids == interval['native_log_wire_ids'] == [wire], 'Native log request ID ambiguous or absent')
        _, hb = ref_json(evidence['health_before'], provenance_path)
        _, ha = ref_json(evidence['health_after'], provenance_path)
        require(all(h['status']=='ok' and h['active_requests']==0 and not h['draining'] for h in (hb,ha)), 'Nonidle request boundary')
        require(ha['completed']-hb['completed']==interval['gateway_completed_delta']==1 and ha['cancelled']-hb['cancelled']==interval['gateway_cancelled_delta']==0, 'Gateway request counts differ')
        binding = receipt['process_binding']
        require(binding['isolated_gateway_port']==8842 and binding['private_credentials_used'] and binding['normal_gateway_down_during_collection'], 'Private collection route not bound')
        require(binding['frontend_process_identity'] and binding['native_process_identity'], 'Missing process identities')
        loaded_assets(evidence['loaded_assets'], provenance_path, receipt)
        for key in ('payload','document'):
            _, first = ref_bytes(request[key], manifest_path)
            _, second = ref_bytes(receipt[key], provenance_path)
            require(first==second, 'Provenance '+key+' differs')
        _, supplied_bytes = ref_bytes(request['decoded'], manifest_path)
        _, receipt_decoded_bytes = ref_bytes(receipt['decoded'], provenance_path)
        require(supplied_bytes == receipt_decoded_bytes, 'Receipt/manifest decoded reference differs')
        supplied = json.loads(supplied_bytes)
        rows = [r for r in supplied['rows'] if r['session_nonce']==nonce and r['wire_request_id']==wire and r['owner_birth']==birth]
        originals = {(r['begin_seq'],r['outcome_seq']):r for r in decoded['rows'] if r['wire_request_id']==wire and r['owner_birth']==birth}
        require(rows and len(rows)==len(originals), 'Decoded request rows missing or duplicated')
        causal_eligible = 0
        begin_events = {e['seq']:e for e in events if e['kind']==5}
        for row in rows:
            original = originals.get((row['begin_seq'], row['outcome_seq']))
            require(original is not None and all(row.get(k)==v for k,v in original.items() if k not in ('model_sha256','tokenizer_sha256','document_id')), 'Decoded row differs from native wire')
            begin = begin_events.get(row['begin_seq'])
            require(begin is not None and begin['birth']==birth and begin['wire_id']==wire, 'Causal begin outside request interval')
            if row['source']=='neural':
                require(begin['adaptive']==0 and begin['depth_low']==2, 'Neural begin contradicts fixed-depth profile')
                if begin['native_allowance'] >= 2:
                    causal_eligible += 1
        _, response = ref_json(evidence['response'], provenance_path)
        observed = receipt['observed_request']
        content = response['choices'][0]['message']['content']
        require(isinstance(content,str), 'Text response required for this cohort')
        output_sha = hashlib.sha256(content.encode('utf-8')).hexdigest()
        require(output_sha == observed['output_sha256'] and response['id']==observed['frontend_response_id'], 'Response output binding differs')
        require(response['usage']['prompt_tokens']==observed['prompt_tokens'] and response['usage']['completion_tokens']==observed['completion_tokens'], 'Response usage differs')
        require(observed['http_status']==200 and observed['reasoning_tokens']==0 and observed['cache_n']==observed['disk_restore_n']==0, 'Observed request controls differ')
        timings = response['timings']
        require(timings['cache_n']==timings['disk_restore_n']==0 and response['usage'].get('completion_tokens_details',{}).get('reasoning_tokens',0)==0, 'API reports thinking or cached work')
        require(timings['draft_n']==observed['draft_n'] and timings['draft_n_accepted']==observed['draft_n_accepted'], 'API draft counters differ')
        parity = receipt['output_parity']
        parity_observed = False
        if evidence.get('normal_response') is not None:
            _, normal = ref_json(evidence['normal_response'], provenance_path)
            normal_sha = hashlib.sha256(normal['choices'][0]['message']['content'].encode('utf-8')).hexdigest()
            require(normal_sha == output_sha == parity['reference_output_sha256'] == parity['capture_output_sha256'], 'Observer output parity failed')
            reference_counters = [normal['timings']['draft_n_accepted'], normal['timings']['draft_n']]
            capture_counters = [timings['draft_n_accepted'], timings['draft_n']]
            require(reference_counters == capture_counters == parity['accepted_and_drafted_reference'] == parity['accepted_and_drafted_capture'], 'Observer counter parity failed')
            parity_observed = True
        results.append(dict(request_id=reqid, split=split, document_ids=request['document_ids'], session_nonce=nonce,
                            wire_request_id=wire, owner_birth=birth, native_rows=len(rows), causal_depth2_eligible_rows=causal_eligible,
                            prompt_tokens=observed['prompt_tokens'], completion_tokens=observed['completion_tokens'],
                            output_parity_observed=parity_observed))
    return dict(schema='halogen0173.selector-cohort-offline-review.v1',
                manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(), retained_hash_and_owner_evidence_consistent=True,
                root_exclusive_collection_and_loaded_file_snapshots_are_trusted_inputs=True,
                requests=results, request_count=len(results),
                train_requests=sum(r['split']=='train' for r in results), test_requests=sum(r['split']=='test' for r in results),
                no_runtime_operations=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = review(args.manifest)
    if args.output:
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, sort_keys=True, indent=2)
            stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='requests'}))


if __name__ == '__main__':
    main()
