"""Process-scoped CLI device/output ownership; the OS releases locks on exit."""
from __future__ import annotations

import getpass
import hashlib
import os
from pathlib import Path
import tempfile


class DeviceBusyError(RuntimeError):
    pass


class OutputBusyError(RuntimeError):
    pass


class _Lease:
    error_type = RuntimeError

    def __init__(self, namespace: str, key: str, message: str):
        owner = str(os.getuid()) if hasattr(os, "getuid") else getpass.getuser()
        owner_key = hashlib.sha256(owner.encode()).hexdigest()[:16]
        root = Path(tempfile.gettempdir()) / f"aft-{namespace}-locks-{owner_key}"
        self.path = root / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
        self.message = message
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b" ")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise self.error_type(self.message) from exc
        self.fd = fd
        return self

    def __exit__(self, *_):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            # Keep the file: deleting it would let another process lock a different inode.
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


class DeviceLease(_Lease):
    error_type = DeviceBusyError

    def __init__(self, serial: str):
        self.serial = serial
        super().__init__("device", serial,
                         f"device {serial!r} is owned by another android_fast_traverse command; "
                         "wait for it to finish (burst can use --trigger in the same process)")


class OutputLease(_Lease):
    error_type = OutputBusyError

    def __init__(self, out: str | Path):
        # Canonical paths also make two symlink spellings share one lock. Keep the
        # lock outside OUT: acquiring ownership must not make burst's directory nonempty.
        self.out = Path(out).resolve()
        super().__init__("output", os.path.normcase(str(self.out)),
                         f"output {str(self.out)!r} is owned by another android_fast_traverse command; "
                         "wait for it to finish, even when using a different device")
