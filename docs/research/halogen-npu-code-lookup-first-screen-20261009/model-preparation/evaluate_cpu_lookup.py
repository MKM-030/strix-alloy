"""One frozen source-location quality screen, CPU only; no threshold search."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import prepare_cpu as model

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
ROOT = PREP.parents[3]
PROTO = PREP / 'npu-code-lookup-cpu-20261009'
DATA = PREP / 'npu-code-lookup-eval-20261009'
OUT = HERE / 'first-quality-screen'
sys.path.insert(0, str(PROTO))
import code_lookup as lookup

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

PREPROCESSING = dict(batch=1, positions=256, max_query_tokens=64, truncation='only_second',
    padding='right, pad_id0/type_id0', passage='File: {path}\nLines: {start_line}-{end_line}\n{excerpt}',
    score='raw logits[0,0]', exact_path_identifier='CPU direct; no reranking',
    no_answer_gate='none; raw ranking is not sufficiency')

class CPUModel:
    def __init__(self):
        self.identity = dict(model_sha256=sha(model.fixed), tokenizer_sha256=sha(HERE/'model/tokenizer.json'),
            preprocessing_sha256=hashlib.sha256(json.dumps(PREPROCESSING, sort_keys=True).encode()).hexdigest())
        self.tokenizer = model.tokenizer()
        start = time.perf_counter_ns()
        self.session = model.cpu_session(model.fixed)
        self.session_load_ms = (time.perf_counter_ns()-start)/1e6
        self.session.run(None, model.pair(self.tokenizer, 'Which planet is known as the Red Planet?', 'Mars is the Red Planet.'))
        self.rows = []
        self.feeds = {}

    def rerank(self, query, candidates):
        scores = []
        for i, candidate in enumerate(candidates):
            passage = PREPROCESSING['passage'].format(**candidate)
            feed = model.pair(self.tokenizer, query, passage)
            start = time.perf_counter_ns()
            score = float(self.session.run(None, feed)[0][0,0])
            elapsed = (time.perf_counter_ns()-start)/1e6
            scores.append(score)
            key = str(len(self.rows))
            for name, value in feed.items():
                self.feeds[key+'_'+name] = value
            self.rows.append(dict(feed_key=key, candidate_position=i, query=query,
                chunk_id=candidate['chunk_id'], score=score, cpu_inference_ms=elapsed,
                actual_pair_tokens=int(feed['attention_mask'].sum()), source_sha256=candidate['source_sha256']))
        return scores

def metrics(result, truth):
    locations = truth['locations']
    found = result['results']
    file_hit = any(a['path']==b['path'] for a in found for b in locations)
    overlaps = [any(a['path']==b['path'] and a['start_line']<=b['line_end'] and b['line_start']<=a['end_line']
                    for a in found) for b in locations]
    return dict(file_top3_hit=file_hit, span_top3_hit=any(overlaps), expected_spans_found=sum(overlaps),
        expected_spans=len(locations), no_answer_correct=truth['expected_status']=='no_answer' and
        result['status']=='no_match' and not found)

def main():
    assert not OUT.exists(), 'Preserve first screen; do not rerun or tune against it'
    assert sha(DATA/'questions.json')=='b6ec91c58ad0926f7a51af17a87d65e9f8611d884ec85b75c3522e0d21f0709a'
    assert sha(DATA/'ground-truth.json')=='47bfa360574b4801a123ffb8ce1e9b1da0f17704bdfd84950b4afc676c8b5156'
    assert sha(PROTO/'code_lookup.py')=='1cab17e904d4c45bb8b071333f82d9de8f18ffc35726cbf2cd39fd093e61c767'
    questions=json.loads((DATA/'questions.json').read_bytes())['questions']
    truths={x['question_id']:x for x in json.loads((DATA/'ground-truth.json').read_bytes())['expected']}
    index=lookup.load_index(PROTO/'index.json')
    frozen_corpus=json.loads((DATA/'eligible-corpus.json').read_bytes())
    frozen_sources=frozen_corpus['files']
    assert {(s['path'],s['sha256']) for s in index['sources']} == {(s['path'],s['sha256']) for s in frozen_sources}
    provider=CPUModel()
    rows=[]
    for question in questions:
        query=question['prompt']
        start=time.perf_counter_ns()
        baseline=lookup.lookup(index, query, repo=ROOT)
        baseline_ms=(time.perf_counter_ns()-start)/1e6
        assert baseline['status'] in ('ok','ambiguous','no_match')
        exact=baseline.get('ranking_method') in ('cpu_path_bm25','cpu_identifier_bm25')
        start=time.perf_counter_ns()
        reranked=lookup.lookup(index, query, repo=ROOT, reranker=provider, enable_provider=not exact)
        rerank_ms=(time.perf_counter_ns()-start)/1e6
        assert reranked['status'] in ('ok','ambiguous','no_match')
        assert exact or not reranked['results'] or reranked['provider']['status']=='enabled', 'Model failure is not an NPU candidate'
        truth=truths[question['question_id']]
        rows.append(dict(**question, baseline=baseline, reranked=reranked, exact_cpu_direct=exact,
            baseline_lookup_ms=baseline_ms, reranked_lookup_ms=rerank_ms,
            baseline_metrics=metrics(baseline,truth), reranked_metrics=metrics(reranked,truth)))
    known=[r for r in rows if r['category']!='no_answer_out_of_scope']
    no_answer=[r for r in rows if r['category']=='no_answer_out_of_scope']
    report=dict(schema=1, authored_quality_screen=True, performance_cohort=False, NPU_executed=False,
        native_prefill_decode_acceptance_gain_established=False, main_model_requests_avoided_measured=False,
        source_script_sha256=sha(Path(__file__)), prototype_sha256=sha(PROTO/'code_lookup.py'),
        questions_sha256=sha(DATA/'questions.json'), truth_sha256=sha(DATA/'ground-truth.json'),
        index_generation=index['generation'], preprocessing=PREPROCESSING, model_identity=provider.identity,
        corpus_files=len(index['sources']), chunks=len(index['chunks']), known_questions=len(known),
        no_answer_questions=len(no_answer), session_load_ms=provider.session_load_ms, excluded_model_warmups=1,
        measured_model_pairs=len(provider.rows), rows=rows, pair_scores=provider.rows)
    for arm in ('baseline','reranked'):
        report[arm+'_summary']=dict(file_top3_hits=sum(r[arm+'_metrics']['file_top3_hit'] for r in known),
            span_top3_hits=sum(r[arm+'_metrics']['span_top3_hit'] for r in known),
            expected_spans_found=sum(r[arm+'_metrics']['expected_spans_found'] for r in known),
            expected_spans=sum(r[arm+'_metrics']['expected_spans'] for r in known),
            no_answer_correct=sum(r[arm+'_metrics']['no_answer_correct'] for r in no_answer),
            raw_lookup_median_ms=statistics.median(r[arm+'_lookup_ms'] if arm=='baseline' else r['reranked_lookup_ms'] for r in rows))
    OUT.mkdir()
    model.np.savez(OUT/'feeds.npz', **provider.feeds)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','pair_scores','preprocessing','model_identity')}))

if __name__=='__main__':
    main()
