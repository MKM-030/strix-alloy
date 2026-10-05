// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Persistent native XRT H backend with exactly once decoded BF16 weights.
// --inspect is strictly offline. Shared wire and arithmetic schedule unchanged.
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include "contract.h"
#include "../halogen_mtp_h_wire.h"
#include <xrt/xrt_bo.h>
#include <xrt/xrt_device.h>
#include <xrt/xrt_hw_context.h>
#include <xrt/xrt_kernel.h>
#include <xrt/experimental/xrt_xclbin.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace hc = hidden_contract;
using Clock = std::chrono::steady_clock;
using Digest = std::array<uint8_t, 32>;

static void require(bool ok, const std::string &message) {
  if (!ok) throw std::runtime_error(message);
}
static std::string quote(const std::string &s) {
  std::ostringstream out; out << '"';
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c == '\n') out << "\\n";
    else if (c == '\r') out << "\\r";
    else if (c == '\t') out << "\\t";
    else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
    else out << c;
  }
  out << '"'; return out.str();
}
static uint64_t decimal(const std::string &s, const std::string &name) {
  require(!s.empty() && s.find_first_not_of("0123456789") == std::string::npos, name + " needs decimal digits");
  return std::stoull(s);
}
static std::vector<uint8_t> unhex(const std::string &s, size_t bytes, const std::string &name) {
  require(s.size() == bytes * 2, name + " has wrong hexadecimal length");
  std::vector<uint8_t> result(bytes);
  for (size_t i = 0; i < bytes; ++i) {
    auto digit = [&](char c) -> unsigned {
      if (c >= '0' && c <= '9') return c - '0';
      if (c >= 'a' && c <= 'f') return c - 'a' + 10;
      if (c >= 'A' && c <= 'F') return c - 'A' + 10;
      throw std::runtime_error(name + " contains nonhexadecimal characters");
    };
    result[i] = uint8_t((digit(s[i * 2]) << 4) | digit(s[i * 2 + 1]));
  }
  return result;
}
static std::string hex(const uint8_t *data, size_t bytes) {
  std::ostringstream out; out << std::hex << std::setfill('0');
  for (size_t i = 0; i < bytes; ++i) out << std::setw(2) << unsigned(data[i]);
  return out.str();
}
static Digest sha256(const void *data, size_t bytes) {
  require(bytes <= std::numeric_limits<ULONG>::max(), "SHA256 input too large");
  BCRYPT_ALG_HANDLE algorithm = nullptr; BCRYPT_HASH_HANDLE hash = nullptr;
  auto cleanup = [&]() { if (hash) BCryptDestroyHash(hash); if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0); };
  try {
    require(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0, "SHA256 provider failed");
    ULONG object_bytes = 0, returned = 0;
    require(BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_bytes),
                             sizeof(object_bytes), &returned, 0) >= 0, "SHA256 object length failed");
    std::vector<uint8_t> object(object_bytes);
    require(BCryptCreateHash(algorithm, &hash, object.data(), object_bytes, nullptr, 0, 0) >= 0, "SHA256 create failed");
    require(BCryptHashData(hash, reinterpret_cast<PUCHAR>(const_cast<void *>(data)), ULONG(bytes), 0) >= 0, "SHA256 update failed");
    Digest digest{};
    require(BCryptFinishHash(hash, digest.data(), ULONG(digest.size()), 0) >= 0, "SHA256 finish failed");
    cleanup(); return digest;
  } catch (...) { cleanup(); throw; }
}
static std::vector<uint8_t> read_file(const std::string &path, size_t maximum, size_t exact = 0) {
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  require(bool(file), "cannot open " + path);
  const auto n = file.tellg();
  require(n > 0 && static_cast<uint64_t>(n) <= maximum && (!exact || static_cast<uint64_t>(n) == exact), "wrong file extent " + path);
  std::vector<uint8_t> bytes(static_cast<size_t>(n)); file.seekg(0);
  require(bool(file.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()))), "short read " + path);
  return bytes;
}
static std::map<std::string, std::string> sidecar(const std::string &path) {
  std::ifstream file(path); require(bool(file), "cannot open sidecar " + path);
  std::map<std::string, std::string> result; std::string line;
  while (std::getline(file, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty() || line[0] == '#') continue;
    const auto p = line.find('=');
    require(p != std::string::npos && p && result.emplace(line.substr(0, p), line.substr(p + 1)).second,
            "malformed/duplicate field in " + path);
  }
  return result;
}
static void fields(const std::map<std::string, std::string> &values,
                   const std::map<std::string, std::string> &expected) {
  for (const auto &kv : expected) {
    const auto it = values.find(kv.first);
    require(it != values.end() && it->second == kv.second, "sidecar mismatch: " + kv.first);
  }
}
static void finite_bf16(const uint8_t *bytes, size_t count, const char *what) {
  for (size_t i = 0; i < count; ++i) {
    const uint16_t word = bytes[i * 2] | uint16_t(bytes[i * 2 + 1]) << 8;
    require((word & 0x7F80U) != 0x7F80U, std::string("nonfinite BF16 ") + what + " at " + std::to_string(i));
  }
}
static float bf16_value(const uint8_t *data, size_t i) {
  uint32_t bits = uint32_t(data[i * 2] | uint16_t(data[i * 2 + 1]) << 8) << 16;
  float value; std::memcpy(&value, &bits, sizeof(value)); return value;
}
static double us(Clock::time_point a, Clock::time_point b) { return std::chrono::duration<double, std::micro>(b - a).count(); }
static void deadline(Clock::time_point when, const char *stage) {
  require(Clock::now() < when, std::string("owned deadline exceeded at ") + stage);
}

