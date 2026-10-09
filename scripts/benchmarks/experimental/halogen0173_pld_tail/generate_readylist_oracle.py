"""Build future-label oracle records from retained *committed* raw-ID suffixes.

Only the root may use the output for consumer measurement. This is neither a
real drafter nor held-out acceptance evidence. No model/inference is imported.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

HERE=Path(__file__).resolve().parent
RUNTIME='af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
RECORD=struct.Struct('<IIiiI3i3i64i')
assert RECORD.size==300

def next_committed(rows,start,width):
    before=rows[start];n=before['context_total'];old=before['context_suffix']
    for after in rows[start+1:]:
        if any(after[k]!=before[k] for k in ('session_nonce','owner_birth','slot_cookie','slot_epoch')):
            continue
        if not after['context_available']:continue
        delta=after['context_total']-n
        if delta<=0:continue
        future=after['context_suffix']
        if delta>len(future):return None
        overlap=min(len(old),len(future)-delta)
        if overlap==0 or old[-overlap:]!=future[:len(future)-delta][-overlap:]:return None
        if delta>=width:return future[len(future)-delta:len(future)-delta+width]
    return None

def prepare_rows(decoded,allowed):
    assert decoded['header']['runtime_sha256']==RUNTIME
    assert decoded['dataset_complete'] and decoded['summary']['gaps']==0
    assert decoded['summary']['dropped_cumulative']==0
    rows=decoded['rows'];records=[];skipped={}
    for at,row in enumerate(rows):
        if row['source']!='pld':continue
        width=row['offer_total'];stock=row['offer_ids']
        reason=None
        if not row['context_available'] or width not in (2,3) or len(stock)!=width:reason='shape'
        proposal=None if reason else next_committed(rows,at,width)
        if not reason and proposal is None:reason='no_complete_future_raw_ids'
        if not reason and proposal[0]!=stock[0]:reason='stock_opening_mismatch'
        if not reason and any(token not in allowed for token in proposal):reason='nonordinary_or_undefined_id'
        if reason:skipped[reason]=skipped.get(reason,0)+1;continue
        suffix=row['context_suffix']
        assert 0<len(suffix)<=64 and suffix[-1]==row['current_id']
        records.append((row['context_total'],len(suffix),row['model_position'],row['current_id'],width,
            *(stock+[0]*(3-width)),*(proposal+[0]*(3-width)),*(suffix+[0]*(64-len(suffix)))))
    records.sort()
    # An ambiguous identical frontier must not pick whichever future label was
    # seen first. Collapse identical answers; drop conflicting oracle records.
    unique={};ambiguous=set()
    for record in records:
        key=record[:8]+record[11:]
        if key in unique and unique[key][8:11]!=record[8:11]:ambiguous.add(key)
        else:unique[key]=record
    records=sorted(record for key,record in unique.items() if key not in ambiguous)
    assert len(records)<=4096
    return records,skipped,len(ambiguous)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decoded',type=Path,required=True)
    parser.add_argument('--target-tokenizer-json',type=Path,required=True)
    parser.add_argument('--model-sha256',required=True)
    parser.add_argument('--tokenizer-sha256',required=True)
    args=parser.parse_args()
    model=bytes.fromhex(args.model_sha256);tokenizer_sha=bytes.fromhex(args.tokenizer_sha256)
    assert len(model)==len(tokenizer_sha)==32 and any(model) and any(tokenizer_sha)
    tokenizer_bytes=args.target_tokenizer_json.read_bytes()
    assert hashlib.sha256(tokenizer_bytes).digest()==tokenizer_sha,'exact tokenizer file pin required'
    tokenizer=json.loads(tokenizer_bytes)
    defined=set(tokenizer['model']['vocab'].values())
    special=set()
    for token in tokenizer.get('added_tokens',[]):
        defined.add(token['id'])
        if token.get('special'):special.add(token['id'])
    allowed=defined-special
    assert allowed and min(allowed)>=0 and max(allowed)<262144
    mask=bytearray(32768)
    for token in allowed:mask[token//8]|=1<<(token%8)
    decoded_bytes=args.decoded.read_bytes();decoded=json.loads(decoded_bytes)
    records,skipped,ambiguous=prepare_rows(decoded,allowed)
    header=struct.pack('<8sII',b'H0PLDOT1',1,len(records))+bytes.fromhex(RUNTIME)+model+tokenizer_sha
    payload=header+b''.join(RECORD.pack(*row) for row in records)
    (HERE/'oracle-readylist.bin').write_bytes(payload)
    (HERE/'allowed_ids.bin').write_bytes(mask)
    receipt={'schema':'halogen0173.pld-tail.oracle.v1','future_label_oracle':True,
        'real_external_drafter':False,'real_npu_integration':False,'model_execution':False,
        'records':len(records),'changed_tail_records':sum(row[5:8]!=row[8:11] for row in records),
        'skipped':skipped,'ambiguous_frontiers_removed':ambiguous,
        'decoded_sha256':hashlib.sha256(decoded_bytes).hexdigest(),
        'runtime_sha256':RUNTIME,'model_sha256':args.model_sha256,
        'tokenizer_sha256':args.tokenizer_sha256,
        'readylist_sha256':hashlib.sha256(payload).hexdigest(),
        'allowed_mask_sha256':hashlib.sha256(mask).hexdigest(),
        'scope':'Only frozen stock PLD frontiers; a changed trajectory may have no table record and retains stock.'}
    (HERE/'oracle-preparation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
