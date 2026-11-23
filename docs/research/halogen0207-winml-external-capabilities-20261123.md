# AMD VitisAI D3D12 capability check on the Halogen Windows host

The installed Windows VitisAI provider advertises **D3D12 resource
import** and reports **D3D12 fence import unavailable** on the Ryzen AI
NPU. Both capability calls returned successfully. The probe ran after
the reserved ServiceNow voice window while Halogen 0.20.7 was online.

| Runtime | Selected device | Resource import | Fence import |
| --- | --- | --- | --- |
| Windows ML ONNX Runtime 1.25.2, API 25, VitisAI 1.8.75.0 | AMD NPU `1022:17f0` | Advertised | Unavailable |

The test loaded the pinned standalone runtime, registered the installed
VitisAI provider and verified that the loaded runtime and provider
matched the expected module paths. It selected one AMD NPU and created
the optional capability importer. It called `CanImportMemory` with
`D3D12_RESOURCE` and `CanImportSemaphore` with `D3D12_FENCE` independently,
then released the importer and unregistered the provider. The launcher
verified 13 DLL hashes before running. It used a 30-second timeout for
its own child process. [ONNX Runtime interop API](https://onnxruntime.ai/docs/api/c/struct_ort_interop_api.html)

The result concerns capability advertising under native Windows. An
actual shared resource import, GPU/NPU synchronization, inference
correctness and throughputs are outside this probe. The WSL 6.6 export
command uses guest resource and device identifiers. Its public contract
provides no application recipient for the host-side export. The checked
result therefore supplies no native fence or supported buffer ownership
path between Halogen's WSL DXG GPU and the Windows NPU process.
[WSL 6.6 DXG command](https://github.com/microsoft/WSL2-Linux-Kernel/blob/linux-msft-wsl-6.6.y/drivers/hv/dxgkrnl/dxgvmbus.h#L809)

Physical and commit reserves sampled before the probe were 30.41 and
121.73 GiB. The same Halogen controller and backend were ready on port
8840 after the probe. ServiceNow routing, Native Voice, TTS and ASR all
passed their health checks.

| Local evidence under `server/.local/halogen-update-20261122/primary0207/winml-d3d12-capability-prep-v1` | SHA-256 |
| --- | --- |
| `capability_native.exe` | `ec9a12b0150a822876f78c7e430d9b2b297f4e6e9e50a46cbbebf03fae2d82c4` |
| `run-capability.ps1` | `acb098bc79a613c25ceefe8a39089ade4d750aecac722424a7d5294790da74d2` |
| `root-run-v1/pre-admission.json` | `6ecbeec96a71efcc8f0585d68c5fb0848396b583f27a92a2a815df7d7b102091` |
| `root-run-v1/provider-capability-raw.json` | `1e76d3037cd229b563bcd4a206afcfbc7c776cd36d216d3de40d3d385af5cc9d` |
| `root-run-v1/verified-capability.json` | `5ecd77c9e23ca0caf83069ce4c4c11b467e08f3300ee7bcac4fca5ded20ef2da` |
