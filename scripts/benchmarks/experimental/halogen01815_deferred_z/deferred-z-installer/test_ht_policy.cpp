#include "ht_policy.h"
#include <cassert>
#include <cstdio>
int main(){
 dz_adapter::HtPolicy p{};
 assert(!dz_adapter::narrow_ht(p));
 p.n=6144;p.m=8192;p.k=2560;p.desc_n=6144;p.desc_k=2560;
 p.weight=p.scale=p.aux=1;p.init_large=p.init_threshold=p.init_direct=p.init_cache=1;
 p.large=p.direct=1;p.capacity_units=1;p.context=1;p.threshold=1024;
 assert(dz_adapter::narrow_ht(p));
 p.cached_weights=1;assert(!dz_adapter::narrow_ht(p));p.cached_weights=0;
 p.alternate=1;assert(!dz_adapter::narrow_ht(p));p.alternate=0;
 p.desc_k=4096;assert(!dz_adapter::narrow_ht(p));p.desc_k=2560;
 p.capacity_units=0;assert(!dz_adapter::narrow_ht(p));p.capacity_units=1;
 p.m=4096;assert(!dz_adapter::narrow_ht(p));p.m=8192;
 p.threshold=8192;assert(!dz_adapter::narrow_ht(p));
 dz_adapter::PlanPolicy plan{8192,6144,2560,0,0x100,0x100,0x200};
 assert(dz_adapter::warm_plan(plan));plan.end++;assert(!dz_adapter::warm_plan(plan));plan.end--;
 plan.algorithm=0;assert(!dz_adapter::warm_plan(plan));plan.algorithm=0x200;
 plan.kind=1;assert(!dz_adapter::warm_plan(plan));
 std::puts("PASS: narrow native HT branch, dimensions, initialization and alternate-path guards");
}
