"""Root-owned persistent paired-FC Windows ML responder, deliberately unqualified.

Import is stdlib-only. Preparation requires independently pinned, successful
CPU/NPU admission receipts before Windows ML bootstrap. One prepared session
may bind one fresh native observation/epoch and serve four consume-once calls.
No CPU fallback, provider acquisition, implicit reset, or timing promotion.
"""
from dataclasses import dataclass
import gc
import hashlib
import importlib
import importlib.machinery
import json
import math
import os
from pathlib import Path
import stat
import sys
import threading
import time
from types import MappingProxyType


QUALIFICATIONS = MappingProxyType(dict(
    full_d_qualified=False, full_head_qualified=False, native_parity_qualified=False,
    npu_qualified=False, acceptance_qualified=False, performance_qualified=False,
    transport_qualified=False))
INPUT_SHAPES = MappingProxyType({"e_norm": (1, 2560), "h_norm": (1, 10240)})
OUTPUT_SHAPES = MappingProxyType({"e_projection": (1, 2560), "h_projection": (4, 2560)})
IDENTITY_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
PROVIDER = "VitisAIExecutionProvider"
AUDITED_NAMESPACES = ("numpy", "onnx", "onnxruntime", "winui3", "winrt")


@dataclass(frozen=True)
class FilePin:
    """Independent pin supplied by the root before it opens this runtime window."""
    path: str
    sha256: str
    bytes: int
    owned_identity: tuple


@dataclass(frozen=True)
class ModulePin:
    name: str
    path: str


@dataclass(frozen=True)
class RuntimePlan:
    files: tuple
    modules: tuple
    import_directories: tuple
    provider_directory: str
    work_directory: str
    setup_seconds: float = 300.0
    preparation_call_seconds: float = 30.0
    response_seconds: float = .15
    monitor_seconds: float = .01
    ort_version: str = "1.25.2"
    numpy_version: str = "2.5.3"


@dataclass(frozen=True)
class Hooks:
    """Mandatory outer owner: exclusive window, reserve, process and cancellation.

window_guard() returns exactly True. reserve_check(admission) returns current
available_bytes and commit_headroom_bytes integer values. live_guard() returns
the authoritative native (PID, starttime_ticks). cancel_owned_job(reason)
must cancel this responder's root-owned job, including blocked native calls,
and return exactly True when that cancellation has been accepted.
"""
    window_guard: object
    reserve_check: object
    live_guard: object
    cancel_owned_job: object


def plan_from_mapping(mapping):
    """Pure JSON mapping decoder. Pins must have been independently frozen by root.

    Schema: halogen-mtp-fc-runtime-plan.v1. File identity is a JSON object with
    the five required stat fields (optional st_mode/st_nlink); no auto-pinning.
    """
    required = {"schema", "files", "modules", "import_directories", "provider_directory", "work_directory"}
    optional = {"setup_seconds", "preparation_call_seconds", "response_seconds", "monitor_seconds", "ort_version", "numpy_version"}
    if (type(mapping) is not dict or not required <= mapping.keys() or
            set(mapping) - required - optional or mapping["schema"] != "halogen-mtp-fc-runtime-plan.v1"):
        raise ValueError("fixed runtime-plan mapping schema required")
    files, modules = [], []
    if any(type(mapping[name]) is not list for name in ("files", "modules", "import_directories")):
        raise ValueError("runtime-plan inventories require JSON arrays")
    for row in mapping["files"]:
        if type(row) is not dict or set(row) != {"path", "sha256", "bytes", "owned_identity"} or type(row["owned_identity"]) is not dict:
            raise ValueError("exact frozen runtime file descriptor required")
        files.append(FilePin(row["path"], row["sha256"], row["bytes"], tuple(sorted(row["owned_identity"].items()))))
    for row in mapping["modules"]:
        if type(row) is not dict or set(row) != {"name", "path"} or any(type(row[key]) is not str or not row[key] for key in row):
            raise ValueError("exact frozen module name/origin required")
        modules.append(ModulePin(row["name"], row["path"]))
    if len({pin.name for pin in modules}) != len(modules):
        raise ValueError("duplicate module origin pin")
    if any(type(value) is not str or not value for value in mapping["import_directories"]):
        raise ValueError("frozen import directories require nonempty paths")
    if any(type(mapping[name]) is not str or not mapping[name] for name in ("provider_directory", "work_directory")):
        raise ValueError("frozen provider/work directories required")
    return RuntimePlan(tuple(files), tuple(modules), tuple(mapping["import_directories"]),
                       mapping["provider_directory"], mapping["work_directory"],
                       **{key: mapping[key] for key in optional if key in mapping})


