"""Pure admission for the pinned count1-D, two-output FC shadow candidate.

The caller owns read-only file handles and independently verifies their bytes,
paths and stat identities. This module performs no file/process/device I/O and
imports no numerical or provider runtime. Genuine matching CPU/native/NPU
receipts are required; synthetic offline fixtures never qualify real assets.
Admission proves the narrow frozen FC screen, not native parity, complete D,
head, acceptance, transport, internal kernel execution or speed improvement.
"""
from dataclasses import dataclass, field
import hashlib
import json
import math
import ntpath
import posixpath
import re
import stat
import struct
from types import MappingProxyType

if __package__:
    from .halogen_mtp_fc_coordinator import (
        CanonicalBinding, Observation, QUALIFICATIONS, ShadowCoordinator,
        encode_observation,
    )
else:
    from halogen_mtp_fc_coordinator import (
        CanonicalBinding, Observation, QUALIFICATIONS, ShadowCoordinator,
        encode_observation,
    )


INPUT_SHAPES = (("e_norm", (1, 2560)), ("h_norm", (1, 10240)))
OUTPUT_SHAPES = (("e_projection", (1, 2560)), ("h_projection", (4, 2560)))
WEIGHT_LINEAGE = "BF16-rounded-original-decoded-FP32"
REFERENCE_MODE = "original-GPU-Q8-FC-before-seed-add"
ARITHMETIC = ("original decoded FP32 weights Cast BF16 RNE then Cast FLOAT; FP32 MatMul; "
              "original projection BF16 RNE then FLOAT; RMS and seed-add excluded; "
              "native Q8 affine-FMA decoder and accumulation parity unqualified")
TOLERANCES = MappingProxyType({"cpu": (0.002, 0.0002), "npu": (0.03, 0.003)})
RECEIPT_ROLES = (
    "receipt.assets", "receipt.cpu", "receipt.cpu_profile", "receipt.fixture",
    "receipt.graph", "receipt.native", "receipt.npu", "receipt.npu_context",
    "receipt.npu_profile", "receipt.source_build",
)
BF16_ROLES = tuple(sorted("fixture." + label + "." + branch + "." + kind
                         for label in ("a", "b") for branch in ("e", "h")
                         for kind in ("input", "native", "numpy_original", "numpy_bf16")))
SOURCE_PINS = MappingProxyType({
    "source.native_probe": "7d1f51fd254389906c66b3ce44117fbe889b38b73861d192e4965893f6b0d9b0",
    "source.transformer": "8b4d6b9fab064cb556637398796412cb1ccdd555d56193e20fbc2c57285e0c66",
    "source.builder": "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544",
    "source.projection": "8cabd689422ef07e0d48684e7b2fae8a6d1d71571b17605619f796a33f0b11bd",
    "source.prepare_probe": "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3",
    "source.graph_probe": "43eeebe26cbc0312832dd65a756c030380e13c964e47363c31f5598cb6a2697f",
    "source.expert": "900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722",
    "source.slice": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
    "source.host_frames": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
    "source.native_oracle": "8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826",
})
ASSET_PINS = MappingProxyType({
    "graph.model": "9672f9b98b8b0b0efc10fadb30d0668ee9af25200681fe9b2e421dec97821291",
    "graph.data": "a220218d57d4eb9c5cd7231bd696c394a226da5a529fb51cb8c8cbe5e7be379f",
    "graph.source_model": "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518",
    "receipt.graph": "10b953f75bc7ba23195f8d5616ef6b46bb5a017bf91666ad7e96fb58a58284a6",
    "receipt.source_build": "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99",
    "receipt.assets": "dbf679c94c75439638b01058c2c6915d43dd211c69b27918f7caa77d826e8fb7",
    "receipt.fixture": "ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11",
    "model.checkpoint": "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687",
    "native.engine": "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b",
    "native.codeobject": "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83",
    "native.oracle_binary": "fc631bcc9f8aecbf38ec457704481dea74603cead686c7da2405572d892beaae",
    "fixture.e.raw_weight": "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d",
    "fixture.h.raw_weight": "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f",
    "fixture.a.e.input": "97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892",
    "fixture.a.h.input": "bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34",
    "fixture.b.e.input": "8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce",
    "fixture.b.h.input": "0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711",
})
FIXED_ROLES = tuple(sorted(set(RECEIPT_ROLES) | set(BF16_ROLES) | set(SOURCE_PINS) |
                          set(ASSET_PINS) | {"native.runtime", "provider.library", "provider.catalog_library"}))
DEPENDENCIES = {
    "scripts/benchmarks/halogen_npu_expert_onnx.py": SOURCE_PINS["source.expert"],
    "scripts/benchmarks/hgn_q4c_slice.py": SOURCE_PINS["source.slice"],
    "server/host_frames.py": SOURCE_PINS["source.host_frames"],
    "scripts/benchmarks/halogen_npu_v2_d_prepare.py": SOURCE_PINS["source.builder"],
}
PROBE_DEPENDENCIES = {
    "halogen_npu_v2_d_prepare_probe.py": SOURCE_PINS["source.prepare_probe"],
    "halogen_npu_v2_d_graph_probe.py": SOURCE_PINS["source.graph_probe"],
    "halogen_npu_v2_d_prepare.py": SOURCE_PINS["source.builder"],
    "halogen_npu_v2_d_projection_graph.py": SOURCE_PINS["source.projection"],
    "halogen_npu_v2_d_native_projection_graph.py": SOURCE_PINS["source.transformer"],
}
REQUIRED_OUTPUTS = tuple(sorted(("h_streams", "e_projection_fp32", "h_projection_fp32",
                                 "e_projection_bf16", "e_projection", "h_projection_bf16", "h_projection")))
PROBE_FALSE = ("native_bit_parity_qualified", "seed_add_implemented", "embedding_rms_qualified",
               "full_d_claim", "full_mtp_claim", "acceptance_claim", "generic_speed_promotion",
               "normalization_in_npu_segment", "native_q8_affine_fma_decoder_proved")
GRAPH_FALSE = ("hardware_placement_qualified", "native_q8_parity_qualified", "native_graph_parity_qualified",
               "native_q8_affine_fma_decoder_qualified", "native_accumulation_parity_qualified", "full_d_claim",
               "full_mtp_claim", "acceptance_claim", "speed_promotion", "normalization_in_segment", "seed_add_in_segment")
