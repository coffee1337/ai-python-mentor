"""Private TLS1.3 service with client-CA and workload-name allowlist."""
import hmac
import fcntl
import json
import os
import re
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .execution import evaluate, response
from .journal import Conflict, Journal
from .policy import BODY_BYTES, SOURCE_BYTES, NotReady, Policy
from .reaper import reap

def validate_request(body, key, catalog):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key or ""):
        raise ValueError("invalid_key")
    if not isinstance(body, dict) or set(body) != {"protocol_version", "exercise_id", "exercise_version", "language", "source", "mode"}:
        raise ValueError("invalid_fields")
    if type(body["protocol_version"]) is not int or body["protocol_version"] != 1:
        raise ValueError("unsupported_protocol")
    if body["language"] != "python" or body["mode"] != "function" or type(body["exercise_version"]) is not int:
        raise ValueError("unsupported_exercise")
    if not isinstance(body["source"], str) or not 1 <= len(body["source"]) <= 20000 or len(body["source"].encode()) > SOURCE_BYTES:
        raise ValueError("source_limit")
    identity = (body["exercise_id"], body["exercise_version"])
    entry = catalog.get(identity)
    if entry is None:
        raise ValueError("unknown_exercise_version")
    return entry

def load_catalog(path):
    raw = path.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise NotReady("catalog_too_large")
    entries = json.loads(raw)
    catalog = {}
    for entry in entries:
        key = (entry["exercise_id"], entry["version"])
        if key in catalog or not 1 <= len(entry["cases"]) <= 256:
            raise NotReady("catalog_invalid")
        if not all(set(case) == {"args", "kwargs", "expected", "visibility"} and case["visibility"] in {"public", "hidden"}
                   and isinstance(case["args"], list) and isinstance(case["kwargs"], dict) for case in entry["cases"]):
            raise NotReady("catalog_invalid")
        if any(len(json.dumps([case["args"], case["kwargs"]], ensure_ascii=False).encode()) > 16384 for case in entry["cases"]):
            raise NotReady("catalog_input_limit")
        catalog[key] = entry
    return catalog

class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, *args, **kwargs):
        self.request_slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def get_request(self):
        connection, address = self.socket.accept()
        connection.settimeout(3)
        try:
            return self.tls_context.wrap_socket(connection, server_side=True), address
        except Exception:
            connection.close()
            raise

    def process_request(self, request, address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.request_slots.release()

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    def log_message(self, *args):
        pass

    def answer(self, code, body):
        raw = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        self.connection.settimeout(20)
        certificate = self.connection.getpeercert()
        # The deployment CA is dedicated to runner workloads. Never trust forwarded cert headers.
        names = [value for kind, value in certificate.get("subjectAltName", ()) if kind == "URI"]
        caller = next((name for name in names if name in self.server.allowed_identities), None)
        supplied = self.headers.get("Authorization", "")
        if caller is None or not hmac.compare_digest(supplied, "Bearer " + self.server.token):
            self.answer(403, {"error_code": "caller_not_allowed", "message": "Caller not allowed"}); return
        if self.path != "/internal/v1/runner/executions":
            self.answer(404, {"error_code": "not_found", "message": "Not found"}); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= BODY_BYTES or self.headers.get("Content-Encoding") or self.headers.get("Transfer-Encoding"):
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            key = self.headers.get("Idempotency-Key")
            entry = validate_request(body, key, self.server.catalog)
        except (ValueError, TypeError, KeyError):
            self.answer(422, {"error_code": "invalid_request", "message": "Invalid request"}); return
        try:
            found, existing = self.server.journal.lookup(caller, key, body)
            if found:
                self.answer(200 if existing else 202, existing or response(key, "in_progress")); return
            self.server.policy.verify()
            if not self.server.capacity.acquire(blocking=False):
                self.answer(429, {"error_code": "worker_capacity", "message": "Worker at capacity"}); return
            try:
                created, existing = self.server.journal.claim(caller, key, body)
                if not created:
                    self.answer(200 if existing else 202, existing or response(key, "in_progress")); return
                try:
                    result = evaluate(self.server.policy, key, body, entry)
                except Exception:
                    result = response(key, error="worker_not_ready")
                self.server.journal.finish(caller, key, result)
                self.answer(200, result)
            finally:
                self.server.capacity.release()
        except Conflict:
            self.answer(409, {"error_code": "idempotency_conflict", "message": "Idempotency conflict"})
        except NotReady:
            self.answer(503, response(key, error="worker_not_ready"))

def main():
    policy = Policy.from_environment()
    policy.verify()
    service_lock = policy.state.joinpath("service.lock").open("a")
    fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    journal = Journal(policy.state)
    # Startup reconciliation first destroys orphan resources; unfinished intent is
    # a permanent unavailable tombstone, never a permission to launch again.
    reap(policy, force=True)
    for caller, key in journal.unfinished():
        journal.finish(caller, key, response(key, error="worker_not_ready"))
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=os.environ["RUNNER_CLIENT_CA_FILE"])
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(os.environ["RUNNER_SERVER_CERT_FILE"], os.environ["RUNNER_SERVER_KEY_FILE"])
    server = Server((os.getenv("RUNNER_BIND", "127.0.0.1"), int(os.getenv("RUNNER_PORT", "8443"))), Handler)
    server.tls_context = context
    server.policy, server.journal, server.catalog = policy, journal, load_catalog(policy.catalog_file)
    server.allowed_identities = set(os.environ["RUNNER_ALLOWED_API_IDENTITIES"].split(","))
    server.token = os.environ["RUNNER_AUTH_TOKEN"]
    server.capacity = threading.BoundedSemaphore(1)
    server.serve_forever()

if __name__ == "__main__":
    main()
