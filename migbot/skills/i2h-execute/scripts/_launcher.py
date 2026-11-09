"""Shared launcher support for the optional Nuitka execute bundle."""
from __future__ import annotations
import os, platform, subprocess, sys
from pathlib import Path


_LEGACY_MARKERS = (b"spec/.a2h", b"a2h-spec", b"a2h-plan", b"a2h-execute")
_CURRENT_MARKERS = (b"spec/.i2h", b"i2h-spec", b"i2h-plan", b"i2h-execute")

def bundled_executable(script_dir: str | os.PathLike[str]) -> Path | None:
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system())
    if system is None:
        return None
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    exe = Path(script_dir) / "bin" / f"{system}-{arch}" / "_entry.dist" / ("_entry.exe" if system == "windows" else "_entry.bin")
    return exe if exe.exists() else None


def bundle_compatibility(exe: Path) -> tuple[bool, str]:
    """Reject a binary compiled from the legacy Android execute sources.

    The repository can contain a stale Nuitka bundle after the Python sources
    have moved from ``a2h`` to ``i2h``.  Executing that bundle silently writes
    the wrong artifact paths.  A missing or unreadable compatibility marker is
    treated as stale so callers with a Python implementation can fall back
    deterministically.
    """
    try:
        payload = exe.read_bytes()
    except OSError as exc:
        return False, f"cannot read bundled binary: {exc}"
    legacy = [marker.decode("ascii") for marker in _LEGACY_MARKERS if marker in payload]
    current = any(marker in payload for marker in _CURRENT_MARKERS)
    if legacy:
        return False, "legacy bundle markers: " + ", ".join(legacy)
    if not current:
        return False, "bundle has no i2h compatibility marker"
    return True, "current i2h bundle"

def dispatch(tool: str, argv: list[str] | None = None, fallback=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    exe = bundled_executable(Path(__file__).resolve().parent)
    if exe is not None:
        compatible, reason = bundle_compatibility(exe)
        if compatible:
            dist = exe.parent
            if platform.system() == "Darwin":
                try:
                    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(dist)], check=False, capture_output=True)
                except OSError:
                    pass
            os.environ.setdefault("ARKTS_SKILL_DIR", str(Path(__file__).resolve().parent))
            cmd = [str(exe), tool, *argv]
            if platform.system() == "Windows":
                return subprocess.run(cmd).returncode
            os.execv(str(exe), cmd)
            return 0
        message = f"stale bundled binary for {tool}: {exe} ({reason})"
        if fallback is None:
            sys.stderr.write(message + "; no Python fallback is available\n")
            return 2
        sys.stderr.write(message + "; using Python fallback\n")
    if fallback is None:
        sys.stderr.write(f"no bundled binary for {platform.system()}-{platform.machine()} and no Python fallback for {tool}\n")
        return 2
    try:
        result = fallback(argv)
    except Exception as exc:
        # CLI entry points must preserve the pipeline's blocked/error exit
        # contract even when the Python fallback raises on stale evidence.
        # The caller still receives the diagnostic on stderr, while the
        # wrapper returns 2 instead of leaking an uncaught traceback as 1.
        sys.stderr.write(f"{tool} fallback failed: {exc}\n")
        return 2
    return int(result or 0)
