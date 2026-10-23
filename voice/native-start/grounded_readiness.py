"""Read-only bridge to the existing runtime owner; never launches or grants proof.

The consumer owner must implement ConversationRuntime.verify_grounded_stage
before activation. It imports GroundedReadinessProof from this canonical module,
verifies its evidence chain, and returns that type rather than profile JSON.
"""
import asyncio
import hashlib
import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GroundedExpected:
    endpoint: str
    model: str
    source_sha256: tuple
    protocol: str = 'pinned_chat_count_v1'
    route_limits: tuple = (3584, 24)
    planner_limits: tuple = (3072, 128)
    context_parallel: tuple = (4096, 1)
    main_context_parallel: tuple = (32768, 1)
    reserve_gib: int = 18


@dataclass(frozen=True)
class GroundedReadinessProof:
    expected: GroundedExpected
    profile_sha256: str
    owner_pid: int
    owner_created: int | float  # Exact existing psutil/owner creation identity; no rounding.
    measured_evidence_sha256: tuple


def expected_grounded(endpoint, model):
    bridge = Path(__file__).resolve().parents[1] / 'native-bridge'
    files = ('route_proposal.py', 'routing_policy.py', 'conversation_router.py',
        'conversation_admission.py', 'grounded_conversation.py', 'task_store.py',
        'task_coordinator.py', 'conversation_output.py', 'native_bridge.py', 'responsive_config.py')
    sources = tuple(('voice/native-bridge/' + name, hashlib.sha256((bridge/name).read_bytes()).hexdigest()) for name in files)
    sources += (('voice/native-start/grounded_readiness.py', hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),)
    return GroundedExpected(endpoint, model, sources)


def _selected_runtime(selection_file, native_config_file):
    # Canonical lazy import also lets the finalizer import this module without
    # circular initialization or a second universe of proof classes.
    name = 'conversation_runtime'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try: spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name].selected_runtime(selection_file, native_config_file)


def validate_proof(proof, expected):
    if type(proof) is not GroundedReadinessProof or proof.expected != expected:
        raise ValueError('grounded readiness proof is missing or bound to different sources')
    def digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
    if (not digest(proof.profile_sha256) or type(proof.owner_pid) is not int or proof.owner_pid <= 0
            or type(proof.owner_created) not in (int, float) or not math.isfinite(proof.owner_created) or not proof.owner_created > 0
            or type(proof.measured_evidence_sha256) is not tuple
            or len(proof.measured_evidence_sha256) != 4
            or any(type(p) is not tuple or len(p) != 2 or not digest(p[1]) for p in proof.measured_evidence_sha256)
            or {p[0] for p in proof.measured_evidence_sha256} != {'admission','grounding','cancellation','coexistence'}):
        raise ValueError('grounded readiness requires verified owner and measured evidence bindings')
    return proof


async def verify_grounded_readiness(selection_file, native_config_file, *, expected):
    def verify():
        runtime = _selected_runtime(selection_file, native_config_file)
        finalizer = getattr(runtime, 'verify_grounded_stage', None)
        if not callable(finalizer):
            raise ValueError('grounded readiness unavailable: reviewed runtime owner must implement verify_grounded_stage and verify admission, grounding, cancellation/release and coexistence evidence')
        # This is the existing synchronous read-only path. 'prepared' proves no
        # running identity. No native HTTP health probe/call reservation cycle.
        if runtime.run(check_only=True) != 'reused':
            raise ValueError('grounded readiness requires an already running verified owner')
        return validate_proof(finalizer(expected), expected)
    return await asyncio.to_thread(verify)
