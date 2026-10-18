"""Finite CPU-only protocol/cleanup check for the Linux H bridge.

Runs a synthetic Python child and a loopback Python endpoint, never an engine,
XRT, model or device. These fixtures do not measure native transport latency.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import struct
import time
import re
import signal

import halogen_mtp_h_wire as wire

CASES = {
    "complete64": (64, True, "hold"),
    "complete56": (56, True, "hold"),
    "truncated-reply": (1, False, "truncate"),
    "idle-remote-death": (0, False, "close"),
    "after-final-remote-death": (64, False, "close"),
    "idle-unsolicited": (0, False, "unsolicited"),
    "after-final-unsolicited": (64, False, "unsolicited"),
    "truncated-local-request": (0, False, "local-truncate"),
    "stalled-local-header": (0, False, "header-stall"),
    "stalled-local-body": (0, False, "body-stall"),
}


def exact(sock, count):
    out = bytearray()
    while len(out) < count:
        part = sock.recv(count - len(out))
        if not part:
            raise EOFError("truncated synthetic stream")
        out.extend(part)
    return bytes(out)


def receive(sock, kind, seq):
    return wire.decode_frame(exact(sock, wire.FRAME_BYTES + wire.FRAME_SIZES[kind]),
                             expected_kind=kind, expected_sequence=seq)


def child(case):
    call_count, _, action = CASES[case]
    sock = socket.socket(fileno=int(os.environ["HALOGEN_MTP_H_FD"]))
    sock.setblocking(True)
    sock.settimeout(5)
    peer_pid, peer_uid, peer_gid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if (peer_pid, peer_uid, peer_gid) != (int(os.environ["HALOGEN_MTP_H_PEER_PID"]), os.geteuid(), os.getegid()):
        raise ValueError("inherited peer identity differs")
    s = wire.HSession(os.getpid(), b"n" * 16, b"e" * 16, b"m" * 32, b"g" * 32)
    hello = wire.encode_hello(s)
    sock.sendall(wire.encode_frame(wire.HELLO, 0, hello))
    wire.validate_ready(hello, receive(sock, wire.READY, 0), expected_session=s)
    if action == "local-truncate":
        # A zero-exit child cannot turn an incomplete next header into success.
        # Ignore cleanup TERM during the short close/exit race, then terminate
        # ourselves immediately; this deliberately exercises exit0 + partial.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        sock.sendall(b"HGNHFRM")
        sock.close()
        os._exit(0)
    if action in ("header-stall", "body-stall"):
        identity = wire.HIdentity(0, 0, 0, 100, 0, s.process_id, s.run_nonce,
                                  s.epoch, 4096, s.model_binding, s.graph_binding)
        request = wire.encode_request(identity, b"\x80\x3f" * (wire.H_BYTES // 2))
        frame = wire.encode_frame(wire.REQUEST, 0, request)
        sock.sendall(frame[:7 if action == "header-stall" else wire.FRAME_BYTES + 4])
        time.sleep(4)
        print("UNEXPECTED_PARTIAL_WINDOW_SURVIVED", flush=True)
        sock.close()
        return
    for seq in range(call_count):
        i = wire.HIdentity(seq, seq, seq % 2, seq + 100, seq, s.process_id,
                           s.run_nonce, s.epoch, 4096, s.model_binding, s.graph_binding)
        payload = (0x3F80 + seq).to_bytes(2, "little") * (wire.H_BYTES // 2)
        request = wire.encode_request(i, payload)
        sock.sendall(wire.encode_frame(wire.REQUEST, seq, request))
        output = wire.validate_response(request, receive(sock, wire.RESPONSE, seq), expected_identity=i)
        if output != payload:
            raise ValueError("synthetic echoed output differs")
    if action in ("close", "unsolicited"):
        # The guardian must detect remote failure and terminate this owned
        # child before it voluntarily exits successfully. An old bridge that
        # only waits for the local child would incorrectly let this survive.
        time.sleep(4)
        print("UNEXPECTED_REMOTE_WINDOW_SURVIVED", flush=True)
        sock.close()
        return
    # Simulate work after publication for both shorter and full cohorts.
    time.sleep(.05)
    sock.setblocking(False)
    try:
        if sock.recv(1, socket.MSG_PEEK) == b"":
            raise ValueError("guardian closed before full owned window completed")
        raise ValueError("unexpected post-budget data")
    except BlockingIOError:
        pass
    sock.close()


def probe(bridge: Path, case: str):
    call_count, should_succeed, action = CASES[case]
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(8)
    port = listener.getsockname()[1]
    errors, counts, expected_resets = [], [], []

    def endpoint():
        try:
            with listener.accept()[0] as peer:
                peer.settimeout(5)
                hello = receive(peer, wire.HELLO, 0)
                session = wire.decode_hello(hello)
                peer.sendall(wire.encode_frame(wire.READY, 0, wire.make_ready(hello)))
                for seq in range(call_count):
                    request = receive(peer, wire.REQUEST, seq)
                    fields = wire.decode_request(request, expected_session=session)
                    response = wire.make_response(request, fields.h_norm, expected_session=session)
                    frame = wire.encode_frame(wire.RESPONSE, seq, response)
                    if action == "truncate":
                        peer.sendall(frame[:wire.FRAME_BYTES + 4])
                        counts.append(1)
                        return
                    peer.sendall(frame)
                counts.append(call_count)
                if action == "close":
                    return
                if action == "unsolicited":
                    peer.sendall(b"!")
                try:
                    tail = peer.recv(1)
                except ConnectionResetError:
                    # Closing a TCP peer with the deliberately injected byte
                    # unread may send RST. Accept it only after all expected
                    # frames completed and that unsolicited send succeeded.
                    if action != "unsolicited" or counts != [call_count]:
                        raise
                    expected_resets.append(True)
                    tail = b""
                if tail != b"":
                    raise ValueError("unexpected post-budget transport data")
        except BaseException as e:
            errors.append(type(e).__name__ + ": " + str(e))

    worker = threading.Thread(target=endpoint, daemon=False)
    worker.start()
    try:
        env = dict(os.environ, HALOGEN_MTP_H_NATIVE="replace64-v1")
        command = [str(bridge), "--run", "127.0.0.1", str(port), "10000", "--",
                   sys.executable, "-B", str(Path(__file__).resolve()), "--child", "--case", case]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
    finally:
        listener.close()
        worker.join(8)
    if worker.is_alive():
        raise RuntimeError("CPU endpoint cleanup incomplete")
    if errors or counts != [call_count]:
        raise RuntimeError(str((errors, counts)))
    if (result.returncode == 0) != should_succeed:
        raise ValueError(f"Bridge exit {result.returncode} disagrees with {case}: {result.stderr}")
    summaries = re.findall(r"H bridge terminal: [^\n]*child_terminal=(\d+) child_exit=(-?\d+) cleanup_ok=(\d+)", result.stderr)
    if not summaries:
        raise RuntimeError("Missing bridge terminal receipt")
    child_terminal, child_exit, cleanup_ok = map(int, summaries[-1])
    if child_terminal != 1 or cleanup_ok != 1:
        raise RuntimeError("Bridge did not prove child cleanup")
    if should_succeed and child_exit != 0:
        raise RuntimeError("Complete cohort did not prove successful child exit")
    if action in ("close", "unsolicited") and (child_exit == 0 or "UNEXPECTED_REMOTE_WINDOW_SURVIVED" in result.stdout):
        raise RuntimeError("Remote failure was not detected while the owned child remained live")
    if action == "local-truncate" and child_exit != 0:
        raise RuntimeError("Partial local frame fixture did not end with its intended zero exit")
    if action in ("header-stall", "body-stall") and (child_exit == 0 or "UNEXPECTED_PARTIAL_WINDOW_SURVIVED" in result.stdout):
        raise RuntimeError("Partial request was not bounded while the owned child remained live")
    return dict(case=case, passed=True,
                exchanges=counts[0], bridge_exit_code=result.returncode,
                endpoint_joined=True, child_terminal_proven=True,
                expected_unsolicited_reset_observed=bool(expected_resets),
                child_exit_code=child_exit, delayed_final_window_preserved=should_succeed,
                remote_failure_while_child_live_proven=action in ("close", "unsolicited"),
                partial_local_frame_rejected=action in ("local-truncate", "header-stall", "body-stall"),
                partial_request_deadline_enforced=action in ("header-stall", "body-stall"),
                NPU_executed=False, engine_executed=False,
                cross_Windows_WSL_transport_tested=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--child", action="store_true")
    p.add_argument("--case", choices=CASES)
    p.add_argument("--bridge", type=Path)
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    if a.child:
        if not a.case:
            p.error("--child requires --case")
        child(a.case)
        return
    if not a.bridge or not a.report or sys.platform != "linux":
        p.error("Linux --bridge and --report required")
    bridge = a.bridge.resolve(strict=True)
    rows = []
    for case in [a.case] if a.case else CASES:
        try:
            rows.append(probe(bridge, case))
        except Exception as error:
            rows.append(dict(case=case, passed=False, error=type(error).__name__ + ": " + str(error)))
    result = dict(passed=all(row["passed"] for row in rows), CPU_protocol_fixture_only=True,
                  performance_measured=False, cases=rows)
    with a.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
