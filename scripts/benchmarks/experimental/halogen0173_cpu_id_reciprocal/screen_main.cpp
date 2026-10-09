#include "screen_kernels.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

using namespace ple_screen;
using ple_native_0172::bits;
using ple_native_0172::signed_bits;
using Clock=std::chrono::steady_clock;
constexpr std::size_t window_tokens=8192,window_ids=window_tokens*16;

static void require(bool condition,const char* message) {
    if (!condition) throw std::runtime_error(message);
}
static void read_exact(const char* path,void* destination,std::size_t bytes) {
    std::ifstream stream(path,std::ios::binary);
    require(bool(stream) && bool(stream.read(static_cast<char*>(destination),std::streamsize(bytes)))
            && stream.peek()==EOF,"Invalid bounded archived input");
}
static void write_exact(const std::string& path,const std::vector<std::int64_t>& ids) {
    std::ofstream stream(path,std::ios::binary);
    require(bool(stream) && bool(stream.write(reinterpret_cast<const char*>(ids.data()),
              std::streamsize(ids.size()*sizeof(std::int64_t)))),"Could not write verification IDs");
    stream.close(); require(bool(stream),"Could not close verification IDs");
}
static std::uint64_t random_word(std::uint64_t& state) noexcept {
    state^=state<<13; state^=state>>7; state^=state<<17; return state;
}
static std::uint64_t checksum(const std::vector<std::int64_t>& ids) noexcept {
    std::uint64_t sum=0x4e8a53825fbd3183;
    for (const auto id:ids) sum=(sum^bits(id))*0x100000001b3;
    return sum;
}
static void reference_window(const std::vector<std::int32_t>& tokens,
                             std::array<std::int64_t,2> history,const Constants& constants,
                             std::vector<std::int64_t>& ids) {
    for (std::size_t token=0;token<tokens.size();++token)
        require(ple_native_0172::scalar_ids(tokens,history,constants,token,
               std::span<std::int64_t,16>(ids.data()+token*16,16)),"Archived scalar reference refused input");
}
static std::size_t verify_remainders() {
    std::size_t checked=0;
    auto compare=[&](std::size_t head,std::int64_t numerator) {
        require(dynamic_remainder(numerator,admitted_moduli[head])==literal_remainder(head,numerator),
                "Signed literal remainder mismatch"); ++checked;
    };
    std::uint64_t state=0x249dbeb054f17a81;
    for (std::size_t head=0;head<16;++head) {
        const auto d=admitted_moduli[head];
        const std::array<std::int64_t,13> edges{
            std::numeric_limits<std::int64_t>::min(),std::numeric_limits<std::int64_t>::min()+1,
            std::numeric_limits<std::int64_t>::max(),std::numeric_limits<std::int64_t>::max()-1,
            -d-1,-d,-d+1,-1,0,1,d-1,d,d+1};
        for (const auto n:edges) compare(head,n);
        // Exact large multiples and their neighbors without signed overflow.
        const auto low_multiple=(std::numeric_limits<std::int64_t>::min()/d)*d;
        const auto high_multiple=(std::numeric_limits<std::int64_t>::max()/d)*d;
        for (const auto multiple:std::array<std::int64_t,2>{low_multiple,high_multiple}) {
            compare(head,multiple);
            if (multiple>std::numeric_limits<std::int64_t>::min()) compare(head,multiple-1);
            if (multiple<std::numeric_limits<std::int64_t>::max()) compare(head,multiple+1);
        }
        for (unsigned i=0;i<4096;++i) compare(head,signed_bits(random_word(state)));
    }
    return checked;
}
static std::size_t verify_scalar_edges(const Constants& archived) {
    std::uint64_t state=0x3801dcaa23a17b95;
    std::size_t checked=0;
    const std::array<std::int64_t,7> extremes{
        std::numeric_limits<std::int64_t>::min(),std::numeric_limits<std::int64_t>::max(),
        -1,0,1,ple_native_0172::eos,signed_bits(0x81234567abcdef09)};
    for (std::size_t trial=0;trial<49;++trial) {
        std::vector<std::int32_t> tokens(65);
        for (auto& token:tokens) token=std::bit_cast<std::int32_t>(std::uint32_t(random_word(state)));
        tokens[0]=trial%3==0 ? std::int32_t(ple_native_0172::eos) : std::numeric_limits<std::int32_t>::min();
        tokens[1]=std::int32_t(ple_native_0172::eos); tokens[2]=-1; tokens[3]=0;
        tokens[4]=std::numeric_limits<std::int32_t>::max();
        tokens[63]=std::int32_t(ple_native_0172::eos); tokens[64]=-1;
        const std::array<std::int64_t,2> history{extremes[trial/7],extremes[trial%7]};
        Constants constants=archived;
        constants.multipliers={extremes[trial%7],extremes[(trial+1)%7],extremes[(trial+2)%7]};
        for (std::size_t head=0;head<16;++head)
            constants.offsets[head]=head<7 ? extremes[head] : signed_bits(random_word(state));
        std::vector<std::int64_t> reference(tokens.size()*16),baseline(reference.size()),candidate(reference.size());
        reference_window(tokens,history,constants,reference);
        require(dynamic_window(tokens.data(),tokens.size(),history,constants,baseline.data()),"Baseline edge failure");
        require(literal_window(tokens.data(),tokens.size(),history,constants,candidate.data()),"Candidate edge failure");
        require(reference==baseline && reference==candidate,"Full scalar signed/carry/EOS/wrap mismatch");
        checked+=reference.size();
    }
    for (std::size_t head=0;head<16;++head)
    for (const auto unsupported:std::array<std::int64_t,4>{0,-1,-20000003,20000004}) {
        Constants constants=archived;
        constants.moduli[head]=unsupported;
        std::array<std::int32_t,1> tokens{1};
        std::array<std::int64_t,16> untouched{};
        untouched.fill(signed_bits(0xe134677609243abc));
        const auto expected=untouched;
        require(!literal_window(tokens.data(),tokens.size(),{0,0},constants,untouched.data())
                && untouched==expected,"Unsupported model did not reject before mutation");
    }
    require(literal_window(nullptr,0,{0,0},archived,nullptr),"Empty admitted window failure");
    return checked;
}
using WindowFunction=bool (*)(const std::int32_t*,std::size_t,std::array<std::int64_t,2>,
                             const Constants&,std::int64_t*) noexcept;
