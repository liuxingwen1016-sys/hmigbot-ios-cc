"""Filesystem boundaries and visible file-count progress for offline installers.

Persist ordinary paths in records; only Win32 I/O calls use extended paths.
No registry changes or global monkey-patches are required.
"""
from contextlib import contextmanager
import os
import shutil
import sys
import time


def fs_path(value):
    if os.name != "nt" or isinstance(value, int):
        return value
    path = os.fsdecode(value)
    if path.startswith("\\\\?\\"):
        return path
    path = os.path.abspath(path)
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def ordinary_path(value):
    value = os.fsdecode(value)
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    return value[4:] if value.startswith("\\\\?\\") else value


def walk_files(root, *args, **kwargs):
    # os.walk yields its extended input prefix; callers expect normal paths for
    # relpath, ownership checks and persistent JSON records.
    for directory, dirs, files in os.walk(fs_path(root), *args, **kwargs):
        yield ordinary_path(directory), dirs, files


def count_files(root, excludes=(), ignore=None):
    root = ordinary_path(os.fsdecode(root))
    if not os.path.isdir(fs_path(root)):
        return 1
    total = 0
    for directory, dirs, files in walk_files(root):
        ignored = set(ignore(directory, dirs + files)) if ignore else set()
        def selected(name):
            relative = os.path.relpath(os.path.join(directory, name), root).replace(os.sep, "/")
            return name not in ignored and not any(relative == x or relative.startswith(x + "/") for x in excludes)
        dirs[:] = [name for name in dirs if selected(name)]
        total += sum(selected(name) for name in files)
    return total


class Progress:
    def __init__(self, label, total):
        self.label, self.total, self.done = label, total, 0
        self.last = 0
        self.emit()

    def emit(self):
        self.last = time.monotonic()
        percent = 100 * self.done / self.total if self.total else 100
        print(f"[install] {self.label}: {self.done}/{self.total} files ({percent:.0f}%)", file=sys.stderr, flush=True)

    def advance(self, amount=1):
        self.done += amount
        if self.done == self.total or time.monotonic() - self.last >= 1:
            self.emit()


_copy_progress = None
_hash_progress = None


@contextmanager
def hashing(label, total):
    global _hash_progress
    previous = _hash_progress
    _hash_progress = Progress(label, total)
    try:
        yield _hash_progress
    finally:
        _hash_progress = previous


def hashed_file():
    if _hash_progress is not None:
        _hash_progress.advance()


def copy_file(source, destination, **kwargs):
    result = shutil.copy2(fs_path(source), fs_path(destination), **kwargs)
    if _copy_progress is not None:
        _copy_progress.advance()
    return ordinary_path(result)


def copy_tree(source, destination, **kwargs):
    global _copy_progress
    previous = _copy_progress
    if previous is None:
        print("[install] Counting files to copy...", file=sys.stderr, flush=True)
        _copy_progress = Progress("Copy " + os.path.basename(os.path.normpath(source)), count_files(source, ignore=kwargs.get("ignore")))
    try:
        kwargs["copy_function"] = copy_file
        result = shutil.copytree(fs_path(source), fs_path(destination), **kwargs)
        return ordinary_path(result)
    finally:
        _copy_progress = previous
