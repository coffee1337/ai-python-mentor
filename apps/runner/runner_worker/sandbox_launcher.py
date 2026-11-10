"""Trusted bootstrap that drops every capability before learner code is parsed.

The runner starts this file as a separate process, hands it a JSON policy
document and never lets the child touch the host outside the policy: rlimits,
a fresh process group, ``no_new_privs``, a Landlock domain with an explicit
read/write allow-list, and then an exec into CPython that installs a seccomp
filter before the learner source is compiled.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sandbox_guest  # noqa: E402
import sandbox_kernel  # noqa: E402


def main() -> None:
    config = json.loads(open(sys.argv[1], "rb").read().decode("utf-8"))
    sandbox_kernel.apply_rlimits(
        cpu_seconds=int(config["cpu_seconds"]),
        address_space=int(config["address_space"]),
        file_size=int(config["file_size"]),
        open_files=int(config["open_files"]),
    )
    os.setsid()
    sandbox_kernel.set_no_new_privs()

    abi = sandbox_kernel.landlock_abi()
    if abi < 4:
        os.write(2, b"sandbox_unavailable\n")
        os._exit(78)
    ruleset = sandbox_kernel.create_ruleset(
        sandbox_kernel.FS_ALL,
        sandbox_kernel.NET_BIND_TCP | sandbox_kernel.NET_CONNECT_TCP,
        sandbox_kernel.SCOPE_ABSTRACT_UNIX_SOCKET | sandbox_kernel.SCOPE_SIGNAL,
        abi=abi,
    )
    read_only = None
    for path in config["read_paths"]:
        sandbox_kernel.add_path_rule(ruleset, path, read_only)
    sandbox_kernel.add_path_rule(ruleset, config["job_dir"], sandbox_kernel.FS_ALL)
    sandbox_kernel.restrict_self(ruleset)
    os.close(ruleset)

    os.chdir(config["job_dir"])
    os.environ.clear()
    os.environ.update({
        "PATH": "/usr/bin:/bin",
        "TMPDIR": config["job_dir"],
        "HOME": config["job_dir"],
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "SANDBOX_JOB": config["job_id"],
        "SANDBOX_PROFILE": "landlock-seccomp-v1",
    })
    executable = config["python"]
    os.execve(executable, [executable, "-I", "-S", "-u", "-c", sandbox_guest.PROGRAM], os.environ)
    os._exit(79)


if __name__ == "__main__":
    main()
