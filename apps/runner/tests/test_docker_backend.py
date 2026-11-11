"""Escape and abuse suite for the container backend, proved by behaviour.

The container path is the one production runs, so it is verified the same way as
the kernel sandbox: every test tries to break out and must be refused, and the
authored catalog must score 100% on the reference solutions.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner_worker.execution import evaluate
from runner_worker.policy import WALL_SECONDS, Policy, host_layers

STATE = Path(os.environ.get("RUNNER_DOCKER_STATE", "/tmp/runner-state"))
ATTESTATION = STATE / "host-attestation.json"
CATALOG = STATE / "catalog.json"
SECCOMP = STATE / "seccomp.json"
RUNTIME = os.environ.get("RUNNER_DOCKER_RUNTIME", "runsc")
FULL = os.environ.get("RUNNER_DOCKER_FULL") == "1"


def docker_available() -> bool:
    if shutil.which("docker") is None or not ATTESTATION.is_file():
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


def policy() -> Policy:
    attestation = json.loads(ATTESTATION.read_text(encoding="utf-8"))
    return Policy(attestation["image"], str(SECCOMP), STATE, CATALOG, ATTESTATION, runtime=RUNTIME, backend="docker")


def heartbeat() -> None:
    """The host must look alive: the runner refuses to admit without a fresh reaper."""
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "reaper-heartbeat").write_text(str(time.time()))


@unittest.skipUnless(docker_available(), "container host is not prepared")
class DockerSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = policy()
        heartbeat()
        cls.policy.verify()

    def setUp(self):
        heartbeat()

    def run_source(self, body, budget=WALL_SECONDS):
        entry = {"cases": [{"args": [None], "kwargs": {}, "expected": True, "visibility": "public"}]}
        request = {"source": "def solve(p):\n" + body}
        return evaluate(self.policy, f"probe-{uuid.uuid4().hex}", request, entry)

    def assertBlocked(self, result):
        """The guest was denied and observed the refusal: it returns True."""
        self.assertEqual(result["status"], "finished", result)
        self.assertEqual(result["tests_passed"], 1, result)

    def test_reference_execution_round_trip(self):
        row = {
            "cases": [
                {"args": [1], "kwargs": {}, "expected": 2, "visibility": "public"},
                {"args": [0], "kwargs": {}, "expected": 1, "visibility": "hidden"},
            ]
        }
        result = evaluate(self.policy, "roundtrip", {"source": "def solve(n):\n    return n + 1\n"}, row)
        self.assertEqual(result["status"], "finished", result)
        self.assertEqual(result["tests_passed"], 2, result)

    def test_reading_host_secrets_is_denied(self):
        result = self.run_source(
            "    data=[]\n"
            "    for path in ('/home/agent/.env', '/etc/shadow', '/var/lib/ai-tutor-runner/catalog.json'):\n"
            "        try:\n"
            "            open(path,'rb').read()\n"
            "            data.append(path)\n"
            "        except OSError:\n"
            "            pass\n"
            "    return data == []\n"
        )
        self.assertBlocked(result)

    def test_writing_outside_tmp_is_denied(self):
        result = self.run_source(
            "    for path in ('/app/pwn.py', '/etc/cron.d/x', '/usr/local/lib/python3.12/site-packages/pwn.py'):\n"
            "        try:\n"
            "            open(path,'w').write('x')\n"
            "            return False\n"
            "        except OSError:\n"
            "            pass\n"
            "    return True\n"
        )
        self.assertBlocked(result)

    def test_network_access_is_denied(self):
        result = self.run_source(
            "    import socket\n"
            "    try:\n"
            "        socket.create_connection(('1.1.1.1', 80), timeout=2)\n"
            "        return False\n"
            "    except OSError:\n"
            "        return True\n"
        )
        self.assertBlocked(result)

    def test_no_environment_secrets_are_visible(self):
        result = self.run_source(
            "    import os\n"
            "    leaked=[k for k in os.environ if any(word in k.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD','DATABASE'))]\n"
            "    return leaked == []\n"
        )
        self.assertBlocked(result)

    def test_infinite_loop_is_stopped_by_the_deadline(self):
        result = self.run_source("    while True:\n        pass\n")
        self.assertEqual(result["status"], "timeout", result)
        self.assertEqual(result["tests_passed"], 0, result)

    def test_memory_bomb_is_a_resource_violation(self):
        result = self.run_source("    blocks=[]\n    while True:\n        blocks.append(bytearray(32*1024*1024))\n")
        self.assertIn(result["status"], ("error", "resource_violation"), result)
        self.assertEqual(result["tests_passed"], 0, result)

    def test_output_flood_is_capped(self):
        result = self.run_source("    import sys\n    while True:\n        sys.stderr.write('x'*4096)\n")
        self.assertIn(result["status"], ("resource_violation", "timeout"), result)
        self.assertEqual(result["tests_passed"], 0, result)

    def test_fork_bomb_hits_the_pid_limit(self):
        result = self.run_source(
            "    import os\n"
            "    spawned=0\n"
            "    for _ in range(200):\n"
            "        try:\n"
            "            pid=os.fork()\n"
            "        except OSError:\n"
            "            break\n"
            "        if pid==0:\n"
            "            os._exit(0)\n"
            "        spawned+=1\n"
            "    return spawned < 200\n"
        )
        self.assertEqual(result["status"], "finished", result)
        self.assertEqual(result["tests_passed"], 1, result)

    def test_arbitrary_binary_is_not_executable(self):
        result = self.run_source(
            "    import subprocess\n"
            "    try:\n"
            "        subprocess.run(['/bin/sh','-c','id'], check=True, timeout=5,\n"
            "                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "    except (OSError, subprocess.SubprocessError):\n"
            "        return True\n"
            "    return False\n"
        )
        self.assertEqual(result["status"], "finished", result)
        self.assertEqual(result["tests_passed"], 1, result)

    def test_host_layers_are_reported(self):
        layers = json.loads((STATE / "host-layers.json").read_text())
        self.assertTrue(layers["cgroup2"], layers)
        self.assertTrue(layers["seccomp"], layers)
        self.assertTrue(layers["gvisor"] or layers["userns"], layers)

    def test_authored_catalog_scores_one_hundred_percent(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
        from app.runner_exercise_content import RUNNER_EXERCISES

        entries = json.loads(CATALOG.read_text(encoding="utf-8"))
        sample = entries if FULL else entries[:12]
        self.assertEqual(len(entries), 90)
        failures = []
        for entry in sample:
            # A real host runs the reaper service; here the test keeps its heartbeat fresh.
            heartbeat()
            row = RUNNER_EXERCISES[entry["exercise_id"]]
            result = evaluate(self.policy, f"catalog-{entry['exercise_id']}", {"source": row["solution"]}, entry)
            if result["status"] != "finished" or result["tests_passed"] != result["tests_total"]:
                failures.append((entry["exercise_id"], result["status"], result["tests_passed"], result["tests_total"]))
        self.assertEqual(failures, [], f"{len(failures)} exercises did not score 100%")

    def test_backends_agree_on_the_same_cases(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
        from app.runner_exercise_content import RUNNER_EXERCISES
        from runner_worker.policy import landlock_ready

        if not landlock_ready():
            self.skipTest("kernel sandbox is unavailable on this host")
        kernel_policy = Policy("", "", STATE, CATALOG, ATTESTATION, backend="landlock")
        mismatches = []
        for entry in json.loads(CATALOG.read_text(encoding="utf-8"))[:12]:
            heartbeat()
            row = RUNNER_EXERCISES[entry["exercise_id"]]
            key = f"parity-{entry['exercise_id']}"
            container = evaluate(self.policy, key, {"source": row["solution"]}, entry)
            kernel = evaluate(kernel_policy, key, {"source": row["solution"]}, entry)
            if (container["status"], container["tests_passed"]) != (kernel["status"], kernel["tests_passed"]):
                mismatches.append((entry["exercise_id"], container["status"], kernel["status"]))
        self.assertEqual(mismatches, [], mismatches)


class HostLayerReportingTests(unittest.TestCase):
    """The layer probe is pure: it must never report a layer the host lacks."""

    def test_plain_root_runtime_without_userns_is_not_accepted(self):
        info = {"OSType": "linux", "CgroupVersion": "2", "MemoryLimit": True, "PidsLimit": True,
                "SecurityOptions": ["name=seccomp,profile=builtin"], "Runtimes": {"runc": {}}}
        layers = host_layers(info, "runsc")
        self.assertFalse(layers["gvisor"])
        self.assertFalse(layers["userns"])
        self.assertTrue(layers["seccomp"])

    def test_gvisor_runtime_is_detected(self):
        info = {"OSType": "linux", "CgroupVersion": "2", "MemoryLimit": True, "PidsLimit": True,
                "SecurityOptions": ["name=seccomp,profile=builtin"], "Runtimes": {"runsc": {}}}
        self.assertTrue(host_layers(info, "runsc")["gvisor"])

    def test_cgroups_v1_is_reported_as_absent(self):
        info = {"OSType": "linux", "CgroupVersion": "1", "MemoryLimit": True, "PidsLimit": True,
                "SecurityOptions": ["name=seccomp"], "Runtimes": {"runsc": {}}}
        self.assertFalse(host_layers(info, "runsc")["cgroup2"])


if __name__ == "__main__":
    unittest.main()
