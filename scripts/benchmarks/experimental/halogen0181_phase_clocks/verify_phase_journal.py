"""Offline reader for the unchanged-native0.18.1 observer.

Reports observed durations and incomplete internal overhead only. It NEVER
publishes token rates or qualifies clean serving performance. Complete root
clock calibration and measured A/B/A overhead evidence are required before
any separately reviewed instrumented rate claim (see OVERHEAD-PROTOCOL.md).
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import struct

ENGINE_SHA='d946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab'
PROVIDER_SHA='972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00'
RETURNS={(1,1):0x181870f,(1,0):0x1818d60,(2,1):0x181a8dc,(2,0):0x181e7c2}


def require(value,message):
    if not value:raise ValueError(message)


def integer(value,message,minimum=None):
    require(type(value) is int and (minimum is None or value>=minimum),message)
    return value


def verify_records(rows,d_rows=None,*,api_sha256=None):
    require(type(rows) is list and 1<len(rows)<=4096,'Nonempty bounded phase journal required')
    require(all(type(row) is dict for row in rows),'Journal record must be an object')
    header=rows[0]
    require(header.get('kind')=='activation' and header.get('schema')=='halogen0181.passive-phase.v1','Activation schema rejected')
    require(header.get('engine_sha256')==ENGINE_SHA and header.get('provider_sha256')==PROVIDER_SHA
        and header.get('raw_clock_id')==4 and header.get('default_off')==1 and header.get('native_returns_unchanged')==1,'Engine/provider clock contract rejected')
    require(type(header.get('nonce')) is str and re.fullmatch('[0-9a-f]{32}',header['nonce']),'Capture nonce rejected')
    require(integer(header['real_clock_address'],'Provider address rejected',1)-integer(header['provider_base'],'Provider base rejected',1)==0xd5490,'Provider symbol RVA rejected')
    integer(header['engine_base'],'Engine base rejected',1)
    if header.get('deferred_arm'):
        integer(header['arm_file_inode'],'Arming inode rejected',1);integer(header['arm_file_device'],'Arming device rejected',0)
    opened={};owners={};rid_owner={};prefill_objects={};chunks=collections.defaultdict(list);ends={};started_decode=set();overheads=[];pending=None
    for expected,row in enumerate(rows[1:],1):
        require(integer(row.get('sequence'),'Sequence rejected',1)==expected,'Noncontiguous event sequence')
        require(row.get('status')==0 and row.get('dropped')==0,'Observer failure/drop rejects capture')
        if row.get('kind')=='overhead':
            require(pending is not None and row.get('phase_sequence')==pending['sequence'],'Missing/duplicate overhead binding')
            for k in ('request_epoch','raw_before_ns','raw_after_ns','bookkeeping_done_raw_ns'):
                require(row.get(k)==pending[k],'Overhead endpoint binding differs')
            done=integer(row.get('phase_emit_done_raw_ns'),'Emit clock rejected',1)
            require(done>=pending['bookkeeping_done_raw_ns'],'Emit clock reversed')
            overheads.append(done-pending['raw_after_ns']);pending=None;continue
        require(row.get('kind')=='phase' and pending is None,'Phase/overhead record missing or out of order')
        phase=integer(row.get('phase'),'Phase rejected');begin=integer(row.get('begin'),'Begin flag rejected')
        require((phase,begin) in RETURNS and row.get('caller_rva')==RETURNS[phase,begin],'Endpoint RVA rejected')
        rid=integer(row.get('request_id'),'Signed request ID rejected')
        require(-(1<<63)<=rid<(1<<63),'Signed request ID out of range')
        epoch=integer(row.get('request_epoch'),'Request epoch rejected',1)
        require(owners.get(epoch,rid)==rid and rid_owner.get(rid,epoch)==epoch,'Same-ID/epoch collision rejected')
        owners[epoch]=rid;rid_owner[rid]=epoch
        before=integer(row.get('raw_before_ns'),'RAW before rejected',1);after=integer(row.get('raw_after_ns'),'RAW after rejected',before)
        integer(row.get('bookkeeping_done_raw_ns'),'Bookkeeping clock rejected',after)
        native=integer(row.get('native_return_ns'),'Native clock rejected',0)
        require(row.get('returned_ns')==native,'Changed native return rejected')
        native_start=integer(row.get('native_start_ns'),'Native start rejected',0)
        integer(row.get('object'),'Object rejected',1);integer(row.get('tid'),'Thread identity rejected',1);integer(row.get('caller_stack'),'Stack identity rejected',1)
        pair_id=integer(row.get('pair_id'),'Pair identity rejected',1)
        require(epoch not in ends,'Completed request ID/epoch reused')
        if begin:
            require(pair_id==expected and pair_id not in opened,'Duplicate pair begin')
            require(not any(p['phase']==phase and p['request_epoch']==epoch for p in opened.values()),'Concurrent/duplicate owner phase begin')
            if phase==1:
                require(epoch not in started_decode,'Prefill occurs after Decode started')
                require(prefill_objects.get(epoch,row['object'])==row['object'],'Same-ID Prefill object collision')
                prefill_objects[epoch]=row['object']
            else:
                require(epoch not in started_decode and not any(p['request_epoch']==epoch for p in opened.values()),'Decode duplicates or overlaps open Prefill')
                integer(row.get('prompt_count'),'Decode begin prompt count rejected',0)
                require(integer(row.get('predicted_count'),'Decode begin count rejected',0)==1,'Native Decode begin count differs')
                started_decode.add(epoch)
            require(native==native_start and row.get('observed_native_start_ns')==native_start
                and row.get('object_native_start_ns')==0 and row.get('begin_object')==row['object'],'Begin native ownership differs')
            require(row.get('start_raw_before_ns')==before and row.get('start_raw_after_ns')==after,'Begin RAW copy differs')
            opened[pair_id]=row
        else:
            start=opened.pop(pair_id,None);require(start is not None,'Missing begin')
            for k in ('phase','request_epoch','request_id','native_start_ns','begin_object'):
                require(start[k]==row[k],'End owner/start binding differs')
            require(row.get('start_raw_before_ns')==start['raw_before_ns'] and row.get('start_raw_after_ns')==start['raw_after_ns'],'End RAW start binding differs')
            require(row.get('observed_native_start_ns')==native_start and native>=native_start,'Native start/end reversed or mismatched')
            require(before>=start['raw_after_ns'],'RAW phase reversed or endpoint brackets overlap')
            if phase==1:
                require(all(start[k]==row[k] for k in ('object','tid','caller_stack')) and row.get('object_native_start_ns')==0,'Prefill ownership changed')
            else:require(row.get('object_native_start_ns')==native_start,'Moved Decode native start differs')
            item=dict(native_ms=(native-native_start)/1e6,raw_before_to_before_ms=(before-start['raw_before_ns'])/1e6,
                raw_lower_ms=(before-start['raw_after_ns'])/1e6,raw_upper_ms=(after-start['raw_before_ns'])/1e6,
                begin_sequence=start['sequence'],end_sequence=expected,moved=start['object']!=row['object'])
            if phase==1:chunks[epoch].append(item)
            else:
                prompt=integer(row.get('prompt_count'),'Prompt count rejected',0);predicted=integer(row.get('predicted_count'),'Output count rejected',2)
                require(prompt==start['prompt_count'],'Decode prompt count changed')
                bits=integer(row.get('native_prefill_ms_bits'),'Prefill scalar bits rejected',0);require(bits<(1<<64),'Prefill bits out of range')
                stored=struct.unpack('<d',struct.pack('<Q',bits))[0]
                total=0.0
                for c in chunks[epoch]:total+=c['native_ms']
                require(math.isfinite(stored) and stored>=0 and abs(stored-total)<=max(1e-7,abs(stored)*2e-14),'Moved native Prefill does not equal observed native chunk sum')
                ends[epoch]=dict(request_epoch=epoch,request_id=rid,prompt_count=prompt,predicted_count=predicted,
                    native_prefill_ms=stored,native_decode_ms=item['native_ms'],prefill_chunks=len(chunks[epoch]),
                    decode_begin_predicted_count=start['predicted_count'],observed_decode_count_delta=predicted-start['predicted_count'],
                    raw_prefill_before_to_before_ms=math.fsum(c['raw_before_to_before_ms'] for c in chunks[epoch]),
                    raw_prefill_lower_ms=math.fsum(c['raw_lower_ms'] for c in chunks[epoch]),raw_prefill_upper_ms=math.fsum(c['raw_upper_ms'] for c in chunks[epoch]),
                    raw_decode_before_to_before_ms=item['raw_before_to_before_ms'],raw_decode_lower_ms=item['raw_lower_ms'],raw_decode_upper_ms=item['raw_upper_ms'],moved_decode=item['moved'])
        pending=row
    require(pending is None and not opened,'Incomplete phase/overhead pairs')
    require(ends and set(chunks)<=set(ends) and set(owners)==set(ends),'Unfinished request ownership')
    requests=list(ends.values());matched=False
    if d_rows is not None:
        require(type(d_rows) is list and 2<len(d_rows)<=258 and all(type(d) is dict for d in d_rows),'Bounded completed native D journal required')
        require(type(api_sha256) is str and re.fullmatch('[0-9a-f]{64}',api_sha256),'Explicit expected API source SHA required')
        dh=d_rows[0]
        require(dh.get('kind')=='activation' and dh.get('schema')=='halogen0181.native-d-after-parser.v1'
            and dh.get('nonce')==header['nonce'] and dh.get('api_sha256')==api_sha256,'Native D nonce/source header differs')
        require(dh.get('deferred_arm')==header.get('deferred_arm'),'Native D arming contract differs')
        if header.get('deferred_arm'):
            require(all(dh.get(k)==header.get(k) for k in ('arm_file_device','arm_file_inode')),'Native D arming identity differs')
        completion=d_rows[-1]
        require(completion.get('kind')=='completion' and completion.get('failed') is False
            and type(completion.get('request_count')) is int and completion['request_count']==len(requests),'Native D successful close missing')
        require(len(d_rows)-2==len(requests),'Native D coverage differs')
        for index,(d,r) in enumerate(zip(d_rows[1:-1],requests),1):
            require(d.get('kind')=='native_d' and d.get('sequence')==index and d.get('request_id')==r['request_id'],'Native D order/ID differs')
            require(d.get('stock_parser_fields_unchanged') is True,'Stock parser result was altered')
            parts=d.get('parts')
            require(type(parts) is list and 7<=len(parts)<=64 and all(type(p) is str and len(p)<=128 for p in parts)
                and parts[0]=='D','Copied native D frame rejected')
            require(int(parts[1])==r['request_id'] and parts[2]==d.get('reason')
                and int(parts[3])==r['prompt_count'] and int(parts[4])==r['predicted_count'],'Copied native D identity/count/reason differs')
            for key in ('prompt_count','predicted_count'):require(type(d.get(key)) is int and d[key]==r[key],'Native D count differs')
            for key,part in (('prefill_ms',5),('decode_ms',6)):
                value=d.get(key);require(type(value) in (int,float) and math.isfinite(value)
                    and float(parts[part])==value and abs(value-r['native_'+key])<=0.050000001,'Native D phase differs beyond native0.1ms rounding')
        matched=True
    return dict(schema='halogen0181.passive-phase-verification.v1',engine_sha256=ENGINE_SHA,provider_sha256=PROVIDER_SHA,
        nonce=header['nonce'],api_sha256=api_sha256,native_returns_unchanged=True,phase_pairs_complete=True,native_d_matched=matched,
        journal_consistency_verified=matched,actual_request_evidence_coupled=False,
        observed_instrumented_durations_verified=False,requests=requests,
        measured_endpoint_tail_through_phase_emit_ns=overheads,
        internal_overhead_is_complete=False,unmeasured_overhead=['dispatch/prologue','forwarded chrono wrappers','final overhead-record write/unlock/return','API D companion'],
        measured_overhead_protocol_completed=False,independent_RAW_QPC_calibration_completed=False,
        phase_count_scope_qualified=False,qualified_tok_per_second=None,clean_serving_phase_rates_qualified=False,instrumentation_is_acceleration=False)


def verify_capture_receipt(result,receipt,clock_digest,d_digest,*,artifact_root):
    """Bind actual saved client artifacts, final journals and QPC; never grant rates.

    Root owns the trusted receipt's recording/provenance. Hash equality verifies
    closure, not authentic clock sampling, count scope or overhead qualification.
    """
    require(result['native_d_matched'] and type(receipt) is dict,'Native D closure required before request coupling')
    require(receipt.get('schema')=='halogen0181.actual-capture-coupling.v1' and receipt.get('capture_kind')=='fresh_actual'
        and receipt.get('nonce')==result['nonce'],'Fresh actual capture receipt rejected')
    require(receipt.get('engine_sha256')==ENGINE_SHA and receipt.get('provider_sha256')==PROVIDER_SHA,'Capture image/provider differs')
    require(receipt.get('api_sha256')==result['api_sha256'],'Capture expected API source differs')
    require(receipt.get('clock_journal_sha256')==clock_digest and receipt.get('native_d_journal_sha256')==d_digest,'Final journal hashes differ')
    require(receipt.get('companion_closed') is True and receipt.get('companion_failed') is False
        and receipt.get('api_callable_source_verified') is True,'Completed stock API companion receipt required')
    for key in ('api_sha256','adapter_sha256','source_pins_sha256','profile_manifest_sha256','client_source_sha256'):
        require(type(receipt.get(key)) is str and re.fullmatch('[0-9a-f]{64}',receipt[key]),'Capture source/profile pin rejected')
    entries=receipt.get('requests');require(type(entries) is list and len(entries)==len(result['requests']),'Client request coverage differs')
    root=Path(artifact_root).resolve()
    for entry,request in zip(entries,result['requests']):
        require(type(entry) is dict and all(type(entry.get(k)) is int and entry[k]==request[k]
            for k in ('request_epoch','request_id','prompt_count','predicted_count')),'Client signed ID/epoch/count differs')
        for stem in ('request','reply'):
            relative=entry.get(stem+'_path');digest=entry.get(stem+'_sha256')
            require(type(relative) is str and relative and not Path(relative).is_absolute(),'Relative saved request/reply artifact required')
            path=(root/relative).resolve();require(path.is_relative_to(root),'Request/reply artifact escapes capture folder')
            require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest)
                and hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Actual saved request/reply hash differs')
        start=integer(entry.get('qpc_start_ticks'),'QPC start rejected',0)
        end=integer(entry.get('qpc_complete_ticks'),'QPC complete rejected',start+1)
        hz=integer(entry.get('qpc_frequency_hz'),'QPC frequency rejected',1)
        request['actual_request_qpc_wall_ms']=(end-start)*1000/hz
    result.update(actual_request_evidence_coupled=True,observed_instrumented_durations_verified=True,
        receipt_provenance_requires_root_review=True,api_sha256=receipt['api_sha256'])
    return result


def read_journal(path):
    raw=path.read_bytes();require(len(raw)<=8*1024*1024,'Journal exceeds8MiB bound')
    require(raw.endswith(b'\n'),'Journal has torn final line')
    return [json.loads(line) for line in raw.splitlines() if line],hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--journal',type=Path,required=True)
    parser.add_argument('--native-d',type=Path);parser.add_argument('--api-source',type=Path)
    parser.add_argument('--capture-receipt',type=Path);args=parser.parse_args()
    rows,digest=read_journal(args.journal);ds,dd=(read_journal(args.native_d) if args.native_d else (None,None))
    require(not args.native_d or args.api_source,'--api-source required with --native-d')
    api_digest=hashlib.sha256(args.api_source.read_bytes()).hexdigest() if args.api_source else None
    result=verify_records(rows,ds,api_sha256=api_digest);result.update(clock_journal_sha256=digest,native_d_journal_sha256=dd)
    if args.capture_receipt:
        receipt=json.loads(args.capture_receipt.read_bytes());require(receipt.get('api_sha256')==api_digest,'Capture expected API source differs')
        verify_capture_receipt(result,receipt,digest,dd,artifact_root=args.capture_receipt.parent)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
