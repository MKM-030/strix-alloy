"""Explicit pinned Inco BF16 payload -> private owned CPU tensors.

Import is passive. No download, device selection, thread mutation or model
payload access occurs until load(path). At most4MiB read workspace in addition
to the1,206,131,200-byte owned tensor storage and Torch overhead. Returned bytes
are exactly those included in the complete pinned SHA; no tensors escape before
verification. This authenticates a file, never native request/feature authority.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
if __package__:
 from . import contract
else:import contract
CHUNK_BYTES=4*1024*1024
HEADER_BYTES=8800
HEADER_SHA256='5ef4772f77b6a3ea349c6515aceffdb999868946aafb04578416494c64ef0513'

def _json(raw):
 def unique(items):
  result={}
  for key,value in items:
   if key in result:raise ValueError('Duplicate JSON header key')
   result[key]=value
  return result
 try:return json.loads(raw,object_pairs_hook=unique)
 except (UnicodeError,json.JSONDecodeError) as e:raise ValueError('Invalid safetensors header') from e

def expected_header():
 """Explicit pinned metadata read only; no tensor runtime or payload."""
 contract.verify_saved_contract()
 raw=(contract.SOURCES/'safetensors-header.json').read_bytes()
 if len(raw)!=HEADER_BYTES or hashlib.sha256(raw).hexdigest()!=HEADER_SHA256:raise ValueError('Pinned header bytes differ')
 return _json(raw)

def validate_header(header,*,total_bytes,header_bytes):
 expected=expected_header()
 if type(total_bytes) is not int or total_bytes!=contract.PAYLOAD_BYTES or type(header_bytes) is not int or header_bytes!=HEADER_BYTES:raise ValueError('Pinned payload/header size differs')
 if type(header) is not dict or set(header)!=set(expected) or len(header)!=81:raise ValueError('Exact81 trained tensor names required')
 end=0
 for name in sorted(expected,key=lambda k:expected[k]['data_offsets'][0]):
  item=header[name];want=expected[name]
  if type(item) is not dict or set(item)!={'dtype','shape','data_offsets'} or item!=want:raise ValueError('Trained tensor dtype/shape/extent differs: '+name)
  if type(item['shape']) is not list or type(item['data_offsets']) is not list or any(type(n) is not int for n in item['shape']+item['data_offsets']):raise ValueError('Exact integer header fields required')
  start,stop=item['data_offsets'];words=1
  for d in item['shape']:words*=d
  if item['dtype']!='BF16' or start!=end or stop-start!=2*words:raise ValueError('Non-contiguous BF16 extent')
  end=stop
 if end!=1206131200 or end+8+header_bytes!=total_bytes:raise ValueError('Incomplete tensor data coverage')
 return end

def _open(path):
 # Owned loading needs no long-lived mapping. During Windows reads reject
 # existing writers and new write/delete opens, including replacement paths.
 if os.name!='nt':return open(path,'rb',buffering=0)
 import ctypes
 from ctypes import wintypes
 import msvcrt
 kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 create=kernel.CreateFileW;create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];create.restype=wintypes.HANDLE
 handle=create(str(Path(path).resolve()),0x80000000,1,None,3,0x08000000,None)
 if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
 try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
 except BaseException:
  kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle);raise
 return os.fdopen(fd,'rb',buffering=0)

def _read_owned(stream,header,header_bytes,total_bytes,expected_sha256):
 """Generic fixture plumbing, not a public model authentication API.

Public load always passes the fixed real contract SHA and validated81 header.
Reads/copies/hash the same data once; returned CPU tensors own their storage.
"""
 import torch
 if torch.get_num_threads()!=1 or torch.get_num_interop_threads()!=1:raise ValueError('Explicit one-thread CPU execution required')
 stream.seek(0);prefix=stream.read(8+header_bytes)
 if len(prefix)!=8+header_bytes:raise ValueError('Truncated header')
 digest=hashlib.sha256(prefix);owned={};copied=len(prefix)
 with torch.inference_mode():
  for name,item in sorted(header.items(),key=lambda kv:kv[1]['data_offsets'][0]):
   start,stop=item['data_offsets']
   if copied!=8+header_bytes+start:raise ValueError('Non-contiguous owned read')
   tensor=torch.empty(tuple(item['shape']),dtype=torch.bfloat16,device='cpu')
   target=tensor.view(torch.uint8).reshape(-1)
   if target.numel()!=stop-start:raise ValueError('Owned tensor extent differs')
   offset=0
   while offset<stop-start:
    data=bytearray(min(CHUNK_BYTES,stop-start-offset))
    count=stream.readinto(data)
    if not count:raise ValueError('Truncated tensor payload')
    if count<len(data):del data[count:]
    digest.update(data);target[offset:offset+len(data)].copy_(torch.frombuffer(data,dtype=torch.uint8))
    offset+=len(data);copied+=len(data)
   owned[name]=tensor
 if copied!=total_bytes or stream.read(1):raise ValueError('Payload length differs')
 if digest.hexdigest()!=expected_sha256:raise ValueError('Full pinned payload SHA256 differs')
 return owned

class LoadedWeights:
 """Private CPU ownership; Python privacy is not a security boundary.

No public tensor aliases. Reference assembly obtains internal read-only-use
aliases; consumers must never mutate them. File identity does not authenticate
caller-owned target weights, features, request birth or native cache ownership.
"""
 def __init__(self,*args,**kwargs):raise TypeError('Use explicit pinned load(path)')
 @property
 def names(self):return tuple(self._tensors)
 @property
 def payload_sha256(self):return contract.PAYLOAD_SHA256
 @property
 def model_revision(self):return contract.MODEL_REVISION
 def _select(self,names):return {name:self._tensors[name] for name in names}

def load(path):
 """Load actual pinned81 BF16 tensors; never changes CPU thread settings.

Root must explicitly configure intra/inter-op threads=1 before this call.
Only after complete fixed SHA validation is the private bundle published.
"""
 with _open(path) as stream:
  st=os.fstat(stream.fileno())
  if not stat.S_ISREG(st.st_mode) or st.st_size!=contract.PAYLOAD_BYTES:raise ValueError('Exact pinned regular-file size required')
  prefix=stream.read(8)
  if len(prefix)!=8:raise ValueError('Truncated safetensors length')
  length=struct.unpack('<Q',prefix)[0]
  if length!=HEADER_BYTES:raise ValueError('Exact pinned header length required')
  raw=stream.read(length)
  if len(raw)!=length:raise ValueError('Truncated safetensors header')
  header=_json(raw);validate_header(header,total_bytes=st.st_size,header_bytes=length)
  owned=_read_owned(stream,header,length,st.st_size,contract.PAYLOAD_SHA256)
  if os.fstat(stream.fileno()).st_size!=st.st_size:raise ValueError('Payload size changed during owned read')
 result=object.__new__(LoadedWeights);result._tensors=owned;return result
