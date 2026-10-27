#define DZ_NO_START_INTERPOSER
#include "installer_linux.cpp"
#include <cassert>
#include <vector>
#include <stdexcept>
namespace {
std::array<Range,10> fake_allocations{};
int fake_address_range(void** address,std::size_t* bytes,void* pointer){
 for(const auto& allocation:fake_allocations)if(contains(allocation,{reinterpret_cast<std::uintptr_t>(pointer),1})){
  *address=reinterpret_cast<void*>(allocation.address);*bytes=allocation.bytes;return 0;
 }
 return 1;
}
unsigned stock_dn_calls{},stock_fc_calls{};bool stock_throw{};
void stock_fc_fixture(void* d,const void* x,void* y,int n,int m,int k){
 assert(d==reinterpret_cast<void*>(0x10)&&x==reinterpret_cast<void*>(0x20)&&y==reinterpret_cast<void*>(0x30));
 assert(n==48&&m==1&&k==2560);assert(native_owner.load()&&stock_dn_owner&&run==nullptr&&active_observation==nullptr);
 ++stock_fc_calls;
}
void stock_dn_fixture(void* m,int l,int c){
 assert(m==nullptr&&l==-1&&(c==1||c==4096||c==8192));
 assert(run==nullptr&&active_observation==nullptr&&active_redirect==nullptr&&native_owner.load());
 bool foreign_acquired=true;
 std::thread foreign([&]{foreign_acquired=owner_mutex.try_lock();if(foreign_acquired)owner_mutex.unlock();});foreign.join();
 assert(!foreign_acquired);
 fc_hook(reinterpret_cast<void*>(0x10),reinterpret_cast<void*>(0x20),reinterpret_cast<void*>(0x30),48,1,2560);
 ++stock_dn_calls;if(stock_throw)throw std::runtime_error("stock native exception");
}
int unused_sync_fixture(void*){assert(false);return 1;}
void put(std::uintptr_t address,std::uint64_t value,std::size_t bytes=8){std::memcpy(reinterpret_cast<void*>(address),&value,bytes);}
}
int main(){
 // Referencing installation symbols prevents artificial unused-function diagnostics in this inclusion fixture.
 (void)adapter_main;(void)engine_name;(void)native_main;
 std::vector<unsigned char> mapped(0x1f10000),model(0xc00),layer(0x300),desc(0x80),ctx(0x90),node(0x50),plan_data(0x90);
 base=reinterpret_cast<std::uintptr_t>(mapped.data());
 const auto model_p=reinterpret_cast<std::uintptr_t>(model.data()),layer_p=reinterpret_cast<std::uintptr_t>(layer.data());
 const auto desc_p=reinterpret_cast<std::uintptr_t>(desc.data()),ctx_p=reinterpret_cast<std::uintptr_t>(ctx.data());
 const auto node_p=reinterpret_cast<std::uintptr_t>(node.data()),plan_p=reinterpret_cast<std::uintptr_t>(plan_data.data());
 put(model_p+0x7c8,layer_p);put(base+0x1f07448,ctx_p);put(ctx_p+0x60,node_p);
 put(node_p+0x28,2560);put(node_p+0x30,6144);put(node_p+0x38,8192);put(node_p+0x40,plan_p);
 put(plan_p+0x20,8192);put(plan_p+0x28,6144);put(plan_p+0x30,2560);put(plan_p+0x61,1,1);
 for(unsigned i=0;i<24;++i)plan_data[0x68+i]=static_cast<unsigned char>(i+1);
 put(plan_p,0x11);put(plan_p+8,0x12);put(plan_p+0x10,0x13);put(plan_p+0x18,0x14);put(ctx_p+0x38,0x15);
 Run r(model.data(),0,8192);r.layer=layer_p;r.tuple={desc_p,0x22000000,0x33000000,6144,8192,2560};
 r.input={r.tuple.input,40*MiB};r.z={r.tuple.output,Zbytes};r.scratch[0]={0x44000000,256*MiB};r.scratch[3]={0x55000000,128*MiB};
 assert(r.bind_plan()&&r.same_plan());
 put(plan_p+0x48,1);assert(!r.plan());put(plan_p+0x48,0);assert(r.plan()==plan_p);
 put(node_p+0x30,1);assert(!r.plan());put(node_p+0x30,6144);
 put(desc_p+0x30,0x60000000);put(desc_p+0x38,0x61000000);put(desc_p+0x40,0x62000000);put(base+0x1f0a398,16,4);put(base+0x1f0a3a0,1,1);put(base+0x1f0a3b0,1,1);put(base+0x1f0a3c0,1,1);
 std::uintptr_t weight=0x60000000,scale=0x61000000,aux=0x62000000,out=0x44000000;int k=2560,config=16;
 void* args[]={&weight,&k,&scale,&aux,&out,&config};
 Submit kernel{};kernel.kind=SubmitKind::kernel;kernel.function=reinterpret_cast<void*>(base+0x1f02a40);
 kernel.caller=reinterpret_cast<void*>(base+0x1dea96a);kernel.args=args;kernel.grid[0]=120;kernel.block[0]=256;
 assert(r.closure(kernel));Trace trace;assert(trace.observe(kernel,true));
 float alpha=1,beta=0;std::array<unsigned char,24> algo=r.reference_algorithm;
 Submit matmul{};matmul.kind=SubmitKind::matmul;matmul.function=reinterpret_cast<void*>(0x11);matmul.caller=reinterpret_cast<void*>(base+0x1ef0c4c);
 matmul.matmul_handle=reinterpret_cast<void*>(0x15);matmul.matmul_operands[0]=reinterpret_cast<void*>(out);
 matmul.matmul_operands[1]=reinterpret_cast<void*>(r.input.address);matmul.matmul_operands[2]=matmul.matmul_operands[3]=reinterpret_cast<void*>(r.z.address);
 matmul.matmul_layouts[0]=reinterpret_cast<void*>(0x12);matmul.matmul_layouts[1]=reinterpret_cast<void*>(0x13);
 matmul.matmul_layouts[2]=matmul.matmul_layouts[3]=reinterpret_cast<void*>(0x14);matmul.matmul_alpha=&alpha;matmul.matmul_beta=&beta;matmul.matmul_algorithm=algo.data();
 matmul.workspace=reinterpret_cast<void*>(r.scratch[3].address);matmul.workspace_bytes=128*MiB;
 assert(r.closure(matmul)&&trace.observe(matmul,true));assert(trace.observe(kernel,false)&&trace.observe(matmul,false));
 trace.cursor=0;k=2561;assert(!r.closure(kernel)&&!trace.observe(kernel,false));k=2560;
 trace.cursor=1;algo[0]^=1;assert(!r.closure(matmul)&&!trace.observe(matmul,false));algo[0]^=1;
 matmul.matmul_operands[1]=nullptr;assert(!r.closure(matmul));
 Submit event{};event.kind=SubmitKind::synchronize;assert(!r.closure(event));
 // The main arena deliberately contains both the history view and Z.
 r.z={0x1a000000,Zbytes};r.input={0x70000000,40*MiB};
 r.scratch={{{0x80000000,256*MiB},{0x90000000,96*MiB},{0xa0000000,128*MiB},{0xb0000000,128*MiB}}};
 r.side_sources={{{0xc0000000,16*MiB},{0xc1000000,16*MiB},{0xc2000000,16*MiB}}};
 fake_allocations={{{0x10000000,1024*MiB},r.input,r.scratch[0],r.scratch[1],r.scratch[2],r.scratch[3],r.side_sources[0],r.side_sources[1],r.side_sources[2],{0xd0000000,16*MiB}}};
 address_range=fake_address_range;
 put(base+0x1f071d8,0x20000000);put(base+0x1f07200,0x11000000);put(base+0x1f071e0,0x30000000);put(layer_p+0x260,0xd0000000);put(base+0x1f074c8,2,4);
 std::uintptr_t raw=0x20000000,history=0x11000000,conv_weight=0xd0000000,prepared=0x30000000;int m=8192;
 void* conv_args[]={&raw,&history,&conv_weight,&prepared,&m};
 Submit conv{};conv.kind=SubmitKind::kernel;conv.function=reinterpret_cast<void*>(base+0x1f006a8);conv.caller=reinterpret_cast<void*>(base+0x1d96eaa);conv.args=conv_args;conv.grid[0]=10;conv.grid[1]=512;conv.grid[2]=1;conv.block[0]=256;conv.block[1]=1;conv.block[2]=1;
 assert(r.known_prep(conv));
 conv.block[0]=128;assert(!r.known_prep(conv));conv.block[0]=256;
 history=r.z.address-0xf000;put(base+0x1f07200,history);assert(r.known_prep(conv));
 history++;put(base+0x1f07200,history);assert(!r.known_prep(conv));
 history=r.z.address;put(base+0x1f07200,history);assert(!r.known_prep(conv));
 history=0x11000000;put(base+0x1f07200,history);prepared=r.z.address;put(base+0x1f071e0,prepared);assert(!r.known_prep(conv));
 // Ineligible DN forms retain ownership but never install an observer or bind/create HIP resources.
 original_dn=stock_dn_fixture;original_fc=stock_fc_fixture;api={};api.stream_sync=unused_sync_fixture;
 dn_hook(nullptr,-1,1);dn_hook(nullptr,-1,4096);dn_hook(nullptr,-1,8192);
 assert(stock_dn_calls==3&&stock_fc_calls==3&&!stock_dn_owner&&!native_owner.load()&&run==nullptr&&active_observation==nullptr);
 stock_throw=true;bool caught=false;try{dn_hook(nullptr,-1,1);}catch(const std::runtime_error&){caught=true;}
 assert(caught&&!stock_dn_owner&&!native_owner.load()&&run==nullptr&&active_observation==nullptr);
 stock_throw=false;dn_hook(nullptr,-1,1);assert(stock_dn_calls==5&&stock_fc_calls==5);
 assert(owner_mutex.try_lock());owner_mutex.unlock();
 std::puts("PASS: bounded native plan lookup, tuner rejection, prepared6args and full matmul-role/algo trace");
}
