// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// XRT setup follows AMD/Xilinx MLIR-AIE examples attributed in README.md.
#define NOMINMAX
#include "contract.h"
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
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace dc = dispatch_contract;
using Clock = std::chrono::steady_clock;

struct Options {
  std::string xclbin, instructions, abi, output;
  unsigned device_index = 0;
  unsigned warmups = 8;
  unsigned measurements = 48;
  unsigned wait_ms = 500;
  unsigned deadline_ms = 20000;
};

static unsigned parse_unsigned(const std::string &text, const std::string &name) {
  if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
    throw std::runtime_error(name + " requires an unsigned decimal integer");
  const auto value = std::stoull(text);
  if (value > std::numeric_limits<unsigned>::max())
    throw std::runtime_error(name + " is out of range");
  return static_cast<unsigned>(value);
}

static Options parse_options(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    const std::string key = argv[i];
    if (key == "--help") {
      std::cout << "host.exe --xclbin FILE --instructions FILE --abi FILE "
                   "[--output FILE] [--device-index N] [--warmups 8] "
                   "[--measurements 48] [--wait-ms 500] [--deadline-ms 20000]\n"
                   "Run only inside the independently owned external process deadline.\n";
      std::exit(0);
    }
    if (i + 1 >= argc)
      throw std::runtime_error("missing value for " + key);
    const std::string value = argv[++i];
    if (key == "--xclbin") o.xclbin = value;
    else if (key == "--instructions") o.instructions = value;
    else if (key == "--abi") o.abi = value;
    else if (key == "--output") o.output = value;
    else if (key == "--device-index") o.device_index = parse_unsigned(value, key);
    else if (key == "--warmups") o.warmups = parse_unsigned(value, key);
    else if (key == "--measurements") o.measurements = parse_unsigned(value, key);
    else if (key == "--wait-ms") o.wait_ms = parse_unsigned(value, key);
    else if (key == "--deadline-ms") o.deadline_ms = parse_unsigned(value, key);
    else throw std::runtime_error("unknown option " + key);
  }
  if (o.xclbin.empty() || o.instructions.empty() || o.abi.empty())
    throw std::runtime_error("--xclbin, --instructions and --abi are required");
  if (o.measurements == 0 || o.measurements > dc::core_calls ||
      o.warmups > dc::core_calls - o.measurements)
    throw std::runtime_error("1 <= measurements and warmups + measurements <= 64 required");
  if (o.deadline_ms < 1000 || o.deadline_ms > 80000 ||
      o.wait_ms == 0 || o.wait_ms > 2000 || o.wait_ms > o.deadline_ms)
    throw std::runtime_error("deadline-ms must be 1000..80000; wait-ms must be 1..2000 and <= deadline");
  return o;
}

static std::string json_string(const std::string &s) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c == '\n') out << "\\n";
    else if (c == '\r') out << "\\r";
    else if (c == '\t') out << "\\t";
    else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                         << static_cast<unsigned>(c) << std::dec;
    else out << c;
  }
  out << '"';
  return out.str();
}

static std::map<std::string, std::string> read_abi(const std::string &path) {
  std::ifstream file(path);
  if (!file) throw std::runtime_error("cannot open ABI sidecar " + path);
  std::map<std::string, std::string> fields;
  std::string line;
  while (std::getline(file, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty() || line.front() == '#') continue;
    const auto split = line.find('=');
    if (split == std::string::npos || split == 0 ||
        !fields.emplace(line.substr(0, split), line.substr(split + 1)).second)
      throw std::runtime_error("malformed or duplicate ABI sidecar field");
  }
  const std::map<std::string, std::string> required = {
      {"format", "halogen-native-dispatch-v1"}, {"device", "npu2_1col"},
      {"kernel", "MLIR_AIE"}, {"input_elements", "256"}, {"input_bytes", "512"},
      {"output_elements", "64"}, {"output_bytes", "256"}, {"core_calls", "64"},
      {"stack_bytes", "4096"}, {"instruction_count_unit", "uint32_words"},
      {"runtime_buffers", "2"}, {"input_arg", "3"}, {"output_arg", "4"},
      {"weight_formula", "(row*7+col*3)%17-8"},
      {"input_formula", "col==0?call-32:(col*5+call*7)%23-11"}};
  for (const auto &item : required) {
    const auto it = fields.find(item.first);
    if (it == fields.end() || it->second != item.second)
      throw std::runtime_error("ABI sidecar mismatch: " + item.first);
  }
  const auto mode_it = fields.find("mode");
  if (mode_it == fields.end() || (mode_it->second != "control" &&
      mode_it->second != "gemv-vector" && mode_it->second != "gemv-scalar"))
    throw std::runtime_error("unknown ABI mode");
  const auto weight_bytes = fields.find("weight_bytes");
  if (weight_bytes == fields.end() || weight_bytes->second !=
      (mode_it->second == "control" ? "0" : "32768"))
    throw std::runtime_error("ABI weight byte count mismatch");
  const auto wheel = fields.find("mlir_aie_version");
  if (wheel == fields.end() || wheel->second.substr(0, wheel->second.find('+')) != "1.3.4")
    throw std::runtime_error("ABI generator was not MLIR-AIE 1.3.4");
  return fields;
}

