"""Untrusted Python runs only in a pinned isolated guest. Expected values stay here."""
import hashlib
import json
import os
import selectors
import subprocess
import time
from .policy import CLEANUP_SECONDS, OUTPUT_BYTES, WALL_SECONDS, LABEL, NotReady, command

# Fixed program, no source interpolation, filesystem imports or user pytest plugins.
# The guest receives one input at a time and never receives expected values/tests.
GUEST = """import contextlib,json,sys
payload=json.loads(sys.stdin.buffer.read(131073))
with contextlib.redirect_stdout(sys.stderr):
    namespace={}
    exec(compile(payload['source'],'<submission>','exec'),namespace)
    result=namespace['solve'](*payload['args'],**payload['kwargs'])
sys.stdout.write(json.dumps({'value':result},ensure_ascii=True,allow_nan=False,separators=(',',':')))
"""

def response(key, status="unavailable", *, passed=0, total=0, error=None):
    return {"protocol_version": 1, "idempotency_key": key, "status": status,
            "tests_passed": passed, "tests_total": total, "timeout": status == "timeout",
            "resource_violation": status == "resource_violation", "stdout": "", "stderr": "",
            "stdout_truncated": False, "stderr_truncated": False,
            "exit_code": (0 if passed == total else 1) if status == "finished" else None,
            "error_code": error, "message": None}

def cleanup(name, *, deadline=None):
    deadline = deadline if deadline is not None else time.monotonic() + CLEANUP_SECONDS
    # Force-remove kills all processes through the runtime, including new process groups.
    command(["docker", "rm", "--force", name], timeout=max(.001, deadline - time.monotonic()))
    remaining = command(["docker", "ps", "--all", "--filter", f"name=^/{name}$", "--format", "{{.ID}}"],
                        timeout=max(.001, deadline - time.monotonic()))
    if remaining.strip():
        raise NotReady("cleanup_not_confirmed")

def capture(process, deadline, remaining, payload):
    selector = selectors.DefaultSelector()
    for pipe in (process.stdout, process.stderr):
        selector.register(pipe, selectors.EVENT_READ)
    os.set_blocking(process.stdin.fileno(), False)
    selector.register(process.stdin, selectors.EVENT_WRITE)
    offset = 0
    output, errors = bytearray(), bytearray()
    used = 0
    try:
        while selector.get_map():
            wait = deadline - time.monotonic()
            if wait <= 0:
                return "timeout", b"", used
            for event, _ in selector.select(min(wait, .1)):
                if event.fileobj is process.stdin:
                    try:
                        offset += os.write(process.stdin.fileno(), payload[offset:offset + 4096])
                    except BrokenPipeError:
                        return "error", b"", used
                    if offset == len(payload):
                        selector.unregister(process.stdin)
                        process.stdin.close()
                    continue
                chunk = event.fileobj.read1(min(4096, max(1, remaining - used + 1)))
                if not chunk:
                    selector.unregister(event.fileobj)
                    continue
                used += len(chunk)
                if used > remaining:
                    return "resource_violation", b"", used
                (output if event.fileobj is process.stdout else errors).extend(chunk)
        try:
            code = process.wait(timeout=max(.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return "timeout", b"", used
        if code:
            return "error", b"", used
        return "finished", bytes(output), used
    finally:
        selector.close()

def evaluate(policy, key, request, entry):
    job_digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    deadline = time.monotonic() + WALL_SECONDS
    absolute = time.time() + WALL_SECONDS
    used, passed, total = 0, 0, len(entry["cases"])
    for ordinal, case in enumerate(entry["cases"]):
        name = f"tutor-{job_digest}-{ordinal}"
        allocated, process = False, None
        try:
            policy.verify()
            command(policy.argv(name, job_digest, absolute, GUEST), timeout=max(.1, deadline - time.monotonic()))
            allocated = True
            process = subprocess.Popen(["docker", "start", "--attach", "--interactive", name],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            payload = json.dumps({"source": request["source"], "args": case["args"], "kwargs": case["kwargs"]}, ensure_ascii=False).encode()
            status, raw, amount = capture(process, deadline, OUTPUT_BYTES - used, payload)
            used += amount
            if status != "finished":
                if status == "error":
                    state = json.loads(command(["docker", "inspect", "--format", "{{json .State}}", name]))
                    if state.get("OOMKilled") is True:
                        status = "resource_violation"
                return response(key, status, total=total, error="execution_limit" if status in {"timeout", "resource_violation"} else "execution_error")
            try:
                value = json.loads(raw)
                if set(value) != {"value"}:
                    raise ValueError()
                # Compare in the trusted host, never accept guest-provided pass counts.
                actual = json.dumps(value["value"], sort_keys=True, allow_nan=False, separators=(",", ":"))
                expected = json.dumps(case["expected"], sort_keys=True, allow_nan=False, separators=(",", ":"))
                passed += actual == expected
            except (ValueError, TypeError, json.JSONDecodeError):
                return response(key, "error", total=total, error="invalid_function_result")
        finally:
            cleanup_deadline = time.monotonic() + CLEANUP_SECONDS
            try:
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    try:
                        process.wait(timeout=max(.001, cleanup_deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        # The runtime, rather than its local CLI process, confirms
                        # termination of all guest processes below.
                        pass
            finally:
                if process is not None:
                    process.stdout.close(); process.stderr.close()
                    if not process.stdin.closed:
                        process.stdin.close()
                if allocated:
                    try:
                        cleanup(name, deadline=cleanup_deadline)
                    except NotReady:
                        policy.state.joinpath("quarantined").write_text("cleanup_not_confirmed")
                        raise
    return response(key, "finished", passed=passed, total=total)
