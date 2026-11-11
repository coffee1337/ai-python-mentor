"""Unprivileged kernel sandbox primitives: Landlock LSM, seccomp-BPF, rlimits.

Used by the runner host to build policies and by the launcher that applies them
inside the child process before any learner source is compiled.

Nothing here needs root: Landlock and seccomp filters are available to
unprivileged processes as soon as ``no_new_privs`` is set.
"""
from __future__ import annotations

import ctypes
import errno
import os
import struct

_libc = ctypes.CDLL("libc.so.6", use_errno=True)

SYS_landlock_create_ruleset = 444
SYS_landlock_add_rule = 445
SYS_landlock_restrict_self = 446

LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1

# Filesystem access rights (uapi/linux/landlock.h).
FS_EXECUTE = 1 << 0
FS_WRITE_FILE = 1 << 1
FS_READ_FILE = 1 << 2
FS_READ_DIR = 1 << 3
FS_REMOVE_DIR = 1 << 4
FS_REMOVE_FILE = 1 << 5
FS_MAKE_CHAR = 1 << 6
FS_MAKE_DIR = 1 << 7
FS_MAKE_REG = 1 << 8
FS_MAKE_SOCK = 1 << 9
FS_MAKE_FIFO = 1 << 10
FS_MAKE_BLOCK = 1 << 11
FS_MAKE_SYM = 1 << 12
FS_REFER = 1 << 13          # ABI 2
FS_TRUNCATE = 1 << 14       # ABI 3
FS_IOCTL_DEV = 1 << 15      # ABI 5

NET_BIND_TCP = 1 << 0       # ABI 4
NET_CONNECT_TCP = 1 << 1    # ABI 4

SCOPE_ABSTRACT_UNIX_SOCKET = 1 << 0  # ABI 6
SCOPE_SIGNAL = 1 << 1                # ABI 6

FS_ALL = (1 << 16) - 1

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000

AUDIT_ARCH_X86_64 = 0xC000003E
X32_SYSCALL_BIT = 0x40000000

# Architecture name -> (audit arch, syscall table) so the filter can be built
# for the machine it actually runs on.
_ARCH = {
    "x86_64": (AUDIT_ARCH_X86_64, {
        "fork": 57, "vfork": 58, "clone": 56, "clone3": 435,
        "execve": 59, "execveat": 322,
        "socket": 41, "socketpair": 53, "connect": 42, "bind": 49,
        "listen": 50, "accept": 43, "accept4": 288, "sendto": 44, "recvfrom": 45,
        "ptrace": 101, "process_vm_readv": 310, "process_vm_writev": 311,
        "mount": 165, "umount2": 166, "pivot_root": 155, "chroot": 161,
        "unshare": 272, "setns": 308, "setuid": 105, "setgid": 106,
        "setreuid": 113, "setregid": 114, "setresuid": 117, "setresgid": 119,
        "keyctl": 250, "add_key": 248, "request_key": 249,
        "bpf": 321, "perf_event_open": 298,
        "kexec_load": 246, "kexec_file_load": 320,
        "init_module": 175, "finit_module": 313, "delete_module": 176,
        "reboot": 169, "swapon": 167, "swapoff": 168,
        "sethostname": 170, "setdomainname": 171,
        "io_uring_setup": 425, "io_uring_enter": 426, "io_uring_register": 427,
        "userfaultfd": 323, "open_by_handle_at": 304, "name_to_handle_at": 303,
        "mknod": 133, "mknodat": 259, "syslog": 103, "acct": 163, "quotactl": 179,
        "fanotify_init": 300, "migrate_pages": 256, "mbind": 237, "set_mempolicy": 238,
        "memfd_create": 319, "pidfd_getfd": 438, "process_madvise": 440,
        "vhangup": 153, "chown": 92, "fchown": 93, "lchown": 94, "fchownat": 260,
    }),
}


def _raise(ret: int, what: str, allow_errno: tuple[int, ...] = ()) -> int:
    if ret < 0:
        code = ctypes.get_errno()
        if code in allow_errno:
            return ret
        raise OSError(code, f"{what}: {os.strerror(code)}")
    return ret


def landlock_abi() -> int:
    """Return the Landlock ABI version, or 0 when the kernel lacks it."""
    ret = _libc.syscall(
        SYS_landlock_create_ruleset, None, ctypes.c_size_t(0),
        ctypes.c_uint32(LANDLOCK_CREATE_RULESET_VERSION),
    )
    if ret < 0:
        return 0
    return int(ret)


def create_ruleset(handled_fs: int, handled_net: int = 0, scoped: int = 0, abi: int | None = None) -> int:
    """Create a Landlock ruleset; unsupported fields are dropped by ABI level."""
    abi = landlock_abi() if abi is None else abi
    if abi <= 0:
        raise OSError(errno.ENOSYS, "landlock unavailable")
    if abi >= 6:
        attr = struct.pack("QQQ", handled_fs, handled_net, scoped)
    elif abi >= 4:
        attr = struct.pack("QQ", handled_fs, handled_net)
    else:
        attr = struct.pack("Q", handled_fs)
    ret = _libc.syscall(
        SYS_landlock_create_ruleset, attr, ctypes.c_size_t(len(attr)), ctypes.c_uint32(0),
    )
    return _raise(ret, "landlock_create_ruleset")