static std::vector<uint32_t> read_instructions(const std::string &path) {
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file) throw std::runtime_error("cannot open instruction binary " + path);
  const auto end = file.tellg();
  if (end <= 0 || end > 16 * 1024 * 1024 || static_cast<uint64_t>(end) % 4 != 0)
    throw std::runtime_error("instruction binary must be nonempty uint32 words, <=16 MiB");
  std::vector<uint32_t> words(static_cast<size_t>(end) / sizeof(uint32_t));
  file.seekg(0);
  if (!file.read(reinterpret_cast<char *>(words.data()), static_cast<std::streamsize>(end)))
    throw std::runtime_error("short instruction binary read");
  return words;
}

static std::string inspect_metadata(const xrt::xclbin &binary) {
  const auto kernels = binary.get_kernels();
  const auto found = std::find_if(kernels.begin(), kernels.end(),
      [](const xrt::xclbin::kernel &k) { return k.get_name() == "MLIR_AIE"; });
  if (found == kernels.end() || std::count_if(kernels.begin(), kernels.end(),
      [](const xrt::xclbin::kernel &k) { return k.get_name() == "MLIR_AIE"; }) != 1)
    throw std::runtime_error("xclbin must contain exactly one kernel named MLIR_AIE");
  auto args = found->get_args();
  std::sort(args.begin(), args.end(), [](const auto &a, const auto &b) {
    return a.get_index() < b.get_index();
  });
  // Two live BOs, optionally followed by up to three compiler padding BOs.
  if (args.size() < 5 || args.size() > 8)
    throw std::runtime_error("expected five live arguments plus at most bo2..bo4 padding");
  std::ostringstream metadata;
  metadata << '[';
  for (size_t i = 0; i < args.size(); ++i) {
    const std::string name = i == 0 ? "opcode" : i == 1 ? "instr" : i == 2 ? "ninstr"
                                      : "bo" + std::to_string(i - 3);
    const uint64_t size = i == 2 ? 4 : 8;
    const uint64_t offset = i < 3 ? i * 8 : 0x14 + (i - 3) * 8;
    if (args[i].get_index() != i || args[i].get_name() != name ||
        args[i].get_size() != size || args[i].get_offset() != offset)
      throw std::runtime_error("incompatible xclbin argument metadata at index " + std::to_string(i));
    if (i) metadata << ',';
    metadata << "{\"index\":" << i << ",\"name\":" << json_string(name)
             << ",\"size\":" << size << ",\"offset\":" << offset
             << ",\"host_type\":" << json_string(args[i].get_host_type())
             << ",\"bound\":" << (i <= 4 ? "true" : "false") << '}';
  }
  metadata << ']';
  return metadata.str();
}

static double us(Clock::time_point start, Clock::time_point end) {
  return std::chrono::duration<double, std::micro>(end - start).count();
}

static void check_deadline(Clock::time_point deadline, const char *stage) {
  if (Clock::now() >= deadline)
    throw std::runtime_error(std::string("overall deadline exceeded at ") + stage);
}

struct Sample { unsigned call; bool measured; double launch_wait, complete, verify; };

