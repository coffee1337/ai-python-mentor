"""Escape and abuse suite for the unprivileged Landlock/seccomp sandbox.

Each test drives the real launcher: if the kernel refuses to confine the
process, admission fails and the run is refused instead of degraded.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner_worker.policy import NotReady, Policy
from runner_worker.sandbox_kernel import landlock_abi
from runner_worker.sandbox_landlock import LandlockSandbox, stray_processes

ABI = landlock_abi()


def run(sandbox, source, args=(None,), kwargs=None, budget=6000):
    payload = json.dumps({"source": source, "args": list(args), "kwargs": kwargs or {}}).encode()
    deadline = time.monotonic() + budget / 1000
    status, raw, used = sandbox.run_payload(payload, deadline=deadline)
    return status, raw, used


@unittest.skipUnless(ABI >= 4, "kernel does not provide Landlock")
class LandlockSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        cls.state = Path(cls.root.name)
        cls.sandbox = LandlockSandbox(cls.state)
        cls.sandbox.verify(require_reaper=False)

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()

    def assertDenied(self, body):
        status, raw, _ = run(self.sandbox, "def solve(p):\n" + body, args=[{}])
        self.assertEqual(status, "error", raw)
        self.assertEqual(list(self.sandbox.jobs.iterdir()), [])

    def test_reference_execution_round_trip(self):
        status, raw, used = run(self.sandbox, "def solve(payload):\n    return payload['a'] * 2\n", args=[{"a": 21}])
        self.assertEqual(status, "finished")
        self.assertEqual(json.loads(raw), {"value": 42})
        self.assertLess(used, 4096)

    def test_reading_any_host_file_is_denied(self):
        for path in ("/home/agent/.hermes/.env", "/etc/passwd", "/etc/shadow", "/proc/self/environ"):
            with self.subTest(path=path):
                self.assertDenied(f"    return open({path!r}).read()\n")

    def test_writing_outside_the_job_directory_is_denied(self):
        for path in ("/tmp/escape.txt", "/usr/lib/escape.txt", "/home/agent/escape.txt"):
            with self.subTest(path=path):
                self.assertDenied(f"    open({path!r}, 'w').write('x')\n    return 1\n")

    def test_network_access_is_denied(self):
        self.assertDenied(
            "    import socket\n"
            "    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(('127.0.0.1', 22))\n"
            "    return 1\n"
        )

    def test_process_creation_and_exec_are_denied(self):
        self.assertDenied("    import os\n    os.fork()\n    return 1\n")
        self.assertDenied("    import os\n    os.execv('/bin/sh', ['sh'])\n    return 1\n")
        self.assertDenied(
            "    import subprocess\n    return subprocess.run(['id'], capture_output=True).stdout.decode()\n"
        )

    def test_signalling_processes_outside_the_sandbox_is_denied(self):
        self.assertDenied(f"    import os\n    os.kill({os.getppid()}, 0)\n    return 1\n")

    def test_importing_stdlib_still_works(self):
        source = (
            "import collections, datetime, itertools, json, math, re, string\n"
            "def solve(payload):\n"
            "    return {'sorted': sorted(set('banana')), 'date': datetime.date(2026, 1, 2).isoformat(),\n"
            "            'count': len(list(itertools.islice(itertools.count(), 3))), 'r': bool(re.match('a', 'a')),\n"
            "            'math': math.floor(2.9), 'c': collections.Counter('aab')['a'], 's': string.digits[:2]}\n"
        )
        status, raw, _ = run(self.sandbox, source)
        self.assertEqual(status, "finished", raw)
        self.assertEqual(json.loads(raw)["value"]["sorted"], ["a", "b", "n"])

    def test_infinite_loop_is_killed_by_wall_clock(self):
        started = time.monotonic()
        status, _, _ = run(self.sandbox, "def solve(p):\n    while True:\n        pass\n", args=[{}], budget=800)
        self.assertEqual(status, "timeout")
        self.assertLess(time.monotonic() - started, 5)

    def test_memory_bomb_is_a_resource_violation(self):
        status, _, _ = run(self.sandbox, "def solve(p):\n    x = 'a' * (8 * 10**9)\n    return len(x)\n", args=[{}])
        self.assertEqual(status, "resource_violation")

    def test_offending_output_is_capped(self):
        source = "import sys\ndef solve(p):\n    sys.stderr.write('x' * 1000000)\n    return 1\n"
        status, _, _ = run(self.sandbox, source, args=[{}])
        self.assertEqual(status, "resource_violation")

    def test_no_environment_secrets_are_visible(self):
        source = ("import os\ndef solve(p):\n    return sorted(k for k in os.environ if 'KEY' in k or 'TOKEN' in k or 'SECRET' in k)\n")
        status, raw, _ = run(self.sandbox, source)
        self.assertEqual(status, "finished")
        self.assertEqual(json.loads(raw)["value"], [])

    def test_quarantine_blocks_admission(self):
        state = Path(tempfile.mkdtemp(dir=self.state))
        sandbox = LandlockSandbox(state)
        (state / "quarantined").write_text("cleanup_not_confirmed")
        with self.assertRaises(NotReady):
            sandbox.verify(require_reaper=False)

    def test_reaper_heartbeat_is_required_for_admission(self):
        sandbox = LandlockSandbox(self.state)
        with self.assertRaises(NotReady):
            sandbox.verify(require_reaper=True)

    def test_policy_selects_landlock_when_no_container_runtime_exists(self):
        environment = {"RUNNER_STATE_DIR": str(self.state),
                       "RUNNER_CATALOG_FILE": str(self.state / "catalog.json"),
                       "RUNNER_SANDBOX_BACKEND": "landlock"}
        (self.state / "catalog.json").write_text("[]")
        saved = {key: os.environ.get(key) for key in environment}
        os.environ.update(environment)
        try:
            policy = Policy.from_environment()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(policy.backend, "landlock")
        self.assertIsInstance(policy.sandbox(), LandlockSandbox)

    def test_reaper_kills_orphans_whose_job_directory_is_gone(self):
        import subprocess

        sandbox = LandlockSandbox(self.state)
        sandbox.jobs.mkdir(parents=True, exist_ok=True)
        orphan = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            env={**os.environ, "SANDBOX_JOB": "orphan-job", "PATH": "/usr/bin:/bin"},
        )
        try:
            self.assertIn(orphan.pid, stray_processes("orphan-job"))
            self.assertGreaterEqual(sandbox.reap(), 1)
            orphan.wait(timeout=10)
        finally:
            if orphan.poll() is None:
                orphan.kill()
                orphan.wait(timeout=10)
        self.assertEqual(stray_processes("orphan-job"), [])


if __name__ == "__main__":
    unittest.main()
