"""Unprivileged isolation backend: Landlock LSM + seccomp-BPF + rlimits.

This backend exists because a runner host may not expose a container runtime
(no Docker, no root).  It provides kernel-enforced isolation without any
privilege: Landlock confines the filesystem, TCP and signals; seccomp removes
process creation, networking and namespaces; rlimits cap CPU, address space,
file size and descriptors; the parent kills the whole process group and then
audits ``/proc`` for stragglers.

The admission contract matches the Docker backend: nothing runs until the host
self-test proves that every abuse vector is denied, and a failed check is a
refusal (``NotReady``), never a degraded run.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import sandbox_kernel
from .policy import CLEANUP_SECONDS, NotReady

PROFILE = "landlock-seccomp-v1"
LAUNCHER = Path(__file__).with_name("sandbox_launcher.py")
ATTESTATION_TTL_SECONDS = 3600.0

# Probe executed through the real pipeline. Every entry must be denied.
PROBE_SOURCE = '''
def solve(payload):
    import os, socket, sys
    path = payload["outside"]
    results = {}
    checks = {
        "read_outside": lambda: open(path, "rb").read(),
        "write_outside": lambda: open("/usr/lib/.mentor-probe", "wb").write(b"x"),
        "write_state": lambda: open("/home/agent/.hermes/.env", "ab").write(b"x"),
        "tcp_connect": lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", 22)),
        "fork": lambda: os.fork(),
        "exec": lambda: os.execv("/bin/sh", ["sh"]),
        "signal_outside": lambda: os.kill(1, 0),
    }
    for name, action in checks.items():
        try:
            action()
        except BaseException as exc:
            results[name] = type(exc).__name__
        else:
            results[name] = "ALLOWED"
    return results
'''


def _kill_group(process: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        process.kill()


def stray_processes(marker: str) -> list[int]:
    """PIDs whose environment carries the job marker (owner-only readable)."""
    found: list[int] = []
    needle = f"SANDBOX_JOB={marker}".encode()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "environ").read_bytes()
        except (OSError, ProcessLookupError):
            continue
        if needle in raw.split(b"\0"):
            found.append(int(entry.name))
    return found


class LandlockSandbox:
    """Filesystem/syscall sandbox that needs no privileges."""

    def __init__(self, state: Path, *, python: str | None = None,
                 wall_seconds: float = 15.0, cpu_seconds: int = 17,
                 address_space: int = 512 * 1024 * 1024,
                 file_size: int = 4 * 1024 * 1024, open_files: int = 64):
        self.state = Path(state)
        self.python = python or sys.executable
        self.wall_seconds = wall_seconds
        self.cpu_seconds = cpu_seconds
        self.address_space = address_space
        self.file_size = file_size
        self.open_files = open_files
        self.jobs = self.state / "jobs"

    # -- admission -----------------------------------------------------------
    def read_paths(self) -> list[str]:
        return sandbox_kernel.runtime_read_paths(self.python)

    def attestation_path(self) -> Path:
        return self.state / "landlock-attestation.json"

    def _probe(self) -> dict:
        sentinel = self.state / "probe-sentinel.txt"
        sentinel.write_text("TOP-SECRET-PROBE", encoding="utf-8")
        try:
            payload = json.dumps({"source": PROBE_SOURCE, "args": [{"outside": str(sentinel)}],
                                  "kwargs": {}}, ensure_ascii=False).encode()
            status, raw, _ = self.run_payload(payload, deadline=time.monotonic() + self.wall_seconds * 2)
            if status != "finished":
                raise NotReady("probe_failed")
            value = json.loads(raw)["value"]
            if set(value) != {"read_outside", "write_outside", "write_state", "tcp_connect",
                              "fork", "exec", "signal_outside"}:
                raise NotReady("probe_incomplete")
            leaked = sorted(name for name, outcome in value.items() if outcome == "ALLOWED")
            if leaked:
                raise NotReady(f"probe_escape:{','.join(leaked)}")
            return value
        finally:
            sentinel.unlink(missing_ok=True)

    def verify(self, *, require_reaper: bool = True) -> None:
        if (self.state / "quarantined").exists():
            raise NotReady("host_quarantined")
        if sandbox_kernel.landlock_abi() < 4:
            raise NotReady("landlock_unavailable")
        if not LAUNCHER.is_file():
            raise NotReady("launcher_missing")
        if require_reaper:
            heartbeat = self.state / "reaper-heartbeat"
            try:
                age = time.time() - float(heartbeat.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                raise NotReady("reaper_unavailable") from None
            if age > 3:
                raise NotReady("reaper_unavailable")
        path = self.attestation_path()
        try:
            attestation = json.loads(path.read_text(encoding="utf-8"))
            if (attestation.get("policy") != PROFILE or attestation.get("isolation_verified") is not True
                    or attestation.get("expires_at", 0) <= time.time()
                    or attestation.get("launcher_sha256") != self._launcher_digest()):
                raise ValueError()
            return
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        probes = self._probe()
        attestation = {
            "policy": PROFILE,
            "isolation_verified": True,
            "landlock_abi": sandbox_kernel.landlock_abi(),
            "kernel": os.uname().release,
            "launcher_sha256": self._launcher_digest(),
            "probes": probes,
            "verified_at": time.time(),
            "expires_at": time.time() + ATTESTATION_TTL_SECONDS,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(attestation, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def _launcher_digest(self) -> str:
        digest = hashlib.sha256()
        for path in (LAUNCHER, Path(__file__).with_name("sandbox_guest.py"),
                     Path(__file__).with_name("sandbox_kernel.py")):
            digest.update(path.read_bytes())
        return digest.hexdigest()

    # -- execution -----------------------------------------------------------
    def run_payload(self, payload: bytes, *, deadline: float) -> tuple[str, bytes, int]:
        self.jobs.mkdir(parents=True, exist_ok=True, mode=0o700)
        job_id = hashlib.sha256(payload).hexdigest()[:24] + f"-{os.getpid()}-{time.monotonic_ns()}"
        job_dir = self.jobs / job_id
        job_dir.mkdir(mode=0o700)
        config_path = job_dir / "policy.json"
        config_path.write_text(json.dumps({
            "job_id": job_id,
            "job_dir": str(job_dir),
            "python": self.python,
            "read_paths": self.read_paths(),
            "cpu_seconds": self.cpu_seconds,
            "address_space": self.address_space,
            "file_size": self.file_size,
            "open_files": self.open_files,
        }), encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        from .execution import capture  # local import: execution owns the wire helper

        process = None
        try:
            process = subprocess.Popen(
                [self.python, "-I", "-S", "-u", str(LAUNCHER), str(config_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, close_fds=True, cwd=str(job_dir),
            )
            status, raw, used = capture(process, deadline, 64 * 1024, payload)
            if status == "error":
                stderr = b""
                if process.stderr is not None:
                    try:
                        stderr = process.stderr.read() or b""
                    except (OSError, ValueError):
                        stderr = b""
                if b"sandbox_unavailable" in stderr:
                    status = "unavailable"
                elif process.returncode == 75:
                    # The guest translates MemoryError into a dedicated exit code:
                    # the kernel reports it, learner code cannot forge it for gain.
                    status = "resource_violation"
            return status, raw, used
        finally:
            if process is not None:
                _kill_group(process)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=CLEANUP_SECONDS)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe is not None and not pipe.closed:
                        with contextlib.suppress(OSError):
                            pipe.close()
            leftovers = stray_processes(job_id)
            for pid in leftovers:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.kill(pid, signal.SIGKILL)
            if leftovers and stray_processes(job_id):
                (self.state / "quarantined").write_text("cleanup_not_confirmed", encoding="utf-8")
                raise NotReady("cleanup_not_confirmed")
            shutil.rmtree(job_dir, ignore_errors=True)

    # -- reaping -------------------------------------------------------------
    def reap(self, *, force: bool = False) -> int:
        """Kill processes whose job directory no longer exists (orphans)."""
        known = {entry.name for entry in self.jobs.iterdir()} if self.jobs.exists() else set()
        victims: list[int] = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "environ").read_bytes()
            except (OSError, ProcessLookupError):
                continue
            fields = dict(item.split(b"=", 1) for item in raw.split(b"\0") if b"=" in item)
            job = fields.get(b"SANDBOX_JOB")
            if job is None:
                continue
            marker = job.decode("utf-8", "replace")
            if force or marker not in known:
                victims.append(int(entry.name))
        for pid in victims:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
        return len(victims)
