#pragma once
// CPU fixture only. Never place this directory on a production include path.
#define RTLD_NEXT reinterpret_cast<void*>(-1)
extern "C" void* dlsym(void*,const char*);
