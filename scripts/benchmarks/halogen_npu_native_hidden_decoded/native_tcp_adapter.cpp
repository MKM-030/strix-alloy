// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Owned, finite Windows TCP<->persistent native host adapter. No XRT imports.
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0A00
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <bcrypt.h>
#include "../halogen_mtp_h_wire.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using Clock = std::chrono::steady_clock;
using Time = Clock::time_point;
using Digest = std::array<uint8_t, 32>;

static void check(bool okay, const std::string &message) {
  if (!okay) throw std::runtime_error(message);
}
class Handle {
  HANDLE value_ = INVALID_HANDLE_VALUE;
public:
  explicit Handle(HANDLE value = INVALID_HANDLE_VALUE) : value_(value) {}
  ~Handle() { reset(); }
  Handle(const Handle &) = delete;
  Handle &operator=(const Handle &) = delete;
  Handle(Handle &&other) noexcept : value_(other.release()) {}
  Handle &operator=(Handle &&other) noexcept { if (this != &other) reset(other.release()); return *this; }
  HANDLE get() const { return value_; }
  HANDLE release() { const HANDLE result = value_; value_ = INVALID_HANDLE_VALUE; return result; }
  void reset(HANDLE value = INVALID_HANDLE_VALUE) { if (value_ != INVALID_HANDLE_VALUE && value_ != nullptr) CloseHandle(value_); value_ = value; }
};
class Socket {
  SOCKET value_ = INVALID_SOCKET;
public:
  explicit Socket(SOCKET value = INVALID_SOCKET) : value_(value) {}
  ~Socket() { if (value_ != INVALID_SOCKET) { shutdown(value_, SD_BOTH); closesocket(value_); } }
  Socket(const Socket &) = delete;
  Socket &operator=(const Socket &) = delete;
  SOCKET get() const { return value_; }
  void close() { if (value_ != INVALID_SOCKET) { closesocket(value_); value_ = INVALID_SOCKET; } }
};
struct Winsock {
  Winsock() { WSADATA data{}; check(WSAStartup(MAKEWORD(2, 2), &data) == 0, "Winsock startup failed"); }
  ~Winsock() { WSACleanup(); }
};
static DWORD remaining(Time deadline) {
  const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
  check(ms > 0, "adapter owned deadline expired");
  return static_cast<DWORD>(std::min<int64_t>(ms, std::numeric_limits<DWORD>::max() - 1));
}
static Time stage_limit(Time overall, unsigned ms) { return std::min(overall, Clock::now() + std::chrono::milliseconds(ms)); }
static double us(Time start, Time end) { return std::chrono::duration<double, std::micro>(end - start).count(); }
static Digest sha256(const void *data, size_t size) {
  check(size <= std::numeric_limits<ULONG>::max(), "hash input too large");
  BCRYPT_ALG_HANDLE algorithm = nullptr; BCRYPT_HASH_HANDLE hash = nullptr;
  auto destroy = [&]() { if (hash) BCryptDestroyHash(hash); if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0); };
  try {
    check(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0, "SHA256 provider failed");
    ULONG bytes = 0, got = 0;
    check(BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&bytes), sizeof(bytes), &got, 0) >= 0, "SHA256 allocation query failed");
    std::vector<uint8_t> object(bytes);
    check(BCryptCreateHash(algorithm, &hash, object.data(), bytes, nullptr, 0, 0) >= 0, "SHA256 initialization failed");
    check(BCryptHashData(hash, reinterpret_cast<PUCHAR>(const_cast<void *>(data)), ULONG(size), 0) >= 0, "SHA256 update failed");
    Digest digest{}; check(BCryptFinishHash(hash, digest.data(), ULONG(digest.size()), 0) >= 0, "SHA256 finish failed");
    destroy(); return digest;
  } catch (...) { destroy(); throw; }
}
static std::string utf8(const std::wstring &s) {
  if (s.empty()) return {};
  const int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), int(s.size()), nullptr, 0, nullptr, nullptr);
  check(n > 0, "invalid UTF16 option"); std::string result(size_t(n), '\0');
  check(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), int(s.size()), result.data(), n, nullptr, nullptr) == n, "UTF8 conversion failed");
  return result;
}
static unsigned number(const std::wstring &s, const char *name, unsigned low, unsigned high) {
  check(!s.empty() && s.find_first_not_of(L"0123456789") == std::wstring::npos, std::string(name) + " requires decimal digits");
  const uint64_t n = std::stoull(s); check(n >= low && n <= high, std::string(name) + " out of range"); return unsigned(n);
}
static IN_ADDR private_ipv4(const std::wstring &value) {
  const std::string text = utf8(value); IN_ADDR address{};
  check(inet_pton(AF_INET, text.c_str(), &address) == 1, "only explicit private IPv4 literals are accepted");
  const uint32_t n = ntohl(address.s_addr); const unsigned a = n >> 24, b = (n >> 16) & 255;
  check(a == 10 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168), "IPv4 must be in10/8,172.16/12 or192.168/16");
  check((n & 255) != 0 && (n & 255) != 255, "network/broadcast-like endpoint rejected"); return address;
}
struct Options {
  std::wstring bind, peer, exe, report;
  unsigned port = 0, accept_ms = 10000, io_ms = 10000, deadline_ms = 80000, shutdown_ms = 5000;
  std::vector<std::wstring> args;
};
static Options parse(int argc, wchar_t **argv) {
  Options o; bool tail = false; std::vector<std::wstring> seen;
  for (int i = 1; i < argc; ++i) {
    const std::wstring key = argv[i];
    if (tail) { o.args.push_back(key); continue; }
    if (key == L"--") { tail = true; continue; }
    if (key == L"--help") {
      std::cout << "native_tcp_adapter.exe --bind-address PRIVATE_IPV4 --peer-address PRIVATE_IPV4\n"
                   " --port N --host-exe ABSOLUTE_HOST_EXE [--report FILE]\n"
                   " [--accept-ms 10000 --io-ms 10000 --deadline-ms 80000 --shutdown-ms 5000]\n"
                   " -- --serve HOST_ARGUMENTS...\n"
                   "One connection, one owned suspended/job child, up to64 replies.\n"; std::exit(0);
    }
    check(std::find(seen.begin(), seen.end(), key) == seen.end(), "duplicate adapter option"); seen.push_back(key);
    check(i + 1 < argc, "missing adapter option value"); const std::wstring value = argv[++i];
    if (key == L"--bind-address") o.bind = value;
    else if (key == L"--peer-address") o.peer = value;
    else if (key == L"--host-exe") o.exe = value;
    else if (key == L"--report") o.report = value;
    else if (key == L"--port") o.port = number(value, "port", 1, 65535);
    else if (key == L"--accept-ms") o.accept_ms = number(value, "accept-ms", 1, 60000);
    else if (key == L"--io-ms") o.io_ms = number(value, "io-ms", 1, 60000);
    else if (key == L"--deadline-ms") o.deadline_ms = number(value, "deadline-ms", 1000, 600000);
    else if (key == L"--shutdown-ms") o.shutdown_ms = number(value, "shutdown-ms", 1, 10000);
    else throw std::runtime_error("unknown adapter option " + utf8(key));
  }
  check(!o.bind.empty() && !o.peer.empty() && !o.exe.empty() && o.port && !o.args.empty(), "explicit bind/peer/port/host executable and forwarded host arguments required");
  check(o.args[0] == L"--serve" && std::count(o.args.begin(), o.args.end(), L"--serve") == 1 &&
        std::find(o.args.begin(), o.args.end(), L"--inspect") == o.args.end() && std::find(o.args.begin(), o.args.end(), L"--cohort") == o.args.end(),
        "adapter child must be the binary --serve host");
  check(o.accept_ms <= o.deadline_ms && o.io_ms <= o.deadline_ms, "stage deadlines cannot exceed overall deadline");
  private_ipv4(o.bind); private_ipv4(o.peer);
  check(o.exe.size() >= 3 && ((o.exe[1] == L':' && (o.exe[2] == L'\\' || o.exe[2] == L'/')) || o.exe.substr(0, 2) == L"\\\\"), "host-exe must be absolute");
  const DWORD attributes = GetFileAttributesW(o.exe.c_str());
  check(attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY), "host-exe does not name an existing file");
  return o;
}
static std::wstring command_quote(const std::wstring &argument) {
  // Windows CRT argv quoting; never passes through cmd.exe or PowerShell.
  std::wstring result = L"\""; size_t backslashes = 0;
  for (wchar_t c : argument) {
    if (c == L'\\') { ++backslashes; continue; }
    if (c == L'\"') { result.append(backslashes * 2 + 1, L'\\'); result += c; }
    else { result.append(backslashes, L'\\'); result += c; }
    backslashes = 0;
  }
  result.append(backslashes * 2, L'\\'); result += L'\"'; return result;
}
struct Pipe { Handle parent, child; };
static Pipe make_pipe(bool parent_reads, const wchar_t *label) {
  std::array<uint8_t, 16> nonce{};
  check(BCryptGenRandom(nullptr, nonce.data(), ULONG(nonce.size()), BCRYPT_USE_SYSTEM_PREFERRED_RNG) >= 0, "pipe nonce generation failed");
  const wchar_t digits[] = L"0123456789abcdef"; std::wstring suffix;
  for (uint8_t c : nonce) { suffix += digits[c >> 4]; suffix += digits[c & 15]; }
  const std::wstring name = L"\\\\.\\pipe\\halogen-native-H-" + std::to_wstring(GetCurrentProcessId()) + L"-" + label + L"-" + suffix;
  Handle parent(CreateNamedPipeW(name.c_str(), (parent_reads ? PIPE_ACCESS_INBOUND : PIPE_ACCESS_OUTBOUND) |
      FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
      1, 65536, 65536, 0, nullptr));
  check(parent.get() != INVALID_HANDLE_VALUE, "owned overlapped pipe creation failed");
  SECURITY_ATTRIBUTES security{sizeof(security), nullptr, TRUE};
  Handle child(CreateFileW(name.c_str(), parent_reads ? GENERIC_WRITE : GENERIC_READ, 0, &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
  check(child.get() != INVALID_HANDLE_VALUE, "owned child pipe endpoint failed");
  Handle connected(CreateEventW(nullptr, TRUE, FALSE, nullptr)); check(connected.get() != nullptr, "pipe connect event failed");
  OVERLAPPED operation{}; operation.hEvent = connected.get();
  const BOOL result = ConnectNamedPipe(parent.get(), &operation);
  check(result || GetLastError() == ERROR_PIPE_CONNECTED, "child pipe did not connect synchronously");
  return {std::move(parent), std::move(child)};
}
class Child {
  Handle job_, process_, input_, output_;
public:
  explicit Child(const Options &o) {
    job_.reset(CreateJobObjectW(nullptr, nullptr)); check(job_.get() != nullptr, "owned Windows job creation failed");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    check(SetInformationJobObject(job_.get(), JobObjectExtendedLimitInformation, &limits, sizeof(limits)), "owned job limits failed");
    Pipe stdin_pipe = make_pipe(false, L"stdin"), stdout_pipe = make_pipe(true, L"stdout");
    HANDLE inherited_stderr = INVALID_HANDLE_VALUE;
    check(DuplicateHandle(GetCurrentProcess(), GetStdHandle(STD_ERROR_HANDLE), GetCurrentProcess(), &inherited_stderr, 0, TRUE, DUPLICATE_SAME_ACCESS), "child stderr inheritance failed");
    Handle stderr_handle(inherited_stderr);
    std::array<HANDLE, 3> inherit{stdin_pipe.child.get(), stdout_pipe.child.get(), stderr_handle.get()};
    SIZE_T attribute_bytes = 0; InitializeProcThreadAttributeList(nullptr, 2, 0, &attribute_bytes);
    check(attribute_bytes > 0, "restricted child handle-list sizing failed");
    std::vector<uint8_t> attribute_memory(attribute_bytes);
    auto *attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attribute_memory.data());
    check(InitializeProcThreadAttributeList(attributes, 2, 0, &attribute_bytes), "restricted child handle-list initialization failed");
    PROCESS_INFORMATION information{};
    try {
      check(UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherit.data(), sizeof(inherit), nullptr, nullptr), "restricted child handle list failed");
      // Windows10+ performs owned-job assignment atomically with creation.
      // No unassigned suspended child exists if an explicit later Assign call
      // were to fail; there is deliberately no unsafe compatibility fallback.
      HANDLE owned_job = job_.get();
      check(UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_JOB_LIST,
          &owned_job, sizeof(owned_job), nullptr, nullptr), "atomic owned child job attribute failed");
      STARTUPINFOEXW startup{}; startup.StartupInfo.cb = sizeof(startup); startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
      startup.StartupInfo.hStdInput = inherit[0]; startup.StartupInfo.hStdOutput = inherit[1]; startup.StartupInfo.hStdError = inherit[2]; startup.lpAttributeList = attributes;
      std::wstring command = command_quote(o.exe);
      for (const auto &argument : o.args) { command += L' '; command += command_quote(argument); }
      check(CreateProcessW(o.exe.c_str(), command.data(), nullptr, nullptr, TRUE,
          CREATE_SUSPENDED | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT, nullptr, nullptr, &startup.StartupInfo, &information), "owned suspended native host creation failed");
      DeleteProcThreadAttributeList(attributes);
    } catch (...) { DeleteProcThreadAttributeList(attributes); throw; }
    process_.reset(information.hProcess); Handle main_thread(information.hThread);
    // CreateProcess already established exclusive job ownership before resume.
    check(ResumeThread(main_thread.get()) == 1, "native child did not resume from exactly one owned suspension");
    input_ = std::move(stdin_pipe.parent); output_ = std::move(stdout_pipe.parent);
    // Child-end copies are closed here; EOF now follows only the owned endpoints.
  }
  HANDLE process() const { return process_.get(); }
  HANDLE input() const { return input_.get(); }
  HANDLE output() const { return output_.get(); }
  bool alive() const { DWORD code = 0; return GetExitCodeProcess(process_.get(), &code) && code == STILL_ACTIVE; }
  void kill() { if (job_.get() != INVALID_HANDLE_VALUE && job_.get() != nullptr) TerminateJobObject(job_.get(), 91); }
  DWORD finish(Time limit) {
    input_.reset(); // Native host remains resident until this owner-close point.
    const DWORD state = WaitForSingleObject(process_.get(), remaining(limit));
    if (state != WAIT_OBJECT_0) { kill(); throw std::runtime_error("native child did not exit within owned close deadline"); }
    DWORD code = 0; check(GetExitCodeProcess(process_.get(), &code), "native child exit status failed"); output_.reset(); return code;
  }
};