struct Options {
  std::string mode, xclbin, instructions, abi, artifacts, artifacts_sha;
  std::string weights, weights_abi, packed_sha, raw_sha, report, cohort_inputs, cohort_oracles;
  std::string nonce, epoch, model_binding, graph_binding, engine_sha;
  uint64_t process_id = 0;
  unsigned device = 0, warmups = 8, measurements = 48, wait_ms = 2000, deadline_ms = 80000;
};
static Options options(int argc, char **argv) {
  Options o;
  std::map<std::string, std::string *> strings = {
      {"--xclbin", &o.xclbin}, {"--instructions", &o.instructions}, {"--abi", &o.abi},
      {"--artifacts", &o.artifacts}, {"--artifacts-sha256", &o.artifacts_sha},
      {"--weights", &o.weights}, {"--weights-abi", &o.weights_abi},
      {"--packed-sha256", &o.packed_sha}, {"--raw-sha256", &o.raw_sha}, {"--report", &o.report},
      {"--cohort-inputs", &o.cohort_inputs}, {"--cohort-oracles", &o.cohort_oracles},
      {"--nonce", &o.nonce}, {"--epoch", &o.epoch}, {"--model-binding", &o.model_binding},
      {"--graph-binding", &o.graph_binding}, {"--engine-sha256", &o.engine_sha}};
  std::map<std::string, unsigned *> numbers = {
      {"--device-index", &o.device}, {"--warmups", &o.warmups}, {"--measurements", &o.measurements},
      {"--wait-ms", &o.wait_ms}, {"--deadline-ms", &o.deadline_ms}};
  std::set<std::string> seen;
  for (int i = 1; i < argc; ++i) {
    const std::string key = argv[i]; require(seen.insert(key).second, "duplicate option " + key);
    if (key == "--serve" || key == "--cohort" || key == "--inspect") {
      require(o.mode.empty(), "select one of --serve/--cohort/--inspect"); o.mode = key.substr(2); continue;
    }
    if (key == "--help") {
      std::cout << "host.exe --inspect --xclbin FILE --instructions FILE --abi FILE\n"
                   "host.exe --cohort|--serve --xclbin FILE --instructions FILE --abi FILE\n"
                   " --artifacts FILE --artifacts-sha256 HEX --weights FILE --weights-abi FILE\n"
                   " --packed-sha256 HEX --raw-sha256 HEX [--report FILE] [--wait-ms2000] [--deadline-ms80000]\n"
                   "cohort: --cohort-inputs FILE --cohort-oracles FILE [--warmups8 --measurements48]\n"
                   "serve: --process-id N --nonce HEX16 --epoch HEX16 --model-binding HEX32\n"
                   " --graph-binding HEX32 --engine-sha256 HEX32. Binary stdin/stdout only.\n"
                   "Runtime requires the root-owned external process/job deadline.\n"; std::exit(0);
    }
    require(i + 1 < argc, "missing value " + key); const std::string value = argv[++i];
    if (strings.count(key)) *strings.at(key) = value;
    else if (numbers.count(key)) {
      const uint64_t v = decimal(value, key); require(v <= std::numeric_limits<unsigned>::max(), key + " exceeds unsigned");
      *numbers.at(key) = unsigned(v);
    } else if (key == "--process-id") o.process_id = decimal(value, key);
    else throw std::runtime_error("unknown option " + key);
  }
  require(!o.mode.empty() && !o.xclbin.empty() && !o.instructions.empty() && !o.abi.empty(), "mode and artifact paths required");
  require(o.deadline_ms >= 1000 && o.deadline_ms <= 600000 && o.wait_ms > 0 && o.wait_ms <= 10000 && o.wait_ms <= o.deadline_ms,
          "deadline-ms1000..600000 and wait-ms1..10000 required");
  if (o.mode == "inspect") return o;
  require(!o.artifacts.empty() && !o.weights.empty() && !o.weights_abi.empty(), "runtime artifact pins and packed weights required");
  unhex(o.artifacts_sha, 32, "artifacts SHA"); unhex(o.packed_sha, 32, "packed SHA"); unhex(o.raw_sha, 32, "raw SHA");
  o.artifacts_sha = hex(unhex(o.artifacts_sha, 32, "artifacts SHA").data(), 32);
  o.packed_sha = hex(unhex(o.packed_sha, 32, "packed SHA").data(), 32);
  o.raw_sha = hex(unhex(o.raw_sha, 32, "raw SHA").data(), 32);
  if (o.mode == "cohort") {
    require(!o.cohort_inputs.empty() && !o.cohort_oracles.empty() && !o.report.empty(), "cohort inputs/oracles/report required");
    require(o.measurements && o.warmups + uint64_t(o.measurements) <= hc::core_calls, "cohort total must be1..64");
  } else {
    require(o.process_id != 0, "serve needs pinned nonzero engine process id");
    unhex(o.nonce, 16, "nonce"); unhex(o.epoch, 16, "epoch");
    unhex(o.model_binding, 32, "model binding"); unhex(o.graph_binding, 32, "graph binding");
    require(unhex(o.engine_sha, 32, "engine SHA") == unhex(HGNH_ENGINE_SHA, 32, "pinned engine SHA"), "original engine hash pin mismatch");
  }
  return o;
}

