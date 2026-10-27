// Default-off, exact-image adapter. Compile together with launch_redirect_linux.cpp.
#include "adapter_core.h"
#include "engine_pins.h"
#include "ht_policy.h"
#include "../deferred-z-stream/deferred_z_stream.h"
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <elf.h>
#include <fcntl.h>
#include <link.h>
#include <mutex>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

extern "C" bool deferred_z_bind_hip(deferred_z::Api*);
namespace {
using namespace dz_adapter;
using namespace deferred_z;
using Dn=void(*)(void*,int,int);
constexpr std::size_t MiB=1024*1024,Zbytes=96*MiB;
std::uintptr_t base;
Dn original_dn,original_helper;
Fc original_fc;
Api api;
int (*address_range)(void**,std::size_t*,void*);
int (*copy_host)(void*,const void*,std::size_t,int);
std::mutex owner_mutex;
std::atomic<bool> native_owner{false};
bool identity_ok;
std::array<std::array<unsigned char,64>, sizeof(dz_pins::all)/sizeof(dz_pins::all[0])> installed_bytes{};
std::array<Pin, sizeof(dz_pins::all)/sizeof(dz_pins::all[0])> runtime_pins{};

template<class T> T read(std::uintptr_t a) { T v;std::memcpy(&v,reinterpret_cast<void*>(a),sizeof v);return v; }
void* global(std::uintptr_t rva){return read<void*>(base+rva);}
[[noreturn]] void stop(const char* why) {
 std::fprintf(stderr,"deferred-z: FAIL-STOP: %s\n",why);std::fflush(stderr);_Exit(86);
}
// OpenSSL is loaded only with explicit opt-in. Missing provider rejects installation.
// SHA256 hashes the actual opened executable, not a caller-supplied digest.
bool seal_executable() {
 int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);if(fd<0)return false;
 struct stat st{};
 if(fstat(fd,&st)||st.st_size!=32523520){close(fd);return false;}
 void* map=mmap(nullptr,static_cast<std::size_t>(st.st_size),PROT_READ,MAP_PRIVATE,fd,0);close(fd);
 if(map==MAP_FAILED)return false;
 bool ok=false;void* crypto=dlopen("libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);
 if(crypto){
  using Sha=unsigned char*(*)(const unsigned char*,std::size_t,unsigned char*);
  auto sha=reinterpret_cast<Sha>(dlsym(crypto,"SHA256"));
  unsigned char digest[32]{};char hex[65]{};
  if(sha&&sha(static_cast<const unsigned char*>(map),static_cast<std::size_t>(st.st_size),digest)){
   for(unsigned i=0;i<32;++i)std::snprintf(hex+i*2,3,"%02x",digest[i]);
   const auto* elf=static_cast<const Elf64_Ehdr*>(map);
   ok=std::strcmp(hex,engine_sha)==0&&elf->e_type==ET_DYN&&elf->e_machine==EM_X86_64;
  }
  dlclose(crypto);
 }
 munmap(map,static_cast<std::size_t>(st.st_size));return ok;
}
int find_main(dl_phdr_info* i,std::size_t,void*) {
 if(!i->dlpi_name||!i->dlpi_name[0]){base=i->dlpi_addr;return 1;}return 0;
}
bool mapped_pins(const char* hash,const Pin* p,std::size_t n) {
 if(!identity_ok||std::strcmp(hash,engine_sha)||n!=runtime_pins.size())return false;
 // Entries are checked before patching; later qualifications reuse sealed identity.
 // Only our three patch windows may differ from the original bytes thereafter.
 for(std::size_t i=0;i<n;++i){
  if(p[i].address!=base+dz_pins::all[i].rva||p[i].bytes!=dz_pins::all[i].size||
   std::memcmp(reinterpret_cast<void*>(p[i].address),p[i].expected,p[i].bytes))return false;
 }
 return n==runtime_pins.size();
}
bool allocation(Range span,Range* full=nullptr) {
 if(!valid(span)||!address_range)return false;
 void* p=nullptr;std::size_t n=0;
 if(address_range(&p,&n,reinterpret_cast<void*>(span.address)))return false;
 Range whole{reinterpret_cast<std::uintptr_t>(p),n};
 if(!contains(whole,span))return false;
 if(full)*full=whole;
 return true;
}
struct Trace {
 struct Entry {
  SubmitKind kind{};const void* function{};const void* caller{};unsigned grid[3]{},block[3]{};std::size_t shared{};
  std::array<std::uint64_t,6> roles{};std::array<const void*,4> layouts{};const void* handle{};
  std::array<unsigned char,24> algorithm{};
 };
 std::array<Entry,128> entries{};std::size_t count{},cursor{};bool safe{true};
 bool observe(const Submit& s,bool record) {
  Entry e{};e.kind=s.kind;e.function=s.function;e.caller=s.caller;e.shared=s.shared;
  std::memcpy(e.grid,s.grid,sizeof e.grid);std::memcpy(e.block,s.block,sizeof e.block);
  if(s.kind==SubmitKind::kernel){
   const std::size_t sizes[]={8,4,8,8,8,4};
   for(unsigned i=0;i<6;++i)std::memcpy(&e.roles[i],s.args[i],sizes[i]);
  }else if(s.kind==SubmitKind::matmul){
   for(unsigned i=0;i<4;++i){e.roles[i]=reinterpret_cast<std::uintptr_t>(s.matmul_operands[i]);e.layouts[i]=s.matmul_layouts[i];}
   std::memcpy(&e.roles[4],s.matmul_alpha,4);std::memcpy(&e.roles[5],s.matmul_beta,4);
   std::memcpy(e.algorithm.data(),s.matmul_algorithm,24);e.handle=s.matmul_handle;
  }else {safe=false;return record;}
  if(record){if(count==entries.size()){safe=false;return true;}entries[count++]=e;return true;}
  if(cursor>=count)return false;
  const auto& x=entries[cursor++];
  return x.kind==e.kind&&x.function==e.function&&x.caller==e.caller&&x.shared==e.shared&&x.roles==e.roles&&
   x.layouts==e.layouts&&x.handle==e.handle&&x.algorithm==e.algorithm&&
   std::memcmp(x.grid,e.grid,sizeof x.grid)==0&&std::memcmp(x.block,e.block,sizeof x.block)==0;
 }
};
struct Qualified {Tuple tuple{};Trace trace{};std::array<std::uint64_t,5> key{};};
std::array<Qualified,64> qualified{};std::size_t qualified_count;
struct Run {
 void* model;std::uintptr_t layer;int count;Context context;
 enum class Stage {none,captured,queued} stage{Stage::none};
 bool recording{},ab{},validation{},opened{},alpha_seen{},beta_seen{};Trace trace;
 Tuple tuple{};int reference_mode{};std::uintptr_t reference_plan{};std::array<unsigned char,24> reference_algorithm{};std::array<std::uint64_t,5> reference_key{};Range z{},input{};std::array<Range,4> scratch{};std::array<Range,3> side_sources{};
 std::vector<unsigned char> reference,actual;
 Run(void* m,int l,int c):model(m),layer(0),count(c){
  const char* prefetch=std::getenv("HALOGEN_DECODE_PREFETCH");
  if(prefetch&&std::strcmp(prefetch,"0")==0&&l>=0&&c==8192&&!read<void*>(reinterpret_cast<std::uintptr_t>(m)+0x320))
   layer=read<std::uintptr_t>(reinterpret_cast<std::uintptr_t>(m)+0x7c8)+static_cast<std::size_t>(l)*0xd08;
 }
 [[noreturn]] void fail(const char* why){context.close();stop(why);}
 std::array<std::uint64_t,5> prep_key(const Tuple& t){
  return {read<std::uintptr_t>(t.descriptor+0x30),read<std::uintptr_t>(t.descriptor+0x38),read<std::uintptr_t>(t.descriptor+0x40),
   (std::uint64_t(read<std::uint32_t>(t.descriptor+0x48))<<32)|read<std::uint32_t>(base+0x1f0a398),
   std::uint64_t(read<std::uint8_t>(base+0x1f0a3a8))|(std::uint64_t(read<std::uint8_t>(base+0x1f0a3b8))<<8)};
 }
 HtPolicy policy(const Tuple& t){
  HtPolicy p{};p.n=t.n;p.m=t.m;p.k=t.k;
  p.desc_n=read<int>(t.descriptor+0x4c);p.desc_k=read<std::int64_t>(t.descriptor+0x50);
  p.weight=read<std::uintptr_t>(t.descriptor+0x30);p.scale=read<std::uintptr_t>(t.descriptor+0x38);p.aux=read<std::uintptr_t>(t.descriptor+0x40);
  p.context=reinterpret_cast<std::uintptr_t>(global(0x1f07448));
  p.init_large=read<std::uint8_t>(base+0x1f09358);p.init_threshold=read<std::uint8_t>(base+0x1f09408);
  p.init_direct=read<std::uint8_t>(base+0x1f09368);p.init_cache=read<std::uint8_t>(base+0x1f09008);
  p.large=read<std::uint8_t>(base+0x1f09350);p.direct=read<std::uint8_t>(base+0x1f09360);
  p.alternate=read<std::uint8_t>(base+0x1f092c8);p.cached_weights=read<std::uint8_t>(base+0x1f09001);
  p.capacity_units=read<std::uint8_t>(base+0x1f07440);p.threshold=read<int>(base+0x1f09400);
  return p;
 }
 std::uintptr_t plan(){
  auto ctx=reinterpret_cast<std::uintptr_t>(global(0x1f07448));if(!ctx)return 0;
  auto node=read<std::uintptr_t>(ctx+0x60);
  for(unsigned depth=0;node&&node!=ctx+0x58&&depth<64;++depth){
   const int kind=read<int>(node+0x20);
   const auto k=read<std::int64_t>(node+0x28),n=read<std::int64_t>(node+0x30),m=read<std::int64_t>(node+0x38);
   int compare=m!=8192?(8192<m?-1:1):(n!=6144?(6144<n?-1:1):(k!=2560?(2560<k?-1:1):(kind!=0?(0<kind?-1:1):0)));
   if(!compare){
    auto p=read<std::uintptr_t>(node+0x40);if(!p)return 0;
    const auto algorithm=read<std::uint8_t>(p+0x61)?p+0x68:read<std::uintptr_t>(p+0x58);
    PlanPolicy check{read<std::int64_t>(p+0x20),read<std::int64_t>(p+0x28),read<std::int64_t>(p+0x30),read<int>(p+0x38),read<std::uintptr_t>(p+0x40),read<std::uintptr_t>(p+0x48),algorithm};
    return warm_plan(check)?p:0;
   }
   node=read<std::uintptr_t>(node+(compare<0?0x10:0x18));
  }
  return 0;
 }
 bool bind_plan(){
  reference_plan=plan();if(!reference_plan)return false;
  auto a=read<std::uint8_t>(reference_plan+0x61)?reference_plan+0x68:read<std::uintptr_t>(reference_plan+0x58);
  std::memcpy(reference_algorithm.data(),reinterpret_cast<void*>(a),reference_algorithm.size());return true;
 }
 bool same_plan(){
  if(plan()!=reference_plan)return false;
  auto a=read<std::uint8_t>(reference_plan+0x61)?reference_plan+0x68:read<std::uintptr_t>(reference_plan+0x58);
  return std::memcmp(reference_algorithm.data(),reinterpret_cast<void*>(a),reference_algorithm.size())==0;
 }
 bool closure(const Submit& s){
  if(s.stream||s.extra||s.start_event||s.stop_event||s.flags)return false;
  if(s.kind==SubmitKind::kernel){
   if(!read<std::uint8_t>(base+0x1f0a3a0)||!read<std::uint8_t>(base+0x1f0a3b0)||!read<std::uint8_t>(base+0x1f0a3c0))return false;
   const auto f=reinterpret_cast<std::uintptr_t>(s.function);
   if(s.caller!=reinterpret_cast<void*>(base+0x1dea96a)||f<base+0x1f02a08||f>base+0x1f02a40||(f-base-0x1f02a08)%8||!s.args)return false;
   for(unsigned i=0;i<6;++i)if(!s.args[i])return false;
   const auto arg=[&](unsigned i){return read<std::uintptr_t>(reinterpret_cast<std::uintptr_t>(s.args[i]));};
   return arg(0)==read<std::uintptr_t>(tuple.descriptor+0x30)&&arg(2)==read<std::uintptr_t>(tuple.descriptor+0x38)&&
    arg(3)==read<std::uintptr_t>(tuple.descriptor+0x40)&&arg(4)==scratch[0].address&&
    read<int>(reinterpret_cast<std::uintptr_t>(s.args[1]))==2560&&
    read<int>(reinterpret_cast<std::uintptr_t>(s.args[5]))==read<int>(base+0x1f0a398);
  }
  if(s.kind==SubmitKind::matmul){
   const auto ctx=reinterpret_cast<std::uintptr_t>(global(0x1f07448));
   if(!reference_plan||!same_plan()||s.caller!=reinterpret_cast<void*>(base+0x1ef0c4c)||
    s.function!=read<void*>(reference_plan)||s.matmul_handle!=read<void*>(ctx+0x38)||
    s.matmul_operands[0]!=reinterpret_cast<void*>(scratch[0].address)||s.matmul_operands[1]!=reinterpret_cast<void*>(input.address)||
    s.matmul_operands[2]!=reinterpret_cast<void*>(z.address)||s.matmul_operands[3]!=reinterpret_cast<void*>(z.address)||
    s.workspace!=reinterpret_cast<void*>(scratch[3].address)||s.workspace_bytes!=128*MiB||!s.matmul_alpha||!s.matmul_beta||!s.matmul_algorithm)return false;
   if(s.matmul_layouts[0]!=read<void*>(reference_plan+8)||s.matmul_layouts[1]!=read<void*>(reference_plan+0x10)||
    s.matmul_layouts[2]!=read<void*>(reference_plan+0x18)||s.matmul_layouts[3]!=read<void*>(reference_plan+0x18))return false;
   return read<std::uint32_t>(reinterpret_cast<std::uintptr_t>(s.matmul_alpha))==0x3f800000&&
    read<std::uint32_t>(reinterpret_cast<std::uintptr_t>(s.matmul_beta))==0&&
    std::memcmp(s.matmul_algorithm,reference_algorithm.data(),24)==0;
  }
  return false;
 }
 bool ranges(const Tuple& t){
  z={t.output,Zbytes};input={t.input,40*MiB};
  const std::uintptr_t globals[]={0x1f07438,0x1f08ff0,0x1f08ff8};
  const std::size_t sizes[]={256*MiB,96*MiB,128*MiB};
  if(!allocation(z)||!allocation(input)||overlap(z,input))return false;
  for(unsigned i=0;i<3;++i)if(!allocation({read<std::uintptr_t>(t.descriptor+0x30+i*8),1},&side_sources[i]))return false;
  for(unsigned i=0;i<3;++i){scratch[i]={reinterpret_cast<std::uintptr_t>(global(globals[i])),sizes[i]};if(!allocation(scratch[i]))return false;}
  auto ctx=reinterpret_cast<std::uintptr_t>(global(0x1f07448));
  if(!ctx||read<void*>(ctx+0x48))return false;
  scratch[3]={read<std::uintptr_t>(ctx+0x40),128*MiB};if(!allocation(scratch[3]))return false;
  // Shared FC scratch allocations may alias each other; Z/input must not alias any.
  for(const auto& r:side_sources)if(overlap(r,z)||!disjoint(r,scratch.data(),scratch.size()))return false;
  return disjoint(z,scratch.data(),scratch.size())&&disjoint(input,scratch.data(),scratch.size());
 }
 bool open(){
  Qualification q{};q.enabled=true;q.event_slots=1;q.single_owner=true;q.disjoint_z_output=true;
  q.unchanged_fc=true;q.scratch_sequential=true;q.no_native_prefetch=true;
  q.all_exits_bound=true;
  q.complete_fc_launch_coverage=trace.safe&&trace.count==2&&trace.entries[0].kind==SubmitKind::kernel&&
   trace.entries[1].kind==SubmitKind::matmul&&narrow_ht(policy(tuple))&&reference_plan&&same_plan();
  q.warmed_algorithm_cache=trace.safe&&trace.count>0;q.stock_ht_path=q.warmed_algorithm_cache;
  q.live_ranges_verified=true;q.image_hash=engine_sha;q.pins=runtime_pins.data();q.pin_count=runtime_pins.size();
  q.verify_identity_and_bytes=mapped_pins;opened=context.open(api,q);return opened;
 }
 bool safe_span(Range r,bool write){
  return allocation(r)&&!overlap(r,z)&&disjoint(r,scratch.data(),scratch.size())&&(!write||(!overlap(r,input)&&disjoint(r,side_sources.data(),side_sources.size())));
 }
 bool known_prep(const Submit& s){
  if(s.kind!=SubmitKind::kernel||s.stream||!s.args||s.extra||s.start_event||s.stop_event||s.flags)return false;
  auto arg=[&](unsigned i){return s.args[i]?read<std::uintptr_t>(reinterpret_cast<std::uintptr_t>(s.args[i])):0;};
  auto whole=[&](unsigned i,bool write){Range r{};return allocation({arg(i),1},&r)&&safe_span(r,write);};
  if(s.function==reinterpret_cast<void*>(base+0x1f006a8)){
   if(s.caller!=reinterpret_cast<void*>(base+0x1d96eaa)||read<int>(base+0x1f074c8)!=2||
    s.grid[0]!=10||s.grid[1]!=512||s.grid[2]!=1||s.block[0]!=256||s.block[1]!=1||s.block[2]!=1||s.shared||!s.args[4]||
    read<int>(reinterpret_cast<std::uintptr_t>(s.args[4]))!=8192)return false;
   if(arg(0)!=reinterpret_cast<std::uintptr_t>(global(0x1f071d8))||arg(1)!=reinterpret_cast<std::uintptr_t>(global(0x1f07200))||
    arg(2)!=read<std::uintptr_t>(layer+0x260)||arg(3)!=reinterpret_cast<std::uintptr_t>(global(0x1f071e0)))return false;
   // Sealed allocator slot and TB2 indexing proof: exactly three 20,480-byte history rows.
   // Bound this view inside the actual allocation; the shared arena itself also contains Z.
   return safe_span({arg(0),160*MiB},false)&&safe_span({arg(1),0xf000},true)&&whole(2,false)&&safe_span({arg(3),160*MiB},true);
  }
  if(s.function==reinterpret_cast<void*>(base+0x1f00690)){
   if(s.caller!=reinterpret_cast<void*>(base+0x1d8aca3)||!s.args[4]||read<int>(reinterpret_cast<std::uintptr_t>(s.args[4]))!=0)return false;
   const auto raw=reinterpret_cast<std::uintptr_t>(global(0x1f071d8));
   const auto prepared=reinterpret_cast<std::uintptr_t>(global(0x1f071e0));
   if(!contains({raw,160*MiB},{arg(0),20480})||(arg(0)-raw)%20480)return false;
   const auto offset=arg(0)-raw;
   if(prepared>UINTPTR_MAX-offset||arg(3)!=prepared+offset||!contains({prepared,160*MiB},{arg(3),20480})||
     arg(1)!=read<std::uintptr_t>(layer+0x260))return false;
   return safe_span({arg(0),20480},false)&&safe_span({arg(3),20480},true)&&whole(1,false)&&whole(2,true)&&(!arg(5)||whole(5,false));
  }
  if(s.function==reinterpret_cast<void*>(base+0x1f00688)){
   if(!s.args[6]||read<int>(reinterpret_cast<std::uintptr_t>(s.args[6]))!=count)return false;
   if(arg(0)!=reinterpret_cast<std::uintptr_t>(global(0x1f071f0))||arg(1)!=reinterpret_cast<std::uintptr_t>(global(0x1f071f8))||
    arg(4)!=reinterpret_cast<std::uintptr_t>(global(0x1f07230))||arg(5)!=reinterpret_cast<std::uintptr_t>(global(0x1f07238)))return false;
   return safe_span({arg(0),768*1024},false)&&safe_span({arg(1),768*1024},false)&&whole(2,false)&&whole(3,false)&&
    safe_span({arg(4),1536*1024},true)&&safe_span({arg(5),1536*1024},true);
  }
  return false;
 }
 void join(){
  if(stage==Stage::none)return;
  if(stage!=Stage::queued||context.join_pending()!=Result::joined)fail("join before submission or failed dependency");
  stage=Stage::none;
  if(validation){
   if(api.stream_sync(nullptr)||copy_host(actual.data(),reinterpret_cast<void*>(z.address),Zbytes,2))fail("Z comparison copy failed");
   if(std::memcmp(reference.data(),actual.data(),Zbytes))fail("full BF16 Z byte comparison differs");
   if(qualified_count<qualified.size())qualified[qualified_count++]={tuple,trace,reference_key};
   std::fprintf(stderr,"deferred-z: Z_BYTES_EQUAL bytes=%zu M=8192 descriptor=%p; full DN/state parity unqualified\n",Zbytes,reinterpret_cast<void*>(tuple.descriptor));
   validation=false;
  }
 }
 static bool observe(void* cookie,const Submit& s){
  auto& r=*static_cast<Run*>(cookie);
  if(r.recording){if(!r.closure(s)){r.trace.safe=false;return true;}return r.trace.observe(s,true);}
  if(active_redirect)return r.closure(s)&&r.trace.observe(s,false);
  if(r.stage==Stage::captured){if(r.ab)return true;r.fail("unexpected submission before after-AB seam");}
  if(r.stage==Stage::queued&&!r.known_prep(s))r.join();
  return true;
 }
};
thread_local Run* run;
thread_local bool stock_dn_owner;
struct NativeOwnerScope {
 NativeOwnerScope(){native_owner.store(true);}
 ~NativeOwnerScope(){native_owner.store(false);}
 NativeOwnerScope(const NativeOwnerScope&)=delete;
};
struct StockDnScope {
 StockDnScope(){stock_dn_owner=true;}
 ~StockDnScope(){stock_dn_owner=false;}
 StockDnScope(const StockDnScope&)=delete;
};
bool eligible_dn(void* m,int l,int c){
 if(c!=8192||l<0||!m)return false;
 const char* prefetch=std::getenv("HALOGEN_DECODE_PREFETCH");
 if(!prefetch||std::strcmp(prefetch,"0"))return false;
 const auto model=reinterpret_cast<std::uintptr_t>(m);
 return !read<void*>(model+0x320)&&read<std::uintptr_t>(model+0x7c8);
}

void fc_hook(void* d,const void* x,void* y,int n,int m,int k){
 if(stock_dn_owner)return original_fc(d,x,y,n,m,k);
 auto caller=reinterpret_cast<std::uintptr_t>(__builtin_return_address(0));
 if(!run){
  std::unique_lock<std::mutex> lock(owner_mutex,std::try_to_lock);
  if(!lock.owns_lock()||native_owner.load())stop("foreign FC while owned DN active");
  return original_fc(d,x,y,n,m,k);
 }
 auto& r=*run;
 const bool is_z=r.layer&&caller==base+0x1d89e55&&reinterpret_cast<std::uintptr_t>(d)==r.layer+0x80&&
  x==read<void*>(reinterpret_cast<std::uintptr_t>(r.model)+0xb38)&&y==global(0x1f071e8)&&n==6144&&m==8192&&k==2560;
 if(r.stage==Run::Stage::captured){
  bool alpha=caller==base+0x1d89fdb&&reinterpret_cast<std::uintptr_t>(d)==r.layer+0xf8&&y==global(0x1f071f0);
  bool beta=caller==base+0x1d8a008&&reinterpret_cast<std::uintptr_t>(d)==r.layer+0x170&&y==global(0x1f071f8);
  if((alpha&&(r.alpha_seen||r.beta_seen))||(beta&&(!r.alpha_seen||r.beta_seen))||!(alpha||beta)||n!=48||m!=8192||k!=2560||x!=reinterpret_cast<void*>(r.tuple.input))r.fail("unexpected FC before after-AB seam");
  if(alpha)r.alpha_seen=true;else r.beta_seen=true;
  r.ab=true;try{original_fc(d,x,y,n,m,k);}catch(...){r.ab=false;r.fail("AB exception after Z suppression");}r.ab=false;return;
 }
 if(r.stage==Run::Stage::queued)r.join();
 if(!is_z)return original_fc(d,x,y,n,m,k);
 Tuple t{reinterpret_cast<std::uintptr_t>(d),reinterpret_cast<std::uintptr_t>(x),reinterpret_cast<std::uintptr_t>(y),n,m,k};
 if(!r.ranges(t))return original_fc(d,x,y,n,m,k);
 r.tuple=t;bool warm=false;
 for(std::size_t i=0;i<qualified_count;++i)if(same(qualified[i].tuple,t)&&qualified[i].key==r.prep_key(t)&&r.bind_plan()&&qualified[i].trace.entries[1].algorithm==r.reference_algorithm){r.trace=qualified[i].trace;r.trace.cursor=0;warm=true;break;}
 if(!warm){
  r.reference.resize(Zbytes);r.actual.resize(Zbytes);
  // Exactly one cold stock warmup, then one observed stock reference. No retry-until-pass loop.
  original_fc(d,x,y,n,m,k);
  if(api.stream_sync(nullptr))r.fail("cold stock warmup synchronization failed");
  if(!narrow_ht(r.policy(t))||!r.bind_plan())return;
  r.reference_mode=read<int>(t.descriptor+0x48);r.reference_key=r.prep_key(t);
  r.recording=true;
  try{original_fc(d,x,y,n,m,k);}catch(...){r.recording=false;throw;}r.recording=false;
  if(!r.trace.safe||r.trace.count!=2||r.trace.entries[0].kind!=SubmitKind::kernel||r.trace.entries[1].kind!=SubmitKind::matmul)return;
  if(api.stream_sync(nullptr)||copy_host(r.reference.data(),y,Zbytes,2))r.fail("stock Z reference copy failed");
  r.validation=true;
 }
 if(!narrow_ht(r.policy(t)))return warm?original_fc(d,x,y,n,m,k):void();
 if(warm){r.reference_mode=read<int>(t.descriptor+0x48);r.reference_key=r.prep_key(t);if(!r.bind_plan())return original_fc(d,x,y,n,m,k);}
 if(!r.open()){if(r.context.poisoned())r.fail("context open partially failed");if(warm)original_fc(d,x,y,n,m,k);return;}
 if(r.context.capture({original_fc,d,x,y,n,m,k})!=Result::captured)r.fail("capture failed");
 r.stage=Run::Stage::captured;
}
void helper_hook(void* m,int l,int c){
 if(run&&run->stage==Run::Stage::captured&&read<void*>(reinterpret_cast<std::uintptr_t>(m)+0x320))run->fail("native prefetch became active after capture");
 original_helper(m,l,c);
 if(!run||run->stage==Run::Stage::none)return;
 auto& r=*run;
 if(m!=r.model||c!=8192||l<0||r.layer!=read<std::uintptr_t>(reinterpret_cast<std::uintptr_t>(m)+0x7c8)+static_cast<std::size_t>(l)*0xd08||!r.alpha_seen||!r.beta_seen||r.stage!=Run::Stage::captured)r.fail("after-AB tuple mismatch");
 if(!narrow_ht(r.policy(r.tuple))||!r.same_plan()||r.prep_key(r.tuple)!=r.reference_key||read<int>(r.tuple.descriptor+0x48)!=r.reference_mode)r.fail("native HT branch changed after capture");
 r.trace.cursor=0;
 if(r.context.after_ab()!=Result::pending||r.trace.cursor!=r.trace.count)r.fail("side FC closure mismatch or launch failure");
 r.stage=Run::Stage::queued;
}
// Keep the large Run/Trace stack frame entirely out of stock decode calls.
__attribute__((noinline)) void candidate_dn(void* m,int l,int c){
 if(!api.stream_sync){
  if(!deferred_z_bind_hip(&api))stop("HIP binding unavailable");
  address_range=reinterpret_cast<decltype(address_range)>(dlsym(RTLD_NEXT,"hipMemGetAddressRange"));
  copy_host=reinterpret_cast<decltype(copy_host)>(dlsym(RTLD_NEXT,"hipMemcpy"));
  if(!address_range||!copy_host)stop("allocation/reference binding unavailable");
 }
 Run scope(m,l,c);run=&scope;
 Observation observation{Run::observe,&scope,false};ObserverScope observer(observation);
 if(!observer.entered())stop("nested observer rejected");
 try{original_dn(m,l,c);scope.join();}
 catch(...){if(scope.stage!=Run::Stage::none)scope.fail("native unwind after suppression");if(!scope.context.close())scope.fail("unwind drain failed");run=nullptr;throw;}
 if(!scope.context.close())scope.fail("close/drain failed");
 run=nullptr;
}

void dn_hook(void* m,int l,int c){
 if(run||stock_dn_owner)stop("nested DN rejected");
 std::unique_lock<std::mutex> lock(owner_mutex,std::try_to_lock);
 if(!lock.owns_lock())stop("concurrent DN rejected");
 NativeOwnerScope ownership;
 if(!eligible_dn(m,l,c)){
  StockDnScope stock;
  return original_dn(m,l,c);
 }
 candidate_dn(m,l,c);
}

void* executable_page(void* hint=nullptr){return mmap(hint,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);}
void protect_rx(void* p){if(mprotect(p,4096,PROT_READ|PROT_EXEC))stop("trampoline RX protection failed");}
void patch(std::uintptr_t a,const unsigned char* p,std::size_t n){
 auto page=a&~std::uintptr_t(4095);auto end=(a+n+4095)&~std::uintptr_t(4095);
 if(mprotect(reinterpret_cast<void*>(page),end-page,PROT_READ|PROT_WRITE))stop("patch protection failed");
 std::memcpy(reinterpret_cast<void*>(a),p,n);__builtin___clear_cache(reinterpret_cast<char*>(a),reinterpret_cast<char*>(a+n));
 if(mprotect(reinterpret_cast<void*>(page),end-page,PROT_READ|PROT_EXEC))stop("patch RX protection failed");
}
void* detour(std::uintptr_t site,std::size_t stolen,std::uintptr_t target){
 auto* p=static_cast<unsigned char*>(executable_page());if(p==MAP_FAILED)stop("trampoline allocation failed");
 std::memcpy(p,reinterpret_cast<void*>(site),stolen);absolute_jump(p+stolen,site+stolen);protect_rx(p);
 std::array<unsigned char,32> bytes{};bytes.fill(0x90);absolute_jump(bytes.data(),target);patch(site,bytes.data(),stolen);return p;
}
void* near_relay(std::uintptr_t site,std::uintptr_t target){
 for(std::uintptr_t delta=0x10000;delta<0x70000000;delta+=0x10000){
  for(int sign:{1,-1}){
   auto a=(sign>0?site+delta:site-delta)&~std::uintptr_t(4095);
   void* p=mmap(reinterpret_cast<void*>(a),4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
   if(p==MAP_FAILED)continue;
   unsigned char call[5];if(!relative_call(call,site,reinterpret_cast<std::uintptr_t>(p))){munmap(p,4096);continue;}
   absolute_jump(static_cast<unsigned char*>(p),target);protect_rx(p);return p;
  }
 }
 return nullptr;
}
bool install(){
 if(!seal_executable())return false;
 dl_iterate_phdr(find_main,nullptr);if(!base)return false;
 for(std::size_t i=0;i<runtime_pins.size();++i){
  const auto& p=dz_pins::all[i];if(std::memcmp(reinterpret_cast<void*>(base+p.rva),p.bytes,p.size))return false;
  runtime_pins[i]={base+p.rva,p.bytes,p.size};
 }
 identity_ok=true;
 // Resolve lazily at DN entry, because HIP initialization belongs to native main.
 auto* relay=near_relay(base+0x1d8a021,reinterpret_cast<std::uintptr_t>(helper_hook));if(!relay)return false;
 original_helper=reinterpret_cast<Dn>(base+0x1d89740);
 original_fc=reinterpret_cast<Fc>(detour(base+0x1d84510,14,reinterpret_cast<std::uintptr_t>(fc_hook)));
 original_dn=reinterpret_cast<Dn>(detour(base+0x1d89a60,17,reinterpret_cast<std::uintptr_t>(dn_hook)));
 unsigned char call[5];if(!relative_call(call,base+0x1d8a021,reinterpret_cast<std::uintptr_t>(relay)))stop("relay range changed");
 patch(base+0x1d8a021,call,sizeof call);
 for(std::size_t i=0;i<runtime_pins.size();++i){
  if(runtime_pins[i].bytes>installed_bytes[i].size())stop("pin exceeds receipt capacity");
  std::memcpy(installed_bytes[i].data(),reinterpret_cast<void*>(runtime_pins[i].address),runtime_pins[i].bytes);
  runtime_pins[i].expected=installed_bytes[i].data();
 }
 return true;
}
bool engine_name(){
 char path[4096];const auto n=readlink("/proc/self/exe",path,sizeof(path)-1);
 if(n<=0)return false;
 path[n]=0;const char* name=std::strrchr(path,'/');
 return std::strcmp(name?name+1:path,"flash_serve")==0;
}
using Main=int(*)(int,char**,char**);Main native_main;
int adapter_main(int argc,char** argv,char** env){
 if(!install())stop("exact image/byte seal or hook installation rejected");
 return native_main(argc,argv,env);
}
}
#ifndef DZ_NO_START_INTERPOSER
extern "C" int __libc_start_main(int(*main_fn)(int,char**,char**),int argc,char** argv,
 void(*init)(),void(*fini)(),void(*rtld_fini)(),void* stack_end){
 using Start=int(*)(Main,int,char**,void(*)(),void(*)(),void(*)(),void*);
 auto next=reinterpret_cast<Start>(dlsym(RTLD_NEXT,"__libc_start_main"));if(!next)_Exit(87);
 if(!dz_adapter::enabled(std::getenv("HALOGEN_DEFERRED_Z"))||!engine_name())return next(main_fn,argc,argv,init,fini,rtld_fini,stack_end);
 native_main=main_fn;return next(adapter_main,argc,argv,init,fini,rtld_fini,stack_end);
}
#endif
