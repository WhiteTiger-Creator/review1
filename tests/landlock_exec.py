#!/usr/bin/env python3
"""Execute one candidate process inside a filesystem allow-list."""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from pathlib import Path
from typing import ClassVar

CREATE_RULESET = 444
ADD_RULE = 445
RESTRICT_SELF = 446
CREATE_RULESET_VERSION = 1
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
BASE_FS_RIGHTS = (1 << 13) - 1


class RulesetAttr(ctypes.Structure):
    _fields_: ClassVar = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_: ClassVar = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


def syscall(libc, number, *arguments):
    result = libc.syscall(number, *arguments)
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return result


def add_path_rule(libc, ruleset_fd, path, rights):
    descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
    try:
        rule = PathBeneathAttr(rights, descriptor)
        syscall(libc, ADD_RULE, ruleset_fd, RULE_PATH_BENEATH, ctypes.byref(rule), 0)
    finally:
        os.close(descriptor)


def enter_landlock(write_paths):
    libc = ctypes.CDLL(None, use_errno=True)
    abi = syscall(libc, CREATE_RULESET, 0, 0, CREATE_RULESET_VERSION)
    if abi < 1:
        raise RuntimeError("Landlock ABI is unavailable")
    handled = (
        BASE_FS_RIGHTS | ((1 << 13) if abi >= 2 else 0) | ((1 << 14) if abi >= 3 else 0)
    )
    ruleset = RulesetAttr(handled)
    ruleset_fd = syscall(
        libc,
        CREATE_RULESET,
        ctypes.byref(ruleset),
        ctypes.sizeof(ruleset),
        0,
    )
    try:
        readonly = EXECUTE | READ_FILE | READ_DIR
        for path in ("/app", "/bin", "/etc", "/lib", "/lib64", "/usr"):
            if Path(path).exists():
                add_path_rule(libc, ruleset_fd, path, readonly)
        for path in ("/dev/null", "/dev/urandom", "/dev/random", "/dev/zero"):
            if Path(path).exists():
                add_path_rule(libc, ruleset_fd, path, READ_FILE | WRITE_FILE)
        for path in write_paths:
            add_path_rule(libc, ruleset_fd, path, handled)
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        syscall(libc, RESTRICT_SELF, ruleset_fd, 0)
    finally:
        os.close(ruleset_fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="append", default=[])
    parser.add_argument("--uid", type=int, default=65534)
    parser.add_argument("--gid", type=int, default=65534)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    command = (
        arguments.command[1:] if arguments.command[:1] == ["--"] else arguments.command
    )
    if not command:
        parser.error("a command is required")
    enter_landlock(arguments.write)
    os.setgroups([])
    os.setgid(arguments.gid)
    os.setuid(arguments.uid)
    os.chdir("/app")
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"candidate sandbox failed: {error}", file=sys.stderr)
        raise SystemExit(126) from error
