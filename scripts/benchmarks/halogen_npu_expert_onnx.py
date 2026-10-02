"""Build a one-expert Flash-Next MTP ONNX graph from decoded HGN weights."""
import argparse,json,pathlib,numpy as np
P=argparse.ArgumentParser(); P.add_argument("--gate-up",type=pathlib.Path,required=True); P.add_argument("--down",type=pathlib.Path,required=True)
P.add_argument("--out",type=pathlib.Path,required=True); a=P.parse_args()
import onnx
from onnx import helper,TensorProto,numpy_helper
gu=np.load(a.gate_up).astype(np.float32); down=np.load(a.down).astype(np.float32)
if gu.shape!=(1280,2560) or down.shape!=(2560,640): raise SystemExit(f"unexpected shapes {gu.shape} {down.shape}")
# ONNX MatMul uses [M,K] x [K,N].
inits=[numpy_helper.from_array(gu.T.copy(),"W_gate_up"),numpy_helper.from_array(down.T.copy(),"W_down")]
nodes=[helper.make_node("MatMul",["x","W_gate_up"],["gu"]),
       helper.make_node("Split",["gu"],["gate","up"],axis=1,num_outputs=2),
       helper.make_node("Sigmoid",["gate"],["gate_sig"]),
       helper.make_node("Mul",["gate","gate_sig"],["silu_gate"]),
       helper.make_node("Mul",["silu_gate","up"],["hidden"]),
       helper.make_node("MatMul",["hidden","W_down"],["y"])]
graph=helper.make_graph(nodes,"flash_next_mtp_expert0",
 [helper.make_tensor_value_info("x",TensorProto.FLOAT,[1,2560])],
 [helper.make_tensor_value_info("y",TensorProto.FLOAT,[1,2560])],inits)
model=helper.make_model(graph,producer_name="strix-alloy-halogen-npu",opset_imports=[helper.make_opsetid("",21)])
# onnxruntime-windowsml 1.25 currently accepts IR <= 13.
model.ir_version=13
onnx.checker.check_model(model); a.out.parent.mkdir(parents=True,exist_ok=True)
onnx.save_model(model,str(a.out),save_as_external_data=True,all_tensors_to_one_file=True,location=a.out.name+".data",size_threshold=1024)
print(json.dumps({"model":str(a.out),"gate_up":list(gu.shape),"down":list(down.shape),
 "weights_bytes":gu.nbytes+down.nbytes},indent=2))
