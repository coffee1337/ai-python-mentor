"""Fixed runtime policy. Every prerequisite is required before admission."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

POLICY = "python-authored-v1"
SOURCE_BYTES = 64 * 1024
BODY_BYTES = 128 * 1024
OUTPUT_BYTES = 64 * 1024
WALL_SECONDS = 15
# CPU backstop sits above the wall clock so the wall deadline is the primary
# limit and produces a clean `timeout` instead of a SIGKILL from RLIMIT_CPU.
CPU_SECONDS = WALL_SECONDS + 2
CLEANUP_SECONDS = 5
LABEL = "ai-tutor-runner"
BACKENDS = ("docker", "landlock")


def docker_ready(timeout=5) -> bool:
    """True when a container runtime that supports the pinned policy is usable."""
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .}}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    try:
        return "runsc" in json.loads(result.stdout).get("Runtimes", {})
    except (ValueError, TypeError):
        return False


def landlock_ready() -> bool:
    from .sandbox_kernel import landlock_abi

    return landlock_abi() >= 4


def select_backend() -> str:
    """Choose the isolation backend; ``auto`` prefers containers when present."""
    configured = os.getenv("RUNNER_SANDBOX_BACKEND", "auto").strip().lower()
    if configured in BACKENDS:
        return configured
    if configured != "auto":
        raise NotReady("policy_invalid")
    if docker_ready():
        return "docker"
    if landlock_ready():
        return "landlock"
    raise NotReady("no_sandbox_backend")


class NotReady(RuntimeError):
    pass

def command(args, timeout=5):
    # Runtime responses are not exposed in public errors or logs.
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        if result.returncode != 0 or len(result.stdout) > BODY_BYTES:
            raise NotReady("runtime_unavailable")
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        raise NotReady("runtime_unavailable") from None

@dataclass(frozen=True)
class Policy:
    image: str
    seccomp_file: str
    state: Path
    catalog_file: Path
    attestation_file: Path
    runtime: str = "runsc"
    backend: str = "docker"

    @classmethod
    def from_environment(cls):
        backend = select_backend()
        try:
            state = Path(os.environ["RUNNER_STATE_DIR"])
            catalog = Path(os.environ["RUNNER_CATALOG_FILE"])
            attestation = Path(os.environ.get(
                "RUNNER_HOST_ATTESTATION_FILE", str(state / "host-attestation.json")))
        except KeyError:
            raise NotReady("policy_missing") from None
        if backend == "landlock":
            if not catalog.is_file():
                raise NotReady("catalog_missing")
            return cls("", "", state, catalog, attestation, backend="landlock")
        try:
            policy = cls(os.environ["SANDBOX_IMAGE"], os.environ["SANDBOX_SECCOMP_FILE"],
                         state, catalog, attestation)
        except KeyError:
            raise NotReady("policy_missing") from None
        if not re.fullmatch(r"[a-zA-Z0-9./_-]+@sha256:[a-f0-9]{64}", policy.image):
            raise NotReady("image_not_pinned")
        if not Path(policy.seccomp_file).is_file():
            raise NotReady("seccomp_missing")
        return policy

    def sandbox(self):
        """Isolation backend used for admission and execution."""
        if self.backend == "landlock":
            from .sandbox_landlock import LandlockSandbox

            return LandlockSandbox(self.state, wall_seconds=WALL_SECONDS, cpu_seconds=CPU_SECONDS)
        return None

    def verify(self, *, require_reaper=True):
        backend = self.sandbox()
        if backend is not None:
            backend.verify(require_reaper=require_reaper)
            return
        if self.state.joinpath("quarantined").exists():
            raise NotReady("host_quarantined")
        try:
            if self.attestation_file.stat().st_size > 4096:
                raise ValueError()
            attestation = json.loads(self.attestation_file.read_text(encoding="utf-8"))
            profile_digest = hashlib.sha256(Path(self.seccomp_file).read_bytes()).hexdigest()
            catalog_digest = hashlib.sha256(self.catalog_file.read_bytes()).hexdigest()
            if not (attestation.get("policy") == POLICY and attestation.get("isolation_verified") is True
                    and attestation.get("image") == self.image and attestation.get("seccomp_sha256") == profile_digest
                    and attestation.get("catalog_sha256") == catalog_digest
                    and attestation.get("expires_at", 0) > time.time()):
                raise ValueError()
            if require_reaper and time.time() - float(self.state.joinpath("reaper-heartbeat").read_text()) > 3:
                raise ValueError()
            info = json.loads(command(["docker", "info", "--format", "{{json .}}"] ))
            options = " ".join(info.get("SecurityOptions", []))
            if info.get("OSType") != "linux" or info.get("CgroupVersion") != "2":
                raise ValueError()
            if not all(value in options for value in ("seccomp", "apparmor", "userns")):
                raise ValueError()
            if self.runtime not in info.get("Runtimes", {}) or not info.get("MemoryLimit") or not info.get("PidsLimit"):
                raise ValueError()
            command(["docker", "image", "inspect", self.image])  # Never pull while admitting.
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            raise NotReady("host_not_verified") from None

    def argv(self, name, job_digest, deadline, guest_program):
        return ["docker", "create", "--name", name, "--label", f"{LABEL}=true",
                "--label", f"{LABEL}.job={job_digest}", "--label", f"{LABEL}.deadline={deadline}",
                "--runtime", self.runtime, "--network", "none", "--ipc", "none",
                "--read-only", "--user", "65532:65532", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges=true", "--security-opt", "apparmor=ai-tutor-runner",
                "--security-opt", f"seccomp={self.seccomp_file}", "--pids-limit", "32",
                "--cpus", "1", "--memory", "512m", "--memory-swap", "512m",
                "--ulimit", "nofile=64:64", "--ulimit", "core=0:0", "--log-driver", "none",
                "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=15728640,nr_inodes=4000,uid=65532,gid=65532,mode=700",
                "--tmpfs", "/dev:rw,nosuid,nodev,noexec,size=1048576,nr_inodes=96,uid=0,gid=0,mode=755",
                "--workdir", "/tmp", "--interactive", "--entrypoint", "/usr/local/bin/python",
                self.image, "-I", "-S", "-u", "-c", guest_program]