static std::string inspect(const Options &o) {
  fields(sidecar(o.abi), {{"format", "halogen-native-hidden-decoded-v1"}, {"device", "npu2"}, {"kernel", "MLIR_AIE"},
      {"input_bytes", "20480"}, {"output_bytes", "20480"}, {"weight_bytes", "13107200"}, {"raw_weight_bytes", "6963200"},
      {"core_calls", "64"}, {"workers", "32"}, {"stack_bytes", "4096"}, {"runtime_buffers", "3"},
      {"weight_arg", "3"}, {"input_arg", "4"}, {"output_arg", "5"}, {"instruction_count_unit", "uint32_words"},
      {"numeric_schedule", "16lane-sequential2mac-block16-xor8,4,2,1"}, {"weight_decode", "exact-dyadic-affine-rn32-rnbf16-once"}});
  const auto abi = sidecar(o.abi);
  require(abi.at("mlir_aie_version").substr(0, abi.at("mlir_aie_version").find('+')) == "1.3.4", "wrong generator version");
  const auto words = read_file(o.instructions, 16 * 1024 * 1024);
  require(words.size() % 4 == 0, "instruction binary is not uint32 words");
  const xrt::xclbin binary(o.xclbin);
  const auto kernels = binary.get_kernels();
  const auto it = std::find_if(kernels.begin(), kernels.end(), [](const auto &k) { return k.get_name() == "MLIR_AIE"; });
  require(it != kernels.end() && std::count_if(kernels.begin(), kernels.end(), [](const auto &k) { return k.get_name() == "MLIR_AIE"; }) == 1,
          "exactly one MLIR_AIE kernel required");
  auto args = it->get_args(); std::sort(args.begin(), args.end(), [](const auto &a, const auto &b) { return a.get_index() < b.get_index(); });
  require(args.size() >= 6 && args.size() <= 8, "six live arguments and only bo3/bo4 padding accepted");
  std::ostringstream out; out << "{\"status\":\"offline-abi-validated\",\"device_opened\":false,\"instruction_words\":" << words.size() / 4 << ",\"arguments\":[";
  for (size_t i = 0; i < args.size(); ++i) {
    const std::string name = i == 0 ? "opcode" : i == 1 ? "instr" : i == 2 ? "ninstr" : "bo" + std::to_string(i - 3);
    const uint64_t size = i == 2 ? 4 : 8, offset = i < 3 ? i * 8 : 0x14 + (i - 3) * 8;
    require(args[i].get_index() == i && args[i].get_name() == name && args[i].get_size() == size && args[i].get_offset() == offset,
            "xclbin ABI mismatch at index " + std::to_string(i));
    if (i) out << ',';
    out << "{\"index\":" << i << ",\"name\":" << quote(name) << ",\"size\":" << size << ",\"offset\":" << offset << ",\"bound\":" << (i <= 5 ? "true" : "false") << '}';
  }
  out << "]}"; return out.str();
}
static void pin_artifacts(const Options &o) {
  const auto manifest = read_file(o.artifacts, 65536);
  require(hex(sha256(manifest.data(), manifest.size()).data(), 32) == o.artifacts_sha, "build manifest pin mismatch");
  auto pins = sidecar(o.artifacts);
  fields(pins, {{"format", "halogen-native-hidden-decoded-artifacts-v1"}, {"emission_verified", "true"}});
  for (const auto &item : std::array<std::pair<const char *, std::string>, 3>{{
      {"xclbin_sha256", o.xclbin}, {"instructions_sha256", o.instructions}, {"abi_sha256", o.abi}}}) {
    const auto data = read_file(item.second, 64 * 1024 * 1024);
    require(hex(sha256(data.data(), data.size()).data(), 32) == pins.at(item.first), "build artifact pin mismatch " + item.second);
  }
}

