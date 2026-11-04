"""A seccomp filter that lets code start threads but no other process, for the bwrap sandbox.

The audit hook in code_sandbox refuses os.fork and subprocess, but ctypes can call libc's
fork past it, and a fork bomb could use up the host's process IDs. RLIMIT_NPROC doesn't
apply to root, and a cgroup isn't writable on an ordinary CI runner, so the kernel's
seccomp does it: bwrap installs this program (--seccomp) before running the code.

The program, for the machine's own architecture only (any other kills the process, so a
32-bit or x32 syscall can't get around it):
- fork and vfork: refused with EPERM.
- clone: allowed with CLONE_THREAD (a thread), refused with EPERM otherwise.
- clone3: refused with ENOSYS, because its flags are in memory a filter can't read; glibc
  then falls back to clone, so threads still start.
- everything else: allowed. The rest of the sandbox is bwrap's job.

Written out in classic BPF by hand from the kernel's seccomp documentation
(Documentation/userspace-api/seccomp_filter.rst), so no library is needed.
"""
import errno
import platform
import struct
from dataclasses import dataclass

# struct seccomp_data: int nr; __u32 arch; __u64 instruction_pointer; __u64 args[6]
NR_OFFSET, ARCH_OFFSET, FIRST_ARG_OFFSET = 0, 4, 16

# classic BPF opcodes
LOAD_WORD = 0x20  # BPF_LD | BPF_W | BPF_ABS
JUMP_IF_EQUAL = 0x15  # BPF_JMP | BPF_JEQ | BPF_K
JUMP_IF_AT_LEAST = 0x35  # BPF_JMP | BPF_JGE | BPF_K
JUMP_IF_ANY_BIT = 0x45  # BPF_JMP | BPF_JSET | BPF_K
RETURN = 0x06  # BPF_RET | BPF_K

ALLOW = 0x7FFF0000
KILL_PROCESS = 0x80000000
CLONE_THREAD = 0x00010000
X32_SYSCALL_BIT = 0x40000000


def refuse_with(code):
    return 0x00050000 | code  # SECCOMP_RET_ERRNO


@dataclass(frozen=True)
class Machine:
    audit_arch: int
    clone: int
    clone3: int
    forks: tuple[int, ...]  # fork and vfork, where the architecture has them
    has_x32: bool = False


MACHINES = {
    "x86_64": Machine(audit_arch=0xC000003E, clone=56, clone3=435, forks=(57, 58), has_x32=True),
    "aarch64": Machine(audit_arch=0xC00000B7, clone=220, clone3=435, forks=()),
}


def machine() -> Machine | None:
    return MACHINES.get(platform.machine())


def _instruction(code, jump_true, jump_false, value):
    return struct.pack("=HBBI", code, jump_true, jump_false, value)


def program(target: Machine) -> bytes:
    """The filter, as the bytes bwrap's --seccomp reads."""
    # each step: (code, label to jump to if true, label if false, value); a label is a step's
    # name, and None falls through to the next step
    steps = [
        ("arch", LOAD_WORD, None, None, ARCH_OFFSET),
        ("own_arch", JUMP_IF_EQUAL, None, "kill", target.audit_arch),
        ("nr", LOAD_WORD, None, None, NR_OFFSET),
    ]
    if target.has_x32:
        steps.append(("x32", JUMP_IF_AT_LEAST, "kill", None, X32_SYSCALL_BIT))
    steps += [(f"fork_{number}", JUMP_IF_EQUAL, "refuse", None, number) for number in target.forks]
    steps += [
        ("clone3", JUMP_IF_EQUAL, "no_clone3", None, target.clone3),
        ("clone", JUMP_IF_EQUAL, "flags", "allow", target.clone),
        ("flags", LOAD_WORD, None, None, FIRST_ARG_OFFSET),  # clone's flags, the low word of its first argument
        ("thread", JUMP_IF_ANY_BIT, "allow", "refuse", CLONE_THREAD),
        ("allow", RETURN, None, None, ALLOW),
        ("refuse", RETURN, None, None, refuse_with(errno.EPERM)),
        ("no_clone3", RETURN, None, None, refuse_with(errno.ENOSYS)),
        ("kill", RETURN, None, None, KILL_PROCESS),
    ]
    position = {name: index for index, (name, *_) in enumerate(steps)}

    def offset(here, label):
        return 0 if label is None else position[label] - here - 1  # jumps count from the next step

    return b"".join(_instruction(code, offset(here, if_true), offset(here, if_false), value)
                    for here, (_, code, if_true, if_false, value) in enumerate(steps))
