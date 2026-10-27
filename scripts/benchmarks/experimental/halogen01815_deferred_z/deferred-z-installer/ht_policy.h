#pragma once
#include <cstdint>
namespace dz_adapter {
struct HtPolicy {
 int n{},m{},k{},desc_n{},threshold{};
 std::int64_t desc_k{};
 std::uintptr_t weight{},scale{},aux{},context{};
 std::uint8_t init_large{},init_threshold{},init_direct{},init_cache{};
 std::uint8_t large{},direct{},alternate{},cached_weights{},capacity_units{};
};
inline bool narrow_ht(const HtPolicy& p){
 const auto capacity=std::uint32_t(p.capacity_units)<<27;
 return p.n==6144&&p.m==8192&&p.k==2560&&p.desc_n==p.n&&p.desc_k==p.k&&
  p.weight&&p.scale&&p.aux&&p.context&&p.init_large&&p.init_threshold&&p.init_direct&&p.init_cache&&
  p.large==1&&p.direct==1&&!p.alternate&&p.cached_weights!=1&&p.m>p.threshold&&
  std::uint64_t(p.n)*std::uint64_t(p.k)<=capacity;
}
struct PlanPolicy {std::int64_t m{},n{},k{};int kind{};std::uintptr_t begin{},end{},algorithm{};};
inline bool warm_plan(const PlanPolicy& p){return p.m==8192&&p.n==6144&&p.k==2560&&p.kind==0&&p.begin==p.end&&p.algorithm;}

}
