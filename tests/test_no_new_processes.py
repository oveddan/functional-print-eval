"""The seccomp filter that stops run_python's code starting processes under bwrap, checked
instruction by instruction with a small classic-BPF interpreter, on both architectures."""
import errno
import struct

import pytest

from pbe.runner import no_new_processes as filters
from pbe.runner.no_new_processes import ALLOW, CLONE_THREAD, KILL_PROCESS, MACHINES, refuse_with


def run_filter(program: bytes, arch: int, nr: int, first_arg: int = 0) -> int:
    """What the kernel would do with one syscall: the value the program returns."""
    data = struct.pack("=iIQ6Q", nr, arch, 0, first_arg, 0, 0, 0, 0, 0)
    instructions = [struct.unpack("=HBBI", program[i:i + 8]) for i in range(0, len(program), 8)]
    accumulator, here = 0, 0
    while True:
        code, jump_true, jump_false, value = instructions[here]
        if code == filters.LOAD_WORD:
            accumulator = struct.unpack_from("=I", data, value)[0]
            here += 1
        elif code == filters.RETURN:
            return value
        else:
            taken = {filters.JUMP_IF_EQUAL: accumulator == value, filters.JUMP_IF_AT_LEAST: accumulator >= value,
                     filters.JUMP_IF_ANY_BIT: bool(accumulator & value)}[code]
            here += 1 + (jump_true if taken else jump_false)


@pytest.mark.parametrize("name", list(MACHINES))
def test_threads_yes_processes_no(name):
    target = MACHINES[name]
    program = filters.program(target)
    for fork in target.forks:
        assert run_filter(program, target.audit_arch, fork) == refuse_with(errno.EPERM)
    assert run_filter(program, target.audit_arch, target.clone, CLONE_THREAD | 0x3D0F00) == ALLOW  # pthread_create's flags
    assert run_filter(program, target.audit_arch, target.clone, 0x4111) == refuse_with(errno.EPERM)  # vfork-style clone
    assert run_filter(program, target.audit_arch, target.clone, 0) == refuse_with(errno.EPERM)
    assert run_filter(program, target.audit_arch, target.clone3) == refuse_with(errno.ENOSYS)  # glibc falls back to clone
    assert run_filter(program, target.audit_arch, 0) == ALLOW  # anything else


@pytest.mark.parametrize("name", list(MACHINES))
def test_another_architecture_is_killed(name):
    target = MACHINES[name]
    other = next(machine for key, machine in MACHINES.items() if key != name)
    assert run_filter(filters.program(target), other.audit_arch, 0) == KILL_PROCESS
    assert run_filter(filters.program(target), 0x40000003, 2) == KILL_PROCESS  # i386's fork


def test_x32_syscalls_are_killed():
    target = MACHINES["x86_64"]
    assert run_filter(filters.program(target), target.audit_arch, filters.X32_SYSCALL_BIT | 57) == KILL_PROCESS
