"""Shared launcher support for the optional Nuitka execute bundle."""
from __future__ import annotations
import os, platform, subprocess, sys
from pathlib import Path

def bundled_executable(script_dir: str | os.PathLike[str]) -> Path | None:
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system())
    if system is None:
        return None
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    exe = Path(script_dir) / "bin" / f"{system}-{arch}" / "_entry.dist" / ("_entry.exe" if system == "windows" else "_entry.bin")
    return exe if exe.exists() else None

def dispatch(tool: str, argv: list[str] | None = None, fallback=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    exe = bundled_executable(Path(__file__).resolve().parent)
    if exe is not None:
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
    if fallback is None:
        sys.stderr.write(f"no bundled binary for {platform.system()}-{platform.machine()} and no Python fallback for {tool}\n")
        return 2
    result = fallback(argv)
    return int(result or 0)
