"""Independent watchdog service; keep running when the HTTP worker crashes."""
import json
import time
from .execution import cleanup
from .policy import LABEL, Policy, NotReady, command

def reap(policy, *, force=False):
    ids = command(["docker", "ps", "--all", "--filter", f"label={LABEL}=true", "--format", "{{.ID}}"])
    for identifier in ids.decode().splitlines():
        details = json.loads(command(["docker", "inspect", identifier]))[0]
        deadline = float(details["Config"]["Labels"][f"{LABEL}.deadline"])
        if force or deadline <= time.time():
            cleanup(details["Name"].lstrip("/"))

def main():
    policy = Policy.from_environment()
    policy.state.mkdir(mode=0o700, parents=True, exist_ok=True)
    while True:
        try:
            # Cleanup continues even if an attestation expires or host is quarantined.
            reap(policy)
            policy.verify(require_reaper=False)
            policy.state.joinpath("reaper-heartbeat").write_text(str(time.time()))
        except Exception:
            policy.state.joinpath("quarantined").write_text("reaper_unavailable")
            print("runner_reaper_unavailable", flush=True)
        time.sleep(.5)

if __name__ == "__main__":
    main()