def _path(value):
    return os.path.normcase(str(Path(value).resolve(strict=True)))


class _HeldFile:
    def __init__(self, pin):
        self.pin, self.stream = pin, None
        if (type(pin.sha256) is not str or len(pin.sha256) != 64 or
                any(c not in "0123456789abcdef" for c in pin.sha256) or
                type(pin.bytes) is not int or pin.bytes < 0 or
                type(pin.owned_identity) is not tuple):
            raise ValueError("file pin requires exact SHA256, extent and identity")
        entries = dict(pin.owned_identity)
        if (tuple(sorted(entries.items())) != pin.owned_identity or
                not set(IDENTITY_FIELDS) <= entries.keys() or
                set(entries) - set(IDENTITY_FIELDS) - {"st_mode", "st_nlink"} or
                any(type(v) is not int or v < 0 for v in entries.values()) or
                entries["st_size"] != pin.bytes):
            raise ValueError("file pin identity differs from the fixed contract")
        self.identity = entries
        original = Path(pin.path).absolute()
        original_info = original.stat(follow_symlinks=False)
        if stat.S_ISLNK(original_info.st_mode) or getattr(original_info, "st_file_attributes", 0) & 0x400:
            raise ValueError("pinned file path cannot be a symlink/reparse entry")
        self.path = original.resolve(strict=True)
        self._regular(self.path.stat(follow_symlinks=False))
        try:
            self.stream = self.path.open("rb")
            self.check(full=True)
        except BaseException:
            if self.stream is not None:
                self.stream.close()
            raise

    def _regular(self, info):
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError("asset must be a regular single-link non-reparse file")
        if any(getattr(info, name, None) != value for name, value in self.identity.items()):
            raise ValueError("retained file identity changed: " + str(self.path))

    def check(self, full=False):
        self._regular(os.fstat(self.stream.fileno()))
        self._regular(self.path.stat(follow_symlinks=False))
        if full:
            self.stream.seek(0)
            digest = hashlib.sha256()
            total = 0
            for block in iter(lambda: self.stream.read(1 << 20), b""):
                total += len(block)
                digest.update(block)
            if total != self.pin.bytes or digest.hexdigest() != self.pin.sha256:
                raise ValueError("retained file bytes differ: " + str(self.path))
            self._regular(os.fstat(self.stream.fileno()))
            self._regular(self.path.stat(follow_symlinks=False))

    def read(self, maximum):
        if self.pin.bytes > maximum:
            raise ValueError("bounded retained receipt/fixture is too large")
        self.check()
        self.stream.seek(0)
        value = self.stream.read(maximum + 1)
        if len(value) != self.pin.bytes or hashlib.sha256(value).hexdigest() != self.pin.sha256:
            raise ValueError("retained receipt/fixture differs from its exact pin")
        self.check()
        return value


