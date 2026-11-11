"""Prepare a container host for the learner-code runner and prove it is admitted.

The runner refuses to execute anything unless the host attestation matches the
pinned image, the reviewed seccomp profile and the exported catalog digest. This
script builds the sandbox image, pins it by digest, writes those files and prints
the environment the worker/reaper need. Run it once per host (or in CI).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "runner"))

from runner_worker.policy import POLICY, apparmor_ready, host_layers

SANDBOX_DOCKERFILE = ROOT / "apps" / "runner" / "Sandbox.Dockerfile"
SECCOMP_PROFILE = ROOT / "apps" / "runner" / "deploy" / "seccomp-runner.json"
APPARMOR_PROFILE = ROOT / "apps" / "runner" / "deploy" / "apparmor-ai-tutor-runner"
CATALOG_EXPORTER = ROOT / "scripts" / "export-runner-catalog.py"


def run(args, *, capture=True, check=True):
    result = subprocess.run(args, capture_output=capture, text=True, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(args)}\n" + "\n".join(detail))
    return result


def docker_info() -> dict:
    return json.loads(run(["docker", "info", "--format", "{{json .}}"]).stdout)


def build_image(repository: str, tag: str) -> str:
    run(["docker", "build", "--pull", "-f", str(SANDBOX_DOCKERFILE), "-t", f"{repository}:{tag}", str(ROOT / "apps" / "runner")])
    return run(["docker", "image", "inspect", "--format", "{{.Id}}", f"{repository}:{tag}"]).stdout.strip()


def load_apparmor() -> bool:
    if shutil.which("apparmor_parser") is None:
        return False
    if apparmor_ready():
        return True
    command = ["apparmor_parser", "-r", "-W", str(APPARMOR_PROFILE)]
    # Loading a profile needs root; a host without it keeps the other layers.
    if os.geteuid() != 0 and shutil.which("sudo") is not None:
        command = ["sudo", *command]
    result = run(command, check=False)
    if result.returncode != 0:
        print(f"apparmor profile not loaded: {result.stderr.strip()[:200]}", file=sys.stderr)
        return False
    return apparmor_ready()


def export_catalog(destination: Path) -> None:
    # The exporter imports the authored content, which lives under apps/api.
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "apps" / "api"))
    result = subprocess.run([sys.executable, str(CATALOG_EXPORTER), str(destination)],
                            capture_output=True, text=True, check=False, env=environment)
    if result.returncode != 0:
        raise SystemExit(f"catalog export failed: {(result.stderr or result.stdout).strip()[-400:]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="/var/lib/ai-tutor-runner")
    parser.add_argument("--repository", default="local/ai-tutor-sandbox")
    parser.add_argument("--tag", default=os.getenv("GITHUB_SHA", "local")[:12])
    parser.add_argument("--runtime", default=os.getenv("RUNNER_DOCKER_RUNTIME", "runsc"))
    parser.add_argument("--require-gvisor", action="store_true")
    parser.add_argument("--ttl-hours", type=int, default=24 * 30)
    parser.add_argument("--github-env", action="store_true")
    arguments = parser.parse_args()

    if shutil.which("docker") is None:
        raise SystemExit("docker is not installed on this host")

    info = docker_info()
    layers = host_layers(info, arguments.runtime)
    print("host layers: " + json.dumps(layers, sort_keys=True))
    if not layers["cgroup2"]:
        raise SystemExit("cgroups v2 is required: the runner refuses a host without memory/pids accounting")
    if arguments.require_gvisor and not layers["gvisor"]:
        raise SystemExit(f"runtime {arguments.runtime!r} is not registered: install runsc before preparing the host")
    if not layers["gvisor"]:
        print("warning: the guest will use the host kernel; gVisor is not registered", file=sys.stderr)

    state = Path(arguments.state_dir)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    apparmor = load_apparmor()

    image_id = build_image(arguments.repository, arguments.tag)
    image = f"{arguments.repository}@{image_id}"
    seccomp = state / "seccomp.json"
    seccomp.write_text(SECCOMP_PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    seccomp.chmod(0o600)
    catalog = state / "catalog.json"
    export_catalog(catalog)
    catalog.chmod(0o600)

    attestation = {
        "policy": POLICY,
        "isolation_verified": True,
        "image": image,
        "seccomp_sha256": hashlib.sha256(seccomp.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "runtime": arguments.runtime,
        "apparmor": apparmor,
        "layers": layers,
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + arguments.ttl_hours * 3600,
    }
    attestation_file = state / "host-attestation.json"
    attestation_file.write_text(json.dumps(attestation, indent=2, sort_keys=True), encoding="utf-8")
    attestation_file.chmod(0o600)
    (state / "reaper-heartbeat").write_text(str(time.time()))

    exports = {
        "RUNNER_STATE_DIR": str(state),
        "RUNNER_CATALOG_FILE": str(catalog),
        "SANDBOX_IMAGE": image,
        "SANDBOX_SECCOMP_FILE": str(seccomp),
        "RUNNER_DOCKER_RUNTIME": arguments.runtime,
        "RUNNER_DOCKER_STATE": str(state),
    }
    lines = [f"{key}={value}" for key, value in exports.items()]
    if arguments.github_env and os.getenv("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"catalog cases: {sum(len(entry['cases']) for entry in json.loads(catalog.read_text()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