struct Sample { unsigned call; double launch_wait, complete; size_t exact_mismatches = 0, gate_mismatches = 0; double max_abs = 0; };
class Backend {
  Clock::time_point deadline_;
  unsigned wait_ms_, used_ = 0;
  xrt::device device_;
  xrt::hw_context context_;
  xrt::kernel kernel_;
  xrt::bo instructions_, weights_, input_, output_;
  uint16_t *input_map_, *output_map_;
  xrt::run run_;
  bool in_flight_ = false;
public:
  Backend(const Options &o, const xrt::xclbin &binary, const std::vector<uint8_t> &words,
          const std::vector<uint8_t> &weights, Clock::time_point limit)
      : deadline_(limit), wait_ms_(o.wait_ms), device_(o.device),
        context_([&]() { device_.register_xclbin(binary); return xrt::hw_context(device_, binary.get_uuid()); }()),
        kernel_(context_, "MLIR_AIE"),
        instructions_(device_, words.size(), XCL_BO_FLAGS_CACHEABLE, kernel_.group_id(1)),
        weights_(device_, hc::weight_bytes, XRT_BO_FLAGS_HOST_ONLY, kernel_.group_id(3)),
        input_(device_, hc::input_bytes, XRT_BO_FLAGS_HOST_ONLY, kernel_.group_id(4)),
        output_(device_, hc::output_bytes, XRT_BO_FLAGS_HOST_ONLY, kernel_.group_id(5)),
        input_map_(input_.map<uint16_t *>()), output_map_(output_.map<uint16_t *>()), run_(kernel_) {
    std::memcpy(instructions_.map<uint8_t *>(), words.data(), words.size());
    std::memcpy(weights_.map<uint8_t *>(), weights.data(), weights.size());
    instructions_.sync(XCL_BO_SYNC_BO_TO_DEVICE); weights_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    run_.set_arg(0, uint64_t{3}); run_.set_arg(1, instructions_); run_.set_arg(2, uint32_t(words.size() / 4));
    run_.set_arg(3, weights_); run_.set_arg(4, input_); run_.set_arg(5, output_);
    deadline(deadline_, "persistent backend init");
  }
  ~Backend() {
    if (in_flight_) {
      std::cerr << "Aborting only owned in-flight XRT run. External job deadline remains required.\n";
      try { run_.abort(); } catch (...) {}
    }
  }
  Sample compute(const uint8_t *source, uint8_t *destination) {
    deadline(deadline_, "launch admission"); require(used_ < hc::core_calls, "finite64 native cohort exhausted");
    const unsigned call = used_++; // Burn on admission, never retry failed runs.
    finite_bf16(source, hc::input_elements, "input");
    const auto start = Clock::now(); std::memcpy(input_map_, source, hc::input_bytes);
    std::fill(output_map_, output_map_ + hc::output_elements, uint16_t{0x7FC1});
    input_.sync(XCL_BO_SYNC_BO_TO_DEVICE); output_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    deadline(deadline_, "input/poison sync");
    const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline_ - Clock::now()).count();
    require(remaining > 0, "no remaining native run budget");
    const auto launch = Clock::now(); in_flight_ = true; run_.start();
    const auto state = run_.wait(std::chrono::milliseconds(std::min<int64_t>(wait_ms_, remaining)));
    const auto waited = Clock::now();
    require(state == ERT_CMD_STATE_COMPLETED, "owned native run incomplete, ERT=" + std::to_string(int(state)));
    in_flight_ = false; output_.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    std::memcpy(destination, output_map_, hc::output_bytes);
    const auto complete = Clock::now(); deadline(deadline_, "output readback");
    finite_bf16(destination, hc::output_elements, "output");
    return Sample{call, us(launch, waited), us(start, complete)};
  }
};

