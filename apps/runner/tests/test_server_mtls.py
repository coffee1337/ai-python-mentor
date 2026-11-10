"""End-to-end contract test for the runner service over mutual TLS.

Starts the real reaper and worker with a freshly generated PKI, then speaks the
private wire protocol exactly as the API does. Admission, grading, idempotency
and caller authentication are all exercised against live processes.
"""
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from runner_worker.policy import select_backend  # noqa: E402
from runner_worker.sandbox_kernel import landlock_abi  # noqa: E402

BUNDLE_SCRIPT = ROOT / "scripts" / "runner-dev-bootstrap.py"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def backend_available() -> bool:
    try:
        select_backend()
    except Exception:
        return False
    return True


@unittest.skipUnless(backend_available() and BUNDLE_SCRIPT.is_file(), "no usable isolation backend")
class RunnerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        cls.bundle = Path(cls.root.name) / "bundle"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "apps" / "api")}
        subprocess.run([sys.executable, str(BUNDLE_SCRIPT), str(cls.bundle)],
                       check=True, capture_output=True, env=env, timeout=120)
        cls.env = {}
        for line in (cls.bundle / "env.sh").read_text(encoding="utf-8").splitlines():
            if line.startswith("export "):
                key, value = line[len("export "):].split("=", 1)
                cls.env[key] = value
        cls.port = free_port()
        cls.env.update({
            "RUNNER_PORT": str(cls.port),
            "RUNNER_SANDBOX_BACKEND": "auto",
            "PYTHONPATH": str(ROOT / "apps" / "runner"),
        })
        cls.reaper = subprocess.Popen([sys.executable, "-m", "runner_worker.reaper"],
                                      env=cls.env, cwd=str(ROOT / "apps" / "runner"))
        deadline = time.monotonic() + 20
        while not (cls.bundle / "state" / "reaper-heartbeat").exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        cls.server = subprocess.Popen([sys.executable, "-m", "runner_worker.server"],
                                      env=cls.env, cwd=str(ROOT / "apps" / "runner"))
        cls.url = f"https://127.0.0.1:{cls.port}/internal/v1/runner/executions"
        context = ssl.create_default_context(cafile=str(cls.bundle / "ca.pem"))
        context.load_cert_chain(str(cls.bundle / "client.pem"), str(cls.bundle / "client.key"))
        cls.client = httpx.Client(verify=context, timeout=30.0, trust_env=False)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if cls.server.poll() is not None:
                    break
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        for process in (getattr(cls, "server", None), getattr(cls, "reaper", None)):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        cls.root.cleanup()

    # -- helpers -------------------------------------------------------------
    def body(self, source, exercise_id="dataclasses-v1-code", version=1):
        return {"protocol_version": 1, "exercise_id": exercise_id, "exercise_version": version,
                "language": "python", "source": source, "mode": "function"}

    def post(self, body, *, key="smoke-key", token=None, headers=None):
        return self.client.post(
            self.url, json=body,
            headers=headers or {"Authorization": f"Bearer {token or self.env['RUNNER_AUTH_TOKEN']}",
                                "Idempotency-Key": key},
        )

    SOLUTION = ("def solve(payload):\n"
                "    return {'total': payload['price'] * payload['quantity'], 'label': 'Line'}\n")

    # -- cases ---------------------------------------------------------------
    def test_reference_solution_passes_every_case(self):
        response = self.post(self.body(self.SOLUTION))
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "finished")
        self.assertEqual(payload["tests_passed"], payload["tests_total"])
        self.assertGreater(payload["tests_total"], 1)
        self.assertNotIn("expected", response.text)

    def test_wrong_solution_reports_partial_credit(self):
        response = self.post(self.body("def solve(payload):\n    return {'total': -1, 'label': 'wrong'}\n"),
                             key="wrong-key")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "finished")
        self.assertEqual(payload["tests_passed"], 0)

    def test_bearer_token_is_required(self):
        response = self.post(self.body(self.SOLUTION), key="token-key", token="not-the-token")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("smoke", response.text)

    def test_client_certificate_is_required(self):
        anonymous = httpx.Client(verify=ssl.create_default_context(cafile=str(self.bundle / "ca.pem")),
                                 timeout=10.0, trust_env=False)
        with self.assertRaises(httpx.TransportError):
            anonymous.post(self.url, json=self.body(self.SOLUTION),
                           headers={"Authorization": f"Bearer {self.env['RUNNER_AUTH_TOKEN']}",
                                    "Idempotency-Key": "anon-key"})

    def test_unknown_exercise_version_is_rejected(self):
        response = self.post(self.body(self.SOLUTION, exercise_id="does-not-exist", version=1), key="unknown-key")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error_code"], "invalid_request")

    def test_expected_values_are_rejected_as_extra_fields(self):
        body = self.body(self.SOLUTION)
        body["cases"] = [{"args": [], "expected": 1}]
        response = self.post(body, key="extra-key")
        self.assertEqual(response.status_code, 422)

    def test_idempotent_replay_returns_the_same_result(self):
        first = self.post(self.body(self.SOLUTION), key="replay-key")
        second = self.post(self.body(self.SOLUTION), key="replay-key")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        clash = self.post(self.body("def solve(payload):\n    return 1\n"), key="replay-key")
        self.assertEqual(clash.status_code, 409)

    def test_resource_abuse_is_reported_without_crashing_the_worker(self):
        response = self.post(self.body("def solve(payload):\n    while True:\n        pass\n"), key="loop-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "timeout")
        healthy = self.post(self.body(self.SOLUTION), key="after-loop-key")
        self.assertEqual(healthy.status_code, 200)
        self.assertEqual(healthy.json()["status"], "finished")


if __name__ == "__main__":
    unittest.main()