def add_path_rule(ruleset_fd: int, path: str, allowed_access: int | None = None) -> None:
    """Allow ``allowed_access`` beneath ``path`` (best effort for missing paths).

    ``None`` selects the rights that are valid for the path type: directories
    get read/execute, files and devices get read (plus write for stdio).
    """
    try:
        parent = os.open(path, os.O_PATH | os.O_CLOEXEC)
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.EACCES):
            return
        raise
    try:
        if allowed_access is None:
            import stat as _stat

            mode = os.fstat(parent).st_mode
            if _stat.S_ISDIR(mode):
                allowed_access = FS_EXECUTE | FS_READ_FILE | FS_READ_DIR
            else:
                allowed_access = FS_READ_FILE | FS_WRITE_FILE
                if landlock_abi() >= 5:
                    allowed_access |= FS_IOCTL_DEV
        attr = struct.pack("Qi", allowed_access, parent)
        ret = _libc.syscall(
            SYS_landlock_add_rule, ruleset_fd,
            ctypes.c_int(LANDLOCK_RULE_PATH_BENEATH), attr, ctypes.c_uint32(0),
        )
        _raise(ret, f"landlock_add_rule({path})")
    finally:
        os.close(parent)


def restrict_self(ruleset_fd: int) -> None:
    ret = _libc.syscall(SYS_landlock_restrict_self, ruleset_fd, ctypes.c_uint32(0))
    _raise(ret, "landlock_restrict_self")


def set_no_new_privs() -> None:
    ret = _libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    _raise(ret, "prctl(NO_NEW_PRIVS)")


class _SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class _SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_SockFilter))]


BPF_LD_W_ABS = 0x20
BPF_JEQ_K = 0x15
BPF_JGE_K = 0x35
BPF_RET_K = 0x06


def seccomp_program(denied: list[int], audit_arch: int, arch: str = "x86_64") -> list[tuple[int, int, int, int]]:
    """Assemble a classic-BPF filter that returns EPERM for ``denied`` syscalls."""
    program: list[tuple[int, int, int, int]] = [
        (BPF_LD_W_ABS, 0, 0, 4),                      # A = arch
        (BPF_JEQ_K, 1, 0, audit_arch),                # if arch == audit_arch -> next
        (BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),  # foreign arch: kill
        (BPF_LD_W_ABS, 0, 0, 0),                      # A = syscall nr
    ]
    if arch == "x86_64":
        # Reject the x32 ABI range before the allow-list comparisons.
        program += [(BPF_JGE_K, 0, 1, X32_SYSCALL_BIT), (BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM)]
    for number in sorted(set(denied)):
        program += [(BPF_JEQ_K, 0, 1, number), (BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM)]
    program.append((BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW))
    return program


def install_seccomp_filter(program: list[tuple[int, int, int, int]]) -> None:
    """Install an already-assembled filter on the current process."""
    filters = (_SockFilter * len(program))(
        *[_SockFilter(code, jt, jf, k) for code, jt, jf, k in program]
    )
    fprog = _SockFprog(len(program), filters)
    set_no_new_privs()
    ret = _libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0)
    _raise(ret, "prctl(SET_SECCOMP)")


def denied_numbers(names: list[str], arch: str | None = None) -> list[int]:
    arch = arch or os.uname().machine
    table = _ARCH[arch][1]
    return [table[name] for name in names]


def audit_arch(arch: str | None = None) -> int:
    arch = arch or os.uname().machine
    return _ARCH[arch][0]


def apply_rlimits(*, cpu_seconds: int, address_space: int, file_size: int,
                  open_files: int, processes: int = 0) -> None:
    """Per-process resource caps. RLIMIT_NPROC is skipped on shared uids."""
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
    resource.setrlimit(resource.RLIMIT_NOFILE, (open_files, open_files))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if processes > 0:
        resource.setrlimit(resource.RLIMIT_NPROC, (processes, processes))


def runtime_read_paths(python_executable: str) -> list[str]:
    """Minimal read-only allow-list needed to start CPython and its stdlib."""
    import sysconfig

    paths = {
        sysconfig.get_paths()["stdlib"],
        sysconfig.get_paths()["platstdlib"],
        "/usr/lib/x86_64-linux-gnu",
        "/lib/x86_64-linux-gnu",
        "/usr/lib64",
        "/lib64",
        "/usr/local/lib",
        "/etc/ld.so.cache",
        "/dev/null",
        "/dev/urandom",
        "/dev/zero",
        python_executable,
    }
    base = os.path.dirname(os.path.dirname(os.path.realpath(python_executable)))
    paths.add(base)
    return sorted(p for p in paths if p and os.path.exists(p))


def current_syscall_names() -> list[str]:
    return sorted(_ARCH[os.uname().machine][1])