static std::string stats_json(std::vector<double> values) {
  if (values.empty()) throw std::runtime_error("no measurement samples");
  std::sort(values.begin(), values.end());
  const auto quantile = [&values](double q) {
    const double p = q * static_cast<double>(values.size() - 1);
    const size_t lo = static_cast<size_t>(std::floor(p));
    const size_t hi = static_cast<size_t>(std::ceil(p));
    return values[lo] + (values[hi] - values[lo]) * (p - lo);
  };
  std::ostringstream out;
  out << std::fixed << std::setprecision(6)
      << "{\"count\":" << values.size() << ",\"p50_us\":" << quantile(0.5)
      << ",\"p95_us\":" << quantile(0.95) << ",\"mean_us\":"
      << std::accumulate(values.begin(), values.end(), 0.0) / values.size()
      << ",\"min_us\":" << values.front() << ",\"max_us\":" << values.back() << '}';
  return out.str();
}

static std::string probe(const Options &o) {
  const auto init_start = Clock::now();
  const auto deadline = init_start + std::chrono::milliseconds(o.deadline_ms);
  const auto abi = read_abi(o.abi);
  const auto words = read_instructions(o.instructions);
  const xrt::xclbin binary(o.xclbin);
  const std::string metadata = inspect_metadata(binary);
  const auto artifacts_end = Clock::now();
  check_deadline(deadline, "artifact validation");

  // Everything below persists for this cohort, including a single run object.
  xrt::device device(o.device_index);
  device.register_xclbin(binary);
  xrt::hw_context context(device, binary.get_uuid());
  xrt::kernel kernel(context, "MLIR_AIE");
  xrt::bo instructions(device, words.size() * sizeof(uint32_t),
                       XCL_BO_FLAGS_CACHEABLE, kernel.group_id(1));
  xrt::bo input(device, dc::input_bytes, XRT_BO_FLAGS_HOST_ONLY, kernel.group_id(3));
  xrt::bo output(device, dc::output_bytes, XRT_BO_FLAGS_HOST_ONLY, kernel.group_id(4));
  auto *instruction_map = instructions.map<uint32_t *>();
  auto *input_map = input.map<int16_t *>();
  auto *output_map = output.map<int32_t *>();
  std::memcpy(instruction_map, words.data(), words.size() * sizeof(uint32_t));
  instructions.sync(XCL_BO_SYNC_BO_TO_DEVICE);

  xrt::run run(kernel);
  run.set_arg(0, uint64_t{3});
  run.set_arg(1, instructions);
  run.set_arg(2, static_cast<uint32_t>(words.size())); // WORD count, never bytes.
  run.set_arg(3, input);
  run.set_arg(4, output);
  const auto init_end = Clock::now();
  check_deadline(deadline, "device initialization");

  std::vector<Sample> samples;
  samples.reserve(o.warmups + o.measurements);
  std::vector<double> launch_times, complete_times;
  launch_times.reserve(o.measurements);
  complete_times.reserve(o.measurements);
  bool in_flight = false;
  try {
    for (unsigned call = 0; call < o.warmups + o.measurements; ++call) {
      check_deadline(deadline, "iteration start");
      std::array<int16_t, dc::cols> source{};
      std::array<int32_t, dc::rows> expected{}, actual{};
      for (unsigned col = 0; col < dc::cols; ++col)
        source[col] = dc::input_value(call, col);
      for (unsigned row = 0; row < dc::rows; ++row) {
        int64_t sum = source[row];
        if (abi.at("mode") != "control") {
          sum = 0;
          for (unsigned col = 0; col < dc::cols; ++col)
            sum += static_cast<int64_t>(dc::weight_value(row, col)) * source[col];
        }
        if (sum < std::numeric_limits<int32_t>::min() || sum > std::numeric_limits<int32_t>::max())
          throw std::runtime_error("reference exceeds i32");
        expected[row] = static_cast<int32_t>(sum);
      }

      const auto complete_start = Clock::now();
      std::memcpy(input_map, source.data(), dc::input_bytes);
      std::fill(output_map, output_map + dc::rows, dc::poison);
      input.sync(XCL_BO_SYNC_BO_TO_DEVICE);
      output.sync(XCL_BO_SYNC_BO_TO_DEVICE); // Make the poison visible to DMA.
      check_deadline(deadline, "input and poison synchronization");
      const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now());
      if (remaining.count() <= 0) throw std::runtime_error("deadline exhausted before launch");
      const auto wait_budget = std::chrono::milliseconds(std::min<int64_t>(o.wait_ms, remaining.count()));
      const auto launch_start = Clock::now();
      in_flight = true;
      run.start();
      const auto state = run.wait(wait_budget);
      const auto launch_end = Clock::now();
      if (state != ERT_CMD_STATE_COMPLETED)
        throw std::runtime_error("run did not complete; ERT state=" + std::to_string(static_cast<int>(state)));
      in_flight = false;
      output.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
      std::memcpy(actual.data(), output_map, dc::output_bytes);
      const auto complete_end = Clock::now();
      for (unsigned row = 0; row < dc::rows; ++row) {
        if (actual[row] != expected[row])
          throw std::runtime_error("verification mismatch call=" + std::to_string(call) +
              " row=" + std::to_string(row) + " expected=" + std::to_string(expected[row]) +
              " actual=" + std::to_string(actual[row]));
      }
      const auto verify_end = Clock::now();
      check_deadline(deadline, "output verification");
      const bool measured = call >= o.warmups;
      const Sample sample{call, measured, us(launch_start, launch_end),
                          us(complete_start, complete_end), us(complete_end, verify_end)};
      samples.push_back(sample);
      if (measured) {
        launch_times.push_back(sample.launch_wait);
        complete_times.push_back(sample.complete);
      }
    }
  } catch (...) {
    // Only this process's owned run is aborted. abort() itself can block;
    // the root-owned external process/job deadline remains mandatory.
    if (in_flight) {
      std::cerr << "Aborting the owned in-flight run after failure.\n";
      try { run.abort(); }
      catch (const std::exception &e) { std::cerr << "Owned run abort failed: " << e.what() << '\n'; }
    }
    throw;
  }

  std::ostringstream out;
  out << std::fixed << std::setprecision(6)
      << "{\"status\":\"passed\",\"mode\":" << json_string(abi.at("mode"))
      << ",\"device_index\":" << o.device_index << ",\"device\":\"npu2_1col\""
      << ",\"kernel\":\"MLIR_AIE\",\"input_bytes\":" << dc::input_bytes
      << ",\"output_bytes\":" << dc::output_bytes << ",\"weight_bytes\":" << abi.at("weight_bytes")
      << ",\"core_calls\":" << dc::core_calls << ",\"warmups\":" << o.warmups
      << ",\"measurements\":" << o.measurements << ",\"verified_calls\":" << samples.size()
      << ",\"verified_values\":" << samples.size() * dc::rows
      << ",\"instruction_words\":" << words.size() << ",\"wait_ms\":" << o.wait_ms
      << ",\"deadline_ms\":" << o.deadline_ms
      << ",\"initialization_total_us\":" << us(init_start, init_end)
      << ",\"artifact_validation_us\":" << us(init_start, artifacts_end)
      << ",\"device_context_buffers_and_run_us\":" << us(artifacts_end, init_end)
      << ",\"launch_wait\":" << stats_json(launch_times)
      << ",\"complete_input_copy_poison_sync_launch_wait_output_sync_readback\":" << stats_json(complete_times)
      << ",\"quantile_method\":\"linear interpolation at q*(n-1)\""
      << ",\"reference_and_verification_excluded_from_complete\":true"
      << ",\"xclbin\":" << json_string(o.xclbin) << ",\"instructions\":" << json_string(o.instructions)
      << ",\"abi\":" << json_string(o.abi) << ",\"arguments\":" << metadata << ",\"samples\":[";
  for (size_t i = 0; i < samples.size(); ++i) {
    if (i) out << ',';
    const auto &s = samples[i];
    out << "{\"call\":" << s.call << ",\"measured\":" << (s.measured ? "true" : "false")
        << ",\"launch_wait_us\":" << s.launch_wait << ",\"complete_us\":" << s.complete
        << ",\"verify_us\":" << s.verify << '}';
  }
  out << "]}";
  return out.str();
}

int main(int argc, char **argv) {
  Options options;
  try {
    options = parse_options(argc, argv);
    const auto report = probe(options);
    if (!options.output.empty()) {
      std::ofstream file(options.output, std::ios::binary | std::ios::trunc);
      if (!file || !(file << report << '\n')) throw std::runtime_error("cannot write output report");
    }
    std::cout << report << '\n';
    return 0;
  } catch (const std::exception &e) {
    const auto report = "{\"status\":\"failed\",\"error\":" + json_string(e.what()) + "}";
    if (!options.output.empty()) {
      std::ofstream file(options.output, std::ios::binary | std::ios::trunc);
      if (file) file << report << '\n';
    }
    std::cerr << report << '\n';
    return 1;
  }
}