static void socket_ready(SOCKET socket, bool write, Time limit, HANDLE child = nullptr) {
  check(!child || WaitForSingleObject(child, 0) == WAIT_TIMEOUT, "native child exited while TCP endpoint still owned");
  fd_set reads, writes, errors; FD_ZERO(&reads); FD_ZERO(&writes); FD_ZERO(&errors);
  FD_SET(socket, write ? &writes : &reads); FD_SET(socket, &errors);
  const DWORD ms = remaining(limit); timeval timeout{long(ms / 1000), long(ms % 1000) * 1000};
  const int state = select(0, &reads, &writes, &errors, &timeout);
  check(state > 0 && !FD_ISSET(socket, &errors), state == 0 ? "TCP stage deadline expired" : "TCP select failure");
  check(!child || WaitForSingleObject(child, 0) == WAIT_TIMEOUT, "native child exited before TCP owner-close boundary");
}
static bool socket_read(SOCKET socket, void *data, size_t bytes, bool empty_eof, Time limit, HANDLE child = nullptr) {
  auto *target = static_cast<uint8_t *>(data); size_t done = 0;
  while (done < bytes) {
    socket_ready(socket, false, limit, child);
    const int n = recv(socket, reinterpret_cast<char *>(target + done), int(bytes - done), 0);
    if (n == SOCKET_ERROR && WSAGetLastError() == WSAEWOULDBLOCK) continue;
    if (n == 0 && empty_eof && done == 0) return false;
    check(n > 0, n == 0 ? "partial TCP frame EOF" : "TCP recv failure"); done += size_t(n);
  }
  remaining(limit); return true;
}
static void socket_write(SOCKET socket, const void *data, size_t bytes, Time limit, HANDLE child) {
  const auto *source = static_cast<const uint8_t *>(data); size_t done = 0;
  while (done < bytes) {
    socket_ready(socket, true, limit, child);
    const int n = send(socket, reinterpret_cast<const char *>(source + done), int(bytes - done), 0);
    if (n == SOCKET_ERROR && WSAGetLastError() == WSAEWOULDBLOCK) continue;
    check(n > 0, "TCP send failure"); done += size_t(n);
  }
  remaining(limit);
}
static DWORD pipe_piece(Child &child, HANDLE pipe, void *data, DWORD size, bool write, Time limit) {
  Handle event(CreateEventW(nullptr, TRUE, FALSE, nullptr)); check(event.get() != nullptr, "pipe I/O event creation failed");
  OVERLAPPED operation{}; operation.hEvent = event.get(); DWORD transferred = 0;
  const BOOL immediate = write ? WriteFile(pipe, data, size, &transferred, &operation) : ReadFile(pipe, data, size, &transferred, &operation);
  if (immediate) return transferred;
  check(GetLastError() == ERROR_IO_PENDING, "native host pipe I/O failed");
  const std::array<HANDLE, 2> handles{event.get(), child.process()};
  DWORD wait = WAIT_FAILED;
  try { wait = WaitForMultipleObjects(DWORD(handles.size()), handles.data(), FALSE, remaining(limit)); }
  catch (...) { wait = WAIT_TIMEOUT; }
  if (wait == WAIT_OBJECT_0) {
    check(GetOverlappedResult(pipe, &operation, &transferred, FALSE), "native pipe completion failed"); return transferred;
  }
  // Never destroy a pending OVERLAPPED/buffer. Cancellation is separately bounded.
  CancelIoEx(pipe, &operation);
  if (WaitForSingleObject(event.get(), 1000) != WAIT_OBJECT_0) {
    child.kill();
    if (WaitForSingleObject(event.get(), 1000) != WAIT_OBJECT_0) {
      // Terminal fail-stop of this adapter also closes its kill-on-close job.
      TerminateProcess(GetCurrentProcess(), 96); std::abort();
    }
  }
  GetOverlappedResult(pipe, &operation, &transferred, FALSE);
  throw std::runtime_error(wait == WAIT_TIMEOUT ? "native pipe stage deadline expired" : "native child exited during pending pipe I/O");
}
static void pipe_read(Child &child, void *data, size_t bytes, Time limit) {
  auto *target = static_cast<uint8_t *>(data); size_t done = 0;
  while (done < bytes) { const DWORD n = pipe_piece(child, child.output(), target + done, DWORD(bytes - done), false, limit); check(n != 0, "native host partial frame EOF"); done += n; }
  remaining(limit);
}
static void pipe_write(Child &child, const void *data, size_t bytes, Time limit) {
  const auto *source = static_cast<const uint8_t *>(data); size_t done = 0;
  while (done < bytes) { const DWORD n = pipe_piece(child, child.input(), const_cast<uint8_t *>(source + done), DWORD(bytes - done), true, limit); check(n != 0, "native host pipe write made no progress"); done += n; }
  remaining(limit);
}
struct Packet { hgnh_frame frame{}; std::vector<uint8_t> payload; };
static void frame_header(const hgnh_frame &frame, unsigned kind, uint64_t sequence, size_t bytes) {
  check(!std::memcmp(frame.magic, HGNH_FRAME_MAGIC, 8) && frame.kind == kind && frame.sequence == sequence && frame.payload_bytes == bytes,
        "fixed frame header/kind/sequence/size admission failed");
}
static void frame_digest(const Packet &packet) {
  const auto digest = sha256(packet.payload.data(), packet.payload.size());
  check(!std::memcmp(digest.data(), packet.frame.payload_sha256, digest.size()), "framed payload SHA256 mismatch");
}
static bool tcp_packet(SOCKET socket, Packet &packet, unsigned kind, uint64_t sequence, size_t bytes, bool eof, Time limit, HANDLE child) {
  if (!socket_read(socket, &packet.frame, sizeof(packet.frame), eof, limit, child)) return false;
  frame_header(packet.frame, kind, sequence, bytes); packet.payload.resize(bytes);
  socket_read(socket, packet.payload.data(), packet.payload.size(), false, limit, child); frame_digest(packet); return true;
}
static Packet native_packet(Child &child, unsigned kind, uint64_t sequence, size_t bytes, Time limit) {
  Packet packet; pipe_read(child, &packet.frame, sizeof(packet.frame), limit);
  frame_header(packet.frame, kind, sequence, bytes); packet.payload.resize(bytes);
  pipe_read(child, packet.payload.data(), packet.payload.size(), limit); frame_digest(packet); return packet;
}
static std::vector<uint8_t> whole_packet(const Packet &packet) {
  std::vector<uint8_t> bytes(sizeof(packet.frame) + packet.payload.size());
  std::memcpy(bytes.data(), &packet.frame, sizeof(packet.frame));
  std::memcpy(bytes.data() + sizeof(packet.frame), packet.payload.data(), packet.payload.size()); return bytes;
}
static void request_contract(const Packet &packet, uint64_t sequence) {
  hgnh_header header{}; std::memcpy(&header, packet.payload.data(), sizeof(header));
  check(!std::memcmp(header.magic, HGNH_REQUEST_MAGIC, 8) && header.version == HGNH_VERSION && header.body_bytes == HGNH_H_BYTES &&
        header.sequence == int32_t(sequence) && header.count == 1 && header.reserved == 0 && header.wire == HGNH_WIRE_D,
        "request packet contract mismatch");
  // Full identity/input/request bindings are admitted by the pinned native host.
}
static void response_contract(const Packet &reply, const Packet &request) {
  check(!std::memcmp(reply.payload.data(), HGNH_RESPONSE_MAGIC, 8) &&
        !std::memcmp(reply.payload.data() + 8, request.payload.data() + 8, HGNH_HEADER_BYTES - 8), "native reply did not echo request header exactly");
  const auto digest = sha256(reply.payload.data(), HGNH_HEADER_BYTES + HGNH_H_BYTES);
  check(!std::memcmp(digest.data(), reply.payload.data() + HGNH_HEADER_BYTES + HGNH_H_BYTES, 32), "native reply inner SHA mismatch");
  for (size_t i = HGNH_HEADER_BYTES; i < HGNH_HEADER_BYTES + HGNH_H_BYTES; i += 2)
    check(((reply.payload[i] | uint16_t(reply.payload[i + 1]) << 8) & 0x7F80U) != 0x7F80U, "native reply contains nonfinite BF16");
}
struct Sample { unsigned sequence; double total, to_native, from_native, to_tcp; };
static std::string run(const Options &o) {
  const auto started = Clock::now(); const auto overall = started + std::chrono::milliseconds(o.deadline_ms);
  Winsock winsock; Socket listener(socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)); check(listener.get() != INVALID_SOCKET, "private TCP socket creation failed");
  BOOL exclusive = TRUE; check(setsockopt(listener.get(), SOL_SOCKET, SO_EXCLUSIVEADDRUSE, reinterpret_cast<const char *>(&exclusive), sizeof(exclusive)) == 0, "exclusive listen socket failed");
  u_long nonblocking = 1; check(ioctlsocket(listener.get(), FIONBIO, &nonblocking) == 0, "listen nonblocking mode failed");
  sockaddr_in local{}; local.sin_family = AF_INET; local.sin_port = htons(uint16_t(o.port)); local.sin_addr = private_ipv4(o.bind);
  check(bind(listener.get(), reinterpret_cast<const sockaddr *>(&local), sizeof(local)) == 0 && listen(listener.get(), 1) == 0, "private fixed-address bind/listen failed");
  std::cerr << "{\"event\":\"private-native-listener-ready\",\"address\":\"" << utf8(o.bind) << "\",\"port\":" << o.port << "}\n";
  socket_ready(listener.get(), false, stage_limit(overall, o.accept_ms));
  sockaddr_in remote{}; int remote_bytes = sizeof(remote); Socket peer(accept(listener.get(), reinterpret_cast<sockaddr *>(&remote), &remote_bytes));
  check(peer.get() != INVALID_SOCKET && remote.sin_family == AF_INET && remote.sin_addr.s_addr == private_ipv4(o.peer).s_addr, "accepted peer differs from pinned private IPv4");
  listener.close(); // This owned cohort admits exactly one connection.
  check(ioctlsocket(peer.get(), FIONBIO, &nonblocking) == 0, "peer nonblocking mode failed");
  BOOL nodelay = TRUE; check(setsockopt(peer.get(), IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char *>(&nodelay), sizeof(nodelay)) == 0, "TCP_NODELAY failed");
  Child child(o); const auto child_created = Clock::now();
  Packet hello; tcp_packet(peer.get(), hello, HGNH_HELLO, 0, HGNH_HELLO_BYTES, false, stage_limit(overall, o.io_ms), child.process());
  hgnh_hello handshake{}; std::memcpy(&handshake, hello.payload.data(), sizeof(handshake));
  check(!std::memcmp(handshake.magic, HGNH_HELLO_MAGIC, 8) && handshake.version == HGNH_VERSION && handshake.max_calls == HGNH_MAX_CALLS &&
      handshake.process_id && handshake.h_bytes == HGNH_H_BYTES && handshake.wire == HGNH_WIRE_D, "HELLO packet contract mismatch");
  auto bytes = whole_packet(hello); pipe_write(child, bytes.data(), bytes.size(), stage_limit(overall, o.io_ms));
  Packet ready = native_packet(child, HGNH_READY, 0, HGNH_HELLO_BYTES, stage_limit(overall, o.io_ms));
  check(!std::memcmp(ready.payload.data(), HGNH_READY_MAGIC, 8) && !std::memcmp(ready.payload.data() + 8, hello.payload.data() + 8, HGNH_HELLO_BYTES - 8), "READY did not echo complete HELLO pins");
  bytes = whole_packet(ready); socket_write(peer.get(), bytes.data(), bytes.size(), stage_limit(overall, o.io_ms), child.process());
  std::vector<Sample> samples; bool owner_closed = false;
  for (unsigned sequence = 0; sequence < HGNH_MAX_CALLS; ++sequence) {
    const auto start = Clock::now(); Packet request;
    if (!tcp_packet(peer.get(), request, HGNH_REQUEST, sequence, HGNH_REQUEST_BYTES, true, stage_limit(overall, o.io_ms), child.process())) {
      owner_closed = true; break; // Clean only with zero bytes of a next frame.
    }
    request_contract(request, sequence); bytes = whole_packet(request); const auto admitted = Clock::now();
    pipe_write(child, bytes.data(), bytes.size(), stage_limit(overall, o.io_ms)); const auto written = Clock::now();
    Packet response = native_packet(child, HGNH_RESPONSE, sequence, HGNH_RESPONSE_BYTES, stage_limit(overall, o.io_ms));
    response_contract(response, request); check(child.alive(), "native host exited before cohort owner closed");
    bytes = whole_packet(response); const auto returned = Clock::now();
    socket_write(peer.get(), bytes.data(), bytes.size(), stage_limit(overall, o.io_ms), child.process()); const auto sent = Clock::now();
    samples.push_back({sequence, us(start, sent), us(admitted, written), us(written, returned), us(returned, sent)});
  }
  if (!owner_closed) {
    // Reply63 has completed. Keep both endpoints/host resident through full head.
    uint8_t extra = 0;
    check(!socket_read(peer.get(), &extra, 1, true, overall, child.process()), "trailing byte/request after finite64 replies");
  }
  const DWORD child_exit = child.finish(stage_limit(overall, o.shutdown_ms));
  check(child_exit == 0, "native host failed during clean owner close; short cohorts require host-short-cohort.patch");
  std::ostringstream report;
  report << "{\"status\":\"owned-cohort-closed\",\"completed_calls\":" << samples.size() << ",\"max_calls\":64,\"native_children\":1,\"per_request_processes\":0,\"tcp_nodelay\":true,\"child_exit\":" << child_exit
      << ",\"accept_and_child_creation_us\":" << us(started, child_created) << ",\"owned_window_us\":" << us(started, Clock::now()) << ",\"samples\":[";
  for (size_t i = 0; i < samples.size(); ++i) {
    if (i) report << ','; const auto &s = samples[i];
    report << "{\"sequence\":" << s.sequence << ",\"receive_validate_roundtrip_reply_us\":" << s.total << ",\"pipe_request_write_us\":" << s.to_native
        << ",\"pipe_response_read_validate_us\":" << s.from_native << ",\"tcp_response_write_us\":" << s.to_tcp << '}';
  }
  report << "]}"; return report.str();
}
int wmain(int argc, wchar_t **argv) {
  Options options;
  try {
    options = parse(argc, argv); const auto report = run(options);
    if (!options.report.empty()) { std::ofstream file(options.report.c_str(), std::ios::binary | std::ios::trunc); check(bool(file) && bool(file << report << '\n'), "adapter report write failed"); }
    std::cerr << report << '\n'; return 0;
  } catch (const std::exception &error) {
    // RAII closes only this adapter's sockets/job/pipes. No error wire frames.
    std::cerr << "{\"status\":\"adapter-failed-latched\",\"error\":\"";
    for (const char c : std::string(error.what())) { if (c == '\\' || c == '"') std::cerr << '\\'; std::cerr << c; }
    std::cerr << "\"}\n"; return 1;
  }
}
