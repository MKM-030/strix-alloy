#include "retained_controller.h"
using namespace hgn_dflash;
struct Sha {u32 state[8];u64 bytes;u32 used;u8 block[64];};
static u32 rotate(u32 x,u32 n)noexcept{return(x>>n)|(x<<(32-n));}
static void hash_block(Sha& s,const u8* b)noexcept{
    static const u32 k[64]={
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    u32 w[64];for(u32 i=0;i<16;++i)w[i]=(u32(b[4*i])<<24)|(u32(b[4*i+1])<<16)|(u32(b[4*i+2])<<8)|b[4*i+3];
    for(u32 i=16;i<64;++i)w[i]=w[i-16]+(rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10));
    auto a=s.state[0],v=s.state[1],c=s.state[2],d=s.state[3],e=s.state[4],f=s.state[5],g=s.state[6],h=s.state[7];
    for(u32 i=0;i<64;++i){auto t1=h+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^((~e)&g))+k[i]+w[i];
        auto t2=(rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&v)^(a&c)^(v&c));h=g;g=f;f=e;e=d+t1;d=c;c=v;v=a;a=t1+t2;}
    s.state[0]+=a;s.state[1]+=v;s.state[2]+=c;s.state[3]+=d;s.state[4]+=e;s.state[5]+=f;s.state[6]+=g;s.state[7]+=h;
}
static void hash_init(Sha& s)noexcept{
    const u32 initial[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    for(u32 i=0;i<8;++i)s.state[i]=initial[i];s.bytes=0;s.used=0;
}
static void hash_update(Sha& s,const u8* b,u64 bytes)noexcept{
    s.bytes+=bytes;for(u64 i=0;i<bytes;++i){s.block[s.used++]=b[i];if(s.used==64){hash_block(s,s.block);s.used=0;}}
}
static void hash_finish(Sha& s,u8* digest)noexcept{
    auto bits=s.bytes*8;s.block[s.used++]=0x80;
    if(s.used>56){while(s.used<64)s.block[s.used++]=0;hash_block(s,s.block);s.used=0;}
    while(s.used<56)s.block[s.used++]=0;
    for(u32 i=0;i<8;++i)s.block[63-i]=u8(bits>>(8*i));hash_block(s,s.block);
    for(u32 i=0;i<32;++i)digest[i]=u8(s.state[i/4]>>(24-8*(i%4)));
}

static u8 fixture[8193];int main(){Sha s{};u8 out[32];hash_init(s);hash_update(s,fixture,0);hash_finish(s,out);const u8 expected0[32]={0xe3,0xb0,0xc4,0x42,0x98,0xfc,0x1c,0x14,0x9a,0xfb,0xf4,0xc8,0x99,0x6f,0xb9,0x24,0x27,0xae,0x41,0xe4,0x64,0x9b,0x93,0x4c,0xa4,0x95,0x99,0x1b,0x78,0x52,0xb8,0x55};for(u32 i=0;i<32;++i)if(out[i]!=expected0[i])return 1;
fixture[0]='a';fixture[1]='b';fixture[2]='c';hash_init(s);hash_update(s,fixture,3);hash_finish(s,out);const u8 expected1[32]={0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad};for(u32 i=0;i<32;++i)if(out[i]!=expected1[i])return 2;
for(u32 i=0;i<8193;++i)fixture[i]=u8(i%251);hash_init(s);hash_update(s,fixture,8193);hash_finish(s,out);const u8 expected2[32]={0x7e,0x36,0x91,0x79,0x0c,0xd6,0x4b,0x19,0xd4,0xed,0xb1,0xa8,0x0e,0x98,0x82,0x14,0x51,0x5a,0xbe,0xb5,0x3a,0xa0,0xf3,0x4f,0xfb,0xfe,0x4b,0x4b,0xf4,0x05,0xd1,0x20};for(u32 i=0;i<32;++i)if(out[i]!=expected2[i])return 3;return 0;}
