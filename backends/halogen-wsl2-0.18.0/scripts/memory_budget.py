"""Windows service admission separate from device KV allocation; reserve 18 GiB."""
import math

# Last 126K run: 49.70943 GiB before load, 17.74257 GiB minimum.
# Round its 31.96686 GiB physical decline up, add 2 GiB uncertainty and
# retain 18 GiB Windows physical reserve. KV growth is not charged to
# this pool a second time; device allocation remains independently checked.
HOST_STARTUP_DECLINE_GIB = 32
HOST_UNCERTAINTY_GIB = 2
RUNTIME_RESERVE_GIB = 18

def admission_floors(context, checkpoint='w4b'):
    if type(context) is not int or not 4096 <= context <= 262144:
        raise ValueError('Context must be 4096..262144')
    if checkpoint not in ('w4b','v2'): raise ValueError('Unknown checkpoint')
    if checkpoint == 'v2':
        # Explicitly selected v2 startup admission; runtime reserve and
        # total-commit admission remain independently enforced.
        physical = 35
    else:
        physical = HOST_STARTUP_DECLINE_GIB + HOST_UNCERTAINTY_GIB + RUNTIME_RESERVE_GIB
    # Keep the existing conservative total-commit estimate until new runs
    # provide measured evidence for both checkpoints. Commit is not RAM.
    kv_commit_gib = (context - 4096) * 32768 / (1024 ** 3)
    commit = max(117, math.ceil(100.247 + 4 + RUNTIME_RESERVE_GIB + kv_commit_gib))
    return physical, commit
