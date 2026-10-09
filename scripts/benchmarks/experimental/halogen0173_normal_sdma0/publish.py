"""Archive numeric evidence and owned experiment source without request content."""
import hashlib
import json
from pathlib import Path
import shutil

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
ARCHIVE=ROOT/'scripts/benchmarks/experimental/halogen0173_normal_sdma0'
REPORT=ROOT/'docs/research/halogen0173-normal-sdma0-20261009.md'
EVIDENCE=REPORT.with_suffix('.json')

def ref(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
    result=json.loads((WORK/'analysis.json').read_bytes())
    assert not ARCHIVE.exists() or (ARCHIVE/'README.md').is_file()
    identities={name:json.loads((WORK/name/'identity.json').read_bytes()) for name in ('before','candidate','after')}
    base=identities['before']['manifest']
    for name,item in identities.items():
        m=item['manifest']
        assert m['image']==base['image'] and m['sources']==base['sources']
        changes={key for key in set(m['environment'])|set(base['environment']) if m['environment'].get(key)!=base['environment'].get(key)}
        assert changes==({'HSA_ENABLE_SDMA'} if name=='candidate' else set())
        assert 'bulk_bn64_candidate' not in m
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    sources=[]
    for name in ('prepare.py','launch.py','control.py','window.py','analyze.py','publish.py','finalize.py','plan.md','independent-control-review.md','analyze-source-review.md'):
        source=WORK/name;dest=ARCHIVE/name
        shutil.copyfile(source,dest)
        assert source.read_bytes()==dest.read_bytes()
        sources.append(ref(dest))
    for source,name in [(PREP/'normal-sdma-source-scope-20261009/decision.md','sdma-source-decision.md'),
                        (PREP/'npu-confidence-selector-scope-20261009/decision.md','npu-selector-source-decision.md')]:
        dest=ARCHIVE/name;shutil.copyfile(source,dest);sources.append(ref(dest))
    rows={}
    for name in identities:
        summary=json.loads((WORK/name/'summary.json').read_bytes())
        rows[name]=[{key:row[key] for key in ('rep','phase','wall_seconds','clock_calibration','pp_tps','decode_tps',
                     'observed_minimum_memory_bytes','timings','finish_reason','output_sha256','accepted','drafted','acceptance')} for row in summary['rows']]
    result.update(raw_rows=rows,source_archive=sources,
        current_mapped_runtime=json.loads((WORK/'current-mapped-runtime.json').read_bytes()),
        experiment_manifest_scope=dict(image=base['image'],normal_preloads=base['environment']['LD_PRELOAD'],
             candidate_only_environment_change='HSA_ENABLE_SDMA=0',identical_normal_backend_sources=True,
             same_immutable_runtime_image=True,mapped_ELF_measurement_scope='before arm'),
        identity_hashes={key:identities['before'][key] for key in ('profile_sha256','client_sha256','prompt_sha256','request_sha256')},
        report_scope='bounded configuration screen; no phase-rate clock normalization; no NPU execution')
    EVIDENCE.write_text(json.dumps(result,indent=2),encoding='utf-8')
    table=[]
    for name,item in result['raw_native_arms'].items():
        table.append(f"| {name} | {item['prefill_mean']:.3f} ± {item['prefill_stdev']:.3f} | {item['decode_mean']:.3f} ± {item['decode_stdev']:.3f} | {item['accepted']}/{item['drafted']} | {item['wall_seconds_mean']:.4f} |")
    clocks=result['clocks_three_arms']
    delta=result['raw_deltas']
    report=f"""# Halogen 0.17.3: normal SDMA copy-policy screen

The standard SDMA1 server is restored ready/open. SDMA0 remains an explicit default-off experiment. The full acceleration goal remains active; no NPU gain or universal speed improvement is claimed.

Only `HSA_ENABLE_SDMA=1` changed to `0`. The normal image, backend sources, GPU kernels, model, preloads, API credential, context 262144, one slot, MTP depth 2 / PLD 3,3, prefill chunk and arena 8192 and normal lifecycle stayed fixed. This is distinct from the disabled BN64 adapter and the previous scalar asynchronous hook. The actual mapped baseline HIP/HSA ELF hashes match the pinned SDK 7.14.0 source. Compute blits retain the source's dependencies, completions and system fences, but consume GPU compute resources. [AMD documentation](https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/debugging.html)

Frozen synthetic pseudoprose has 8192 actual input tokens, including 116 repeated calibration units; each request generates 128 ordinary tokens. Cache and Thinking off, temperature 0 / seed 1. Each arm has one excluded warmup and three measurements. These are not new natural-input post benchmarks. Acceptance is combined API MTP/PLD draft-token accounting, not separately isolated MTP acceptance.

| Arm | Native API Prefill tok/s, mean ± SD | Native API Decode tok/s, mean ± SD | Accepted/drafted | Host QPC request seconds, mean |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(table)}

All 12 output hashes and draft-counter pairs match; each measured arm has 210/339=61.946903% acceptance. SDMA0 versus before gives raw mean Prefill{delta['before']['prefill_percent']:+.4f}%/Decode{delta['before']['decode_percent']:+.4f}%; that pair passes its clock gate. Versus after, the raw differences are Prefill{delta['after']['prefill_percent']:+.4f}%/Decode{delta['after']['decode_percent']:+.4f}%, but that comparison fails its clock gate and establishes no regression. A positive mean alone does not prove a causal improvement beyond sample spread.

Measured whole-request MONOTONIC/RAW ranges {clocks['monotonic_per_raw_min']:.9f}..{clocks['monotonic_per_raw_max']:.9f}, relative spread {clocks['relative_spread']:.9g}. RAW/QPC ranges {clocks['raw_per_qpc_min']:.9f}..{clocks['raw_per_qpc_max']:.9f}. The cross-arm 0.1% clock gate is {'passed' if clocks['comparable'] else 'failed'}. Native phase rates remain unchanged API observations; they are not converted to RAW/QPC-derived rates. MONOTONIC advances about 10% faster than RAW in before/candidate and about 0.258% faster in after. These are not independently calibrated absolute token-speed claims. The whole-request probes do not independently establish the ratio inside either phase. QPC request seconds describe the complete request and do not isolate Prefill or Decode. No comparison to the historical 48.42 tok/s workload is made.

Decision: **{result['decision']}**. A small cohort is a screen, not a statistical general-performance proof. Completed windows will not be repeated solely to obtain favorable numbers. Startup and load are excluded from request rates; their original lifecycle evidence remains private. Collection `passed` means successful requests and parity, while clock qualification is checked separately.

All arms passed 22/22 GiB measurement entry and 18/18 GiB runtime reserves, with no observed League/Riot process or unrelated GPU load at each entry. Startup remains 35 GiB physical / 131 GiB commit, with unchanged guards and recovery. Root alone performed all hardware/lifecycle actions. Own clients, clock probes and stop observers are closed; final standard serving remains in its visible PowerShell 5.1 console.

The independent NPU source scope identifies a tiny token-only prefix-survival/offer-width classifier as a different hypothesis. It would select stock offers without splitting target weights or reading GPU logits. Current 0.17.3 lacks a supported, request-generation-safe per-round selection callback and aligned outcome/training feed; instruction addresses alone do not implement that interface. No selector was trained, exported or run on NPU. Native adaptation already uses accepted-prefix EMA/hysteresis. Raising a reported acceptance ratio by truncating offers is not itself a Decode gain.

[Numeric evidence]({EVIDENCE.name}) · [Owned source archive](../../scripts/benchmarks/experimental/halogen0173_normal_sdma0/README.md)
"""
    REPORT.write_text(report,encoding='utf-8')
    (ARCHIVE/'README.md').write_text("# Retained normal SDMA experiment source\n\nThese are byte-preserved executed local controls and source-only reviews. They are provenance, not portable launchers: their original private directory, sealed profile, frozen input and identity receipts are required. Do not run the archive directly or start alongside an engine. The production launcher remains unchanged and SDMA0 stays off. No model, binary, request/answer text or credential is included. The public JSON retains numeric warmup/measured rows and exact clocks.\n",encoding='utf-8')
    print(json.dumps(dict(report=ref(REPORT),evidence=ref(EVIDENCE),source_files=len(sources))))

if __name__=='__main__': main()
