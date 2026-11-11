"""Lazy request ownership for the reviewed native backend; import is inert.

Only a valid seed creates a native engine. The unchanged actor always keeps an
owned snapshot through normal promotion/correction; freeing its last state is
therefore request retirement. Partial cleanup failures remain retained/explicit.
"""
import threading
import time

from actor import ROWS,need


class RequestScopedBackend:
    def __init__(self,dll_path,model_dir,bundle_root,runtime_dir,*,backend_factory=None):
        self.args=(dll_path,model_dir,bundle_root,runtime_dir)
        self.factory=backend_factory;self.owner=threading.get_ident()
        self._active=None;self._completed=[];self._context_id=0
        self._cleanup_error=None;self._failed_owners=[]

    @property
    def context_active(self):return self._active is not None

    @property
    def cleanup_failed(self):return self._cleanup_error is not None

    @property
    def retained_failed_owners(self):return tuple(self._failed_owners)

    @property
    def states(self):return self._active.states if self._active is not None else frozenset()

    @property
    def operations(self):
        result=list(self._completed)
        if self._active is not None:
            result.extend(dict(op,request_context=self._context_id,request_context_closed=False)
                          for op in self._active.operations)
        return result

    def _thread(self):
        if threading.get_ident()!=self.owner:raise RuntimeError('Request context belongs to its serial actor thread')

    def _failure(self,message):
        self._cleanup_error=message
        error=RuntimeError(message);error.native_cleanup_complete=False;error.resource_owner=self
        return error

    def _live(self):
        self._thread()
        if self.cleanup_failed:raise self._failure(self._cleanup_error)
        need(self._active is not None,'No native request context is active')
        return self._active

    def _release(self):
        self._thread()
        if self.cleanup_failed:raise self._failure(self._cleanup_error)
        backend=self._active
        if backend is None:return
        started=time.perf_counter_ns()
        try:
            backend.close()
            need(backend.handle is None and not backend.states,'Native request context did not close completely')
        except BaseException as error:
            raise self._failure('Native request cleanup failed: '+str(error))from error
        finished=time.perf_counter_ns()
        self._completed.extend(dict(op,request_context=self._context_id,request_context_closed=True,
            request_close_started_qpc_ns=started,request_close_finished_qpc_ns=finished)for op in backend.operations)
        self._active=None

    def seed(self,ids):
        self._thread()
        if self.cleanup_failed:raise self._failure(self._cleanup_error)
        need(type(ids)in(list,tuple)and len(ids)==512
             and all(type(i)is int and 0<=i<ROWS for i in ids),'Exact shared seed512 required before native creation')
        need(self._active is None,'Previous native request must retire before a new seed')
        self._context_id+=1
        try:
            if self.factory is None:
                from native_backend import NativeBackend
                self._active=NativeBackend(*self.args)
            else:self._active=self.factory()
            return self._active.seed(ids)
        except BaseException as original:
            if getattr(original,'native_cleanup_complete',True)is not True:
                owner=getattr(original,'resource_owner',None)
                if owner is not None:self._failed_owners.append(owner)
                raise self._failure('Partial native construction cleanup failed: '+str(original))from original
            try:self._release()
            except BaseException as cleanup:
                raise self._failure('Native seed failed: '+str(original)+'; '+str(cleanup))from original
            raise

    def context_length(self):return self._live().context_length()

    def forward(self,token):return self._live().forward(token)

    def append_only(self,token):return self._live().append_only(token)

    def save(self):return self._live().save()

    def restore(self,state):return self._live().restore(state)

    def free(self,state):
        backend=self._live();backend.free(state)
        if not backend.states:self._release()

    def close(self):self._release()
