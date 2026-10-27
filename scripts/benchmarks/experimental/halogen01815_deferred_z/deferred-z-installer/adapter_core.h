#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <limits>
namespace dz_adapter {
inline bool enabled(const char* s) { return s && s[0]=='1' && s[1]==0; }
struct Range { std::uintptr_t address; std::size_t bytes; };
inline bool valid(Range r) { return r.address && r.bytes && r.bytes<=std::numeric_limits<std::uintptr_t>::max()-r.address; }
inline bool overlap(Range a,Range b) { return !valid(a)||!valid(b)||(a.address<b.address+b.bytes && b.address<a.address+a.bytes); }
inline bool contains(Range a,Range b) { return valid(a)&&valid(b)&&b.address>=a.address&&b.address+b.bytes<=a.address+a.bytes; }
inline bool disjoint(Range r,const Range* a,std::size_t n) { if(!valid(r))return false; for(std::size_t i=0;i<n;++i)if(overlap(r,a[i]))return false;return true; }
struct Tuple { std::uintptr_t descriptor,input,output; int n,m,k; };
inline bool same(Tuple a,Tuple b) { return a.descriptor==b.descriptor&&a.input==b.input&&a.output==b.output&&a.n==b.n&&a.m==b.m&&a.k==b.k; }
class Warmup { Tuple tuple_{};bool valid_{};public:bool ready(Tuple t)const{return valid_&&same(tuple_,t);}void remember(Tuple t){tuple_=t;valid_=true;} };
inline void absolute_jump(unsigned char* p,std::uintptr_t target) { const unsigned char head[]={0xff,0x25,0,0,0,0};std::memcpy(p,head,6);std::memcpy(p+6,&target,8); }
inline bool relative_call(unsigned char* p,std::uintptr_t site,std::uintptr_t target) {
 if(site>std::numeric_limits<std::uintptr_t>::max()-5)return false;
 const auto next=site+5;
 if(target>=next) {if(target-next>0x7fffffffULL)return false;}
 else if(next-target>0x80000000ULL)return false;
 const auto delta=static_cast<std::uint32_t>(target-next);p[0]=0xe8;std::memcpy(p+1,&delta,4);return true;
}
}
