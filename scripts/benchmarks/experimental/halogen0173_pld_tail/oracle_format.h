#pragma once
#include "tail_adapter.h"
namespace halogen0173::tail {
#pragma pack(push,1)
struct OracleHeader {
    char magic[8]{'H','0','P','L','D','O','T','1'};
    u32 version{1}, records{};
    u8 runtime_sha256[32]{}, model_sha256[32]{}, tokenizer_sha256[32]{};
};
struct OracleRecord {
    u32 context_total{}, context_count{};
    i32 model_position{}, current_id{};
    u32 width{};
    i32 stock[3]{}, proposal[3]{}, suffix[64]{};
};
#pragma pack(pop)
static_assert(sizeof(OracleHeader)==112 && sizeof(OracleRecord)==300);
}
