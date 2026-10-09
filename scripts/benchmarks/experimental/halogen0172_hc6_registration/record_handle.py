"""Save actual returned session identifiers without inventing completion."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
sys.path.insert(0,str(ROOT/'server'))
from controller import atomic,read
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('role');parser.add_argument('session',type=int)
    parser.add_argument('--exit-code',type=int)
    args=parser.parse_args()
    path=PREP.parent/'continuation-current.json'
    state=read(path)
    current=state.setdefault('active0172_hc6_registration_comparison',{})
    entry=dict(role=args.role,session_id=args.session,scope=WORK.name)
    if args.exit_code is None:
        current[args.role+'_session_id']=args.session
    else:
        entry['exit_code']=args.exit_code
        state.setdefault('terminal_sessions',[]).append(entry)
        current.pop(args.role+'_session_id',None)
    current['utc']=datetime.now(timezone.utc).isoformat()
    state['full_goal_completed']=False
    atomic(path,state)
    print(entry)
