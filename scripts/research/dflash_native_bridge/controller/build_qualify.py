"""Offline CPU/source qualification; no native ELF or device runtime is executed.

All emitted files stay beside this script. This is not an installer or a
serving/hardware qualification. Run with python -B build_qualify.py.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
DEFAULT_BIN = Path("C:/Program Files/AMD/ROCm/7.2/bin")
ELF = PREP / "updates-20261009-0202/runtime-data/usr/local/bin/flash_serve.data"
TEXT = PREP / "native0173-phase-clock-20261009/current-text.txt"
HELPER = PREP / "static-compatibility-audit/passive_elf_review.py"
ELF_SHA = "af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7"
TEXT_SHA = "1c7ace3b584ec57139b052413381522a414c6d012d93da237dc4d5942f8a7f73"
SITES = [
    dict(site=0,name="Entry",rva=0x173FCD5,displaced="83 be 1c 01 00 00 00",stock=0x173FCDC,cfa=0x1A40,
         replay="83 be 1c 01 00 00 00",ready=0x173FD86,scalar=0x1740408),
    dict(site=1,name="Prepare",rva=0x1782BDC,displaced="48 8b bb 08 01 00 00",stock=0x1782BE3,cfa=0x30,
         replay="48 8b bb 08 01 00 00"),
    dict(site=2,name="PostReset",rva=0x173CE9A,displaced="48 8b 44 24 08",stock=0x173CE9F,cfa=0x1A40,
         replay="48 8b 44 24 08"),
    dict(site=3,name="InitialFlag",rva=0x173CC71,displaced="48 8b b0 80 01 00 00",stock=0x173CC78,cfa=0x1A40,
         replay="48 8b b0 80 01 00 00"),
    dict(site=4,name="ChunkFlag",rva=0x1746C96,displaced="49 8d 86 28 03 00 00",stock=0x1746C9D,cfa=0x120,
         replay="49 8d 86 28 03 00 00"),
]

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def write(name: str, data: str) -> None:
    destination = (WORK / name).resolve()
    assert destination.parent == WORK
    destination.write_text(data, encoding="utf-8")

def run(args: list[str], receipt: list[dict]) -> str:
    result = subprocess.run(args, cwd=WORK, text=True, capture_output=True, check=False)
    receipt.append(dict(argv=args,exit_code=result.returncode,
                        stdout_sha256=digest(result.stdout.encode()),stderr=result.stderr))
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args}\n{result.stdout}\n{result.stderr}")
    return result.stdout

class Object:
    """Small bounded ELF64 little-endian section/symbol/RELA reader."""
    def __init__(self, path: Path):
        self.data = path.read_bytes()
        assert self.data[:6] == b"\x7fELF\x02\x01"
        header = struct.unpack_from("<HHIQQQIHHHHHH", self.data, 16)
        assert header[1] == 62 and header[10] == 64
        self.sections = []
        for index in range(header[11]):
            values = struct.unpack_from("<IIQQQQIIQQ", self.data, header[5] + index * 64)
            self.sections.append(dict(index=index,name_offset=values[0],kind=values[1],address=values[3],
                offset=values[4],size=values[5],link=values[6],info=values[7],entry_size=values[9]))
        names = self.payload(self.sections[header[12]])
        for section in self.sections:
            section["name"] = self.string(names, section["name_offset"])
        self.by_name = {section["name"]:section for section in self.sections}
        self.symbol_tables = {}
        for section in self.sections:
            if section["kind"] not in (2,11):
                continue
            strings = self.payload(self.sections[section["link"]])
            symbols = []
            assert section["entry_size"] == 24
            for offset in range(section["offset"],section["offset"] + section["size"],24):
                name,info,other,shndx,value,size = struct.unpack_from("<IBBHQQ", self.data, offset)
                symbols.append(dict(name=self.string(strings,name),info=info,other=other,shndx=shndx,value=value,size=size))
            self.symbol_tables[section["index"]] = symbols
        self.symbols = {symbol["name"]:symbol for table in self.symbol_tables.values() for symbol in table if symbol["name"]}
        self.relocations = []
        for section in self.sections:
            if section["kind"] != 4:
                continue
            assert section["entry_size"] == 24
            for offset in range(section["offset"],section["offset"]+section["size"],24):
                location,info,addend = struct.unpack_from("<QQq",self.data,offset)
                self.relocations.append(dict(section=section["name"],target=section["info"],offset=location,
                    kind=info&0xFFFFFFFF,addend=addend,symbol=self.symbol_tables[section["link"]][info>>32]))
    @staticmethod
    def string(data: bytes, offset: int) -> str:
        return data[offset:data.index(0,offset)].decode()
    def payload(self, section: dict) -> bytes:
        return self.data[section["offset"]:section["offset"]+section["size"]]
    def symbol_bytes(self,name: str,count: int) -> bytes:
        symbol=self.symbols[name]
        section=self.sections[symbol["shndx"]]
        start=section["offset"]+symbol["value"]-section["address"]
        return self.data[start:start+count]

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--tool-bin",type=Path,default=DEFAULT_BIN)
    options=parser.parse_args()
    tool_bin=options.tool_bin.resolve()
    suffix=".exe" if sys.platform=="win32" else ""
    clang=str(tool_bin/("clang"+suffix));clangxx=str(tool_bin/("clang++"+suffix))
    lld=str(tool_bin/("ld.lld"+suffix));objdump=str(tool_bin/("llvm-objdump"+suffix));objcopy=str(tool_bin/("llvm-objcopy"+suffix))
    commands=[]
    base=["-std=c++20","-O2","-Wall","-Wextra","-Werror","-ffreestanding","-fno-builtin","-fno-exceptions","-fno-rtti"]
    harness="controller-cpu-harness.exe" if sys.platform=="win32" else "controller-cpu-harness"
    if sys.platform=="win32":
        link=["-nostdlib","-fuse-ld=lld","-Wl,/entry:main,/subsystem:console"]
    else:
        link=[]
    run([clangxx,*base,*link,"controller_cpu_harness.cpp","-o",harness],commands)
    run([str(WORK/harness)],commands)  # Freestanding host CPU fixture only.
    # Execute only the installer's exact SHA routines on ordinary known host
    # byte fixtures. No installer/syscall/engine code enters this CPU test.
    install_source=(WORK/"cold_install.cpp").read_text(encoding="utf-8")
    sha_source=install_source[install_source.index("struct Sha {"):install_source.index("struct NativeStat {")]
    digest_cases=[b"",b"abc",bytes(i%251 for i in range(8193))]
    case_checks=[]
    for index,data in enumerate(digest_cases):
        expected=",".join("0x"+digest(data)[i:i+2] for i in range(0,64,2))
        case_checks.append(f"hash_init(s);hash_update(s,fixture,{len(data)});hash_finish(s,out);const u8 expected{index}[32]={{{expected}}};"
                           f"for(u32 i=0;i<32;++i)if(out[i]!=expected{index}[i])return {index+1};")
    # abc fixture first, then fixed long fixture; zero length case reads none.
    case_checks[1]="fixture[0]='a';fixture[1]='b';fixture[2]='c';"+case_checks[1]
    case_checks[2]="for(u32 i=0;i<8193;++i)fixture[i]=u8(i%251);"+case_checks[2]
    write("installer_hash_cpu.cpp",'#include "retained_controller.h"\nusing namespace hgn_dflash;\n'+sha_source+
          '\nstatic u8 fixture[8193];int main(){Sha s{};u8 out[32];'+"\n".join(case_checks)+'return 0;}\n')
    hash_harness="installer-hash-cpu.exe" if sys.platform=="win32" else "installer-hash-cpu"
    run([clangxx,*base,*link,"installer_hash_cpu.cpp","-o",hash_harness],commands)
    run([str(WORK/hash_harness)],commands)
    admission_source=install_source[install_source.index("static int find_main("):install_source.index("struct Cpu {")]
    fixture_pins="\n".join('{'+hex(site["rva"])+','+str(len(bytes.fromhex(site["displaced"])))+',{' +
                          ','.join('0x'+byte for byte in site["displaced"].split())+'}},' for site in SITES)
    write("installer_admission_cpu.cpp",'#include "retained_controller.h"\nusing namespace hgn_dflash;\n'+
          'struct NativePhdr {u32 type,flags;u64 offset,vaddr,paddr,filesz,memsz,align;};\n'+
          'struct NativeImage {u64 base;const char* name;const NativePhdr* phdr;unsigned short count;};\n'+
          'struct Pin {u64 rva;u32 bytes;u8 original[7];};\nstatic const Pin pins[]={'+fixture_pins+'};\n'+
          'static u64 image_base;static u8 image_bytes[0x1800000];static NativePhdr phdr{1,5,0,0x1000,0,0x1800000,0x1800000,4096};\n'+
          'static NativeImage image{u64(image_bytes),"",&phdr,1};\n'+
          'static bool equal(const void* a,const void* b,u64 n)noexcept{auto* x=static_cast<const u8*>(a);auto* y=static_cast<const u8*>(b);for(u64 i=0;i<n;++i)if(x[i]!=y[i])return false;return true;}\n'+
          'static int dl_iterate_phdr(int(*fn)(NativeImage*,__SIZE_TYPE__,void*),void* ctx){return fn(&image,sizeof(image),ctx);}\n'+
          admission_source+'\nint main(){for(const auto& p:pins)for(u32 i=0;i<p.bytes;++i)image_bytes[p.rva+i]=p.original[i];\n'+
          'const u8 reset[5]={0xe8,0x66,0x68,5,0},ready[3]={0x44,0x89,0xed},scalar[5]={0x48,0x8b,0x5c,0x24,0x10};\n'+
          'for(u32 i=0;i<5;++i){image_bytes[0x173ce95+i]=reset[i];image_bytes[0x1740408+i]=scalar[i];}for(u32 i=0;i<3;++i)image_bytes[0x173fd86+i]=ready[i];\n'+
          'const u64 changed[3]={0x173ce95,0x173fd86,0x1740408};for(auto rva:changed){if(!admit_main())return 10;\n'+
          '// Emulate CpuRejected/IslandRejected/MapFailed after image admission.\n'+
          'image_bytes[rva]^=1;if(admit_main()||image_base)return 1;image_bytes[rva]^=1;}return 0;}\n')
    admission_harness="installer-admission-cpu.exe" if sys.platform=="win32" else "installer-admission-cpu"
    run([clangxx,*base,*link,"installer_admission_cpu.cpp","-o",admission_harness],commands)
    run([str(WORK/admission_harness)],commands)
    run([clang,"--target=x86_64-linux-gnu","-c","retained_relay.S","-o","retained_relay.o"],commands)
    run([objcopy,"--rename-section",".eh_frame=.hgn_dflash_relay_frames","retained_relay.o","retained_relay_island.o"],commands)
    run([clangxx,"--target=x86_64-linux-gnu",*base,"-fPIC","-fvisibility-inlines-hidden","-fcf-protection=full",
         "-c","retained_callback.cpp","-o","retained_callback.o"],commands)
    run([clangxx,"--target=x86_64-linux-gnu",*base,"-fPIC","-fvisibility-inlines-hidden","-fcf-protection=full",
         "-c","cold_install.cpp","-o","cold_install.o"],commands)
    run([lld,"-shared","-z","noexecstack","--build-id=none","-Bsymbolic-functions",
         "-T","retained_relay.ld","retained_relay_island.o","retained_callback.o","cold_install.o","-o","retained_controller_source.so"],commands)
    disassembly=run([objdump,"-dr","retained_relay.o"],commands)
    frames=run([objdump,"--dwarf=frames","retained_relay.o"],commands)
    write("relay-disassembly.txt",disassembly);write("relay-frames.txt",frames)
    write("callback-disassembly.txt",run([objdump,"-dr","retained_callback.o"],commands))
    relay=Object(WORK/"retained_relay.o")
    code=relay.by_name[".hgn_dflash_relay_templates"]
    code_bytes=relay.payload(code)
    built_sites=[]
    fdes=re.findall(r"FDE cie=[0-9a-f]+ pc=([0-9a-f]+)\.\.\.([0-9a-f]+)",frames)
    assert len(fdes)==len(SITES)
    for site,fde in zip(SITES,fdes):
        prefix=f"hgn_dflash_relay_{site['site']}_"
        begin=relay.symbols[prefix+"begin"]["value"]
        end=relay.symbols[prefix+"code_end"]["value"]
        gate=relay.symbols[prefix+"mandatory_gate"]["value"]
        assert (int(fde[0],16),int(fde[1],16))==(begin,end)
        assert code_bytes[begin:begin+4]==bytes.fromhex("f3 0f 1e fa")
        assert begin<gate<end
        assert relay.symbol_bytes(prefix+"config",80)==bytes(80)
        exits={}
        for name in ("stock","ready","scalar"):
            if name not in site:
                continue
            delta=relay.symbols[prefix+name+"_delta"]["value"]
            assert code_bytes[delta-1]==0xE9 and struct.unpack_from("<I",code_bytes,delta)[0]==0x5A17C0DE
            if name=="stock":
                replay=bytes.fromhex(site["replay"])
                assert code_bytes[delta-1-len(replay):delta-1]==replay
            exits[name]=dict(delta_offset=delta,target_rva=hex(site[name]))
        if site["site"]==0:
            assert gate<relay.symbols[prefix+"optional_begin"]["value"]<end
        built_sites.append(dict(site=site["site"],name=site["name"],begin=begin,mandatory_gate=gate,code_end=end,
                                native_cfa=hex(site["cfa"]),exits=exits,default_off=True))
    code_relocations=[r for r in relay.relocations if r["target"]==code["index"]]
    assert code_relocations
    for relocation in code_relocations:
        assert relocation["kind"]==2 and relocation["symbol"]["shndx"]==code["index"], "External copied-code relocation"
    eh_relocations=[r for r in relay.relocations if r["section"]==".rela.eh_frame"]
    assert len(eh_relocations)==len(SITES)
    assert len(re.findall(r"\bcallq?\s",disassembly))==1
    callback=Object(WORK/"retained_callback.o")
    assert callback.symbol_bytes("hgn_dflash_ready_callback",4)==bytes.fromhex("f3 0f 1e fa")
    shared=Object(WORK/"retained_controller_source.so")
    undefined=sorted({symbol["name"] for table in shared.symbol_tables.values() for symbol in table
                      if symbol["name"] and symbol["shndx"]==0})
    assert set(undefined)<={"__errno_location","memcpy","memset","dl_iterate_phdr","__register_frame","_Unwind_Find_FDE"},undefined
    assert not any(name in shared.by_name for name in (".init_array",".fini_array",".init"))
    frame_start=shared.symbols["hgn_dflash_island_frames"]["value"]
    frame_end=shared.symbols["hgn_dflash_island_frames_end"]["value"]
    frame_data=shared.symbol_bytes("hgn_dflash_island_frames",frame_end-frame_start)
    linked_fdes=[];at=0;cies=set()
    while at+4<=len(frame_data):
        length=struct.unpack_from("<I",frame_data,at)[0]
        if not length:
            assert at+4==len(frame_data) and len(linked_fdes)==len(SITES)
            break
        assert 13<=length<=len(frame_data)-at-4
        cie=struct.unpack_from("<I",frame_data,at+4)[0]
        if not cie:
            assert frame_data[at+8:at+17]==bytes([1,ord('z'),ord('R'),0,1,0x78,16,1,0x1B])
            cies.add(at)
        else:
            assert at+4-cie in cies
            begin=frame_start+at+8+struct.unpack_from("<i",frame_data,at+8)[0]
            extent=struct.unpack_from("<I",frame_data,at+12)[0]
            matches=[site for site in SITES if shared.symbols[f"hgn_dflash_relay_{site['site']}_begin"]["value"]==begin
                     and shared.symbols[f"hgn_dflash_relay_{site['site']}_code_end"]["value"]==begin+extent]
            assert len(matches)==1
            linked_fdes.append(dict(site=matches[0]["site"],begin=begin,extent=extent))
        at+=length+4
    else:
        raise AssertionError("Linked frame envelope missing terminator")
    smoke_executed=False
    if sys.platform=="win32":
        # Same assembled templates; only object-format directives/CFI metadata
        # are removed and host TLS segment prefixes change FS to Windows GS.
        lines=[]
        for line in (WORK/"retained_relay.S").read_text(encoding="utf-8").splitlines():
            stripped=line.strip()
            if stripped.startswith(("#if ","#error ","#endif",".cfi_",".hidden ",".type ",".size ")):
                continue
            if stripped.startswith(".section .note.GNU-stack"):
                continue
            if stripped.startswith(".section .hgn_dflash_relay_templates"):
                line='    .section .hgnmock,"xr"'
            lines.append(line.replace("%fs:","%gs:"))
        write("relay_cpu_mock.S","\n".join(lines)+"\n")
        run([clangxx,*base,"-DHGN_DFLASH_SYSV_MOCK=1","-fcf-protection=full","-nostdlib","-fuse-ld=lld",
             "-Wl,/entry:main,/subsystem:console,/stack:8388608","-Xlinker","/section:.hgnmock,ERW",
             "relay_cpu_smoke.cpp","retained_callback.cpp","relay_cpu_mock.S","relay_cpu_entry.S",
             "-o","relay-cpu-smoke.exe"],commands)
        pe=(WORK/"relay-cpu-smoke.exe").read_bytes()
        pe_start=struct.unpack_from("<I",pe,0x3C)[0]
        assert pe[pe_start:pe_start+4]==b"PE\0\0"
        section_count=struct.unpack_from("<H",pe,pe_start+6)[0]
        optional_size=struct.unpack_from("<H",pe,pe_start+20)[0]
        section_start=pe_start+24+optional_size
        mock_bytes=None
        for index in range(section_count):
            location=section_start+index*40
            if pe[location:location+8].rstrip(b"\0")==b".hgnmock":
                extent=struct.unpack_from("<I",pe,location+8)[0]
                raw_offset=struct.unpack_from("<I",pe,location+20)[0]
                mock_bytes=pe[raw_offset:raw_offset+extent]
        expected=shared.symbol_bytes("hgn_dflash_templates_begin",relay.symbols["hgn_dflash_templates_end"]["value"])
        assert mock_bytes is not None and len(mock_bytes)==len(expected)
        differences=[i for i,(left,right) in enumerate(zip(expected,mock_bytes)) if left!=right]
        assert len(differences)==2 and all(expected[i]==0x64 and mock_bytes[i]==0x65 for i in differences),differences
        run([str(WORK/"relay-cpu-smoke.exe")],commands)
        smoke_executed=True
    # Native image is read, parsed and byte-matched only; it is never executed.
    blob=ELF.read_bytes();text_bytes=TEXT.read_bytes()
    assert len(blob)==26_188_824 and digest(blob)==ELF_SHA and digest(text_bytes)==TEXT_SHA
    tree=ast.parse(HELPER.read_text(encoding="utf-8"))
    classes=[node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=="Elf"]
    assert len(classes)==1
    namespace={"struct":struct}
    exec(compile(ast.Module(body=classes,type_ignores=[]),"passive_Elf","exec"),namespace)
    native=namespace["Elf"](blob)
    anchors=[]
    for site in SITES:
        expected=bytes.fromhex(site["displaced"]);offset=native.offset(site["rva"],len(expected))
        assert blob[offset:offset+len(expected)]==expected
        anchors.append(dict(site=site["site"],name=site["name"],rva=hex(site["rva"]),bytes=site["displaced"],
                            stock_resume_rva=hex(site["stock"]),native_cfa=hex(site["cfa"]),fde=native.unwind_range(site["rva"])))
    for address,expected in ((0x173CE95,"e8 66 68 05 00"),(0x173FD86,"44 89 ed"),(0x1740408,"48 8b 5c 24 10")):
        raw=bytes.fromhex(expected);offset=native.offset(address,len(raw));assert blob[offset:offset+len(raw)]==raw
    manifest=dict(schema="halogen0173.dflash.retained-native-seams.v1",runtime_sha256=ELF_SHA,
                  disassembly_sha256=TEXT_SHA,sites=anchors,built_templates=built_sites)
    write("native_seams.json",json.dumps(manifest,indent=2)+"\n")
    filenames=["retained_controller.h","controller_cpu_harness.cpp","retained_relay.h","retained_relay.S",
               "retained_callback.cpp","cold_install.h","cold_install.cpp","cold_install.o","retained_relay.ld","installer_hash_cpu.cpp",hash_harness,"installer_admission_cpu.cpp",admission_harness,"build_qualify.py","README.md",harness,"retained_relay.o",
               "retained_relay_island.o","retained_callback.o","retained_controller_source.so","native_seams.json","relay-disassembly.txt","relay-frames.txt","callback-disassembly.txt"]
    if smoke_executed:
        filenames += ["relay_cpu_smoke.cpp","relay_cpu_entry.S","relay_cpu_mock.S","relay-cpu-smoke.exe"]
    receipt=dict(schema="halogen0173.dflash.retained-controller-qualification.v1",scope="host CPU plus passive native/source qualification",
        cpu_harness_exit=0,native_engine_executed=False,native_relay_executed=False,native_installed=False,
        installer_hash_cpu_known_fixture_cases=3,installer_hash_cpu_exit=0,
        installer_admission_late_reject_changed_mapped_retry_exit=0,
        explicit_default_off_cold_installer_built=True,cold_installer_executed=False,
        host_relay_cpu_smoke_executed=smoke_executed,host_mock_tls_segment_adaptation="FS to GS only" if smoke_executed else None,
        host_mock_code_matches_linked_linux_bytes_except_two_tls_prefixes=smoke_executed,
        wsl_executed=False,api_requests=0,device_or_provider_initialized=False,default_off=True,
        mandatory_gate_precedes_optional_admission=True,invocation_owned_action=True,template_count=len(SITES),
        copied_code_relocations_are_internal=True,copied_eh_frame_fde_count=len(eh_relocations),
        linked_copied_frame_envelope=dict(bytes=len(frame_data),fdes=linked_fdes,cie_encoding_verified=True,exact_single_terminator=True),
        real_callback_call_count=1,shared_undefined_symbols=undefined,commands=commands,
        artifacts={name:dict(bytes=(WORK/name).stat().st_size,sha256=digest((WORK/name).read_bytes())) for name in filenames},
        all_writes_confined_to=str(WORK),limits=["Linux FS/unwind runtime not executed; host adapted relay smoke only", "Cold installer compiled but not executed; no runtime patch",
        "No provider scheduling window or causal serving speed proved", "One isolated native slot/null-cache full-reset scope only"])
    write("qualification_receipt.json",json.dumps(receipt,indent=2)+"\n")
    seal=dict(schema="halogen0173.dflash.retained-controller-delivery.v1",runtime_sha256=ELF_SHA,
        retained_header_sha256=digest((WORK/"retained_controller.h").read_bytes()),
        shared_library_sha256=digest((WORK/"retained_controller_source.so").read_bytes()),
        qualification_receipt_sha256=digest((WORK/"qualification_receipt.json").read_bytes()),
        readme_sha256=digest((WORK/"README.md").read_bytes()),
        cpu_controller_passed=True,host_instruction_smoke_passed=smoke_executed,
        exact_linux_template_bytes_except_two_windows_tls_prefixes=smoke_executed,
        linked_copied_fdes_verified=len(linked_fdes),cold_installer_built=True,cold_installer_executed=False,
        native_installed=False,device_initialized=False,api_requests=0,wsl_executed=False,
        root_integration_required=["Cold install before native execution/threads",
            "Retained Lane and exact provider/model/tokenizer/drafter/session ownership pins",
            "One native slot with actual null-cache full-reset admission",
            "Mapped stack registration for every native callback thread",
            "Pending publication/materialization/birth and terminal retirement hooks",
            "Accepted feature capture and causal provider coordination before Entry",
            "Linux FS and unwind runtime smoke before serving publication"])
    write("delivery_seal.json",json.dumps(seal,indent=2)+"\n")
    print(json.dumps(dict(cpu_harness_exit=0,relay_templates=len(SITES),native_installed=False,
                          receipt=str(WORK/"qualification_receipt.json"))))

if __name__=="__main__":
    main()
