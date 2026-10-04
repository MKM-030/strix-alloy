# Paired count1-D FC packet codec

The new `scripts/benchmarks/halogen_mtp_fc_wire.py` implements the paired
packet contract proposed in
[the projection integration plan](halogen-mtp-d-projection-integration-20261004.md).
It uses only the Python standard library and immutable byte records. Model
pointers are opaque uint64 identities; the codec never dereferences them.
The existing complete-MLP packet helper and its magic remain unchanged.

The exact little-endian header is 224 bytes:
`<8sIIiiiIiiiI16s16sQQ32s32s32s32s>`.
Request magic is `HGNFCPQ1`; response magic is `HGNFCPR1`. Version is 1,
count is 1, wire is 68, and both reserved fields are zero. Sequence is 0..3.
ABI position, slot, token and outer position are nonnegative signed32 values.
Run nonce (16 bytes), reset/model epoch (16 bytes), opaque model pointer,
model binding SHA (32 bytes) and graph binding SHA (32 bytes) must be nonzero.

| Packet region | Bytes | Binding |
|---|---:|---|
| Request e_norm then h_norm | 25600 | Input SHA covers these exact bytes |
| Request native e_projection then h_projection | 25600 | Included in complete request SHA |
| Request header plus body | 51424 | Request SHA covers header bytes 0..191 then all 51200 body bytes |
| Response candidate e_projection then h_projection | 25600 | Final SHA covers all 224 header bytes and candidate bytes |
| Response header, body and final SHA32 | 25856 | Every request identity/binding field is echoed; only magic/body-size change |

Embedding arrays occupy 5120 bytes and hidden arrays 20480 bytes. All arrays
are exact little-endian BF16 words and must be finite. Validation returns
neither candidate until the entire paired response, full header echo, digest,
length and both arrays pass.

`FcIdentity` carries all caller identities. `encode_request` takes that identity
and four raw arrays. `decode_request` returns `FcRequest`.
`make_response` takes a complete request and the two candidate arrays;
`validate_response` returns `ProjectionPair`. Decoding/making/validating accept
`expected_identity` for an exact armed coordinator check. A caller without it
performs structural decoding only and has not established live model/epoch
authority. Changed normalized inputs or saved native outputs change the request
binding, so a response for an older body fails even under the same identity.

The coordinator must enforce consume-once sequences and current live epoch,
pointer/model and canonical model/graph qualification manifests. A stateless
codec cannot reject an identical packet consumed twice. No file publication,
persistent responder, device work or provider session is implemented here;
transport and atomic publication remain separate qualification work. All
full-D/head, NPU, native parity, acceptance and performance qualifications
are false.

Focused offline tests cover exact framing/digest boundaries, rehashed malformed
headers, nonfinite words in every request/candidate array, complete response
echo, changed model/reset/run/call/graph identities, changed bodies, corruption,
strict lengths and integer/nonzero bounds. They use synthetic finite words and
read no model or fixture payload.
