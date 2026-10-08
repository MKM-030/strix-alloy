"""Opt-in native ATTN_QS_BT4_OPT=0 computation through the unchanged normal lifecycle."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
BASE = PREP / 'ple0172-native-worker-detour-v1/native_worker_launcher_0172.py'
BASE_SHA = '93076e4e9451d5881900ea86ebb90c0abf10c963823f4c7584315f4af62f78a7'
PROFILE = PREP / 'servicenow-thinking-defaults-20261008/thinking-latest-profile.json'
PROFILE_SHA = 'b5d3692b2623034f5a9c4a5f90b234ba6b792793196963fc0e7b474b3937c839'
PYTHON = ROOT / 'server/.local/venv/Scripts/python.exe'
BACKEND = ROOT / 'backends/halogen-wsl2-0.17.2'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def normal():
    require(hashlib.sha256(BASE.read_bytes()).hexdigest() == BASE_SHA, 'Normal wrapper changed')
    require(hashlib.sha256(PROFILE.read_bytes()).hexdigest() == PROFILE_SHA, 'Frozen profile changed')
    spec = importlib.util.spec_from_file_location('sealed_normal', BASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = argparse.Namespace(mode='stock', launcher_sha256=BASE_SHA, receipt=None)
    receipt = module.load_receipt(args)
    return module, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=('controller', 'service'), default='controller')
    parser.add_argument('--launcher-sha256', required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == args.launcher_sha256,
            'Independent launcher seal changed')
    require(not any(k == 'LD_PRELOAD' or k.startswith(('HG0172_', 'PLE0172_', 'HALOGEN_'))
                    for k in os.environ), 'Inherited experiment environment refused')
    base, receipt = normal()
    if not args.run:
        print(json.dumps(dict(validated=True, launched=False, profile_sha256=PROFILE_SHA,
            candidate={'HALOGEN_ATTN_QS_BT4_OPT': '0'}, mode_v2_unchanged=True)))
        return 0
    require(os.name == 'nt' and Path(sys.executable).resolve() == PYTHON.resolve(),
            'Normal project Python required')
    if args.role == 'service':
        service = base.import_normal('service', BACKEND / 'scripts')
        original = service.build_manifest

        def build(options, attempt, run_id):
            require(normal()[1] == receipt, 'Normal source inventory changed')
            manifest = original(options, attempt, run_id)
            env = manifest['environment']
            expected = {'HALOGEN_CTX': '262144', 'HALOGEN_MTP_DEPTH': '2',
                'HALOGEN_PLD': '3,3', 'HALOGEN_PREFILL_CHUNK': '8192', 'HALOGEN_MAX_TOK': '8192',
                'HALOGEN_PROMPT_CACHE': '0', 'HALOGEN_HOST_RESERVE_GIB': '18'}
            require(manifest['image'] == base.IMAGE and manifest['version'] == '0.17.2'
                and manifest['slots'] == 1 and env.get('LD_PRELOAD') == base.PRELOAD
                and all(env.get(k) == v for k, v in expected.items())
                and manifest['sources'] == receipt['backend_sources'], 'Normal manifest changed')
            require('HALOGEN_ATTN_QS_BT4_OPT' not in env and 'HALOGEN_FLASH_MOE_V2' not in env
                and '_hg_flash_serve' not in env, 'Native candidate controls already present')
            env['HALOGEN_ATTN_QS_BT4_OPT'] = '0'
            manifest['native_attn_bt4_opt_candidate'] = dict(enabled=True,
                launcher_sha256=args.launcher_sha256, engine_sha256=base.ENGINE_SHA,
                controls={'HALOGEN_ATTN_QS_BT4_OPT': '0'}, v2_mode_default_unchanged=True,
                normal_lifecycle=True, extra_preload=False, source_only_eligibility=True)
            return manifest

        service.build_manifest = build
        configuration = json.loads(PROFILE.read_text(encoding='utf-8'))['engine']
        controller = base.import_normal('controller', ROOT / 'server')
        command = controller.halogen_launch_command(configuration, BACKEND)
        require(command[:4] == [str(PYTHON), '-u', '-B', str(BACKEND / 'scripts/service.py')],
                'Normal Python service command changed')
        sys.argv = [command[3]] + command[4:]
        return service.main()
    controller = base.import_normal('controller', ROOT / 'server')
    configuration = json.loads(PROFILE.read_text(encoding='utf-8'))['engine']
    expected_command = controller.halogen_launch_command(configuration, BACKEND)
    original_child = controller.JobChild

    class CandidateChild(original_child):
        def __init__(self, command, *, cwd, env, stdout_path, stderr_path):
            require(list(command) == expected_command and Path(cwd).resolve() == BACKEND.resolve()
                and env.get('ALLOY_MANAGED') == '1' and normal()[1] == receipt,
                'Unexpected normal managed child')
            replacement = [str(PYTHON), '-B', '-u', str(Path(__file__).resolve()),
                '--launcher-sha256', args.launcher_sha256, '--role', 'service', '--run']
            super().__init__(replacement, cwd=cwd, env=env,
                stdout_path=stdout_path, stderr_path=stderr_path)

    controller.JobChild = CandidateChild
    sys.argv = [str(ROOT / 'server/controller.py'), 'run', '--config', str(PROFILE), '--port', '8840']
    return controller.main()


if __name__ == '__main__':
    raise SystemExit(main())
