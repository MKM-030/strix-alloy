"""Opt-in training or sealed read-only matmul plan for the pinned engine."""
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PLAN_ROOT = ROOT / '.local/matmul'
TRAIN_PATH = '/tmp/strix-alloy-matmul.plan'
FROZEN_PATH = '/candidate/frozen-matmul.plan'


def validator():
    path = ROOT / 'scripts/matmul_plan.py'
    spec = importlib.util.spec_from_file_location('alloy_matmul_plan_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(value):
    if type(value) is not dict:
        raise ValueError('Matmul tuning must be an explicit object')
    mode = value.get('mode')
    if mode == 'train':
        if set(value) != {'mode'}:
            raise ValueError('Training uses only the fixed fresh container-local plan path')
        return {'mode': 'train'}
    fields = {'mode', 'path', 'sha256', 'hipblaslt_version', 'wgp_count'}
    if mode != 'frozen' or set(value) != fields:
        raise ValueError('Frozen matmul tuning requires path, SHA256 and runtime header pins')
    if type(value['wgp_count']) is not int or value['wgp_count'] != 20:
        raise ValueError('This pinned gfx1151 experiment requires 20 WGP')
    if type(value['hipblaslt_version']) is not int or not 0 < value['hipblaslt_version'] <= 2147483647:
        raise ValueError('Invalid hipBLASLt runtime version pin')
    if not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ValueError('Frozen plan SHA256 must be lowercase hexadecimal')
    if not isinstance(value['path'], str) or '\x00' in value['path']:
        raise ValueError('Invalid frozen plan path')
    original = Path(value['path'])
    if not original.is_absolute() or not original.is_relative_to(PLAN_ROOT):
        raise ValueError('Frozen plans must be within this backend .local/matmul directory')
    for part in (original, *original.parents):
        info = part.lstat()
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Frozen plan paths cannot use links or reparse points')
    path = original.resolve(strict=True)
    if not path.is_relative_to(PLAN_ROOT.resolve(strict=True)):
        raise ValueError('Frozen plan escapes its owned directory')
    validator().validate_plan(path, expected_architecture='gfx1151',
        expected_wgp_count=value['wgp_count'], expected_hipblaslt_version=value['hipblaslt_version'],
        expected_sha256=value['sha256'], frozen=True)
    return {**value, 'path': str(path)}


def parse(text):
    if not isinstance(text, str) or len(text) > 2048:
        raise ValueError('Matmul tuning JSON exceeds the 2048-character budget')
    def unique(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise ValueError('Duplicate matmul tuning key')
            output[key] = value
        return output
    return validate(json.loads(text, object_pairs_hook=unique))


def environment(value):
    if value is None:
        return {}
    config = validate(value)
    return {'HALOGEN_MATMUL_ALGOS': '8' if config['mode'] == 'train' else '1',
            'HALOGEN_MATMUL_TUNING_FILE': TRAIN_PATH if config['mode'] == 'train' else FROZEN_PATH}


def receipt(value):
    if value is None:
        return None
    config = validate(value)
    if config['mode'] == 'train':
        return {'mode': 'train', 'container_path': TRAIN_PATH, 'algorithms': 8,
                'timing_qualified': False}
    plan = validator().validate_plan(config['path'], expected_architecture='gfx1151',
        expected_wgp_count=config['wgp_count'], expected_hipblaslt_version=config['hipblaslt_version'],
        expected_sha256=config['sha256'], frozen=True)
    return {'mode': 'frozen', 'container_path': FROZEN_PATH, 'algorithms': 1,
            'source': config['path'], 'plan': plan}


def revalidate_receipt(tuning, native_log=None):
    """Recheck a sealed frozen file at launch and reject native refusal logs."""
    if tuning is None or tuning['mode'] != 'frozen':
        return
    seal = tuning['plan']
    config = {'mode': 'frozen', 'path': tuning['source'], 'sha256': seal['sha256'],
              'hipblaslt_version': seal['header']['hipblaslt_version'],
              'wgp_count': seal['header']['wgp_count']}
    validate(config)
    module = validator()
    module.validate_plan(tuning['source'], expected_architecture='gfx1151',
        expected_wgp_count=config['wgp_count'], expected_hipblaslt_version=config['hipblaslt_version'],
        expected_sha256=config['sha256'], expected_identity=seal['identity'], frozen=True)
    if native_log is not None:
        refusals = module.native_diagnostic_refusals(native_log)
        if refusals:
            raise ValueError('Frozen plan refused by native engine: ' + '; '.join(refusals))
