// Ordinary host memory backend only. No HIP symbols are loaded or called.
#define main lifetime_fixture_main
#include "transport_cpu_test.cpp"
#undef main
#include "worker_io.h"
static Fixture wire;
int main(){
    auto* out=std::fopen("cpu-wire-fixture.bin","wb");if(!out)return 1;
    wire.override_sink=file_sink(out);
    if(!wire.setup()||!prefill(wire)||!wire.make_decode(DecodeSource::Verify,7,2)||wire.exporter.step()!=Step::Queued||wire.exporter.step()!=Step::Sent||wire.exporter.step()!=Step::Acknowledged)return 2;
    if(!wire.make_decode(DecodeSource::Scalar,9,1,7,99)||wire.exporter.step()!=Step::Queued||wire.exporter.step()!=Step::Sent||wire.exporter.step()!=Step::Acknowledged)return 3;
    wire.exporter.disable_new();if(wire.exporter.step()!=Step::Stopped||std::fclose(out)!=0)return 4;return 0;
}
