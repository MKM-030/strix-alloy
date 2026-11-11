"""Explicit native binding; import is inert, construction belongs to Root's worker."""
import ctypes as c
import hashlib
import os
from pathlib import Path
import threading

from actor import OwnedRow,ROWS,need

QWEN_SHA256='81b9349b5eb6cc7af277a41fad3a5dd7aa71321a82f8a484e7a980d80c334fad'


def verify_loaded_qwen(expected_path):
    """Prove the actual loaded provider, never load one to satisfy this guard."""
    expected=Path(expected_path).resolve()
    api=c.WinDLL('kernel32',use_last_error=True)
    api.GetModuleHandleW.argtypes=[c.c_wchar_p];api.GetModuleHandleW.restype=c.c_void_p
    api.GetModuleFileNameW.argtypes=[c.c_void_p,c.c_wchar_p,c.c_uint32]
    api.GetModuleFileNameW.restype=c.c_uint32
    handle=api.GetModuleHandleW('qwen3_5vl_npu.dll')
    need(bool(handle),'Expected Qwen provider is not actually loaded')
    buffer=c.create_unicode_buffer(32768)
    length=api.GetModuleFileNameW(handle,buffer,len(buffer))
    need(0<length<len(buffer),'Actual loaded Qwen module path unavailable or truncated')
    actual=Path(buffer.value).resolve()
    need(os.path.normcase(str(actual))==os.path.normcase(str(expected)),
         'Actual loaded Qwen module path differs from qualified runtime')
    h=hashlib.sha256()
    with actual.open('rb')as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    need(h.hexdigest()==QWEN_SHA256,'Actual loaded Qwen module SHA256 differs')
    return dict(path=str(actual),sha256=h.hexdigest())


class Timing(c.Structure):
    _fields_=[('started_ticks',c.c_int64),('finished_ticks',c.c_int64),('frequency',c.c_int64)]


