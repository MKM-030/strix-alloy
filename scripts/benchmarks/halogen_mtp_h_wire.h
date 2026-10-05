/* Source-only H-only resident protocol. All integers are little endian.
 * Linux x86-64 and Windows x64 share these natural layouts; other targets
 * must explicitly serialize. SHA256 is integrity/binding, not authentication.
 * Owner pins peer/process identity, nonce, epoch and immutable bindings before
 * launch. No error frames: any framing/backend failure poisons the session.
 * Burn sequence before candidate work; accept exactly sequence 0..63 once.
 * Host pins the first request's opaque model pointer for this owned epoch.
 */
#ifndef HALOGEN_MTP_H_WIRE_H
#define HALOGEN_MTP_H_WIRE_H
#include <stddef.h>
#include <stdint.h>

#define HGNH_VERSION 1U
#define HGNH_MAX_CALLS 64U
#define HGNH_WIRE_D 68U
#define HGNH_H_BYTES 20480U
#define HGNH_HEADER_BYTES 224U
#define HGNH_HELLO_BYTES 160U
#define HGNH_REQUEST_BYTES 20704U
#define HGNH_RESPONSE_BYTES 20736U
#define HGNH_FRAME_BYTES 56U
#define HGNH_REQUEST_BINDING_OFFSET 192U
#define HGNH_HELLO_MAGIC "HGNHHEL1"
#define HGNH_READY_MAGIC "HGNHACK1"
#define HGNH_REQUEST_MAGIC "HGNHCPQ1"
#define HGNH_RESPONSE_MAGIC "HGNHCPR1"
#define HGNH_FRAME_MAGIC "HGNHFRM1"
#define HGNH_ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
enum hgnh_frame_kind { HGNH_HELLO=1, HGNH_READY=2, HGNH_REQUEST=3, HGNH_RESPONSE=4 };

struct hgnh_hello {
    uint8_t magic[8];
    uint32_t version,max_calls;
    uint64_t process_id;
    uint8_t nonce[16],epoch[16],model_binding[32],graph_binding[32],engine_sha256[32];
    uint32_t h_bytes,wire;
};
struct hgnh_header {
    uint8_t magic[8];
    uint32_t version,body_bytes;
    int32_t sequence,position,slot;
    uint32_t reserved;
    int32_t count,token,outer_position;
    uint32_t wire;
    uint8_t nonce[16],epoch[16];
    uint64_t model,process_id;
    uint8_t model_binding[32],graph_binding[32],input_binding[32],request_binding[32];
};
/* Request digest = SHA256(header[0:192] || input); input binding = SHA256(input).
 * Reply header exactly echoes request except magic. Reply digest covers the
 * complete header and output. No native output belongs in a request.
 */
struct hgnh_request { struct hgnh_header header; uint8_t body[HGNH_H_BYTES]; };
struct hgnh_response { struct hgnh_header header; uint8_t body[HGNH_H_BYTES],digest[32]; };
/* Frame digest covers its complete payload; kind selects its only legal size.
 * HELLO/READY sequence is zero. REQUEST/RESPONSE frame sequence must equal
 * the packet header sequence. Payload must be fully buffered and validated
 * before consuming it, running arithmetic, or exposing candidate output.
 */
struct hgnh_frame {
    uint8_t magic[8];
    uint32_t kind,payload_bytes;
    uint64_t sequence;
    uint8_t payload_sha256[32];
};
#ifdef __cplusplus
#define HGNH_ASSERT static_assert
#else
#define HGNH_ASSERT _Static_assert
#endif
HGNH_ASSERT(sizeof(struct hgnh_hello)==HGNH_HELLO_BYTES &&
    offsetof(struct hgnh_hello,process_id)==16 && offsetof(struct hgnh_hello,nonce)==24 &&
    offsetof(struct hgnh_hello,epoch)==40 && offsetof(struct hgnh_hello,model_binding)==56 &&
    offsetof(struct hgnh_hello,graph_binding)==88 && offsetof(struct hgnh_hello,engine_sha256)==120 &&
    offsetof(struct hgnh_hello,h_bytes)==152 && offsetof(struct hgnh_hello,wire)==156,"H handshake ABI");
HGNH_ASSERT(sizeof(struct hgnh_header)==HGNH_HEADER_BYTES &&
    offsetof(struct hgnh_header,nonce)==48 && offsetof(struct hgnh_header,epoch)==64 &&
    offsetof(struct hgnh_header,model)==80 && offsetof(struct hgnh_header,process_id)==88 &&
    offsetof(struct hgnh_header,model_binding)==96 && offsetof(struct hgnh_header,graph_binding)==128 &&
    offsetof(struct hgnh_header,input_binding)==160 &&
    offsetof(struct hgnh_header,request_binding)==HGNH_REQUEST_BINDING_OFFSET,"H packet ABI");
HGNH_ASSERT(sizeof(struct hgnh_request)==HGNH_REQUEST_BYTES &&
    sizeof(struct hgnh_response)==HGNH_RESPONSE_BYTES &&
    offsetof(struct hgnh_response,digest)==HGNH_HEADER_BYTES+HGNH_H_BYTES,"H packet extents");
HGNH_ASSERT(sizeof(struct hgnh_frame)==HGNH_FRAME_BYTES && offsetof(struct hgnh_frame,sequence)==16 &&
    offsetof(struct hgnh_frame,payload_sha256)==24,"H frame ABI");
#undef HGNH_ASSERT
#endif
