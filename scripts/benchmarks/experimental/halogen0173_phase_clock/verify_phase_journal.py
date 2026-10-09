"""Validate paired RAW durations against captured native D records.

--d-records accepts a JSON array (or {'records': [...]}) containing request_id,
prefill_ms, decode_ms, prompt_count and predicted_count, parsed unchanged from D.
No bracket normalization, inference, runtime launch, or clock probe is used.
"""
from pathlib import Path
import argparse, collections, json, math, struct
from launch_phase_clock import ENGINE_SHA
PROVIDER_SHA='972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00'
def validate(journal,d_records=None,require_deferred_arm=False):
    rows=[json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    if not rows or rows[0].get('kind')!='activation':raise ValueError('Activation record missing')
    header=rows[0]
    if header.get('decode_pairing_version')!=2:raise ValueError('Decode ownership pairing v2 required')
    if header.get('engine_sha256')!=ENGINE_SHA or header.get('provider_sha256')!=PROVIDER_SHA or header.get('raw_clock_id')!=4:
        raise ValueError('Engine/provider/RAW binding rejected')
    if header['real_clock_address']-header['provider_base']!=0xd5490:raise ValueError('Real symbol RVA rejected')
    if require_deferred_arm and (header.get('deferred_arm')!=1 or
        not isinstance(header.get('arm_file_device'),int) or header['arm_file_device']<0 or
        not isinstance(header.get('arm_file_inode'),int) or header['arm_file_inode']<=0):
        raise ValueError('Deferred activation with bound arming-file identity required')
    chunks=collections.defaultdict(list);ends={};expected_sequence=1;open_pairs={};consumed=0
    for row in rows[1:]:
        if row.get('kind')!='phase' or row.get('sequence')!=expected_sequence:raise ValueError('Noncontiguous phase journal')
        expected_sequence+=1
        if row['status']!=0:raise ValueError('Native fallback occurred; RAW phase qualification rejected')
        if not isinstance(row['request_id'],int) or isinstance(row['request_id'],bool) or not -(1<<63)<=row['request_id']<(1<<63):
            raise ValueError('Signed native request ID rejected')
        if row['begin']:
            expected=0x1746b3f if row['phase']==1 else 0x17490bb
            if row['phase'] not in [1,2] or row['caller_rva']!=expected or row['pair_id']!=row['sequence']:
                raise ValueError('Unexpected phase begin')
            if row['pair_id'] in open_pairs or any(x['phase']==row['phase'] and
                (x['request_id']==row['request_id'] if row['phase']==2 else
                 (x['object'],x['caller_stack'],x['tid'])==(row['object'],row['caller_stack'],row['tid']))
                for x in open_pairs.values()):
                raise ValueError('Duplicate begin')
            if row['returned_end_ns']!=row['native_start_ns'] or row['raw_end_ns']!=row['raw_start_ns']:
                raise ValueError('Native start return changed')
            if row['begin_object']!=row['object'] or row['observed_native_start_ns']!=row['native_start_ns'] or row['object_native_start_ns']!=0:
                raise ValueError('Begin ownership/native start evidence rejected')
            open_pairs[row['pair_id']]=row;continue
        begin=open_pairs.pop(row['pair_id'],None)
        if begin is None or any(begin[k]!=row[k] for k in ['phase','begin_object','native_start_ns','raw_start_ns','request_id']):
            raise ValueError('Unpaired or mismatched end')
        if row['observed_native_start_ns']!=begin['native_start_ns']:
            raise ValueError('Observed native start differs from active pair')
        if row['phase']==1:
            if any(begin[k]!=row[k] for k in ['object','tid','caller_stack']) or row['object_native_start_ns']!=0:
                raise ValueError('Prefill end changed object/thread/stack')
        elif row['object_native_start_ns']!=begin['native_start_ns']:
            raise ValueError('Moved Decode object does not contain the exact native start')
        consumed+=1
        if row['raw_end_ns']<row['raw_start_ns']:raise ValueError('RAW clock reversal')
        delta=row['raw_end_ns']-row['raw_start_ns']
        if delta!=row['raw_delta_ns'] or row['returned_end_ns']-row['native_start_ns']!=delta:
            raise ValueError('Returned-end/native-start does not equal the measured RAW pair')
        if row['phase']==1:
            if row['caller_rva']!=0x1746f16:raise ValueError('Unexpected Prefill end')
            chunks[row['request_id']].append(row)
        elif row['phase']==2:
            if row['caller_rva']!=0x174ca12 or row['request_id'] in ends:raise ValueError('Unexpected or duplicate Decode end')
            ends[row['request_id']]=row
        else:raise ValueError('Unknown phase')
    if open_pairs:raise ValueError('Unconsumed phase begins remain; journal is not complete')
    if set(chunks)-set(ends):raise ValueError('Prefill chunks lack a completed Decode request')
    requests=[]
    for request_id,row in ends.items():
        prefill_ms=math.fsum(x['raw_delta_ns']/1e6 for x in chunks[request_id])
        stored_ms=struct.unpack('<d',struct.pack('<Q',row['native_prefill_ms_bits']))[0]
        if not math.isfinite(stored_ms) or abs(prefill_ms-stored_ms)>max(1e-7,abs(stored_ms)*2e-14):
            raise ValueError('Stored native Prefill value differs from summed RAW chunk durations')
        requests.append(dict(request_id=request_id,prefill_chunks=len(chunks[request_id]),prefill_ms=stored_ms,
            decode_ms=row['raw_delta_ns']/1e6,prompt_count=row['prompt_count'],predicted_count=row['predicted_count']))
    by_id={r['request_id']:r for r in requests}
    matched=[]
    if d_records is not None:
        source=json.loads(d_records.read_text())
        records=source['records'] if isinstance(source,dict) else source
        if not isinstance(records,list) or not records:raise ValueError('Nonempty native D records required')
        seen=set()
        for d in records:
            rid=d['request_id']
            if rid in seen or rid not in by_id:raise ValueError('Duplicate/unpaired native D request')
            seen.add(rid);raw=by_id[rid]
            if any(not isinstance(d[k],int) or isinstance(d[k],bool) or d[k]<0 or d[k]!=raw[k]
                   for k in ['prompt_count','predicted_count']):
                raise ValueError('Native D token counts differ from the instrumented request')
            for name in ['prefill_ms','decode_ms']:
                value=float(d[name])
                if not math.isfinite(value) or abs(value-raw[name])>0.050000001:
                    raise ValueError('Native D duration differs from RAW duration beyond %.1f rounding')
            matched.append(rid)
        if seen!=set(by_id):raise ValueError('Native D records do not cover every completed instrumented request')
    return dict(schema='halogen0173.phase-raw-verification.v2',engine_sha256=ENGINE_SHA,
        provider_sha256=PROVIDER_SHA,phase_records=len(rows)-1,consumed_pairs=consumed,requests=requests,native_d_matched=matched,
        deferred_arm=bool(header.get('deferred_arm',0)),arm_file_device=header.get('arm_file_device',0),
        arm_file_inode=header.get('arm_file_inode',0),
        decode_pairing_version=2,decode_pairing_identity='unique_active_signed_request_id_and_exact_native_start',
        moved_decode_pairs=sum(row['object']!=row['begin_object'] for row in ends.values()),
        paired_raw_phase_verified=bool(matched),whole_bracket_normalization_used=False,
        instrumentation_is_acceleration=False)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--journal',required=True,type=Path)
    p.add_argument('--d-records',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--require-deferred-arm',action='store_true');args=p.parse_args()
    result=validate(args.journal,args.d_records,args.require_deferred_arm);text=json.dumps(result,indent=2)+'\n'
    if args.out:args.out.write_text(text)
    print(text,end='')
if __name__=='__main__':main()
