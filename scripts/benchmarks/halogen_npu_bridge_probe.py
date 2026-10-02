"""Assess whether FastFlowLM NPU primitives can host Halogen Flash-Next's MTP head."""
import argparse,json,pathlib,subprocess
P=argparse.ArgumentParser(); P.add_argument("--inspect",type=pathlib.Path,required=True)
P.add_argument("--flm-q38-dll",type=pathlib.Path,required=True); P.add_argument("--flm-moe-dll",type=pathlib.Path,required=True)
P.add_argument("--out",type=pathlib.Path,required=True); a=P.parse_args()
p=json.loads(a.inspect.read_text(encoding="utf-8")); mtp=[x for x in p["tensors"] if x["name"].startswith("mtp.")]
by={x["name"]:x for x in mtp}
def strings(path,patterns):
    q=subprocess.run(["wsl.exe","-d","Ubuntu-24.04","--","strings","-a","/mnt/"+path.drive[0].lower()+str(path)[2:].replace("\\","/")],
                     capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=120)
    return {s:(s.lower() in q.stdout.lower()) for s in patterns}
q38=strings(a.flm_q38_dll,["speculate_npu","npu_mtp_layer","MTP_layer.xclbin","dequant_mm.xclbin","npu_lm_head"])
moe=strings(a.flm_moe_dll,["num_experts","moe_router","expert_prefill","moe_gate"])
q4=sum(x["nbytes"] for x in mtp if x["dtype"]=="q4c"); bf=sum(x["nbytes"] for x in mtp if x["dtype"]=="bf16")
gate=by["mtp.layers.0.mlp.experts.gate_up_proj.weight"]; down=by["mtp.layers.0.mlp.experts.down_proj.weight"]
experts=512; topk=10
active_expert_bytes=topk*(gate["nbytes"]//experts+down["nbytes"]//experts)
result={"schema":1,"halogen":{"hidden_size":2560,"hyperconnection_width":10240,"experts":experts,"experts_per_token":topk,
 "expert_intermediate":640,"mtp_tensors":len(mtp),"mtp_q4_bytes":q4,"mtp_bf16_bytes":bf,
 "active_expert_weight_bytes_per_step_estimate":active_expert_bytes},
 "flm_qwen38_27b":{"hidden_size":5120,"dense_mtp":True,"features":q38},
 "flm_qwen36_moe":{"features":moe},
 "direct_qwen38_mtp_reuse":False,
 "reason":["Flash-Next hidden size is 2560 with four 10240-wide hyperconnection streams; Qwen3.8-27B is 5120-wide.",
           "Flash-Next MTP contains a 512-expert MoE layer (top-10) and hyperconnection mixers; the 27B MTP head is dense.",
           "FLM's shipped NPU DLL therefore cannot consume Halogen target state without a new Flash-Next-specific graph."],
 "candidate_reuse":["FLM NPU dequantized-matmul/lm-head infrastructure","FLM Qwen3.6-MoE routing/expert design patterns",
                    "FLM Qwen3.8 attention/MTP dispatch and checkpoint/rollback design"],
 "promotion":"Requires Flash-Next-specific AIE2P bitstreams plus an online Halogen state-export/import seam; fail closed until measured."}
a.out.write_text(json.dumps(result,indent=2),encoding="utf-8"); print(json.dumps(result,indent=2))
