"""Process-lifetime exclusion for the owned database launcher.

operation.guard is permanent: deleting it could split one lock into two files.
The old operation.lock JSON marker requires explicit, evidence-preserving recovery.
"""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import stat

from .config import ConfigurationError


def _file_identity(path, fd):
    actual = os.fstat(fd)
    named = path.lstat()
    if (not stat.S_ISREG(actual.st_mode) or not stat.S_ISREG(named.st_mode)
            or actual.st_nlink != 1 or named.st_nlink != 1
            or (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino)
            or getattr(named, "st_file_attributes", 0) & 0x400):
        raise ConfigurationError("Runtime guard must be an ordinary local file without hard links.")
    return actual


def _acquire(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def runtime_lock(path):
    """Hold an OS lock until all owned database cleanup has completed."""
    path = Path(path)
    guard = path / "operation.guard"
    # Refuse special files before open (a FIFO could otherwise block).
    try:
        existing = guard.lstat()
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1:
            raise ConfigurationError("Runtime guard must be an ordinary local file without hard links.")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(guard, flags, 0o600)
    locked = False
    try:
        os.set_inheritable(fd, False)
        _file_identity(guard, fd)
        try:
            _acquire(fd)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise ConfigurationError(
                    "Another operation holds the Alliance runtime guard. "
                    "Wait for its launcher to finish; do not remove operation.guard.") from None
            raise
        locked = True
        info = _file_identity(guard, fd)
        if info.st_size not in (0, 1):
            raise ConfigurationError("Runtime guard has unexpected contents; preserve it for review.")
        os.lseek(fd, 0, os.SEEK_SET)
        if info.st_size == 1 and os.read(fd, 1) != b"\0":
            raise ConfigurationError("Runtime guard has unexpected contents; preserve it for review.")
        if info.st_size == 0:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.write(fd, b"\0") != 1:
                raise OSError("Could not initialize runtime guard.")
            os.fsync(fd)
        legacy = path / "operation.lock"
        try:
            legacy.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ConfigurationError(
                "A legacy operation.lock marker remains; its presence does not prove a live process. "
                "Use the reviewed Repair-WindowsAllianceRuntimeLock.ps1 recovery; "
                "do not delete database files or repeat initialization.")
        yield
    finally:
        try:
            if locked:
                _release(fd)
        finally:
            os.close(fd)
