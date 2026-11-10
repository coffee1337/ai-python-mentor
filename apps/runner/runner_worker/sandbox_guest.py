"""Fixed guest program: seccomp guard followed by the grading shim.

The guard is inlined so it runs even though the sandbox hides every host path:
it is installed before the learner source is compiled, and it can never be
removed afterwards (no_new_privs + seccomp are irreversible).
"""
from __future__ import annotations

import os

from sandbox_kernel import denied_numbers

DENIED = (
    "fork", "vfork", "clone", "clone3", "execve", "execveat",
    "socket", "connect", "bind", "listen", "accept", "accept4",
    "ptrace", "process_vm_readv", "process_vm_writev",
    "mount", "umount2", "pivot_root", "chroot", "unshare", "setns",
    "setuid", "setgid", "setreuid", "setregid", "setresuid", "setresgid",
    "keyctl", "add_key", "request_key", "bpf", "perf_event_open",
    "kexec_load", "kexec_file_load", "init_module", "finit_module", "delete_module",
    "reboot", "swapon", "swapoff", "sethostname", "setdomainname",
    "io_uring_setup", "io_uring_enter", "io_uring_register",
    "userfaultfd", "open_by_handle_at", "name_to_handle_at",
    "mknod", "mknodat", "syslog", "acct", "quotactl", "fanotify_init",
    "migrate_pages", "mbind", "set_mempolicy", "memfd_create",
    "pidfd_getfd", "process_madvise", "vhangup",
    "chown", "fchown", "lchown", "fchownat",
)


def build_program() -> str:
    numbers = denied_numbers(list(DENIED))
    pairs = ", ".join(f"(0x15,0,1,{n}),(0x06,0,0,0x00050000|1)" for n in numbers)
    return f'''import ctypes,errno,os,struct
_libc=ctypes.CDLL("libc.so.6",use_errno=True)
class _SF(ctypes.Structure):
    _fields_=[("code",ctypes.c_ushort),("jt",ctypes.c_ubyte),("jf",ctypes.c_ubyte),("k",ctypes.c_uint32)]
class _FP(ctypes.Structure):
    _fields_=[("len",ctypes.c_ushort),("filter",ctypes.POINTER(_SF))]
_prog=[(0x20,0,0,4),(0x15,1,0,0xC000003E),(0x06,0,0,0x80000000),(0x20,0,0,0),
       (0x35,0,1,0x40000000),(0x06,0,0,0x00050000|1),{pairs},(0x06,0,0,0x7FFF0000)]
_f=(_SF*len(_prog))(*[_SF(*_i) for _i in _prog])
_fp=_FP(len(_prog),_f)
_libc.prctl(38,1,0,0,0)
if _libc.prctl(22,2,ctypes.byref(_fp),0,0)!=0:
    raise SystemExit(70)
'''


GUEST = """import contextlib,json,sys
payload=json.loads(sys.stdin.buffer.read(131073))
try:
    with contextlib.redirect_stdout(sys.stderr):
        namespace={}
        exec(compile(payload['source'],'<submission>','exec'),namespace)
        result=namespace['solve'](*payload['args'],**payload['kwargs'])
except MemoryError:
    sys.exit(75)
sys.stdout.write(json.dumps({'value':result},ensure_ascii=True,allow_nan=False,separators=(',',':')))
"""

PROGRAM = build_program() + GUEST

if __name__ == "__main__":
    sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"guard bytes: {len(build_program())} guest bytes: {len(GUEST)} path: {sys_path}")
