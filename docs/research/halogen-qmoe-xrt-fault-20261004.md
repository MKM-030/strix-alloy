# QMoEBf: null-object fault in XRT buffer-size query

Date: 2026-10-04. Static/read-only diagnosis of root's saved first-call crash.
No DLL loading, inference, hardware call, model/bank payload read, installed-file
change, or commit was performed. Only this new note was written.

The receipt is
`server/.local/optimization9h-20261004/qmoe-light-admission-d35f5a8b9b034d63a4f58faf0850e933/`.
Its stdout records strict ORT 1.29 session admission, collector arming, and
`synthetic_call_0_invoke`; no return marker follows. Guard result records child
exit 3221225477 (`0xC0000005`) and owned-job closure. Native receipt SHA256:
`f5ea4ac45de04148a29fd79975df3a9c44ae1ac021fa7361d22ef806a50deb77`.

## Native boundary

The one record reports a read at address zero, RIP `0x00007ffbdb7d2186`, module
base `0x00007ffbdb6e0000`, and RVA `0xf2186` in
`C:\Windows\System32\xrt_coreutil.dll`. `RBX=0`; `RCX=0x15` at the exception.
The collector's module lookup uses its arm-time snapshot.

Static PE exports identify ordinal 421, RVA `0xf2150`,
`?size@bo@xrt@@QEBA_KXZ` (`xrt::bo::size() const`). The exception directory
places the fault inside function range `[0xf2150,0xf22c9)`, unwind RVA
`0x1b4628`. `.text` begins at RVA `0x1000` / file offset `0x400`; the fault's
file offset is `0xf1586`, bytes `48 8b 0b`.

```text
0xf2171  mov rbx,rcx          ; save this, per Windows x64 calling convention
0xf2174  call 0xeaad0
0xf217d  call 0x961d0
0xf2186  mov rcx,qword [rbx]  ; fault: RBX == 0
0xf2189  test rcx,rcx
0xf218c  je 0xf21a3           ; a valid object with null impl returns size zero
0xf218e  mov rax,qword [rcx]
0xf2191  mov rax,qword [rax+0x40]
```

Thus the supported immediate diagnosis is a null `xrt::bo` object pointer in a
host-side size query, at `xrt::bo::size()+0x36`. It faults before inspecting that
object's implementation pointer. The current scratch register `RCX=0x15` is
not the saved object pointer. This record does not identify the caller, buffer
role, allocation/initialization failure, unsupported command, or bank-shape
cause. It does not establish accelerator dispatch or successful execution.

## XRT and provider comparison

Both installed XRT files have 2,010,984 bytes, AMD file/product version
`32.00.20102.3931`, and SHA256
`04a26d37c6e0c713491ad0bfae74ce74ea94c74136d2aa056333616dac6c3a44`:

- `C:\Windows\System32\xrt_coreutil.dll`
- `C:\Windows\System32\DriverStore\FileRepository\kipudrv.inf_amd64_7b0051e064968f34\xrt_coreutil.dll`

Their byte identity also establishes equal PE exports and dependencies. Static
inspection shows PE32+ x64, image size `0x1ed000`, 541 named exports, and imports
from KERNEL32, GDI32, ADVAPI32 and Windows CRT API-set DLLs. Replacing System32
with the qualified DriverStore copy would not change the XRT binary.

The verified task provider directory
`C:\AI\halogen-mtp-npu\npu-ep-1.8.75-20261004` contains no XRT DLL. Its Light
library has file version `1.8.0.6`, SHA256
`ccc3bd0c2a8f519f9cd5fb112491785918810819f80c804302f717d2a93456ec`, and a direct
XRT import of `xrt::bo::size()` at IAT RVA `0x34bba8`. The VitisAI EP and Dynamic
Dispatch DLLs also delay-import this method. Static scanning finds 97 direct
Light-library callsites, so the fault receipt cannot uniquely select one.

The probe adds the verified provider-copy and sealed ORT directories to DLL
search, registers the Light library by absolute path, and does not explicitly
select XRT. The native receipt is evidence that the selected XRT was System32;
the exact preceding Windows loader search sequence was not captured.

## Candidate decision

The pinned [official AMD GPT-OSS configuration](https://huggingface.co/amd/gpt-oss-20B_eager_rai_1.8.0_npu_16K/blob/bcbb238a3e7e1c11fcac9850bde957e34eb51ebd/genai_config.json)
was read as JSON metadata only. It uses the same four relevant settings:
`external_data_file` naming the Header, `hybrid_opt_token_backend="npu"`,
`hybrid_opt_qmoe_dynamic_experts="0"`, and
`hybrid_opt_qmoe_num_dynamic_layers="0"`. Its other settings concern the complete
model's embedding, sequence length and chunking; they do not establish a missing
standalone-QMoE initialization step. AMD's [1.8 OGA deployment documentation](https://ryzenai.docs.amd.com/projects/WinML/en/stable/hybrid_oga.html)
describes the hosted OGA route, not a qualified isolated Light QMoEBf session.

The Light export `RyzenAI_RegisterCustomOps` jumps directly to its standard
`RegisterCustomOps` export. Switching to that alias would add no initialization.
Its `RyzenAI_SetSessionOptions` code processes only the two spinning-default
keys, with value `0`; that inspected export supplies no BO-preparation remedy.
The existence of these exports is not a contract for calling guessed ABIs.

No source-backed single local candidate change follows from these checks.
Keep the frozen graph, Header, bank and four provider options unchanged; close
this NPU branch provisionally with the null-object boundary recorded. A missing
global weight manager remains an unverified hypothesis, as do geometry and
packing limits. No additional EP/graph probe was prepared.

PE checks used existing MSVC `dumpbin` (`/headers /exports /imports` and bounded
`/disasm:bytes /range`), plus read-only parsing of native PE metadata/bytes.
