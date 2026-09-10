"""Launch a collection command after denying network-related Linux syscalls."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Sequence

_ALLOW = 0x7FFF0000
_ERRNO_EPERM = 0x00050001
_BLOCKED_SYSCALLS = (b"socket", b"socketpair", b"connect", b"accept", b"accept4")


def install() -> None:
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_release.restype = None
    context = library.seccomp_init(_ALLOW)
    if not context:
        raise RuntimeError("could not initialize the network syscall guard")
    try:
        for name in _BLOCKED_SYSCALLS:
            syscall = library.seccomp_syscall_resolve_name(name)
            if syscall < 0 or library.seccomp_rule_add(context, _ERRNO_EPERM, syscall, 0) != 0:
                raise RuntimeError(f"could not block syscall {name.decode()}")
        if library.seccomp_load(context) != 0:
            raise RuntimeError("could not activate the network syscall guard")
    finally:
        library.seccomp_release(context)


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != "--":
        raise SystemExit("usage: python -m code_data_factory.interaction.network_guard -- <cdf arguments>")
    install()
    os.execv(sys.executable, [sys.executable, "-m", "code_data_factory.cli", *arguments[1:]])


if __name__ == "__main__":
    main()
