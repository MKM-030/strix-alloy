"""Recount published native token evidence offline (Python3, standard library)."""
import argparse
import json
import math
import pathlib


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(data):
    terminal = data['terminal']
    require(not terminal['running'] and terminal['pid']==0 and terminal['stopSucceeded'], 'cleanup not verified')
    if 'memory_samples' in data:
        samples = data['memory_samples']
        require(bool(samples), 'memory samples missing')
        available = [m['windows_available_bytes'] for m in samples]
        for sample in data['guard_samples']:
            available.extend(sample[k] for k in ('available_bytes','minimum_available_bytes','current_available_bytes','availableBytes') if k in sample)
        peak = max((dict(utc=m['utc'], **g, combinedBytes=g['dedicatedBytes']+g['sharedBytes'])
                    for m in samples for g in m['gpu']),key=lambda g:g['combinedBytes'])
        require(min(available)==data['minimum_windows_available_bytes'] and peak==data['sampled_gpu_adapter_peak'], 'memory summary mismatch')
        require(max(m['cgroup_peak_bytes'] for m in samples)==data['cgroup_peak_bytes'] and
                max(m['swap_bytes'] for m in samples)==data['sampled_swap_peak_bytes'], 'memory cgroup summary mismatch')
    events = data['native_events']
    require(len({e['pid'] for e in events})==1, 'mixed native clocks')
    require(all(a['monotonic_ns'] <= b['monotonic_ns'] for a,b in zip(events,events[1:])), 'clock order')
    streams = {}
    for label,response in data['responses'].items():
        if not response['completed']:
            continue
        starts = [e for e in events if e['parts'][0]=='G' and e.get('label')==label]
        require(len(starts)==1, 'generation count')
        rid = starts[0]['parts'][1]
        tokens = [e['monotonic_ns'] for e in events if e['parts'][:2]==['T',rid]]
        dones = [e for e in events if e['parts'][:2]==['D',rid]]
        require(len(dones)==1 and len(tokens)>0, 'done/token count')
        d = dones[0]['parts']
        usage,timing = response['usage'],response['timings']
        require(len(tokens)==int(d[4])==usage['completion_tokens'], 'native/API output count mismatch')
        require(int(starts[0]['parts'][2])==int(d[3])==usage['prompt_tokens'], 'prompt count mismatch')
        require(int(d[10])==timing['cache_n']==0, 'cache mismatch')
        require(response['marker_present'] and label in response['content'], 'marker missing')
        require(tokens[0]>starts[0]['monotonic_ns'] and tokens[-1]<=dones[0]['monotonic_ns'], 'token lifecycle')
        require(float(d[5])==timing['prompt_ms'] and float(d[6])==timing['predicted_ms'], 'timing mismatch')
        require(all(math.isfinite(float(d[i])) and float(d[i])>0 for i in (5,6)), 'invalid time')
        streams[label] = dict(tokens=tokens,done=dones[0]['monotonic_ns'],input=usage['prompt_tokens'],
                              output=len(tokens),prefill_tokens_per_second=usage['prompt_tokens']*1000/float(d[5]),
                              whole_generation_tokens_per_second=len(tokens)*1000/float(d[6]))
    measured = {}
    for name,phase in data['phases'].items():
        if phase['classification'] != 'measured':
            require(phase.get('aggregate_tokens_per_second') is None, 'failed phase has rate')
            continue
        require(data['passed'], 'failed run promoted to measured comparison')
        labels = phase['labels']
        require(len(labels)==len(set(labels)) and all(label in streams for label in labels), 'phase stream count')
        ctime = phase['pool']['cache_event_ns']
        snapshots = [e for e in events if e['parts'][0]=='C' and e['monotonic_ns']==ctime]
        require(len(snapshots)==1, 'cache snapshot count')
        raw = snapshots[0]['parts']
        prefix = ('C 0 0 0 0 0 0 0 0 0 0.0 0.0 0.0 0.0 0 0 0.0 '
                  '0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.0 0 0 0').split()
        require(len(raw)==51 and raw[:40]==prefix, 'unknown C layout')
        require(int(raw[44])>=sum(streams[l]['input'] for l in labels) and
                int(raw[46])==len(labels) and int(raw[47])==0, 'pool occupancy')
        first = max(streams[l]['tokens'][0] for l in labels)
        require(ctime>first, 'stale C')
        start = max(first+5_000_000_000,ctime+1_000_000_000)
        end = start+20_000_000_000
        require(data['common_window_seconds']==phase['duration_seconds']==20 and
                (start,end)==(phase['start_ns'],phase['end_ns']), 'window mismatch')
        require(all(streams[l]['done']>end for l in labels), 'early done')
        counts = {l:sum(start<t<=end for t in streams[l]['tokens']) for l in labels}
        rate = sum(counts.values())/20
        require(counts==phase['counts'] and rate==phase['aggregate_tokens_per_second'] and
                {l:counts[l]/20 for l in labels}==phase['per_session_tokens_per_second'], 'window count/rate mismatch')
        measured[name] = dict(counts=counts,aggregate_tokens_per_second=rate)
    return dict(passed=data['passed'],input_tokens=sum(s['input'] for s in streams.values()),
                output_tokens=sum(s['output'] for s in streams.values()),measured_phases=measured,
                sessions={k:{a:b for a,b in v.items() if a not in ('tokens','done')} for k,v in streams.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps(verify(json.loads(args.evidence.read_bytes())),indent=2,allow_nan=False))
