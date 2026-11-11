"""One-time source-only v3 materialization from hash-bound reviewed v2 files."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
V2=HERE.parent/'dnz-prefill-capacity8192-v2'


def replace_one(source,old,new):
    if source.count(old)!=1:raise ValueError('Frozen v2 source anchor count differs: '+old[:90])
    return source.replace(old,new)


def write_new(name,data):
    target=HERE/name
    if not target.resolve().is_relative_to(HERE):raise ValueError('Nonprivate source target')
    with target.open('xb') as stream:stream.write(data)


def main():
    raw=(V2/'campaign.py').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='5259cd0cd0bb3cf953963f89e1c7301c296262ce6a8d134a32b123603bfe2b71':
        raise ValueError('Frozen reviewed v2 coordinator differs')
    source=raw.decode()
    source=replace_one(source,"SCHEMA = prep.SCHEMA\n", "SCHEMA = prep.SCHEMA\n"
        "if Path(prep.__file__).resolve().parent != HERE:\n"
        "    raise ValueError('Explicit private v3 preparation import required')\n")
    anchor='def require_execution_seal(binding):\n'
    helper="""RESTORE_MARGIN = load('dnz_arena2048_private_restore_margin', HERE / 'restore_margin.py')


def launch_normal_after_margin(runtime, launch, publish, record_failure, *, wait=None):
    # This is one ordinary launch after a bounded real-frame margin, never a
    # retry trigger for a live launch or observation timeout.
    wait = RESTORE_MARGIN.wait_for_normal if wait is None else wait
    margin = wait(runtime, record_failure=record_failure)
    publish(margin)
    return launch()


"""
    source=replace_one(source,anchor,helper+anchor)
    source=replace_one(source,"HALOGEN_PREFILL_CHUNK='8192', HALOGEN_MAX_TOK='8192')",
                              "HALOGEN_PREFILL_CHUNK='2048', HALOGEN_MAX_TOK='2048')")
    source=replace_one(source,"and env.get('HALOGEN_MAX_TOK') == env.get('HALOGEN_PREFILL_CHUNK') == '8192'",
                              "and env.get('HALOGEN_MAX_TOK') == env.get('HALOGEN_PREFILL_CHUNK') == '2048'")
    source=replace_one(source,"module, reference, collector = support(output, binding)\n",
        "module, reference, collector = support(output, binding)\n"
        "    need(Path(collector.m.__file__).resolve() == HERE / 'measure_helpers.py',\n"
        "         'Explicit v3 private reserve helper import required')\n"
        "    collector.m.configure_failure_capture(output)\n")
    source=replace_one(source,"halogen0203.DNZ-GPU-capacity8192-cohort.v2","halogen0203.DNZ-GPU-arena2048-cohort.v3")
    source=replace_one(source,"NPU_helper=False, capacity_context=8192, actual_input_tokens=case['actual_input_tokens'], output_tokens=128,",
        "NPU_helper=False, capacity_context=8192, paired_prefill_arena=2048, actual_input_tokens=case['actual_input_tokens'], output_tokens=128,")
    source=replace_one(source,"scope='halogen0203_DNZ_GPU_capacity8192_finite'","scope='halogen0203_DNZ_GPU_arena2048_v3_finite'")
    source=replace_one(source,"rollback=rollback, launch=lambda: launch(NORMAL, 'restore-normal', 8840),",
        "rollback=rollback, launch=lambda: launch_normal_after_margin(runtime,\n"
        "                    lambda: launch(NORMAL, 'restore-normal', 8840),\n"
        "                    lambda margin: record.update(normal_restore_margin=margin),\n"
        "                    collector.m.record_admission_failure),")
    source=replace_one(source,'epoch=0x020300D800000001 + index','epoch=0x020300DA00000001 + index')
    write_new('campaign.py',source.encode())
    counter=(V2/'counter_reader.py').read_bytes()
    if hashlib.sha256(counter).hexdigest()!='90b8b10ef2c738a702b73a3e3bb6fba26c0d8e36b7d78f4ae5641409be56bff2':
        raise ValueError('Frozen v2 counter reader changed')
    write_new('counter_reader.py',counter)
    tests=(V2/'test_reused_v1.py').read_bytes().replace(b'tempfile.TemporaryDirectory()',b'tempfile.TemporaryDirectory(dir=HERE)')
    write_new('test_reused_v2.py',tests)


if __name__=='__main__':main()
