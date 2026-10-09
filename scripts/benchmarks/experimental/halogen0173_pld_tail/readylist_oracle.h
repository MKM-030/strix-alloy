#pragma once
#include "tail_adapter.h"
#include "oracle_format.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// Measurement producer only. This is future-label oracle material and must
// never be described as real external/NPU drafting or released as a default.
namespace halogen0173::tail {
inline Adapter measured_tail;
inline OracleRecord oracle_rows[4096];
inline u32 oracle_count;
inline bool oracle_stock_mode;
inline u8 oracle_allowed[32768];
inline bool readylist(void*,const Snapshot& s,Candidate& result) noexcept {
    const auto& k=s.key;
    u32 low=0,high=oracle_count;
    while(low<high) { auto mid=low+(high-low)/2;
        if(oracle_rows[mid].context_total<k.context_total) low=mid+1; else high=mid; }
    for(u32 n=low;n<oracle_count && oracle_rows[n].context_total==k.context_total;++n) {
        const auto& row=oracle_rows[n];
        if(row.context_count!=k.context_count || row.model_position!=k.model_position
            || row.current_id!=k.current_id || row.width!=k.width) continue;
        bool matches=true;
        for(u32 i=0;i<3;++i) matches&=(row.stock[i]==k.stock[i]);
        for(u32 i=0;i<64;++i) matches&=(row.suffix[i]==k.suffix[i]);
        if(!matches) continue;
        result.binding=k;result.count=k.width;
        for(u32 i=0;i<3;++i) result.ids[i]=oracle_stock_mode?row.stock[i]:row.proposal[i];
        return true;
    }
    return false;
}
inline bool parse_sha(const char* text,u8 (&out)[32]) noexcept {
    if(!text || std::strlen(text)!=64) return false;
    for(u32 i=0;i<32;++i) {
        unsigned value=0;
        for(u32 j=0;j<2;++j) { const char c=text[2*i+j];unsigned v;
            if(c>='0' && c<='9') v=unsigned(c-'0');
            else if(c>='a' && c<='f') v=unsigned(c-'a')+10;
            else if(c>='A' && c<='F') v=unsigned(c-'A')+10;else return false;
            value=16*value+v;
        } out[i]=u8(value);
    } return nonzero(out);
}
inline bool read_exact(const char* path,void* output,std::size_t bytes) noexcept {
    if(!path || path[0]!='/') return false;
    auto* file=std::fopen(path,"rb");if(!file) return false;
    const bool ok=std::fread(output,1,bytes,file)==bytes && std::fgetc(file)==EOF;
    std::fclose(file);return ok;
}
// Call only after verify_elf(), before collector enable and native publication.
// Model/tokenizer pins must be supplied from the root-verified current launch
// receipt. This helper does not infer model identity from arbitrary table bytes.
inline bool init_readylist(const std::array<std::uint8_t,16>& nonce) noexcept {
    const auto* mode=std::getenv("HALOGEN0173_PLD_TAIL");
    if(!mode || !*mode) return true;
    oracle_stock_mode=!std::strcmp(mode,"readylist-stock-v1");
    if(!oracle_stock_mode && std::strcmp(mode,"readylist-oracle-v1")) return false;
    OracleHeader header{};
    const auto* path=std::getenv("HALOGEN0173_PLD_TAIL_LIST");
    if(!path || path[0]!='/') return false;
    auto* file=std::fopen(path,"rb");if(!file) return false;
    bool ok=std::fread(&header,1,sizeof(header),file)==sizeof(header);
    constexpr char magic[8]{'H','0','P','L','D','O','T','1'};
    ok=ok && !std::memcmp(header.magic,magic,8) && header.version==1 && header.records<=4096;
    if(ok) ok=std::fread(oracle_rows,sizeof(OracleRecord),header.records,file)==header.records
        && std::fgetc(file)==EOF;
    std::fclose(file);if(!ok) return false;
    Configuration cfg{};cfg.enabled=cfg.exact_native_pins_verified=true;
    for(u32 i=0;i<16;++i) cfg.session[i]=nonce[i];
    u8 runtime[32]{};
    if(!parse_sha("af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7",runtime)
        || !equal(runtime,header.runtime_sha256)
        || !parse_sha(std::getenv("HALOGEN0173_PLD_TAIL_MODEL_SHA256"),cfg.model_sha256)
        || !parse_sha(std::getenv("HALOGEN0173_PLD_TAIL_TOKENIZER_SHA256"),cfg.tokenizer_sha256)
        || !equal(cfg.model_sha256,header.model_sha256)
        || !equal(cfg.tokenizer_sha256,header.tokenizer_sha256)) return false;
    // The fixed 262144-bit mask is built from the exact target tokenizer.
    if(!read_exact(std::getenv("HALOGEN0173_PLD_TAIL_ID_MASK"),oracle_allowed,sizeof(oracle_allowed))) return false;
    cfg.allowed_ids=oracle_allowed;cfg.allowed_id_count=262144;
    cfg.provider=&readylist;
    for(u32 n=0;n<header.records;++n) {
        const auto& row=oracle_rows[n];
        if(row.width<2 || row.width>3 || !row.context_count || row.context_count>64
            || row.context_count>row.context_total || row.model_position<0
            || row.suffix[row.context_count-1]!=row.current_id
            || row.stock[0]!=row.proposal[0]
            || (n && oracle_rows[n-1].context_total>row.context_total)) return false;
        for(u32 i=0;i<row.width;++i) {
            const auto id=row.proposal[i];
            if(id<0 || u32(id)>=cfg.allowed_id_count
                || !(cfg.allowed_ids[u32(id)/8] & u8(1u<<(u32(id)%8)))) return false;
        }
    }
    oracle_count=header.records;return measured_tail.configure(cfg);
}
inline void report_readylist_counts() noexcept {
    if(!measured_tail.enabled()) return;
    std::fprintf(stderr,"halogen0173 PLD tail %s: applied=%llu unavailable=%llu stale=%llu invalid=%llu ineligible=%llu lost_owner=%llu changed_input=%llu\n",
        oracle_stock_mode?"readylist-stock-v1":"readylist-oracle-v1",
        static_cast<unsigned long long>(measured_tail.count(Status::Applied)),
        static_cast<unsigned long long>(measured_tail.count(Status::Unavailable)),
        static_cast<unsigned long long>(measured_tail.count(Status::Stale)),
        static_cast<unsigned long long>(measured_tail.count(Status::Invalid)),
        static_cast<unsigned long long>(measured_tail.count(Status::Ineligible)),
        static_cast<unsigned long long>(measured_tail.count(Status::LostOwner)),
        static_cast<unsigned long long>(measured_tail.count(Status::ChangedInput)));
}
}
