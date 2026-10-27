#include "hcmean_plan.h"
#include <cstdio>
using namespace hgn01816_hcmean_gpu;
unsigned checks=0,failures=0;
void check(bool ok) {++checks;if (!ok)++failures;}
int main() {
    Job j{};
    // Fabricated addresses exercise arithmetic only, never dereferenced.
    j.raw=reinterpret_cast<const std::uint16_t*>(0x100000000ull);
    j.owned_output=reinterpret_cast<std::uint16_t*>(0x200000000ull);
    j.full_rows=4;j.rows=4;j.destination_rows=4;j.raw_elements=40960;j.output_elements=51200;
    j.completed_layer=5;
    check(validate(j)==Status::Ok);
    for (unsigned tap=0;tap<5;++tap){j.tap=tap;j.completed_layer=completed_layers[tap];check(validate(j)==Status::Ok);}
    auto bad=j;bad.completed_layer=44;check(validate(bad)==Status::Tap);
    bad=j;bad.rows=0;check(validate(bad)==Status::Rows);
    bad=j;bad.source_first=1;check(validate(bad)==Status::Rows);
    bad=j;bad.destination_first=1;check(validate(bad)==Status::Rows);
    bad=j;bad.full_rows=5;check(validate(bad)==Status::Rows);
    bad=j;bad.raw_elements--;check(validate(bad)==Status::Capacity);
    bad=j;bad.output_elements--;check(validate(bad)==Status::Capacity);
    bad=j;bad.raw_stream_stride=2561;check(validate(bad)==Status::Stride);
    bad=j;bad.raw_row_stride=10232;check(validate(bad)==Status::Stride);
    bad=j;bad.output_row_stride=12808;check(validate(bad)==Status::Stride);
    bad=j;bad.owned_output=const_cast<std::uint16_t*>(bad.raw);check(validate(bad)==Status::Overlap);
    bad=j;bad.raw=nullptr;check(validate(bad)==Status::Pointer);
    bad=j;bad.mode=static_cast<Mode>(3);check(validate(bad)==Status::Mode);
    bad=j;bad.raw_elements=~std::uint64_t(0);check(validate(bad)==Status::Capacity);
    j.mode=Mode::Prefill;j.full_rows=8192;j.source_first=8190;j.rows=2;
    j.raw_elements=std::uint64_t(8192)*10240;j.destination_first=1;
    check(validate(j)==Status::Ok);
    j.raw_stream_stride=2568;j.raw_row_stride=10280;
    j.raw_elements=std::uint64_t(8191)*10280+3*2568+2560;
    check(validate(j)==Status::Ok);
    j.output_row_stride=2560;j.output_elements=4*2560;
    check(validate(j)==Status::Ok);
    std::printf("%u checks %u failures\n",checks,failures);
    return failures?1:0;
}
