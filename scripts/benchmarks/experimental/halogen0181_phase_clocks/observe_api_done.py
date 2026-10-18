"""Default-OFF D companion. Wrap the exact stock parser AFTER its one call.

Root supplies the actual0.18.1 API file/hash in a measurement-only wrapper.
No module patch, launch, HTTP, token access or lifecycle action occurs here.
The wrapper always returns the same stock result object. Diagnostic I/O
failure marks this companion failed while preserving the stock result.
"""
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading


class DObserver:
    def __init__(self,enabled=False,*,journal=None,nonce=None,api_file=None,api_sha256=None,arm_file=None):
        self.enabled=enabled;self.failed=False;self.error=None;self.fd=None;self.sequence=0;self.lock=threading.Lock();self.arm_identity=None
        if not enabled:return
        if not re.fullmatch('[0-9a-f]{32}',nonce or '') or not re.fullmatch('[0-9a-f]{64}',api_sha256 or ''):
            raise ValueError('Explicit source pin and matching32hex capture nonce required')
        self.journal=Path(journal);self.arm=Path(arm_file) if arm_file else None
        if not self.journal.is_absolute() or self.journal.exists() or not self.journal.parent.is_dir():
            raise ValueError('Fresh absolute observer journal required')
        if self.arm is not None and (not self.arm.is_absolute() or self.arm==self.journal or self.arm.exists()):
            raise ValueError('Distinct fresh absolute observer arm required')
        self.api_sha256=api_sha256;self.nonce=nonce
        if hashlib.sha256(Path(api_file).read_bytes()).hexdigest()!=api_sha256:raise ValueError('Actual API file SHA differs')

    def _write(self,value):
        data=(json.dumps(value,separators=(',',':'))+'\n').encode('ascii')
        if os.write(self.fd,data)!=len(data):raise OSError('Short D journal write')

    def _arm_ready(self):
        if self.arm is None:return True
        flags=os.O_RDONLY|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
        try:fd=os.open(self.arm,flags)
        except FileNotFoundError:return False
        try:
            value=os.fstat(fd)
            if not (stat.S_ISREG(value.st_mode) and stat.S_IMODE(value.st_mode)==0o600 and value.st_size==0
                and value.st_nlink==1 and hasattr(os,'getuid') and value.st_uid==os.getuid()):
                raise ValueError('Owned empty regular0600 arm required')
            identity=(value.st_dev,value.st_ino)
            if self.arm_identity is not None and self.arm_identity!=identity:raise ValueError('Observer arm identity changed')
            self.arm_identity=identity
            return True
        finally:os.close(fd)

    def record(self,parts,stock_result):
        with self.lock:
            try:
                # Close and record share the lock: a closed journal cannot reopen.
                if not self.enabled or self.failed or not self._arm_ready():return
                # Native protocol only; no prompt, output text or credentials.
                if not isinstance(parts,list) or not 7<=len(parts)<=64 or parts[0]!='D':
                    raise ValueError('Native D frame rejected')
                if not all(isinstance(p,str) and len(p)<=128 for p in parts):raise ValueError('D field bound rejected')
                rid,prompt,predicted=int(parts[1]),int(parts[3]),int(parts[4]);pms,dms=float(parts[5]),float(parts[6])
                if not -(1<<63)<=rid<(1<<63) or not 0<=prompt<(1<<32) or not 0<=predicted<(1<<32) or not all(math.isfinite(x) and x>=0 for x in (pms,dms)):
                    raise ValueError('Native D scalar rejected')
                if not isinstance(stock_result,dict) or any(stock_result.get(k)!=v for k,v in
                    [('n_prompt',prompt),('n_gen',predicted),('prefill_ms',pms),('decode_ms',dms),('reason',parts[2])]):
                    raise ValueError('Stock parser native fields differ')
                if self.sequence>=256:raise ValueError('Bounded D capture exhausted')
                if self.fd is None:
                    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_APPEND|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)
                    self.fd=os.open(self.journal,flags,0o600)
                    self._write(dict(kind='activation',schema='halogen0181.native-d-after-parser.v1',nonce=self.nonce,api_sha256=self.api_sha256,
                        deferred_arm=int(self.arm is not None),arm_file_device=self.arm_identity[0] if self.arm_identity else 0,
                        arm_file_inode=self.arm_identity[1] if self.arm_identity else 0))
                self.sequence+=1
                self._write(dict(kind='native_d',sequence=self.sequence,request_id=rid,prompt_count=prompt,predicted_count=predicted,
                    prefill_ms=pms,decode_ms=dms,reason=parts[2],parts=list(parts),stock_parser_fields_unchanged=True))
            except (OSError,ValueError,TypeError,KeyError) as error:
                self.failed=True;self.error=str(error)

    def wrap(self,stock_done):
        @functools.wraps(stock_done)
        def done(parts):
            result=stock_done(parts)  # Exactly once, before all observer work.
            self.record(parts,result)
            return result            # Same object; never mutate fields.
        return done

    def close(self):
        with self.lock:
            self.enabled=False
            if self.fd is not None:
                try:
                    if not self.failed:self._write(dict(kind='completion',request_count=self.sequence,failed=False))
                    os.fsync(self.fd)
                except OSError as error:self.failed=True;self.error=str(error)
                finally:
                    try:os.close(self.fd)
                    except OSError as error:self.failed=True;self.error=str(error)
                    self.fd=None
