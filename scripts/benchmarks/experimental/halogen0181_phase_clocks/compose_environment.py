"""Pure environment composition. Does not launch or inspect a process."""
from pathlib import PurePosixPath
import re


def compose_environment(adapter,*,enabled=False,journal=None,nonce=None,arm_file=None,engine_args=(),environment=None):
    env=dict(environment or {})
    for key in ('ENABLE','JOURNAL','NONCE','ARM_FILE'):env.pop('HGN0181_OBSERVER_'+key,None)
    adapter=str(adapter);preloads=[p for p in env.get('LD_PRELOAD','').replace(':',' ').split() if p!=adapter]
    resident=any(arg=='--resident-gib' or arg.startswith('--resident-gib=') for arg in engine_args)
    if enabled and not resident:
        if not PurePosixPath(adapter).is_absolute() or re.search(r'\s|:',adapter):raise ValueError('Absolute Linux adapter path required')
        if not journal or not PurePosixPath(str(journal)).is_absolute():raise ValueError('Fresh absolute Linux journal required')
        if not re.fullmatch('[0-9a-f]{32}',nonce or ''):raise ValueError('Capture nonce required')
        if arm_file is not None and (not PurePosixPath(str(arm_file)).is_absolute() or str(arm_file)==str(journal)):
            raise ValueError('Distinct fresh absolute arm required')
        preloads.insert(0,adapter);env.update(HGN0181_OBSERVER_ENABLE='1',HGN0181_OBSERVER_JOURNAL=str(journal),HGN0181_OBSERVER_NONCE=nonce)
        if arm_file is not None:env['HGN0181_OBSERVER_ARM_FILE']=str(arm_file)
    if preloads:env['LD_PRELOAD']=' '.join(preloads)
    else:env.pop('LD_PRELOAD',None)
    return env