// One resident watchdog cancels main-thread synchronous Windows pipe I/O at
// the overall deadline. XRT waits/sync/destruction still need the outer job kill.
class IoWatchdog {
  HANDLE stop_ = nullptr, main_ = nullptr; std::thread thread_;
public:
  explicit IoWatchdog(unsigned timeout_ms) {
    stop_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    require(stop_ != nullptr, "watchdog event creation failed");
    if (!DuplicateHandle(GetCurrentProcess(), GetCurrentThread(), GetCurrentProcess(), &main_, 0, FALSE, DUPLICATE_SAME_ACCESS)) {
      CloseHandle(stop_); throw std::runtime_error("watchdog thread handle failed");
    }
    thread_ = std::thread([this, timeout_ms]() {
      if (WaitForSingleObject(stop_, timeout_ms) == WAIT_TIMEOUT) CancelSynchronousIo(main_);
    });
  }
  ~IoWatchdog() { SetEvent(stop_); if (thread_.joinable()) thread_.join(); CloseHandle(main_); CloseHandle(stop_); }
};
static bool read_exact(HANDLE pipe, void *data, size_t bytes, bool eof_allowed, Clock::time_point limit) {
  auto *dst = static_cast<uint8_t *>(data); size_t done = 0;
  while (done < bytes) {
    deadline(limit, "framed input"); DWORD n = 0;
    if (!ReadFile(pipe, dst + done, DWORD(bytes - done), &n, nullptr)) {
      const auto error = GetLastError();
      if (eof_allowed && done == 0 && error == ERROR_BROKEN_PIPE) return false;
      throw std::runtime_error("framed ReadFile failed " + std::to_string(error));
    }
    if (!n && eof_allowed && !done) return false;
    require(n != 0, "partial frame EOF"); done += n;
  }
  deadline(limit, "framed input completion"); return true;
}
static void write_exact(HANDLE pipe, const void *data, size_t bytes, Clock::time_point limit) {
  const auto *src = static_cast<const uint8_t *>(data); size_t done = 0;
  while (done < bytes) {
    deadline(limit, "framed output"); DWORD n = 0;
    require(WriteFile(pipe, src + done, DWORD(bytes - done), &n, nullptr) && n, "framed WriteFile failed"); done += n;
  }
  deadline(limit, "framed output completion");
}
static std::vector<uint8_t> receive(HANDLE pipe, unsigned kind, uint64_t seq, size_t bytes, Clock::time_point limit, bool empty_eof = false) {
  hgnh_frame frame{};
  if (!read_exact(pipe, &frame, sizeof(frame), empty_eof, limit)) return {};
  require(!std::memcmp(frame.magic, HGNH_FRAME_MAGIC, 8) && frame.kind == kind && frame.sequence == seq && frame.payload_bytes == bytes,
          "outer frame admission failed");
  std::vector<uint8_t> payload(bytes); read_exact(pipe, payload.data(), bytes, false, limit);
  const auto digest = sha256(payload.data(), payload.size());
  require(!std::memcmp(frame.payload_sha256, digest.data(), 32), "outer frame SHA mismatch"); return payload;
}
static void send(HANDLE pipe, unsigned kind, uint64_t seq, const void *data, size_t bytes, Clock::time_point limit) {
  hgnh_frame frame{}; std::memcpy(frame.magic, HGNH_FRAME_MAGIC, 8); frame.kind = kind;
  frame.payload_bytes = uint32_t(bytes); frame.sequence = seq;
  const auto digest = sha256(data, bytes); std::memcpy(frame.payload_sha256, digest.data(), 32);
  // Entire validated success packet is assembled before any byte is emitted.
  std::vector<uint8_t> packet(sizeof(frame) + bytes);
  std::memcpy(packet.data(), &frame, sizeof(frame)); std::memcpy(packet.data() + sizeof(frame), data, bytes);
  write_exact(pipe, packet.data(), packet.size(), limit);
}
static void binding(uint8_t *target, const std::string &value, size_t bytes, const char *name) {
  const auto b = unhex(value, bytes, name); std::memcpy(target, b.data(), bytes);
}
static std::string serve(const Options &o, Backend &backend, Clock::time_point limit, double init_us) {
  const HANDLE input = GetStdHandle(STD_INPUT_HANDLE), output = GetStdHandle(STD_OUTPUT_HANDLE);
  require(input != INVALID_HANDLE_VALUE && output != INVALID_HANDLE_VALUE && GetFileType(input) == FILE_TYPE_PIPE && GetFileType(output) == FILE_TYPE_PIPE,
          "serve requires inherited binary stdin/stdout pipes");
  hgnh_hello pinned{}; std::memcpy(pinned.magic, HGNH_HELLO_MAGIC, 8);
  pinned.version = HGNH_VERSION; pinned.max_calls = HGNH_MAX_CALLS; pinned.process_id = o.process_id;
  binding(pinned.nonce, o.nonce, 16, "nonce"); binding(pinned.epoch, o.epoch, 16, "epoch");
  binding(pinned.model_binding, o.model_binding, 32, "model"); binding(pinned.graph_binding, o.graph_binding, 32, "graph");
  binding(pinned.engine_sha256, o.engine_sha, 32, "engine"); pinned.h_bytes = HGNH_H_BYTES; pinned.wire = HGNH_WIRE_D;
  const auto hello = receive(input, HGNH_HELLO, 0, HGNH_HELLO_BYTES, limit);
  require(!std::memcmp(hello.data(), &pinned, sizeof(pinned)), "HELLO differs from CLI pins");
  std::memcpy(pinned.magic, HGNH_READY_MAGIC, 8); send(output, HGNH_READY, 0, &pinned, sizeof(pinned), limit);
  uint64_t model = 0; std::vector<Sample> samples; samples.reserve(HGNH_MAX_CALLS);
  bool owner_closed = false;
  for (unsigned sequence = 0; sequence < HGNH_MAX_CALLS; ++sequence) {
    const auto begin = Clock::now();
    const auto packet = receive(input, HGNH_REQUEST, sequence, HGNH_REQUEST_BYTES, limit, true);
    if (packet.empty()) { owner_closed = true; break; }
    hgnh_request request{}; std::memcpy(&request, packet.data(), sizeof(request));
    const auto &h = request.header;
    require(!std::memcmp(h.magic, HGNH_REQUEST_MAGIC, 8) && h.version == HGNH_VERSION && h.body_bytes == HGNH_H_BYTES &&
        h.sequence == int32_t(sequence) && h.position >= 0 && h.outer_position >= 0 && h.slot >= 0 &&
        h.count == 1 && h.token >= 0 && h.wire == HGNH_WIRE_D && h.reserved == 0 && h.model != 0 && h.process_id == pinned.process_id &&
        !std::memcmp(h.nonce, pinned.nonce, 16) && !std::memcmp(h.epoch, pinned.epoch, 16) &&
        !std::memcmp(h.model_binding, pinned.model_binding, 32) && !std::memcmp(h.graph_binding, pinned.graph_binding, 32), "request binding/admission failed");
    if (!model) model = h.model; require(model == h.model, "opaque model pointer changed within owned epoch");
    const auto input_sha = sha256(request.body, sizeof(request.body));
    require(!std::memcmp(h.input_binding, input_sha.data(), 32), "request input SHA mismatch");
    std::array<uint8_t, HGNH_REQUEST_BINDING_OFFSET + HGNH_H_BYTES> preimage{};
    std::memcpy(preimage.data(), &h, HGNH_REQUEST_BINDING_OFFSET);
    std::memcpy(preimage.data() + HGNH_REQUEST_BINDING_OFFSET, request.body, HGNH_H_BYTES);
    const auto request_sha = sha256(preimage.data(), preimage.size());
    require(!std::memcmp(h.request_binding, request_sha.data(), 32), "request SHA mismatch");
    finite_bf16(request.body, hc::input_elements, "request");
    hgnh_response response{}; response.header = h; std::memcpy(response.header.magic, HGNH_RESPONSE_MAGIC, 8);
    auto sample = backend.compute(request.body, response.body); // Backend burns before native work.
    const auto response_sha = sha256(&response, offsetof(hgnh_response, digest));
    std::memcpy(response.digest, response_sha.data(), 32);
    send(output, HGNH_RESPONSE, sequence, &response, sizeof(response), limit);
    samples.push_back(sample);
    std::cerr << "{\"event\":\"native-H-reply\",\"sequence\":" << sequence << ",\"complete_native_us\":" << sample.complete
              << ",\"framed_receive_validate_compute_response_write_us\":" << us(begin, Clock::now()) << "}\n";
  }
  // Root's full head continues after response63. Remain resident until owner
  // closes stdin; reject every extra byte. The finite device core is exhausted.
  if (!owner_closed) {
    uint8_t extra = 0; require(!read_exact(input, &extra, 1, true, limit), "extra request after finite64 cohort");
  }
  return "{\"status\":\"native-cohort-complete\",\"mode\":\"serve\",\"calls\":" + std::to_string(samples.size()) + ",\"initialization_us\":" +
      std::to_string(init_us) + ",\"oracles_checked_in_this_process\":false}";
}
static std::string stats(std::vector<double> values) {
  require(!values.empty(), "no measured samples"); std::sort(values.begin(), values.end());
  const auto q = [&](double quantile) { double p = quantile * (values.size() - 1); size_t lo = size_t(std::floor(p)), hi = size_t(std::ceil(p)); return values[lo] + (values[hi] - values[lo]) * (p - lo); };
  std::ostringstream out; out << std::fixed << std::setprecision(6) << "{\"count\":" << values.size() << ",\"mean_us\":" <<
      std::accumulate(values.begin(), values.end(), 0.0) / values.size() << ",\"p50_us\":" << q(.5) << ",\"p95_us\":" << q(.95)
      << ",\"min_us\":" << values.front() << ",\"max_us\":" << values.back() << '}'; return out.str();
}
static std::string cohort(const Options &o, Backend &backend, Clock::time_point limit, double init_us) {
  const unsigned total = o.warmups + o.measurements; const size_t bytes = size_t(total) * hc::input_bytes;
  const auto inputs = read_file(o.cohort_inputs, size_t(hc::core_calls) * hc::input_bytes, bytes);
  const auto oracles = read_file(o.cohort_oracles, size_t(hc::core_calls) * hc::output_bytes, bytes);
  std::set<std::string> distinct;
  for (unsigned i = 0; i < total; ++i) {
    finite_bf16(inputs.data() + size_t(i) * hc::input_bytes, hc::input_elements, "cohort input");
    finite_bf16(oracles.data() + size_t(i) * hc::output_bytes, hc::output_elements, "cohort oracle");
    const auto digest = sha256(inputs.data() + size_t(i) * hc::input_bytes, hc::input_bytes);
    require(distinct.insert(hex(digest.data(), digest.size())).second, "cohort inputs must be distinct, no repeated-input speed claim");
  }
  std::vector<Sample> samples; std::vector<double> launches, completes;
  std::array<uint8_t, hc::output_bytes> actual{}; size_t exact_total = 0, gate_total = 0;
  for (unsigned call = 0; call < total; ++call) {
    deadline(limit, "cohort call"); auto sample = backend.compute(inputs.data() + size_t(call) * hc::input_bytes, actual.data());
    const uint8_t *expected = oracles.data() + size_t(call) * hc::output_bytes;
    for (size_t i = 0; i < hc::output_elements; ++i) {
      const float a = bf16_value(actual.data(), i), e = bf16_value(expected, i);
      const double error = std::abs(double(a) - double(e)); sample.max_abs = std::max(sample.max_abs, error);
      sample.exact_mismatches += actual[i * 2] != expected[i * 2] || actual[i * 2 + 1] != expected[i * 2 + 1];
      sample.gate_mismatches += error > .003 + .03 * std::abs(double(e));
    }
    exact_total += sample.exact_mismatches; gate_total += sample.gate_mismatches; samples.push_back(sample);
    if (call >= o.warmups) { launches.push_back(sample.launch_wait); completes.push_back(sample.complete); }
    // Frozen gate failure latches immediately, no additional device launches.
    if (sample.gate_mismatches) break;
  }
  std::ostringstream out; out << std::fixed << std::setprecision(6) << "{\"status\":" << quote(gate_total ? "failed-numeric-gate" : "passed")
      << ",\"mode\":\"cohort\",\"initialization_us\":" << init_us << ",\"warmups\":" << o.warmups << ",\"requested_measurements\":" << o.measurements
      << ",\"calls\":" << samples.size() << ",\"verified_values\":" << samples.size() * hc::output_elements << ",\"exact_word_mismatches\":" << exact_total
      << ",\"npu_gate_mismatches\":" << gate_total << ",\"rtol\":0.03,\"atol\":0.003,\"ddr_bytes_per_call\":13291520,\"weights_synced_once\":true,\"per_projection_weight_decoder_calls\":0";
  if (!completes.empty()) out << ",\"launch_wait\":" << stats(launches) << ",\"complete_input_copy_poison_sync_launch_wait_output_sync_readback\":" << stats(completes);
  out << ",\"samples\":[";
  for (size_t i = 0; i < samples.size(); ++i) {
    if (i) out << ','; const auto &s = samples[i];
    out << "{\"call\":" << s.call << ",\"measured\":" << (s.call >= o.warmups ? "true" : "false") << ",\"launch_wait_us\":" << s.launch_wait
        << ",\"complete_us\":" << s.complete << ",\"exact_word_mismatches\":" << s.exact_mismatches << ",\"npu_gate_mismatches\":" << s.gate_mismatches << ",\"max_abs\":" << s.max_abs << '}';
  }
  out << "]}"; return out.str();
}
int main(int argc, char **argv) {
  Options o;
  try {
    o = options(argc, argv); const auto start = Clock::now(); const auto limit = start + std::chrono::milliseconds(o.deadline_ms);
    IoWatchdog watchdog(o.deadline_ms); const auto inspection = inspect(o);
    if (o.mode == "inspect") { std::cout << inspection << '\n'; return 0; }
    pin_artifacts(o);
    const auto weight_pins = sidecar(o.weights_abi);
    fields(weight_pins, {{"format", "halogen-native-hidden-decoded-pack-v1"}, {"raw_weight_bytes", "6963200"}, {"weight_bytes", "13107200"},
        {"raw_sha256", o.raw_sha}, {"packed_sha256", o.packed_sha},
        {"inverse_decoded_bitwise_equal", "true"}, {"finite_bf16_weights", "true"}, {"decode", "exact-dyadic-affine-rn32-rnbf16-once"}});
    unhex(weight_pins.at("decoded_sha256"), 32, "decoded BF16 matrix SHA");
    require(weight_pins.at("decoded_sha256") == weight_pins.at("reconstructed_sha256"), "decoded-weight inverse digest mismatch");
    const auto packed = read_file(o.weights, hc::weight_bytes, hc::weight_bytes);
    require(hex(sha256(packed.data(), packed.size()).data(), 32) == o.packed_sha, "packed weights SHA mismatch");
    // Independently inspect every decoded BF16 weight before device construction.
    finite_bf16(packed.data(), hc::weight_elements, "packed weight");
    const auto instructions = read_file(o.instructions, 16 * 1024 * 1024);
    const xrt::xclbin binary(o.xclbin);
    Backend backend(o, binary, instructions, packed, limit); const auto initialized = Clock::now();
    std::cerr << "{\"event\":\"persistent-backend-ready\",\"initialization_us\":" << us(start, initialized) << ",\"abi\":" << inspection << "}\n";
    const auto result = o.mode == "serve" ? serve(o, backend, limit, us(start, initialized)) : cohort(o, backend, limit, us(start, initialized));
    if (!o.report.empty()) { std::ofstream file(o.report, std::ios::binary | std::ios::trunc); require(bool(file) && bool(file << result << '\n'), "report write failed"); }
    std::cerr << result << '\n'; return result.find("failed-numeric-gate") == std::string::npos ? 0 : 2;
  } catch (const std::exception &e) {
    const std::string result = "{\"status\":\"failed-latched\",\"error\":" + quote(e.what()) + "}";
    if (!o.report.empty()) { std::ofstream file(o.report, std::ios::binary | std::ios::trunc); if (file) file << result << '\n'; }
    std::cerr << result << '\n'; return 1;
  }
}