class NativeBackend:
    def __init__(self,dll_path,model_dir,bundle_root,runtime_dir):
        need(os.name=='nt','Only matching Windows AMD64 FLM 1.0.12 is supported')
        self.owner=threading.get_ident();self.operations=[];self.states=set();self.handle=None
        self._dll_directories=[];self.dll=None
        self.append_head_skip_enabled=False;self.head_skip_identity=None
        try:self._construct(dll_path,model_dir,bundle_root,runtime_dir)
        except BaseException as original:
            try:self.close()
            except BaseException as cleanup:
                failure=RuntimeError('Native initialization failed: '+str(original)+'; cleanup failed: '+str(cleanup))
                failure.native_cleanup_complete=False;failure.resource_owner=self
                raise failure from original
            raise

    def _construct(self,dll_path,model_dir,bundle_root,runtime_dir):
        dll_path=Path(dll_path).resolve();runtime_dir=Path(runtime_dir).resolve()
        self._expected_qwen_path=runtime_dir/'qwen3_5vl_npu.dll'
        need(dll_path.is_file(),'Explicit compiled bridge DLL required')
        need(runtime_dir.is_dir(),'Explicit qualified runtime directory required')
        for directory in(dict.fromkeys((dll_path.parent,runtime_dir))):
            self._dll_directories.append(os.add_dll_directory(str(directory)))
        self.dll=c.CDLL(str(dll_path))
        signatures={
            'sl1012_last_error':([],c.c_char_p),
            'sl1012_create':([c.c_wchar_p,c.c_wchar_p,c.POINTER(Timing)],c.c_void_p),
            'sl1012_close':([c.c_void_p],c.c_int),
            'sl1012_context':([c.c_void_p,c.POINTER(c.c_int32)],c.c_int),
            'sl1012_seed':([c.c_void_p,c.POINTER(c.c_int32),c.c_uint32,c.POINTER(c.c_uint16),
                c.c_uint32,c.POINTER(c.c_int32),c.POINTER(Timing)],c.c_int),
            'sl1012_forward':([c.c_void_p,c.c_int32,c.POINTER(c.c_uint16),c.c_uint32,
                c.POINTER(c.c_int32),c.POINTER(Timing)],c.c_int),
            'sl1012_append_only':([c.c_void_p,c.c_int32,c.POINTER(Timing)],c.c_int),
            'sl1012_set_append_head_skip':([c.c_void_p,c.c_int],c.c_int),
            'sl1012_head_skip_status':([c.c_void_p,c.POINTER(c.c_uint64),c.POINTER(c.c_int32)],c.c_int),
            'sl1012_state_read':([c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(c.c_uint64),c.POINTER(Timing)],c.c_int),
            'sl1012_state_write':([c.c_void_p,c.c_void_p,c.POINTER(c.c_int32),c.POINTER(Timing)],c.c_int),
            'sl1012_state_free':([c.c_void_p,c.c_void_p],c.c_int)}
        for name,(args,result)in signatures.items():
            fn=getattr(self.dll,name);fn.argtypes=args;fn.restype=result
        timing=Timing();self.handle=self.dll.sl1012_create(str(Path(model_dir).resolve()),
            str(Path(bundle_root).resolve()),c.byref(timing))
        if not self.handle:raise RuntimeError(self._error())
        self._record('startup',timing)

    def _error(self):return(self.dll.sl1012_last_error()or b'Unknown native failure').decode('utf-8',errors='replace')

    def _check(self,result):
        if result!=0:raise RuntimeError(self._error())

    def _thread(self):
        if threading.get_ident()!=self.owner or not self.handle:raise RuntimeError('Native backend must stay on its live owner thread')

    def _record(self,operation,timing,**extra):
        need(0<=timing.started_ticks<=timing.finished_ticks and timing.frequency>0,'Actual native QPC endpoints required')
        self.operations.append(dict(operation=operation,clock='Windows QPC',frequency=timing.frequency,
            started_ticks=timing.started_ticks,finished_ticks=timing.finished_ticks,**extra))
        need(len(self.operations)<=4096,'Finite component operation bound exceeded')

    def context_length(self):
        self._thread();count=c.c_int32();self._check(self.dll.sl1012_context(self.handle,c.byref(count)));return count.value

    def head_skip_status(self):
        self._thread();count=c.c_uint64();restored=c.c_int32()
        self._check(self.dll.sl1012_head_skip_status(self.handle,c.byref(count),c.byref(restored)))
        need(restored.value in(0,1),'Invalid native head-restoration observation')
        return dict(count=count.value,restored=restored.value==1)

    def set_append_head_skip(self,enabled):
        self._thread();need(type(enabled)is bool,'Explicit boolean append-head selector required')
        identity=verify_loaded_qwen(self._expected_qwen_path)if enabled else None
        self._check(self.dll.sl1012_set_append_head_skip(self.handle,int(enabled)))
        status=self.head_skip_status()
        if not status['restored']:raise RuntimeError('Native head instructions are not restored after mode selection')
        self.append_head_skip_enabled=enabled
        if identity is not None:self.head_skip_identity=identity

    def _row(self,method,*args):
        self._thread();row=(c.c_uint16*ROWS)();greedy=c.c_int32();timing=Timing()
        self._check(method(self.handle,*args,row,ROWS,c.byref(greedy),c.byref(timing)))
        result=OwnedRow(greedy.value,bytes(row));need(len(result.data)==ROWS*2,'Complete native row required')
        self._record('seed'if method==self.dll.sl1012_seed else 'forward',timing,
            local_count=self.context_length(),greedy_id=result.greedy_id,owned_row_sha256=result.sha256)
        return result

    def seed(self,ids):
        need(len(ids)==512,'Exact seed tail512 required');values=(c.c_int32*len(ids))(*ids)
        return self._row(self.dll.sl1012_seed,values,len(ids))

    def forward(self,token):return self._row(self.dll.sl1012_forward,token)

    def append_only(self,token):
        self._thread();need(type(token)is int and 0<=token<ROWS,'Shared int32 append token required')
        before=self.context_length();need(512<=before<640,'Qualified local bound512..640 exceeded')
        timing=Timing();self._check(self.dll.sl1012_append_only(self.handle,token,c.byref(timing)))
        count=self.context_length();need(count==before+1,'Scalar append context did not advance exactly once')
        self._record('append_only',timing,local_count=count)

    def save(self):
        self._thread();state=c.c_void_p();estimated=c.c_uint64();timing=Timing()
        self._check(self.dll.sl1012_state_read(self.handle,c.byref(state),c.byref(estimated),c.byref(timing)))
        need(state.value is not None and state.value not in self.states,'Fresh opaque state handle required')
        self.states.add(state.value)
        self._record('state_read',timing,local_count=self.context_length(),estimated_state_bytes=estimated.value)
        return state.value

    def restore(self,state):
        self._thread();need(state in self.states,'Owned opaque state required');count=c.c_int32();timing=Timing()
        self._check(self.dll.sl1012_state_write(self.handle,state,c.byref(count),c.byref(timing)))
        self._record('state_write',timing,local_count=count.value);return count.value

    def free(self,state):
        self._thread();need(state in self.states,'Cannot free a foreign state')
        self._check(self.dll.sl1012_state_free(self.handle,state));self.states.remove(state)

    def close(self):
        if self.handle is not None:
            self._thread()
            if not self.head_skip_status()['restored']:
                failure=RuntimeError('Native head restoration failed; resource owner retained')
                failure.native_cleanup_complete=False;failure.resource_owner=self
                raise failure
            self._thread();self._check(self.dll.sl1012_close(self.handle));self.handle=None;self.states.clear()
            self.append_head_skip_enabled=False
        # Keep dependency search directories alive until the native engine is
        # actually freed. A failed native close leaves them retained for Root.
        while self._dll_directories:
            self._dll_directories[-1].close();self._dll_directories.pop()
