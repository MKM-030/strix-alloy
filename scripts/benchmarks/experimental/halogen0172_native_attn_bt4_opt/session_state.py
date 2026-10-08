"""Record observed tool handles; this helper never starts or stops a process."""
import argparse
from datetime import datetime, timezone
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(ROOT / 'server'))
from controller import atomic, read

parser = argparse.ArgumentParser()
parser.add_argument('role')
parser.add_argument('session_id', type=int)
parser.add_argument('phase')
args = parser.parse_args()
path = PREP.parent / 'continuation-current.json'
state = read(path)
entry = state['active0172_native_attn_bt4_opt_comparison']
entry.update(phase=args.phase, last_updated_utc=datetime.now(timezone.utc).isoformat())
entry[args.role + '_session_id'] = args.session_id or None
if args.role.endswith('client'):
    entry['benchmark_session_id'] = args.session_id or None
    state['active_measurement_session'] = (
        dict(kind='exec-session', session_id=args.session_id, role=args.role,
            directory=str(WORK), hardware_owner='/root') if args.session_id else None)
    if state.get('active_session'):
        state['active_session']['benchmark_session_id'] = args.session_id or None
elif args.role == 'candidate-engine':
    entry['engine_session_id'] = args.session_id or None
atomic(path, state)
print('Recorded ' + args.role + ' session ' + str(args.session_id or 'terminal') + ': ' + args.phase)
