"""Bounded real-frame normal recovery margin. Import is inert; Root executes."""
import copy
import time

PHYSICAL=30.25
COMMIT=131
RUNTIME=18
STABLE_SECONDS=10
MAXIMUM_SECONDS=300
SAMPLE_SECONDS=.25


def wait_for_normal(runtime,*,record_failure,clock=time.monotonic,sleep=time.sleep):
    start=clock();deadline=start+MAXIMUM_SECONDS
    stable_start=None;stable_frames=[];samples=0
    minimum_physical=float('inf');minimum_commit=float('inf')
    while True:
        frame=runtime.ops.host.frame();observed=clock();samples+=1
        physical=frame['available_bytes']/2**30;commit=frame['commit_headroom_bytes']/2**30
        minimum_physical=min(minimum_physical,physical);minimum_commit=min(minimum_commit,commit)
        if physical<RUNTIME or commit<RUNTIME:
            record_failure(frame,physical_floor_gib=RUNTIME,commit_floor_gib=RUNTIME,
                           kind='normal_restore_runtime18',observed_monotonic=observed)
            raise ValueError('18-GiB runtime reserve unavailable during normal restoration margin')
        if observed>deadline:
            record_failure(frame,physical_floor_gib=PHYSICAL,commit_floor_gib=COMMIT,
                           kind='normal_restore_margin_timeout300',observed_monotonic=observed,
                           stable_started_monotonic=stable_start)
            raise ValueError('300-second actual normal restoration margin deadline reached')
        if physical>=PHYSICAL and commit>=COMMIT:
            if stable_start is None:stable_start=observed
            stable_frames.append(dict(observed_monotonic=observed,frame=copy.deepcopy(frame)))
            if observed-stable_start>=STABLE_SECONDS:
                return dict(schema='halogen0203.DNZ-arena2048-normal-restore-margin.v3',
                    required_physical_gib=PHYSICAL,required_commit_gib=COMMIT,
                    runtime_physical_commit_gib=RUNTIME,service_startup_physical_commit_gib=[30,131],
                    stable_seconds_required=STABLE_SECONDS,maximum_seconds=MAXIMUM_SECONDS,
                    started_monotonic=start,finished_monotonic=observed,
                    stable_started_monotonic=stable_start,stable_seconds_observed=observed-stable_start,
                    observed_samples=samples,stable_frames=stable_frames,
                    minimum_physical_gib=minimum_physical,minimum_commit_gib=minimum_commit,
                    passing_check_file_writes=0,new_launch_attempts_performed=0)
        else:stable_start=None;stable_frames=[]
        if observed>=deadline:
            record_failure(frame,physical_floor_gib=PHYSICAL,commit_floor_gib=COMMIT,
                           kind='normal_restore_margin_timeout300',observed_monotonic=observed,
                           stable_started_monotonic=stable_start)
            raise ValueError('300-second actual normal restoration margin deadline reached')
        sleep(min(SAMPLE_SECONDS,deadline-observed))
