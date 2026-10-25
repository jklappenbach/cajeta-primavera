#!/usr/bin/env python3
"""svc.py — the one-shot service measurements the bench harness runs as
external commands (dev.cajeta.bench ExternalBenchmark: one command per trial).
Each prints `key=value` tokens on one stdout line that the harness reads; the
harness's own wall-clock time of the command also covers this helper's start
and the server's teardown, so the figure on the row is the one printed here.

  svc.py launch --dir D --port P --log F --pids F [--settle S]
                [--load SECONDS:CONNECTIONS] [--timeout T] -- argv...
      exec argv in D (stdout and stderr to F), poll GET /health until 200,
      then optionally sleep S seconds (idle RSS) or drive the contract's
      POST /users with oha (`-w`, so in-flight requests at the deadline are
      not errors) for SECONDS at CONNECTIONS (loaded RSS), read the server's resident set, SIGKILL it and
      reap it. Prints
        first200_ns=<exec to first 200> rss_kb=<VmRSS> hwm_kb=<VmHWM> pid=<pid>
      plus, with --load, oha's req/s and error count. The clock starts
      immediately before the fork. RSS is the server process plus any
      children it started (each server here runs as one process).

  svc.py wait --port P [--pid N] [--log F] [--timeout T]
      poll GET /health until 200 (a server the harness started itself, as
      pid N; its death fails the wait at once, with the log's tail).

  svc.py free --port P
      exit 0 when 127.0.0.1:P can be bound.

  svc.py build --dir D --clean CMD --build CMD --log F [--timeout T]
      run CMD-clean (untimed), then time CMD-build (sh -c, in D). Prints
        build_ns=<clean build to a runnable artifact>

Exit status: 0 on success; 1 with a message on stderr otherwise.
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time

POLL_S = 0.001
BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def health_ok(port):
    """True when GET /health on 127.0.0.1:port answers 200."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as s:
            s.sendall(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            data = b""
            while b"\r\n" not in data:
                chunk = s.recv(256)
                if not chunk:
                    break
                data += chunk
            return data.startswith(b"HTTP/1.1 200") or data.startswith(b"HTTP/1.0 200")
    except OSError:
        return False


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def status_kb(pid, key):
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith(key + ":"):
                return int(line.split()[1])
    except OSError:
        pass
    return -1


def tree(pid):
    """pid and every descendant, from /proc/<pid>/task/*/children."""
    out, todo = [], [pid]
    while todo:
        p = todo.pop()
        out.append(p)
        try:
            for t in os.listdir(f"/proc/{p}/task"):
                with open(f"/proc/{p}/task/{t}/children") as f:
                    todo.extend(int(c) for c in f.read().split())
        except OSError:
            pass
    return out


def rss(pid):
    ps = tree(pid)
    return (sum(max(0, status_kb(p, "VmRSS")) for p in ps),
            sum(max(0, status_kb(p, "VmHWM")) for p in ps))


def oha_path():
    return os.environ.get("OHA") or os.path.expanduser("~/.cargo/bin/oha")


def oha_register(port, seconds, conns):
    """oha driving the contract's POST /users for `seconds` at `conns` connections."""
    body = open(os.path.join(BENCH, "contract", "register.json")).read()
    return [oha_path(), "-z", f"{seconds}s", "-c", str(conns), "-w", "--no-tui",
            "--output-format", "json", "-m", "POST",
            "-H", "Authorization: Bearer bench-7f3c9a1e", "-H", "Content-Type: application/json",
            "-d", body, f"http://127.0.0.1:{port}/users"]


def die(msg):
    print(f"svc: {msg}", file=sys.stderr)
    sys.exit(1)


def kill(proc):
    try:
        os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def tail(path, n=5):
    try:
        lines = open(path, errors="replace").read().splitlines()
        return " | ".join(lines[-n:])
    except OSError:
        return ""


def cmd_launch(a, argv):
    if not port_free(a.port):
        die(f"port {a.port} is in use")
    log = open(a.log, "ab")
    t0 = time.perf_counter_ns()
    proc = subprocess.Popen(argv, cwd=a.dir, stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, close_fds=True)
    if a.pids:
        with open(a.pids, "a") as f:
            f.write(f"{proc.pid} {os.path.basename(argv[0])}\n")
    deadline = time.monotonic() + a.timeout
    while True:
        if health_ok(a.port):
            t1 = time.perf_counter_ns()
            break
        if proc.poll() is not None:
            die(f"{argv[0]} exited {proc.returncode} before answering: {tail(a.log)}")
        if time.monotonic() > deadline:
            kill(proc)
            die(f"no 200 from /health within {a.timeout}s: {tail(a.log)}")
        time.sleep(POLL_S)
    extra = ""
    try:
        if a.settle > 0:
            time.sleep(a.settle)
        if a.load:
            seconds, conns = a.load.split(":")
            oha = subprocess.run(oha_register(a.port, seconds, conns), capture_output=True, text=True)
            if oha.returncode != 0:
                die(f"oha exited {oha.returncode}: {oha.stderr.strip()[:300]}")
            j = json.loads(oha.stdout)
            errors = sum(j.get("errorDistribution", {}).values())
            codes = j.get("statusCodeDistribution", {})
            bad = sum(v for k, v in codes.items() if k != "201")
            extra = (f" rps={j['summary']['requestsPerSec']:.1f} requests={sum(codes.values())}"
                     f" errors={errors + bad}")
            if errors + bad:
                die(f"load had {errors} errors and {bad} answers other than 201: {codes} {j.get('errorDistribution')}")
        if proc.poll() is not None:
            die(f"{argv[0]} died after start: {tail(a.log)}")
        r, h = rss(proc.pid)
    finally:
        kill(proc)
    print(f"first200_ns={t1 - t0} rss_kb={r} hwm_kb={h} pid={proc.pid}{extra}", flush=True)


def alive(pid):
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("State:"):
                return "Z" not in line.split()[1]
    except OSError:
        return False
    return True


def cmd_wait(a, argv):
    deadline = time.monotonic() + a.timeout
    while not health_ok(a.port):
        if a.pid and not alive(a.pid):
            die(f"pid {a.pid} exited before 127.0.0.1:{a.port}/health answered: {tail(a.log)}")
        if time.monotonic() > deadline:
            die(f"no 200 from 127.0.0.1:{a.port}/health within {a.timeout}s")
        time.sleep(POLL_S)
    print("up", flush=True)


def cmd_free(a, argv):
    """Exit 0 when the port can be bound on 127.0.0.1."""
    sys.exit(0 if port_free(a.port) else 1)


def cmd_build(a, argv):
    with open(a.log, "ab") as log:
        if a.clean and a.clean != "-":
            c = subprocess.run(["sh", "-c", a.clean], cwd=a.dir, stdout=log, stderr=subprocess.STDOUT)
            if c.returncode != 0:
                die(f"clean exited {c.returncode}: {tail(a.log)}")
        t0 = time.perf_counter_ns()
        try:
            b = subprocess.run(["sh", "-c", a.build], cwd=a.dir, stdout=log, stderr=subprocess.STDOUT,
                               timeout=a.timeout)
        except subprocess.TimeoutExpired:
            die(f"build passed {a.timeout}s")
        t1 = time.perf_counter_ns()
    if b.returncode != 0:
        die(f"build exited {b.returncode}: {tail(a.log)}")
    print(f"build_ns={t1 - t0}", flush=True)


def main():
    args = sys.argv[1:]
    argv = []
    if "--" in args:
        i = args.index("--")
        args, argv = args[:i], args[i + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["launch", "wait", "build", "free"])
    ap.add_argument("--dir", default=".")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--log", default=os.devnull)
    ap.add_argument("--pids", default="")
    ap.add_argument("--pid", type=int, default=0)
    ap.add_argument("--settle", type=float, default=0.0)
    ap.add_argument("--load", default="")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--clean", default="")
    ap.add_argument("--build", default="")
    a = ap.parse_args(args)
    if a.mode == "launch" and not argv:
        die("launch needs -- argv")
    {"launch": cmd_launch, "wait": cmd_wait, "build": cmd_build, "free": cmd_free}[a.mode](a, argv)


if __name__ == "__main__":
    main()