class _WindowWatch:
    """Runs concurrently with native code; post-call checks alone are insufficient."""
    def __init__(self, owner, seconds, run_options=None, live=False):
        self.owner, self.run_options, self.live = owner, run_options, live
        self.seconds = seconds
        self.deadline = time.monotonic() + seconds
        self.done = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._watch, name="paired-FC-deadline", daemon=True)
        # Independent timer: a blocked root guard must not defer ORT termination.
        self.timer = threading.Thread(target=self._deadline_watch, name="paired-FC-timer", daemon=True)

    def _trip(self, reason):
        if self.run_options is not None:
            try:
                self.run_options.terminate = True
            except BaseException as terminate_error:
                self.owner._cleanup_errors.append("RunOptions terminate: " + str(terminate_error))
        self.owner._fail(reason)

    def _deadline_watch(self):
        remaining = max(0.0, self.deadline - time.monotonic())
        if not self.done.wait(remaining):
            self._trip("paired FC native deadline expired")

    def _watch(self):
        try:
            while not self.done.is_set():
                if time.monotonic() >= self.deadline:
                    raise TimeoutError("paired FC native deadline expired")
                self.owner._external_check(live=self.live)
                self.ready.set()
                self.done.wait(self.owner.plan.monitor_seconds)
        except BaseException as exc:
            self._trip("watchdog: " + type(exc).__name__ + ": " + str(exc))
            self.ready.set()

    def __enter__(self):
        self.timer.start()
        self.thread.start()
        try:
            if not self.ready.wait(min(2.0, self.seconds)):
                self.owner._fail("watchdog did not start")
                raise RuntimeError("paired FC watchdog did not start")
            self.owner._healthy()
        except BaseException:
            self.done.set()
            self.thread.join(2.0)
            self.timer.join(2.0)
            if self.thread.is_alive() or self.timer.is_alive():
                self.owner._cleanup_errors.append("failed-entry watchdog did not stop")
            raise
        return self

    def __exit__(self, exc_type, exc, trace):
        self.done.set()
        self.thread.join(2.0)
        self.timer.join(2.0)
        if self.thread.is_alive() or self.timer.is_alive():
            self.owner._fail("watchdog did not stop; outer cancellation required")
            raise RuntimeError("paired FC watchdog did not stop")
        if exc_type is None:
            if time.monotonic() >= self.deadline:
                self.owner._fail("paired FC deadline elapsed before result admission")
            self.owner._healthy()