static double measure(WindowFunction function,unsigned batch,const std::vector<std::int32_t>& tokens,
                      std::array<std::int64_t,2> history,const Constants& constants,
                      std::vector<std::int64_t>& ids) {
    std::atomic_signal_fence(std::memory_order_seq_cst);
    const auto begin=Clock::now();
    for (unsigned i=0;i<batch;++i)
        require(function(tokens.data(),tokens.size(),history,constants,ids.data()),"Timed window failure");
    const auto end=Clock::now();
    std::atomic_signal_fence(std::memory_order_seq_cst);
    return std::chrono::duration<double,std::milli>(end-begin).count()/batch;
}
static double quantile(std::vector<double> values,double fraction) {
    std::sort(values.begin(),values.end());
    const auto index=fraction*double(values.size()-1);
    const auto lo=std::size_t(index),hi=std::min(lo+1,values.size()-1);
    return values[lo]+(values[hi]-values[lo])*(index-double(lo));
}
static void print_stats(const char* name,const std::vector<double>& values) {
    std::printf("\"%s\":{\"median_ms\":%.9f,\"p10_ms\":%.9f,\"p90_ms\":%.9f,\"min_ms\":%.9f,\"max_ms\":%.9f,\"mean_ms\":%.9f}",
        name,quantile(values,0.5),quantile(values,0.1),quantile(values,0.9),
        *std::min_element(values.begin(),values.end()),*std::max_element(values.begin(),values.end()),
        std::accumulate(values.begin(),values.end(),0.0)/double(values.size()));
}
int main(int argc,char** argv) {
    try {
        require(argc==7 || argc==9,"Usage: screen.exe --verify|--bench tokens history constants oracle output-prefix [samples batch]");
        const bool benchmark=std::string(argv[1])=="--bench";
        require(benchmark || std::string(argv[1])=="--verify","Unknown mode");
        require((benchmark && argc==9) || (!benchmark && argc==7),"Mode/argument mismatch");
        const unsigned samples=benchmark ? unsigned(std::stoul(argv[7])) : 0;
        const unsigned batch=benchmark ? unsigned(std::stoul(argv[8])) : 0;
        require(!benchmark || (samples>=5 && samples<=101 && batch>=1 && batch<=64),"Bounded samples/batch invalid");
        std::vector<std::int32_t> tokens(window_tokens);
        std::array<std::int64_t,2> history{};
        std::array<std::int64_t,35> words{};
        std::vector<std::int64_t> oracle(window_ids),baseline(window_ids),candidate(window_ids),reference(window_ids);
        read_exact(argv[2],tokens.data(),tokens.size()*sizeof(std::int32_t));
        read_exact(argv[3],history.data(),sizeof(history)); read_exact(argv[4],words.data(),sizeof(words));
        read_exact(argv[5],oracle.data(),oracle.size()*sizeof(std::int64_t));
        Constants constants;
        std::copy_n(words.begin(),3,constants.multipliers.begin());
        std::copy_n(words.begin()+3,16,constants.offsets.begin());
        std::copy_n(words.begin()+19,16,constants.moduli.begin());
        require(admit(constants),"Archived model constants differ from literal admission");
        reference_window(tokens,history,constants,reference);
        require(dynamic_window(tokens.data(),tokens.size(),history,constants,baseline.data()),"Baseline archive failure");
        require(literal_window(tokens.data(),tokens.size(),history,constants,candidate.data()),"Candidate archive failure");
        require(reference==oracle && baseline==oracle && candidate==oracle,"Archived 131072-ID oracle mismatch");
        const auto remainder_checks=verify_remainders(),scalar_edge_ids=verify_scalar_edges(constants);
        write_exact(std::string(argv[6])+".baseline-ids-i64.bin",baseline);
        write_exact(std::string(argv[6])+".literal-ids-i64.bin",candidate);
        std::printf("{\"mode\":\"%s\",\"tokens\":8192,\"ids\":131072,\"archived_oracle_exact\":true,\"signed_remainder_checks\":%zu,\"scalar_edge_ids_checked\":%zu,\"unsupported_models_rejected_before_write\":64,\"row_payload_reads\":false,\"checksum_u64\":\"%016llx\"",
            benchmark ? "bench" : "verify",remainder_checks,scalar_edge_ids,
            static_cast<unsigned long long>(checksum(oracle)));
        if (benchmark) {
            std::vector<double> dynamic_ms,literal_ms,saved_ms;
            dynamic_ms.reserve(samples); literal_ms.reserve(samples); saved_ms.reserve(samples);
            // Small untimed warmup, then alternate order to limit thermal/order bias.
            for (unsigned i=0;i<2;++i) {
                require(dynamic_window(tokens.data(),tokens.size(),history,constants,baseline.data()),"Warmup baseline failure");
                require(literal_window(tokens.data(),tokens.size(),history,constants,candidate.data()),"Warmup candidate failure");
            }
            for (unsigned sample=0;sample<samples;++sample) {
                double base=0,cand=0;
                if (sample%2==0) {
                    base=measure(dynamic_window,batch,tokens,history,constants,baseline);
                    cand=measure(literal_window,batch,tokens,history,constants,candidate);
                } else {
                    cand=measure(literal_window,batch,tokens,history,constants,candidate);
                    base=measure(dynamic_window,batch,tokens,history,constants,baseline);
                }
                // Full post-batch comparisons and checksum are outside timing.
                require(baseline==oracle && candidate==oracle,"Timed output mismatch");
                require(checksum(baseline)==checksum(oracle) && checksum(candidate)==checksum(oracle),"Timed checksum mismatch");
                dynamic_ms.push_back(base);literal_ms.push_back(cand);saved_ms.push_back(base-cand);
            }
            std::printf(",\"samples\":%u,\"windows_per_sample\":%u,\"one_admission_per_candidate_window_included\":true,\"literal_descriptor_setup_required\":false,\"time_unit\":\"ms_per_full_8192_token_ID_window\",",samples,batch);
            print_stats("dynamic_signed_division",dynamic_ms); std::printf(",");
            print_stats("literal_exact_remainder",literal_ms); std::printf(",");
            print_stats("paired_cpu_ms_saved",saved_ms);
            std::printf(",\"paired_samples\":[");
            for (unsigned sample=0;sample<samples;++sample)
                std::printf("%s[%.9f,%.9f,%.9f]",sample ? "," : "",dynamic_ms[sample],literal_ms[sample],saved_ms[sample]);
            std::printf("]");
        }
        std::puts("}");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr,"CPU screen failed: %s\n",error.what());return 1;
    }
}
