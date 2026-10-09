from pathlib import Path
import hashlib,json,statistics
w=Path('C:/Projects/strix-alloy-clean')
dp=w/'docs/research/halogen0173-selector-pilot-20261009/native-capture/decoded.json'
db=dp.read_bytes();decoded=json.loads(db);rows=decoded['rows']
tp=Path('C:/AI/models/halogen-flashnext/tokenizer/tokenizer.json');tb=tp.read_bytes()
assert hashlib.sha256(tb).hexdigest()=='0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
tok=json.loads(tb);defined=set(tok['model']['vocab'].values());special=set()
for t in tok.get('added_tokens',[]):
 defined.add(t['id'])
 if t.get('special'):special.add(t['id'])
allowed=defined-special
assert decoded['dataset_complete'] and decoded['summary']['gaps']==0 and decoded['summary']['dropped_cumulative']==0
assert decoded['header']['runtime_sha256']=='af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
# FIXED PREDICTOR: only copied pre-Begin suffix and actual stock offer are inputs.
# No outcome, future row, accepted prefix, label, task split or cost is read here.
def propose(h,stock):
 width=len(stock);n=len(h);best=None;checks=0
 if width not in (2,3) or n<6:return stock[:],{'reason':'shape','checks':checks}
 for j in range(3,n-width+1):
  checks+=1
  if h[j-3:j]!=h[-3:] or h[j]!=stock[0]:continue
  block=h[j:j+width]
  if any(x not in allowed for x in block):continue
  match=3
  while match<j and h[j-1-match]==h[n-1-match]:match+=1
  rank=(match,j)
  if best is None or rank>best[0]:best=(rank,block[:])
 if best is None or best[0][0]<=3:return stock[:],{'reason':'no_longer_compatible_match','checks':checks}
 return best[1],{'reason':'longer_compatible_match','match':best[0][0],'index':best[0][1],'checks':checks}
proposals=[]
for at,r in enumerate(rows):
 if r['source']!='pld':continue
 assert r['offer_total']==r['stock_width']==r['attempted']==3 and len(r['offer_ids'])==3
 assert r['context_available'] and len(r['context_suffix'])==64 and r['context_suffix'][-1]==r['current_id']
 assert r['native_allowance']>=3
 draft,meta=propose(r['context_suffix'],r['offer_ids'])
 assert len(draft)==3 and draft[0]==r['offer_ids'][0]
 proposals.append({'at':at,'wire_request_id':r['wire_request_id'],'round':r['round'],'proposal':draft,'stock':r['offer_ids'][:],'changed':draft!=r['offer_ids'],'meta':meta})
assert len(proposals)==96
# Freeze every prediction before evaluating any later committed suffix.
frozen=json.dumps(proposals,sort_keys=True,separators=(',',':')).encode();frozen_sha=hashlib.sha256(frozen).hexdigest()
def next_committed(allrows,start,width):
 before=allrows[start];n=before['context_total'];old=before['context_suffix']
 for after in allrows[start+1:]:
  if any(after[k]!=before[k] for k in ('session_nonce','owner_birth','slot_cookie','slot_epoch')):continue
  if not after['context_available']:continue
  delta=after['context_total']-n
  if delta<=0:continue
  future=after['context_suffix']
  if delta>len(future):return None
  overlap=min(len(old),len(future)-delta)
  if overlap==0 or old[-overlap:]!=future[:len(future)-delta][-overlap:]:return None
  if delta>=width:return future[len(future)-delta:len(future)-delta+width]
 return None
def prefix(draft,label):
 count=0
 for a,b in zip(draft,label):
  if a!=b:break
  count+=1
 return count
scores=[];unavailable=[]
for p in proposals:
 label=next_committed(rows,p['at'],3)
 if label is None:unavailable.append((p['wire_request_id'],p['round']));continue
 base=prefix(p['stock'],label);assert base==rows[p['at']]['accepted_prefix'],'stock prefix differs from complete native outcome'
 score=prefix(p['proposal'],label)
 scores.append({'wire_request_id':p['wire_request_id'],'round':p['round'],'changed':p['changed'],'stock_prefix':base,'candidate_prefix':score,'delta':score-base,'match':p['meta'].get('match')})
assert hashlib.sha256(json.dumps(proposals,sort_keys=True,separators=(',',':')).encode()).hexdigest()==frozen_sha
changed=[x for x in scores if x['changed']]
result={'schema':'read-only.causal-pld64-longer-match-screen.v1','prediction_only_inputs':['copied_pre_begin_committed_suffix64','stock_width3_offer','frozen_ordinary_token_id_set'],'policy':'exact prior trigram; complete prior3-ID continuation; same opening; largest backward match>3; newest tie; preserve width/opening','predictor_uses_future_labels':False,'predictions_frozen_before_scoring':True,'sweeps_or_fit':0,'decoded_sha256':hashlib.sha256(db).hexdigest(),'tokenizer_sha256':hashlib.sha256(tb).hexdigest(),'frozen_prediction_bytes':len(frozen),'frozen_prediction_sha256':frozen_sha,'frontiers':len(proposals),'match_frontiers':sum(x['meta']['reason']=='longer_compatible_match' for x in proposals),'changed_frontiers':sum(x['changed'] for x in proposals),'labelled_frontiers':len(scores),'unavailable_label_frontiers':unavailable,'changed_labelled_frontiers':len(changed),'stock_exact_prefix_total':sum(x['stock_prefix'] for x in scores),'candidate_exact_prefix_total':sum(x['candidate_prefix'] for x in scores),'net_extra_exact_prefix_ids':sum(x['delta'] for x in scores),'improved_frontiers':sum(x['delta']>0 for x in scores),'worsened_frontiers':sum(x['delta']<0 for x in scores),'changed_scores':changed,'max_prior_occurrence_positions_scanned':max(x['meta']['checks'] for x in proposals),'native_rollout_executed':False,'timing_measured':False,'serving_gain_claim':False}
print(json.dumps(result,sort_keys=True))