class PersistentFcResponder:
    """Use prepare(), bind() exactly once, callback(request), then checked close()."""
    def __init__(self, plan, hooks):
        if type(plan) is not RuntimePlan or type(hooks) is not Hooks:
            raise ValueError("frozen RuntimePlan and mandatory root Hooks required")
        if any(not callable(getattr(hooks, name)) for name in Hooks.__dataclass_fields__):
            raise ValueError("all root-owned hooks are mandatory")
        for name, upper in (("setup_seconds", 600), ("preparation_call_seconds", 60),
                            ("response_seconds", .18), ("monitor_seconds", .05)):
            value = getattr(plan, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= upper:
                raise ValueError("bounded positive runtime deadline required: " + name)
        if plan.monitor_seconds > plan.response_seconds / 2:
            raise ValueError("watchdog must sample within the response deadline")
        if any(type(getattr(plan, name)) is not tuple for name in ("files", "modules", "import_directories")):
            raise ValueError("runtime pins and import paths must be frozen tuples")
        self.plan, self.hooks = plan, hooks
        self._state_lock, self._call_lock = threading.RLock(), threading.Lock()
        self._failure, self._closed, self._bound = None, False, None
        self._held, self._assets, self._modules = {}, {}, {}
        self._cleanup_errors, self._calls, self._next = [], [], 0
        self._session = self._ort = self._np = self._runtime = self._dll = None
        self._registered = self._profile_finished = self._prepared = False
        self._setup_attempted = False
        self._proof, self._admission = {}, None

    @property
    def qualifications(self):
        return QUALIFICATIONS

    @property
    def preparation_evidence(self):
        return json.loads(json.dumps(self._proof, allow_nan=False))

    def _healthy(self):
        if self._closed or self._failure is not None:
            raise RuntimeError("responder unavailable: " + str(self._failure or "closed"))

    def _fail(self, reason):
        with self._state_lock:
            first = self._failure is None
            if first:
                self._failure = str(reason)
        if first:
            try:
                if self.hooks.cancel_owned_job(self._failure) is not True:
                    raise RuntimeError("root cancellation was not acknowledged")
            except BaseException as exc:
                self._cleanup_errors.append("external cancellation: " + type(exc).__name__ + ": " + str(exc))

    def _external_check(self, admission=False, live=False):
        self._healthy()
        if self.hooks.window_guard() is not True:
            raise RuntimeError("root exclusive serving/NPU window is no longer valid")
        row = self.hooks.reserve_check(admission)
        minimum = (22 if admission else 18) * (1 << 30)
        if (not isinstance(row, dict) or any(type(row.get(name)) is not int or row[name] < minimum
                for name in ("available_bytes", "commit_headroom_bytes"))):
            raise RuntimeError("physical or commit reserve below required GiB")
        if live:
            expected = (self._bound.observation.pid, self._bound.observation.starttime)
            actual = self.hooks.live_guard()
            if type(actual) is not tuple or len(actual) != 2 or any(type(v) is not int or v <= 0 for v in actual) or actual != expected:
                raise RuntimeError("live native PID/starttime differs from admitted discovery")

    def _files_check(self, full=False):
        for held in self._held.values():
            held.check(full=full)

    def _hold(self, pin):
        key = _path(pin.path)
        if key in self._held:
            old = self._held[key].pin
            if (old.sha256, old.bytes, old.owned_identity) != (pin.sha256, pin.bytes, pin.owned_identity):
                raise ValueError("conflicting immutable pins for one file")
        else:
            self._held[key] = _HeldFile(pin)
        return self._held[key]

    def _module(self, name):
        pins = [pin for pin in self.plan.modules if type(pin) is ModulePin and pin.name == name]
        if len(pins) != 1 or _path(pins[0].path) not in self._held:
            raise ValueError("exact independently hashed module origin required: " + name)
        # Resolve parents with PathFinder, which does not execute their __init__.
        # Every concrete package initializer must already have a retained pin.
        search = sys.path
        parts = name.split(".")
        for index in range(len(parts)):
            prefix = ".".join(parts[:index + 1])
            spec = importlib.machinery.PathFinder.find_spec(prefix, search)
            if spec is None:
                raise ValueError("pinned module cannot be located: " + prefix)
            if spec.origin is not None:
                origin = _path(spec.origin)
                if origin not in self._held:
                    raise ValueError("package/module origin was not pinned before import: " + prefix)
                self._held[origin].check()
                loaded = sys.modules.get(prefix)
                if loaded is not None and (not getattr(loaded, "__file__", None) or _path(loaded.__file__) != origin):
                    raise ValueError("resident package/module origin differs: " + prefix)
            if index == len(parts) - 1 and (spec.origin is None or _path(spec.origin) != _path(pins[0].path)):
                raise ValueError("resolved module origin differs before import: " + name)
            search = spec.submodule_search_locations
            if index < len(parts) - 1 and search is None:
                raise ValueError("pinned module parent must be a package")
        module = importlib.import_module(name)
        if not getattr(module, "__file__", None) or _path(module.__file__) != _path(pins[0].path):
            raise ValueError("imported runtime/helper origin differs: " + name)
        self._held[_path(module.__file__)].check(full=True)
        self._modules[name] = module
        self._audit_namespace_origins()
        return module

    def _audit_namespace_origins(self):
        """Loaded concrete origins only; complete native dependency proof is external.

        Every retained file was fully hashed before imports. These subsequent
        origin checks use fd/path identities, never pin newly discovered bytes.
        """
        for name, module in tuple(sys.modules.items()):
            if not any(name == prefix or name.startswith(prefix + ".") for prefix in AUDITED_NAMESPACES):
                continue
            if module is None:
                raise ValueError("runtime namespace contains an unresolved module: " + name)
            origin = getattr(module, "__file__", None)
            spec = getattr(module, "__spec__", None)
            if origin is None:
                locations = getattr(spec, "submodule_search_locations", None)
                if spec is None or spec.origin is not None or locations is None or not tuple(locations):
                    raise ValueError("runtime module has no attestable concrete/namespace origin: " + name)
                continue  # A namespace package has no executable initializer.
            key = _path(origin)
            held = self._held.get(key)
            if held is None:
                raise ValueError("preloaded/transitive runtime module origin was not independently pinned: " + name)
            if spec is not None and spec.origin is not None and _path(spec.origin) != key:
                raise ValueError("runtime module file and loader origin differ: " + name)
            held.check()

    def _read_asset(self, role, maximum):
        return self._assets[role].read(maximum)

    def _fact_pins(self, facts):
        for name, digest in facts.dependency_sha256 + facts.probe_dependency_sha256:
            matches = [held for held in self._held.values()
                       if held.path.name == Path(name).name and held.pin.sha256 == digest]
            if len(matches) != 1:
                raise ValueError("admitted source dependency lacks one retained exact pin: " + name)
        catalog = self._assets["provider.catalog_library"].path.parent
        copied = Path(self.plan.provider_directory).resolve(strict=True)
        for relative, extent, source_sha, copy_sha in facts.provider_copy_files:
            for base, digest in ((catalog, source_sha), (copied, copy_sha)):
                child = (base / relative).resolve(strict=True)
                if not child.is_relative_to(base):
                    raise ValueError("provider-copy file escapes admitted directory")
                held = self._held.get(_path(child))
                if held is None or (held.pin.sha256, held.pin.bytes) != (digest, extent):
                    raise ValueError("provider-copy inventory lacks exact retained pin")

    def prepare(self, prepared_assets):
        """Create/warm one persistent session before the native discovery pause."""
        self._healthy()
        if self._setup_attempted:
            raise RuntimeError("preparation cannot retry; close/recreate in a new owned window")
        self._setup_attempted = True
        if not self._call_lock.acquire(blocking=False):
            self._fail("preparation cannot be concurrent")
            raise RuntimeError("exclusive preparation required")
        lock_held = True
        previous_path = list(sys.path)
        try:
            self._external_check(admission=True)
            with _WindowWatch(self, self.plan.setup_seconds):
                for asset in prepared_assets.assets:
                    if asset.role in self._assets:
                        raise ValueError("duplicate admitted asset role")
                    self._assets[asset.role] = self._hold(asset)
                for pin in self.plan.files:
                    if type(pin) is not FilePin:
                        raise ValueError("runtime/source pins must be exact FilePin values")
                    self._hold(pin)
                if _path(__file__) not in self._held:
                    raise ValueError("independently pinned responder source required before bootstrap")
                self._audit_namespace_origins()
                for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                    if os.environ.get(name) != "1":
                        raise ValueError("root must set BLAS/OpenMP environment before process startup")
                sys.path[:0] = [str(Path(p).resolve(strict=True)) for p in self.plan.import_directories]
                self._module("halogen_mtp_fc_wire")
                self._module("halogen_mtp_fc_coordinator")
                admission = self._module("halogen_mtp_fc_admission")
                if type(prepared_assets) is not admission.PreparedAssets:
                    raise ValueError("factory-created PreparedAssets required")
                receipts = tuple(admission.PinnedReceipt(asset, self._read_asset(asset.role, 16 << 20))
                                 for asset in prepared_assets.assets if asset.role.startswith("receipt."))
                binaries = tuple(admission.PinnedReceipt(asset, self._read_asset(asset.role, 20480))
                                 for asset in prepared_assets.assets if asset.role.startswith(("fixture.a.", "fixture.b.")))
                verified = admission.admit_assets(assets=prepared_assets.assets, receipts=receipts, bf16_payloads=binaries)
                if verified != prepared_assets:
                    raise ValueError("retained admission no longer matches prepared asset facts")
                self._admission = verified
                if verified.input_shapes != tuple(INPUT_SHAPES.items()) or verified.output_shapes != tuple(OUTPUT_SHAPES.items()):
                    raise ValueError("admitted immutable shape contract differs")
                self._fact_pins(verified.cpu_facts)
                self._fact_pins(verified.npu_facts)
                # These imports are deferred until all arithmetic/provider receipts pass.
                np = self._np = self._module("numpy")
                self._module("onnx")
                self._module("hgn_q4c_slice")
                helper = self._module("halogen_npu_expert_onnx")
                proof_helper = self._module("halogen_npu_v2_d_prepare_probe")
                bootstrap = self._module("winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap")
                winml = self._module("winui3.microsoft.windows.ai.machinelearning")
                self._files_check()
                self._external_check(admission=True)
                self._audit_namespace_origins()
                self._runtime = bootstrap.initialize()
                self._audit_namespace_origins()
                providers = [ep for ep in winml.ExecutionProviderCatalog.get_default().find_all_providers() if ep.name == PROVIDER]
                if len(providers) != 1 or providers[0].ready_state != winml.ExecutionProviderReadyState.READY:
                    raise RuntimeError("installed READY VitisAI required; acquisition is disabled")
                ep = providers[0]
                if _path(ep.library_path) != _path(self._assets["provider.catalog_library"].path):
                    raise ValueError("active catalog provider differs from admitted library")
                chosen, records = helper.verified_provider_copy(ep.library_path, self.plan.provider_directory)
                normalized = tuple((r["relative_path"], r["bytes"], r["catalog_sha256"], r["copied_sha256"]) for r in records)
                if normalized != verified.npu_facts.provider_copy_files or _path(chosen) != _path(self._assets["provider.library"].path):
                    raise ValueError("complete provider-copy inventory differs from admitted NPU receipt")
                ort = self._ort = self._module("onnxruntime")
                if ort.__version__ != self.plan.ort_version or np.__version__ != self.plan.numpy_version:
                    raise ValueError("frozen runtime versions differ")
                directory = Path(self.plan.work_directory).absolute()
                directory.mkdir(exist_ok=False)
                cache = directory / "vitisai-cache"
                cache.mkdir(exist_ok=False)
                cache_key = hashlib.sha256((self._assets["graph.model"].pin.sha256 + ":" +
                    self._assets["graph.data"].pin.sha256 + ":" + self._assets["provider.library"].pin.sha256).encode("ascii")).hexdigest()
                self._dll = os.add_dll_directory(str(chosen.parent))
                ort.register_execution_provider_library(PROVIDER, str(chosen))
                self._registered = True
                devices = [d for d in ort.get_ep_devices() if d.ep_name == PROVIDER and str(d.device.type).endswith(".NPU")]
                if len(devices) != 1:
                    raise RuntimeError("exactly one actual catalog VitisAI NPU device required")
                options = ort.SessionOptions()
                options.intra_op_num_threads = 1
                options.enable_profiling = True
                options.profile_file_prefix = str(directory / "paired-fc")
                options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
                options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
                self._external_check(admission=True)
                self._audit_namespace_origins()
                self._session = ort.InferenceSession(str(self._assets["graph.model"].path), sess_options=options, enable_fallback=False)
                self._audit_namespace_origins()
                self._session.disable_fallback()
                for values, shapes in ((self._session.get_inputs(), INPUT_SHAPES), (self._session.get_outputs(), OUTPUT_SHAPES)):
                    if [(v.name, tuple(v.shape), v.type) for v in values] != [(name, shape, "tensor(float)") for name, shape in shapes.items()]:
                        raise RuntimeError("session normalized-input/two-projection shape or dtype differs")
                context = cache / cache_key / "context.json"
                context_payload = self._generated_read(context, 2 << 20)
                context_proof = proof_helper.context_proof(json.loads(context_payload), verified.npu_facts.required_hardware_partition_outputs, cache_key, chosen)
                if context_proof.get("passed") is not True:
                    raise RuntimeError("strict hardware/stx coverage of every paired FC output required")
                stable = self._warm()
                profile = Path(self._session.end_profiling())
                self._profile_finished = True
                profile_payload = self._generated_read(profile, 16 << 20)
                profile_proof = proof_helper.profile_proof(json.loads(profile_payload), "npu")
                if profile_proof.get("passed") is not True:
                    raise RuntimeError("all executed warmup nodes must use VitisAI")
                self._audit_namespace_origins()
                self._files_check(full=True)
                self._external_check()
                self._proof = dict(session_creations=1, context=str(context), context_sha256=hashlib.sha256(context_payload).hexdigest(),
                    context_proof=context_proof, profile=str(profile), profile_sha256=hashlib.sha256(profile_payload).hexdigest(),
                    profile_proof=profile_proof, warmup_output_hashes=stable, qualifications=dict(QUALIFICATIONS))
                self._prepared = True
            return self
        except BaseException as exc:
            self._fail("prepare: " + type(exc).__name__ + ": " + str(exc))
            self._call_lock.release()
            lock_held = False
            self.close()
            raise
        finally:
            sys.path[:] = previous_path
            if lock_held:
                self._call_lock.release()

    @staticmethod
    def _generated_read(path, maximum):
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("fresh compiler/profile file must be a bounded regular file")
        with path.open("rb") as stream:
            payload = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        if len(payload) != info.st_size or any(getattr(info, key) != getattr(after, key) for key in IDENTITY_FIELDS):
            raise ValueError("fresh compiler/profile changed while being read")
        return payload

    def _widen(self, raw, shape):
        np = self._np
        if type(raw) is not bytes or len(raw) != math.prod(shape) * 2:
            raise ValueError("exact immutable BF16 input extent required")
        value = (np.frombuffer(raw, dtype="<u2").astype(np.uint32) << np.uint32(16)).view(np.float32).reshape(shape).copy(order="C")
        if not np.isfinite(value).all():
            raise ValueError("normalized BF16 input contains nonfinite values")
        return value

    def _pair(self, outputs):
        np = self._np
        if type(outputs) not in (tuple, list) or len(outputs) != 2:
            raise ValueError("provider must return both projections atomically")
        words = []
        for value, shape in zip(outputs, OUTPUT_SHAPES.values(), strict=True):
            if (type(value) is not np.ndarray or value.dtype != np.float32 or value.shape != shape or
                    not np.isfinite(value).all() or ((value.view(np.uint32) & np.uint32(0xffff)) != 0).any()):
                raise ValueError("projection must be finite FP32 on the exact BF16 lattice")
            words.append((value.view(np.uint32) >> np.uint32(16)).astype("<u2").tobytes(order="C"))
        return self._modules["halogen_mtp_fc_wire"].ProjectionPair(*words)

    def _run(self, feeds, seconds, live=False):
        options = self._ort.RunOptions()
        with _WindowWatch(self, seconds, options, live=live):
            outputs = self._session.run(list(OUTPUT_SHAPES), feeds, options)
            pair = self._pair(outputs)
            self._external_check(live=live)
            return pair

    def _warm(self):
        np = self._np
        stable, wanted = {}, dict((label, (e, h)) for label, e, h in self._admission.npu_facts.output_hashes)
        for index in range(12):
            label = "a" if index % 2 == 0 else "b"
            feeds = {name: self._widen(self._read_asset("fixture." + label + "." + branch + ".input", width * 2), INPUT_SHAPES[name])
                     for name, branch, width in (("e_norm", "e", 2560), ("h_norm", "h", 10240))}
            pair = self._run(feeds, self.plan.preparation_call_seconds)
            hashes = []
            for value, branch, shape in ((pair.e_projection, "e", (1, 2560)), (pair.h_projection, "h", (4, 2560))):
                actual = self._widen(value, shape)
                expected = self._widen(self._read_asset("fixture." + label + "." + branch + ".native", math.prod(shape) * 2), shape)
                if not np.isclose(actual, expected, rtol=.03, atol=.003).all():
                    raise ValueError("frozen original Q8 GPU projection arithmetic gate failed")
                hashes.append(hashlib.sha256(actual.tobytes(order="C")).hexdigest())
            current = tuple(hashes)
            if current != wanted.get(label.upper()) or (label in stable and stable[label] != current):
                raise ValueError("persistent A/B outputs differ from admitted NPU hashes or prior calls")
            stable[label] = current
        if any(stable["a"][i] == stable["b"][i] for i in range(2)):
            raise ValueError("both persistent outputs must distinguish alternating A/B inputs")
        return stable

    def bind(self, shadow_admission):
        self._healthy()
        if not self._prepared or self._bound is not None or not self._call_lock.acquire(blocking=False):
            self._fail("bind requires one unused prepared session")
            raise RuntimeError("one late bind is allowed")
        try:
            admission = self._modules["halogen_mtp_fc_admission"]
            if type(shadow_admission) is not admission.ShadowAdmission or shadow_admission.prepared != self._admission:
                raise ValueError("live arm assets differ from the prepared persistent session")
            verified = admission.bind_shadow_admission(shadow_admission.observation, shadow_admission.epoch, self._admission)
            if verified != shadow_admission:
                raise ValueError("live binding differs from fresh observation/model/epoch admission")
            self._bound = verified
            self._files_check()
            self._external_check(live=True)
            return self
        except BaseException as exc:
            self._fail("bind: " + type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            self._call_lock.release()

    def __call__(self, request):
        self._healthy()
        if not self._call_lock.acquire(blocking=False):
            self._fail("concurrent/reentrant paired FC proposal")
            raise RuntimeError("paired FC proposal cannot be concurrent")
        try:
            if self._bound is None:
                raise RuntimeError("fresh native binding required before callback")
            wire = self._modules["halogen_mtp_fc_wire"]
            if type(request) is not wire.FcRequest:
                raise ValueError("validated immutable FcRequest required")
            identity, bound = request.identity, self._bound
            if (identity.sequence != self._next or self._next >= 4 or identity.run_nonce != bound.observation.run_nonce or
                    identity.epoch != bound.epoch or identity.model_pointer != bound.observation.model_pointer or
                    identity.model_binding != bound.model_binding.digest or identity.graph_binding != bound.graph_binding.digest):
                raise ValueError("proposal differs from armed run/model/epoch/next sequence")
            packet = wire.encode_request(identity, request.e_norm, request.h_norm,
                                         request.native_projections.e_projection, request.native_projections.h_projection)
            if wire.decode_request(packet, expected_identity=identity) != request:
                raise ValueError("callback request input/body bindings differ")
            self._next += 1  # consume before copies/provider call; failures cannot retry.
            started = time.monotonic()
            options = self._ort.RunOptions()
            with _WindowWatch(self, self.plan.response_seconds, options, live=True):
                self._files_check()
                self._external_check(live=True)
                feeds = {"e_norm": self._widen(request.e_norm, INPUT_SHAPES["e_norm"]),
                         "h_norm": self._widen(request.h_norm, INPUT_SHAPES["h_norm"])}
                pair = self._pair(self._session.run(list(OUTPUT_SHAPES), feeds, options))
                self._files_check()
                self._external_check(live=True)
                self._calls.append(dict(sequence=identity.sequence, request_binding=request.request_binding.hex(),
                    input_binding=request.input_binding.hex(), callback_ms=(time.monotonic() - started) * 1000,
                    timing_qualified=False, e_sha256=hashlib.sha256(pair.e_projection).hexdigest(),
                    h_sha256=hashlib.sha256(pair.h_projection).hexdigest()))
                return pair
        except BaseException as exc:
            self._fail("callback: " + type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            self._call_lock.release()

    def callback(self, request):
        """Explicit callback alias for the transport owner."""
        return self(request)

    def close(self):
        """Checked teardown; never unload resources underneath an active native call."""
        if self._closed:
            return self._close_report()
        if not self._call_lock.acquire(blocking=False):
            self._fail("close while native call active; root-owned job must terminate")
            return self._close_report()
        try:
            if self._session is not None and not self._profile_finished:
                try:
                    self._session.end_profiling()
                    self._profile_finished = True
                except BaseException as exc:
                    self._cleanup_errors.append("profile close: " + str(exc))
            self._session = None
            gc.collect()
            if self._registered:
                try:
                    self._ort.unregister_execution_provider_library(PROVIDER)
                    self._registered = False
                except BaseException as exc:
                    self._cleanup_errors.append("provider unregister: " + str(exc))
            if self._dll is not None:
                try:
                    self._dll.close()
                    self._dll = None
                except BaseException as exc:
                    self._cleanup_errors.append("DLL directory close: " + str(exc))
            if self._runtime is not None:
                try:
                    self._runtime()
                    self._runtime = None
                except BaseException as exc:
                    self._cleanup_errors.append("bootstrap shutdown: " + str(exc))
            for held in self._held.values():
                try:
                    held.check(full=True)
                except BaseException as exc:
                    self._cleanup_errors.append("final immutable check: " + str(exc))
                try:
                    held.stream.close()
                except BaseException as exc:
                    self._cleanup_errors.append("retained file close: " + str(exc))
            self._closed = True
            return self._close_report()
        finally:
            self._call_lock.release()

    def _close_report(self):
        return dict(schema="halogen-mtp-fc-persistent-responder.v1", closed=self._closed,
                    cleanup_passed=self._closed and not self._cleanup_errors, cleanup_errors=list(self._cleanup_errors),
                    failure=self._failure, prepared=self._prepared, bound=self._bound is not None,
                    consumed_calls=self._next, calls=list(self._calls), qualifications=dict(QUALIFICATIONS))