_SEAL = object()


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("lowercase SHA256 required")
    return value


def _integer(value, minimum=0, maximum=(1 << 64) - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("bounded exact integer required")
    return value


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("finite nonnegative number required")
    return value


def _path(value):
    if type(value) is not str or not value or any(c in value for c in ("\0", "\n", "\r")):
        raise ValueError("absolute stable asset path required")
    drive, tail = ntpath.splitdrive(value)
    if not ((drive and ntpath.isabs(value)) or (value.startswith("/") and posixpath.isabs(value))):
        raise ValueError("absolute asset path required without filesystem resolution")
    if any(part in (".", "..") for part in value.replace("\\", "/").split("/")):
        raise ValueError("asset path contains ambiguous traversal")
    if not tail or value.endswith(("/", "\\")):
        raise ValueError("asset path must name a file")
    return value


def _normal_path(value):
    _path(value)
    return ntpath.normcase(ntpath.normpath(value)) if ntpath.splitdrive(value)[0] else posixpath.normpath(value)


def _same_path(left, right):
    return _normal_path(left) == _normal_path(right)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_equal(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _require(row, expected, label):
    if type(row) is not dict or any(not _equal(row.get(k), v) for k, v in expected.items()):
        raise ValueError(label + " contract differs")


def _freeze(value):
    if type(value) is dict:
        return tuple((key, _freeze(item)) for key, item in sorted(value.items()))
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class AssetDescriptor:
    """Caller-attested, retained read-only file identity; no stat/read occurs here."""
    role: str
    path: str
    sha256: str
    bytes: int
    owned_identity: tuple

    def __post_init__(self):
        if type(self.role) is not str or self.role not in FIXED_ROLES:
            raise ValueError("unknown fixed admission asset role")
        _path(self.path)
        _sha(self.sha256)
        _integer(self.bytes, 1)
        if type(self.owned_identity) is not tuple:
            raise ValueError("immutable owned stat identity required")
        names = []
        for row in self.owned_identity:
            if type(row) is not tuple or len(row) != 2 or type(row[0]) is not str:
                raise ValueError("exact owned stat pair required")
            names.append(row[0])
            _integer(row[1])
        fields = {"st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"}
        if names != sorted(set(names)) or not fields <= set(names) or set(names) - fields - {"st_mode", "st_nlink"}:
            raise ValueError("sorted unique fixed owned stat fields required")
        identity = dict(self.owned_identity)
        if identity["st_size"] != self.bytes:
            raise ValueError("owned extent differs")
        if "st_mode" in identity and not stat.S_ISREG(identity["st_mode"]):
            raise ValueError("owned identity must be a regular file")
        if "st_nlink" in identity and identity["st_nlink"] != 1:
            raise ValueError("multiply linked asset refused")


@dataclass(frozen=True)
class PinnedReceipt:
    asset: AssetDescriptor
    payload: bytes

    def __post_init__(self):
        if type(self.asset) is not AssetDescriptor or type(self.payload) is not bytes:
            raise ValueError("exact descriptor and immutable payload required")
        if len(self.payload) != self.asset.bytes or hashlib.sha256(self.payload).hexdigest() != self.asset.sha256:
            raise ValueError("independently pinned payload extent/hash differs")


Bf16Payload = PinnedReceipt


def descriptors_from_manifest(mapping):
    """Convert an already parsed, independently pinned plan; never read paths."""
    if type(mapping) is not dict or set(mapping) != {"schema", "assets", "receipts", "bf16_payloads"}:
        raise ValueError("fixed admission manifest fields required")
    _require(mapping, {"schema": "halogen-mtp-fc-admission-manifest.v1"}, "admission manifest")
    if (type(mapping["assets"]) is not list or type(mapping["receipts"]) is not list or type(mapping["bf16_payloads"]) is not list or
            any(type(role) is not str for role in mapping["receipts"] + mapping["bf16_payloads"]) or
            not _equal(sorted(mapping["receipts"]), list(RECEIPT_ROLES)) or not _equal(sorted(mapping["bf16_payloads"]), list(BF16_ROLES))):
        raise ValueError("complete fixed receipt/BF16 role lists required")
    descriptors = []
    for row in mapping["assets"]:
        if type(row) is not dict or set(row) != {"role", "path", "sha256", "bytes", "owned_identity"} or type(row["owned_identity"]) is not dict:
            raise ValueError("exact manifest asset descriptor fields required")
        descriptors.append(AssetDescriptor(row["role"], row["path"], row["sha256"], row["bytes"], tuple(sorted(row["owned_identity"].items()))))
    assets = tuple(sorted(descriptors, key=lambda asset: asset.role))
    _asset_map(assets)
    return assets


def _asset_map(assets):
    if type(assets) is not tuple or any(type(asset) is not AssetDescriptor for asset in assets):
        raise ValueError("immutable exact asset descriptors required")
    rows = {asset.role: asset for asset in assets}
    if len(rows) != len(assets) or tuple(sorted(rows)) != FIXED_ROLES:
        raise ValueError("complete unique fixed asset roles required; real gates absent")
    for role, digest in {**SOURCE_PINS, **ASSET_PINS}.items():
        if rows[role].sha256 != digest:
            raise ValueError("pinned raw-Q8/source/graph lineage differs: " + role)
    return rows


def _holders(holders, roles, assets):
    if type(holders) is not tuple or any(type(row) is not PinnedReceipt for row in holders):
        raise ValueError("immutable pinned byte holders required")
    rows = {row.asset.role: row for row in holders}
    if len(rows) != len(holders) or set(rows) != set(roles):
        raise ValueError("complete exact pinned payload roles required")
    if any(row.asset != assets[role] for role, row in rows.items()):
        raise ValueError("payload descriptor differs from retained asset identity")
    return rows


def _json(holder, limit=16 << 20):
    if type(holder) is not PinnedReceipt or not 0 < len(holder.payload) <= limit:
        raise ValueError("bounded exact pinned JSON receipt required")
    # Holders have checked SHA/extent before parsing, even for malformed JSON.
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("duplicate receipt JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite receipt JSON constant: " + value)
    def floating(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite receipt JSON number")
        return parsed
    try:
        return json.loads(holder.payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid bounded receipt JSON") from exc


@dataclass(frozen=True)
class ProbeFacts:
    provider: str
    receipt: AssetDescriptor
    canonical_receipt: bytes
    executed_node_providers: tuple
    node_events: int
    stable_output_hashes: tuple
    input_hashes: tuple
    provider_copy_files: tuple = ()
    provider_library: str = ""
    cache_key: str = ""
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._seal is not _SEAL:
            raise ValueError("ProbeFacts requires complete pinned receipt admission")

    @property
    def output_hashes(self):
        return tuple((label, dict(hashes)["e_projection"], dict(hashes)["h_projection"])
                     for label, hashes in self.stable_output_hashes)

    @property
    def required_hardware_partition_outputs(self):
        return REQUIRED_OUTPUTS

    @property
    def dependency_sha256(self):
        return tuple(sorted(DEPENDENCIES.items()))

    @property
    def probe_dependency_sha256(self):
        return tuple(sorted(PROBE_DEPENDENCIES.items()))


@dataclass(frozen=True)
class PreparedAssets:
    assets: tuple
    receipts: tuple
    bf16_payloads: tuple
    cpu_facts: ProbeFacts
    npu_facts: ProbeFacts
    model_binding: CanonicalBinding
    graph_binding: CanonicalBinding
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._seal is not _SEAL:
            raise ValueError("PreparedAssets requires complete pinned receipt admission")

    @property
    def assets_by_role(self):
        return MappingProxyType({asset.role: asset for asset in self.assets})

    def asset(self, role):
        return self.assets_by_role[role]

    @property
    def input_shapes(self):
        return INPUT_SHAPES

    @property
    def output_shapes(self):
        return OUTPUT_SHAPES

    @property
    def qualifications(self):
        return QUALIFICATIONS


@dataclass(frozen=True)
class ShadowAdmission:
    prepared: PreparedAssets
    observation: Observation
    epoch: bytes
    model_binding: CanonicalBinding
    graph_binding: CanonicalBinding
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._seal is not _SEAL:
            raise ValueError("ShadowAdmission requires live identity binding")

    @property
    def cpu_facts(self):
        return self.prepared.cpu_facts

    @property
    def npu_facts(self):
        return self.prepared.npu_facts

    @property
    def qualifications(self):
        return QUALIFICATIONS

    def coordinator(self):
        return ShadowCoordinator(self.observation, epoch=self.epoch,
                                 model_assets=self.model_binding, graph_assets=self.graph_binding)


def _file_binding(row, asset, shape=None, float_sha=None):
    _require(row, {"sha256": asset.sha256, "bytes": asset.bytes}, "bound file")
    if not _same_path(row.get("path"), asset.path):
        raise ValueError("bound file path differs")
    if shape is not None:
        _require(row, {"shape": list(shape), "float_array_sha256": float_sha}, "bound BF16 file")


def _bf16_arrays(payloads):
    arrays = {}
    for role, holder in payloads.items():
        count = 2560 if ".e." in role else 10240
        if len(holder.payload) != count * 2:
            raise ValueError("fixed BF16 file extent differs")
        words = tuple(word[0] << 16 for word in struct.iter_unpack("<H", holder.payload))
        if any(word & 0x7f800000 == 0x7f800000 for word in words):
            raise ValueError("nonfinite pinned BF16 word")
        widened = struct.pack("<" + "I" * count, *words)
        arrays[role] = (words, tuple(value[0] for value in struct.iter_unpack("<f", widened)), hashlib.sha256(widened).hexdigest())
    return arrays


def _graph_lineage(receipts, assets):
    graph, build, original = receipts["receipt.graph"], receipts["receipt.source_build"], receipts["receipt.assets"]
    _require(graph, {
        "schema": "halogen_v2_count1_D_native_projection_graph.v1", "wire_mode": "D", "count": 1,
        "arithmetic": ARITHMETIC, "weight_lineage": WEIGHT_LINEAGE,
        "transformer_sha256": SOURCE_PINS["source.transformer"], "projection_helper_sha256": SOURCE_PINS["source.projection"],
        "builder_sha256": SOURCE_PINS["source.builder"], "source_model_sha256": assets["graph.source_model"].sha256,
        "source_build_receipt_sha256": assets["receipt.source_build"].sha256,
        "model_sha256": assets["graph.model"].sha256, "data_sha256": assets["graph.data"].sha256,
        "data_bytes": 52480000, "assets_receipt_sha256": assets["receipt.assets"].sha256,
        "original_external_data_unchanged": True, "no_external_weight_copy": True,
        **{key: False for key in GRAPH_FALSE},
    }, "native projection graph")
    for key, role in (("model", "graph.model"), ("data", "graph.data"), ("source_model", "graph.source_model"), ("source_build_receipt", "receipt.source_build")):
        if not _same_path(graph.get(key), assets[role].path):
            raise ValueError("graph path lineage differs")
    if (not _same_path(assets["receipt.graph"].path, assets["graph.model"].path + ".json") or
            _normal_path(ntpath.dirname(assets["graph.model"].path)) != _normal_path(ntpath.dirname(assets["graph.source_model"].path))):
        raise ValueError("graph/source/receipt placement differs")
    _require(build, {"schema": "halogen_v2_count1_D_prepare.v1", "wire_mode": "D", "count": 1,
                     "model_sha256": assets["graph.source_model"].sha256, "data_sha256": assets["graph.data"].sha256,
                     "data_bytes": 52480000, "builder_sha256": SOURCE_PINS["source.builder"],
                     "assets_receipt_sha256": assets["receipt.assets"].sha256}, "source build")
    for key, role in (("model", "graph.source_model"), ("data", "graph.data"), ("assets_receipt", "receipt.assets")):
        if not _same_path(build.get(key), assets[role].path):
            raise ValueError("source build path differs")
    _require(original, {"schema": 1, "data_sha256": build.get("assets_data_sha256")}, "original assets")
    _require(original.get("source"), {"checkpoint_sha256": assets["model.checkpoint"].sha256}, "original checkpoint")
    if original.get("source_identity_after") != original["source"].get("native_identity"):
        raise ValueError("original checkpoint extraction identity differs")
    expected_nodes = []
    for weight in ("W_embedding", "W_hidden"):
        expected_nodes += [dict(name=weight + "_bf16", op_type="Cast", inputs=[weight], outputs=[weight + "_bf16"]),
                           dict(name=weight + "_bf16_widened", op_type="Cast", inputs=[weight + "_bf16"], outputs=[weight + "_bf16_widened"])]
    for name, op, inputs in (
        ("h_streams", "Reshape", ["h_norm", "stream_shape"]),
        ("e_projection_fp32", "MatMul", ["e_norm", "W_embedding_bf16_widened"]),
        ("h_projection_fp32", "MatMul", ["h_streams", "W_hidden_bf16_widened"]),
        ("e_projection_bf16", "Cast", ["e_projection_fp32"]), ("e_projection", "Cast", ["e_projection_bf16"]),
        ("h_projection_bf16", "Cast", ["h_projection_fp32"]), ("h_projection", "Cast", ["h_projection_bf16"]),
    ):
        expected_nodes.append(dict(name=name, op_type=op, inputs=inputs, outputs=[name]))
    _require(graph.get("metadata"), {
        "input_shapes": {name: list(shape) for name, shape in INPUT_SHAPES},
        "output_shapes": {name: list(shape) for name, shape in OUTPUT_SHAPES},
        "output_names": [name for name, _ in OUTPUT_SHAPES], "nodes": expected_nodes,
        "operator_counts": {"Cast": 8, "MatMul": 2, "Reshape": 1},
        "required_hardware_partition_outputs": list(REQUIRED_OUTPUTS),
        "constant_foldable_node_outputs": sorted(node["name"] for node in expected_nodes[:4]),
        "normalization_in_segment": False, "seed_add_in_segment": False,
        "weight_lineage": WEIGHT_LINEAGE, "suffix_nodes_serialized_unchanged": False,
        "native_fc_weight_rounding_modeled": True, "native_q8_affine_fma_decoder_proved": False,
        "projection_output_boundaries_preserved": True, "native_graph_parity_qualified": False,
        "native_accumulation_parity_qualified": False, "projection_helper_sha256": SOURCE_PINS["source.projection"],
    }, "exact two-output graph metadata")
    for role, extent in (("graph.data", 52480000), ("model.checkpoint", 66687678432), ("native.engine", 26052768), ("native.codeobject", 17704408)):
        if assets[role].bytes != extent:
            raise ValueError("pinned asset geometry differs")


def _native_oracle(receipts, assets):
    fixture, native = receipts["receipt.fixture"], receipts["receipt.native"]
    _require(fixture, {"schema": 1, "arithmetic_fitting": False, "tolerance_adjustment": False,
                       "native_hidden_rms_inputs": True, "native_embedding_rms_inputs": False}, "raw fixtures")
    _require(fixture.get("source"), {"checkpoint_sha256": assets["model.checkpoint"].sha256}, "fixture checkpoint")
    identity = fixture.get("source_identity_before")
    if type(identity) is not dict or identity != fixture.get("source_identity_after") or identity != fixture["source"].get("native_identity"):
        raise ValueError("fixture extraction identity differs")
    for name in ("size", "device", "inode", "mtime_ns", "ctime_ns"):
        _integer(identity.get(name))
    if identity["size"] != assets["model.checkpoint"].bytes:
        raise ValueError("fixture checkpoint size differs")
    pins = fixture.get("pins")
    if type(pins) is not dict or pins.get(receipts["receipt.source_build"].get("assets_receipt")) != assets["receipt.assets"].sha256:
        raise ValueError("fixture/original decoded assets lineage differs")
    _require(native, {
        "schema": "halogen0162.original-q8-fc-kernel-replay.v1", "passed": True,
        "engine_sha256": assets["native.engine"].sha256, "codeobject_sha256": assets["native.codeobject"].sha256,
        "runtime_sha256": assets["native.runtime"].sha256, "codeobject_engine_offset": 331776, "codeobject_bytes": 17704408,
        "K": 2560, "N": 2560, "grid": [160, 1, 1], "block": [256, 1, 1], "shared_bytes": 0, "default_stream": True,
        "static_lds_bytes": 0, "wave_size": 32, "kernarg_bytes": 40, "kernarg_alignment": 8, "hidden_arguments": False,
        "user_argument_offsets": [0, 8, 16, 24, 32], "user_argument_types": ["u8*", "u16*", "u16*", "i64", "i64"],
        "q8_group_size": 64, "weight_row_bytes": 2720, "weight_bytes": 6963200, "raw_weights_copied_unchanged": True,
        "native_arithmetic": "affine dequant FMA; decoded-weight BF16 RNE; packed BF16 dot2 FP32 accumulation/reduction; output BF16 RNE",
        "embedding_rms_qualified": False, "full_D_parity_qualified": False, "seed_add_implemented": False,
        "full_head_qualified": False, "acceptance_claim": False, "speed_claim": False, "tolerance_adjustment": False,
        "arithmetic_fitting": False, "logical_calls": 4, "launch_attempts": 4, "launches_ok": 4, "synchronizations_ok": 4,
        "copies_ok": 14, "allocations_ok": 4, "free_ok": 4, "module_loads": 1, "module_unloads": 1,
        "cleanup_errors": 0, "file_close_errors": 0, "immutable_files_rechecked": True, "output_files_written": 4,
        "error": "", "error_code": 0,
    }, "original native Q8 FC oracle")
    kernels = [dict(branch="embedding", symbol="_ZN7halogen12_GLOBAL__N_16k_lq8wILi1ELi16ELi1EEEvPKhPKtPtll", host_identity_rva="0x18d6690", registration_rva="0x184b596", gpu_entry_rva="0x2d1200", descriptor_rva="0x1fa340", M=1),
               dict(branch="hidden", symbol="_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll", host_identity_rva="0x18d66f0", registration_rva="0x184b7be", gpu_entry_rva="0x2d7800", descriptor_rva="0x1fa640", M=4)]
    _require(native, {"kernels": kernels}, "fixed original native kernels")
    if native.get("halogen_lq8_wave") not in ("1", "unset-native-default1"):
        raise ValueError("original native wave selection differs")
    _integer(native.get("runtime_version"), 1)
    _integer(native.get("driver_version"), 1)
    if type(native.get("fixtures")) is not list or len(native["fixtures"]) != 4:
        raise ValueError("four completed original FC fixtures required")
    for branch, full in (("e", "embedding"), ("h", "hidden")):
        weight = fixture.get("raw_weights", {}).get(branch)
        role = "fixture." + branch + ".raw_weight"
        _require(weight, {"file": branch + "-weight.q8g64", "bytes": 6963200, "sha256": assets[role].sha256,
                          "decoded_matches_frozen_external_data": True}, "raw Q8 weight")
        _require(weight.get("entry"), {"name": "mtp.fc_" + full + ".weight", "store": 7, "variant": 0, "rank": 2, "dims": [2560, 2560], "size": 6963200}, "raw Q8 entry")
        if native.get("raw_weight_sha256", {}).get(full) != assets[role].sha256 or assets[role].bytes != 6963200:
            raise ValueError("native raw Q8 weight hash differs")
    for li, label in enumerate(("A", "B")):
        for bi, (branch, full) in enumerate((("e", "embedding"), ("h", "hidden"))):
            prefix = "fixture." + label.lower() + "." + branch + "."
            shape = dict(INPUT_SHAPES)[branch + "_norm"]
            row = fixture.get("inputs", {}).get(label, {}).get(branch)
            _require(row, {"file": label + "-" + branch + "-norm.u16", "shape": list(shape), "bytes": math.prod(shape) * 2, "sha256": assets[prefix + "input"].sha256}, "fixed normalized input")
            streams = 1 if branch == "e" else 4
            _require(native["fixtures"][li * 2 + bi], {
                "id": label + "-" + full, "input_sha256": assets[prefix + "input"].sha256,
                "output_sha256": assets[prefix + "native"].sha256, "output_file": label + "-" + full + "-fc-u16.bin",
                "input_bytes": math.prod(shape) * 2, "output_bytes": math.prod(shape) * 2, "streams": streams,
                "vectors_completed": streams, "output_copied": True, "completed": True, "nonfinite_output": 0,
            }, "completed original native FC fixture")


def _oracle_binding(probe, receipts, assets, arrays):
    binding = probe.get("oracle_binding")
    _require(binding, {"fixture_sha256": assets["receipt.fixture"].sha256, "native_replay_sha256": assets["receipt.native"].sha256,
                       "native_hidden_rms_inputs": True, "native_embedding_rms_inputs": False}, "probe native oracle")
    if not _same_path(binding.get("fixture_path"), assets["receipt.fixture"].path) or not _same_path(binding.get("native_replay_path"), assets["receipt.native"].path):
        raise ValueError("native oracle receipt paths differ")
    for branch in ("e", "h"):
        row = binding.get("raw_weights", {}).get(branch)
        _file_binding(row, assets["fixture." + branch + ".raw_weight"])
        _require(row, {"entry": receipts["receipt.fixture"]["raw_weights"][branch]["entry"], "decoded_matches_frozen_external_data": True}, "native raw weight binding")
    input_hashes = {}
    for label in ("A", "B"):
        input_hashes[label] = {}
        for branch in ("e", "h"):
            name = branch + "_projection"
            prefix = "fixture." + label.lower() + "." + branch + "."
            row = binding.get("normalized_inputs_and_projection_references", {}).get(label, {}).get(name)
            if type(row) is not dict or set(row) != {"input", "native_GPU", "informational"}:
                raise ValueError("both native and separate informational bindings required")
            _file_binding(row["input"], assets[prefix + "input"], dict(INPUT_SHAPES)[branch + "_norm"], arrays[prefix + "input"][2])
            _require(row["input"], {"preparation_provenance": receipts["receipt.fixture"]["inputs"][label][branch]["source"]}, "normalized input provenance")
            _file_binding(row["native_GPU"], assets[prefix + "native"], dict(OUTPUT_SHAPES)[name], arrays[prefix + "native"][2])
            info = row["informational"]
            if type(info) is not dict or set(info) != {"original_decoded_FP32_numpy", "BF16_weight_numpy"}:
                raise ValueError("separate NumPy comparison bindings required")
            old = receipts["receipt.fixture"]["references"][label][branch]
            for mode, kind, record in (("original_decoded_FP32_numpy", "numpy_original", old["bf16"]), ("BF16_weight_numpy", "numpy_bf16", old["bf16_weight_reference"]["bf16"])):
                asset = assets[prefix + kind]
                _require(record, {"bytes": asset.bytes, "sha256": asset.sha256}, "frozen informational reference")
                _file_binding(info[mode], asset, dict(OUTPUT_SHAPES)[name], arrays[prefix + kind][2])
            input_hashes[label][branch + "_norm"] = arrays[prefix + "input"][2]
    _require(probe, {"runtime_input_sets": input_hashes}, "runtime normalized input bytes")
    if any(input_hashes["A"][name] == input_hashes["B"][name] for name, _ in INPUT_SHAPES):
        raise ValueError("both A/B normalized inputs must differ")
    return input_hashes


def _actual_output(row, shape):
    _require(row, {"actual_shape": list(shape), "actual_dtype": "float32"}, "actual FC output")
    numbers, words = row.get("actual_output"), row.get("actual_output_words_u32")
    if type(numbers) is not list or type(words) is not list or len(numbers) != shape[0] or len(words) != shape[0]:
        raise ValueError("two-dimensional actual output records required")
    flat_words, flat_values = [], []
    for values, bits in zip(numbers, words):
        if type(values) is not list or type(bits) is not list or len(values) != shape[1] or len(bits) != shape[1]:
            raise ValueError("actual output row extent differs")
        for value, word in zip(values, bits):
            _integer(word, 0, (1 << 32) - 1)
            if word & 0xffff or word & 0x7f800000 == 0x7f800000:
                raise ValueError("actual output must contain finite BF16-lattice words")
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("finite actual output value required")
            wanted = struct.unpack("<f", struct.pack("<I", word))[0]
            if value != wanted or (value == 0 and math.copysign(1, value) != math.copysign(1, wanted)):
                raise ValueError("actual numeric output differs from retained words")
            flat_words.append(word)
            flat_values.append(wanted)
    packed = struct.pack("<" + "I" * len(flat_words), *flat_words)
    if hashlib.sha256(packed).hexdigest() != _sha(row.get("output_sha256")):
        raise ValueError("actual output bytes/hash differs")
    return tuple(flat_words), tuple(flat_values)


def _f32(value):
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        return math.copysign(math.inf, value)


def _comparison(row, actual, reference, tolerance, *, must_pass):
    """Rederive the pinned probe's NumPy float32 isclose/count/error contract."""
    words, values = actual
    ref_words, ref_values, _ = reference
    rtol, atol = tolerance
    # NumPy 2.5.3 keeps Python tolerance scalars weak: float32 array
    # multiplication/addition first converts each scalar to float32.
    rtol32, atol32 = _f32(rtol), _f32(atol)
    differences = [abs(_f32(value - expected)) for value, expected in zip(values, ref_values)]
    mismatches = sum(delta > _f32(_f32(rtol32 * abs(expected)) + atol32) for delta, expected in zip(differences, ref_values))
    maximum = max(differences)
    if not math.isfinite(maximum):
        raise ValueError("nonfinite comparison error")
    expected = dict(passed=mismatches == 0, tolerance={"rtol": rtol, "atol": atol},
                    exact_BF16_word_mismatches=sum(a != b for a, b in zip(words, ref_words)),
                    max_abs_error=float(maximum), mismatched_elements=mismatches,
                    elements=len(words), non_BF16_lattice_elements=0)
    _require(row, expected, "rederived FC comparison")
    if must_pass and mismatches:
        raise ValueError("frozen native FC tolerance screen failed")
    return expected["exact_BF16_word_mismatches"] == 0


def _calls(probe, provider, arrays):
    calls = probe.get("calls")
    if type(calls) is not list or len(calls) != 12:
        raise ValueError("exact four warmups/eight balanced FC calls required")
    stable, exact = {}, True
    for index, row in enumerate(calls):
        label = "A" if index % 2 == 0 else "B"
        _require(row, {"call_index": index, "input_set": label, "warmup": index < 4, "passed": True, "output_stability_passed": True}, "FC replay call")
        for key in ("host_call_ms", "prepare_and_copy_ms", "session_run_ms"):
            _number(row.get(key))
        outputs = row.get("outputs")
        if type(outputs) is not dict or set(outputs) != dict(OUTPUT_SHAPES).keys():
            raise ValueError("both FC outputs required on every call")
        hashes = {}
        for name, shape in OUTPUT_SHAPES:
            output = outputs[name]
            actual = _actual_output(output, shape)
            prefix = "fixture." + label.lower() + "." + name[0] + "."
            exact = _comparison(output.get("native_comparison"), actual, arrays[prefix + "native"], TOLERANCES[provider], must_pass=True) and exact
            information = output.get("independent_numpy_comparisons")
            if type(information) is not dict or set(information) != {"original_decoded_FP32_numpy", "BF16_weight_numpy"}:
                raise ValueError("separate informational comparisons required")
            for mode, kind in (("original_decoded_FP32_numpy", "numpy_original"), ("BF16_weight_numpy", "numpy_bf16")):
                _comparison(information[mode], actual, arrays[prefix + kind], TOLERANCES["cpu"], must_pass=False)
            hashes[name] = output["output_sha256"]
        if label in stable and stable[label] != hashes:
            raise ValueError("same-label paired FC outputs changed during replay")
        stable.setdefault(label, hashes)
    changed = {name: stable["A"][name] != stable["B"][name] for name, _ in OUTPUT_SHAPES}
    if not all(changed.values()):
        raise ValueError("both alternating FC outputs must change")
    _require(probe, {"alternating_input_output_checks": changed, "exact_native_FC_word_parity_on_frozen_inputs": exact}, "derived replay stability")
    return stable


def _profile(events, provider):
    if type(events) is not list or any(type(event) is not dict for event in events):
        raise ValueError("raw profile event array required")
    nodes = [event for event in events if event.get("cat") == "Node"]
    if not nodes or any(type(event.get("args")) is not dict for event in nodes):
        raise ValueError("executed node provider events required")
    providers = sorted({event["args"].get("provider", "<missing>") for event in nodes})
    ops = sorted({event["args"].get("op_name", "<missing>") for event in nodes})
    expected = "VitisAIExecutionProvider" if provider == "npu" else "CPUExecutionProvider"
    if providers != [expected] or any(type(op) is not str or op == "<missing>" for op in ops):
        raise ValueError("every executed node must use the requested provider")
    return dict(passed=True, node_events=len(nodes), executed_node_providers=providers, node_event_ops=ops)


def _context(context, cache_key, library):
    if type(context) is not dict or type(context.get("config")) is not dict:
        raise ValueError("raw compiler context required")
    config, defs = context["config"], context.get("metaDef")
    if type(defs) is not list or not defs or any(type(row) is not dict for row in defs):
        raise ValueError("nonempty hardware partitions required")
    covered = set()
    partitions = []
    for row in defs:
        _require(row, {"device": "VAIML"}, "VAIML partition")
        _require(row.get("vaimlParam"), {"deviceName": "stx", "runnerType": "hw"}, "hardware partition")
        for key in ("nodes", "inputs", "outputs", "constantInitializers"):
            values = row.get(key, [])
            if type(values) is not list or any(type(value) is not str for value in values):
                raise ValueError("partition value names required")
        covered.update(row.get("nodes", []))
        partitions.append({key: row.get(key, {} if key == "vaimlParam" else None if key in ("id", "device") else [])
                           for key in ("id", "device", "nodes", "inputs", "outputs", "constantInitializers", "vaimlParam")})
    options = config.get("sessionOptions")
    _require(config, {"cacheKey": cache_key}, "compiler cache")
    _require(options, {"cache_key": cache_key}, "compiler session cache")
    _require(config.get("ort_session_config"), {"session.disable_cpu_ep_fallback": "1"}, "compiler CPU fallback")
    if not _same_path(options.get("library_path"), library):
        raise ValueError("compiler provider library differs")
    passes = config.get("passes")
    if (type(passes) is not list or any(type(row) is not dict for row in passes) or
            not any(row.get("name") == "vaiml_partition" and row.get("vaimlConfig", {}).get("device") == "stx" for row in passes)):
        raise ValueError("stx partition compiler pass required")
    if set(REQUIRED_OUTPUTS) - covered:
        raise ValueError("hardware partitions miss dynamic FC outputs")
    return dict(passed=True, hardware_partitions_only=True, missing_required_outputs=[], cpu_fallback_disabled_in_context=True,
                cache_key_matches=True, provider_library_matches=True, stx_partition_pass=True, partitions=partitions, config_passes=passes)


def _provider_copy(probe, assets):
    library, catalog = assets["provider.library"], assets["provider.catalog_library"]
    if not _same_path(probe.get("provider_library"), library.path) or not _same_path(probe.get("catalog_library"), catalog.path):
        raise ValueError("chosen/catalog provider library path differs")
    _require(probe, {"provider_library_sha256": library.sha256}, "chosen provider DLL")
    if library.sha256 != catalog.sha256 or library.bytes != catalog.bytes:
        raise ValueError("catalog/copied provider DLL differs")
    rows = probe.get("provider_copy_files")
    if type(rows) is not list or not rows:
        raise ValueError("complete provider copy evidence required")
    names, selected = set(), False
    for row in rows:
        if type(row) is not dict or set(row) != {"relative_path", "bytes", "catalog_sha256", "copied_sha256"}:
            raise ValueError("provider copy record fields differ")
        name = row["relative_path"]
        if type(name) is not str or ntpath.isabs(name) or ntpath.splitdrive(name)[0] or not name or any(c in name for c in ("\0", "\r", "\n", ":")) or any(part in ("", ".", "..") for part in name.replace("\\", "/").split("/")):
            raise ValueError("bounded provider copy relative path required")
        normalized = ntpath.normcase(ntpath.normpath(name))
        if normalized in names:
            raise ValueError("duplicate provider copy file")
        names.add(normalized)
        _integer(row["bytes"])
        if _sha(row["catalog_sha256"]) != _sha(row["copied_sha256"]):
            raise ValueError("provider copied file hash differs")
        if _same_path(ntpath.join(ntpath.dirname(library.path), name), library.path):
            _require(row, {"bytes": library.bytes, "catalog_sha256": library.sha256, "copied_sha256": library.sha256}, "selected provider copy")
            selected = True
    if not selected:
        raise ValueError("selected provider DLL absent from copy inventory")
    return tuple((row["relative_path"], row["bytes"], row["catalog_sha256"], row["copied_sha256"]) for row in rows)


def _reserves(probe):
    if probe.get("error") not in (None, "") or probe.get("cleanup_errors", []) != [] or probe.get("reserve_guard_error") is not None:
        raise ValueError("probe error/cleanup/reserve failure")
    samples = probe.get("reserve_samples")
    if type(samples) is not list or len(samples) < 2:
        raise ValueError("continuous reserve samples required")
    admission_samples = 0
    for index, row in enumerate(samples):
        if type(row) is not dict:
            raise ValueError("reserve sample object required")
        _number(row.get("time"))
        physical, commit = _integer(row.get("available_bytes")), _integer(row.get("commit_headroom_bytes"))
        if min(physical, commit) < 18 * (1 << 30) or index == 0 and min(physical, commit) < 22 * (1 << 30):
            raise ValueError("frozen physical/commit reserve breached")
        admission_samples += min(physical, commit) >= 22 * (1 << 30)
        for key in ("committed_bytes", "commit_limit_bytes"):
            if key in row:
                _integer(row[key])
        if "committed_bytes" in row and "commit_limit_bytes" in row and row["commit_limit_bytes"] - row["committed_bytes"] != commit:
            raise ValueError("reserve commit headroom arithmetic differs")
    if admission_samples < 2:
        raise ValueError("initial and pre-session admission reserve evidence absent")


def _probe(provider, receipts, assets, arrays):
    probe = receipts["receipt." + provider]
    rtol, atol = TOLERANCES[provider]
    _require(probe, {
        "schema": "halogen_v2_count1_D_native_projection_probe.v1", "provider": provider,
        "source_sha256": SOURCE_PINS["source.native_probe"], "reference_mode": REFERENCE_MODE, "wire_mode": "D", "count": 1,
        "weight_lineage": WEIGHT_LINEAGE, "tolerance": {"rtol": rtol, "atol": atol}, "tolerance_frozen_before_session": True,
        "session_creations": 1, "warmup_count": 4, "repetitions": 8, "passed": True,
        "native_FC_screen_passed": True, "output_replay_stability_passed": True, "alternating_inputs_changed": True,
        "reference_weights_released_before_session": True, "ort_version": "1.25.2", "numpy_version": "2.5.3",
        "admission_gib": 22, "reserve_gib": 18, "outer_owned_job_guard_required": True, "root_exclusive_serving_state_check_required": True,
        "model_sha256": assets["graph.model"].sha256, "data_sha256": assets["graph.data"].sha256, "data_bytes": assets["graph.data"].bytes,
        "projection_receipt_sha256": assets["receipt.graph"].sha256, "transformer_sha256": SOURCE_PINS["source.transformer"],
        "source_model_sha256": assets["graph.source_model"].sha256, "source_build_receipt_sha256": assets["receipt.source_build"].sha256,
        "fc_fixtures_sha256": assets["receipt.fixture"].sha256, "native_fc_replay_sha256": assets["receipt.native"].sha256,
        "dependency_sha256": DEPENDENCIES, "probe_dependency_sha256": PROBE_DEPENDENCIES,
        "required_hardware_partition_outputs": list(REQUIRED_OUTPUTS), "arithmetic": ARITHMETIC,
        "independent_numpy_comparisons_are_informational": True, **{key: False for key in PROBE_FALSE},
    }, provider + " native projection probe")
    for key, role in (("model", "graph.model"), ("data", "graph.data"), ("projection_receipt", "receipt.graph"), ("source_model", "graph.source_model"), ("source_build_receipt", "receipt.source_build")):
        if not _same_path(probe.get(key), assets[role].path):
            raise ValueError("probe graph path differs")
    _reserves(probe)
    inputs = _oracle_binding(probe, receipts, assets, arrays)
    stable = _calls(probe, provider, arrays)
    profile_role = "receipt." + provider + "_profile"
    if not _same_path(probe.get("profile"), assets[profile_role].path):
        raise ValueError("executed-provider profile path differs")
    _require(probe, {"profile_sha256": assets[profile_role].sha256}, "executed-provider profile")
    proof = _profile(receipts[profile_role], provider)
    _require(probe, {"profile_proof": proof}, "raw executed-provider profile proof")
    providers = probe.get("session_providers")
    if type(providers) is not list or not providers or any(type(name) is not str for name in providers) or len(set(providers)) != len(providers):
        raise ValueError("session provider enumeration required")
    copies, library, cache_key = (), "", ""
    if provider == "cpu":
        if providers != ["CPUExecutionProvider"] or "cpu_gate" in probe:
            raise ValueError("CPU native FC gate session contract differs")
    else:
        if providers[0] != "VitisAIExecutionProvider" or set(providers) - {"VitisAIExecutionProvider", "CPUExecutionProvider"}:
            raise ValueError("NPU session provider contract differs")
        _require(probe.get("cpu_gate"), {"path": assets["receipt.cpu"].path, "sha256": assets["receipt.cpu"].sha256}, "frozen CPU before NPU gate")
        _require(probe, {"provider_unregistered": True, "dll_directory_closed": True, "bootstrap_shutdown": True,
                         "session_disable_cpu_ep_fallback": "1"}, "NPU cleanup/fallback")
        copies = _provider_copy(probe, assets)
        library = assets["provider.library"].path
        cache_key = hashlib.sha256((assets["graph.model"].sha256 + ":" + assets["graph.data"].sha256 + ":" + assets["provider.library"].sha256).encode("ascii")).hexdigest()
        _require(probe, {"cache_key": cache_key, "context_sha256": assets["receipt.npu_context"].sha256}, "fresh hardware context")
        if not _same_path(probe.get("context"), assets["receipt.npu_context"].path):
            raise ValueError("compiler context path differs")
        proof_context = _context(receipts["receipt.npu_context"], cache_key, library)
        _require(probe.get("context_proof"), proof_context, "raw compiler hardware coverage proof")
    return ProbeFacts(provider, assets["receipt." + provider], _canonical(probe), tuple(proof["executed_node_providers"]), proof["node_events"],
                      _freeze(stable), _freeze(inputs), copies, library, cache_key, _SEAL)


def admit_assets(*, assets, receipts, bf16_payloads):
    """Heavy offline proof, before persistent session preparation or discovery.

    No receipt is self-authenticating: root must supply independently verified
    immutable bytes and retained read-only descriptors for this exact pin set.
    Current absent native/CPU/NPU gates therefore always reject admission.
    """
    asset_map = _asset_map(assets)
    json_holders = _holders(receipts, RECEIPT_ROLES, asset_map)
    binary_holders = _holders(bf16_payloads, BF16_ROLES, asset_map)
    parsed = {role: _json(holder, 32768 if role == "receipt.native" else 2 << 20 if role in ("receipt.graph", "receipt.npu_context") else 16 << 20) for role, holder in json_holders.items()}
    arrays = _bf16_arrays(binary_holders)
    _graph_lineage(parsed, asset_map)
    _native_oracle(parsed, asset_map)
    cpu = _probe("cpu", parsed, asset_map, arrays)
    npu = _probe("npu", parsed, asset_map, arrays)
    keys = ("source_sha256", "reference_mode", "model_sha256", "data_sha256", "projection_receipt_sha256", "transformer_sha256",
            "weight_lineage", "fc_fixtures_sha256", "native_fc_replay_sha256", "oracle_binding", "runtime_input_sets",
            "dependency_sha256", "probe_dependency_sha256", "required_hardware_partition_outputs")
    if any(not _equal(parsed["receipt.cpu"].get(key), parsed["receipt.npu"].get(key)) for key in keys):
        raise ValueError("CPU/NPU gates do not bind identical native oracle and source/model/data")
    ordered_assets = tuple(sorted(assets, key=lambda asset: asset.role))
    identity_record = [dict(role=asset.role, path=asset.path, sha256=asset.sha256, bytes=asset.bytes, owned_identity=list(asset.owned_identity)) for asset in ordered_assets]
    identity_hash = hashlib.sha256(_canonical(identity_record)).hexdigest()
    asset_hashes = {role: asset.sha256 for role, asset in asset_map.items() if role not in RECEIPT_ROLES}
    receipt_hashes = {role: asset_map[role].sha256 for role in RECEIPT_ROLES}
    receipt_hashes["asset_identities"] = identity_hash
    model = CanonicalBinding.from_hashes("model", assets=asset_hashes, receipts=receipt_hashes)
    graph = CanonicalBinding.from_hashes("graph", assets=asset_hashes, receipts=receipt_hashes)
    return PreparedAssets(ordered_assets, tuple(json_holders[role] for role in RECEIPT_ROLES), tuple(binary_holders[role] for role in BF16_ROLES), cpu, npu, model, graph, _SEAL)


def bind_shadow_admission(observation, epoch, prepared_assets):
    """Cheap binding within the native arm window; no parsing/large hashing."""
    if type(prepared_assets) is not PreparedAssets or prepared_assets._seal is not _SEAL or type(observation) is not Observation:
        raise ValueError("genuine prepared assets and immutable native discovery required")
    if type(epoch) is not bytes or len(epoch) != 16 or not any(epoch):
        raise ValueError("fresh nonzero immutable 16-byte epoch required")
    observation_hash = hashlib.sha256(encode_observation(observation)).hexdigest()
    live = hashlib.sha256(b"halogen-mtp-fc-live-identity-v1\0" + observation.run_nonce + epoch +
                          struct.pack("<IQQ", observation.pid, observation.starttime, observation.model_pointer) + bytes.fromhex(observation_hash)).hexdigest()
    def binding(base):
        return CanonicalBinding.from_hashes(base.domain, assets={name: value.hex() for name, value in base.assets},
                                            receipts={**{name: value.hex() for name, value in base.receipts}, "native_observation": observation_hash, "live_epoch_identity": live})
    return ShadowAdmission(prepared_assets, observation, epoch, binding(prepared_assets.model_binding), binding(prepared_assets.graph_binding), _SEAL)


admit_shadow_assets = bind_shadow_admission
