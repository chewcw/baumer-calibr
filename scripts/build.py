#!/usr/bin/env python3
"""Build a standalone baumer-calib bundle (PyInstaller --onedir) for this OS.

Cross-platform on purpose: run it identically on Linux, Windows and macOS CI
runners (and locally). Steps:

  1. ensure Baumer neoAPI is installed (extracts the matching vendor wheel
     from vendor/ when the platform has one; macOS has none -> offline-only
     bundle: calibrate/verify work, camera commands fail with a clear error)
  2. ensure PyInstaller is installed
  3. build dist/baumer-calib/ (onedir; onedir avoids the self-extract overhead
     and antivirus false-positives of --onefile, and plays nicer with the
     dynamically loaded native libs in cv2/neoapi)
  4. smoke-test the produced binary (--help)
  5. archive -> dist/baumer-calib-<version>-<os>-<arch>.zip|.tar.gz
     + <archive>.sha256 sidecar

Version precedence: --version arg > $BUILD_VERSION (set from git tag in CI)
> project version from pyproject.toml.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP = "baumer-calib"
PYPROJECT = ROOT / "pyproject.toml"


def log(msg: str = "") -> None:
    print(msg, flush=True)


def run(cmd: list[str]) -> None:
    log("$ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def os_tag() -> str:
    return {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}[
        platform.system()
    ]


def arch_tag() -> str:
    m = platform.machine().lower()
    return {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(m, m)


def default_version() -> str:
    import tomllib

    try:
        return tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    except Exception:
        return "0.0.0"


def installer(*pkgs: Path | str) -> list[str]:
    """Install into the current interpreter's env: prefer uv, fall back to pip."""
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", sys.executable, *map(str, pkgs)]
    return [sys.executable, "-m", "pip", "install", *map(str, pkgs)]


def extract_vendor_wheel() -> Path | None:
    """Unpack the neoAPI wheel matching this OS from vendor/ into build/vendor/."""
    vendor = ROOT / "vendor"
    if not vendor.is_dir():
        return None
    tag = os_tag()
    dest = BUILD / "vendor"
    dest.mkdir(parents=True, exist_ok=True)
    if tag == "linux":
        archives = sorted(vendor.glob("Baumer_neoAPI_*_lin_x86_64_python.tar.gz"))
        if not archives:
            return None
        with tarfile.open(archives[-1]) as tf:
            tf.extractall(dest)  # trusted: our own vendor bundle
    elif tag == "windows":
        archives = sorted(vendor.glob("Baumer_neoAPI_*_win_x86_64_python.zip"))
        if not archives:
            return None
        with zipfile.ZipFile(archives[-1]) as zf:
            zf.extractall(dest)  # trusted: our own vendor bundle
    else:
        # Baumer ships no neoAPI wheel for macOS; keep bundle offline-only.
        return None
    wheels = sorted(dest.rglob("*.whl"))
    return wheels[0] if wheels else None


def ensure_neoapi() -> bool:
    if importlib.util.find_spec("neoapi") is not None:
        log("neoapi: already installed")
        return True
    wheel = extract_vendor_wheel()
    if wheel is None:
        log(
            f"WARNING [{os_tag()}]: no vendor neoAPI wheel for this platform - "
            "building offline-only bundle (calibrate/make-board/verify-folder work; "
            "capture/upload/read need Linux or Windows)"
        )
        return False
    run(installer(wheel))
    if importlib.util.find_spec("neoapi") is None:
        raise SystemExit(f"neoapi still not importable after installing {wheel}")
    return True


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        run(installer("pyinstaller>=6.0"))


def build(has_neoapi: bool) -> Path:
    exe = DIST / APP / (APP + (".exe" if os_tag() == "windows" else ""))
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        APP,
        "--distpath",
        DIST,
        "--workpath",
        BUILD / "pyinstaller",
        "--specpath",
        BUILD,
        "--paths",
        ROOT / "src",
    ]
    if has_neoapi:
        cmd += ["--collect-all", "neoapi"]
    cmd += [ROOT / "src" / "baumer_calib" / "cli.py"]
    run(cmd)
    if not exe.is_file():
        raise SystemExit(f"expected binary missing: {exe}")
    return exe


def smoke_test(exe: Path) -> None:
    log(f"smoke test: {exe} --help")
    subprocess.run(
        [str(exe), "--help"], check=True, cwd=ROOT, stdout=subprocess.DEVNULL
    )


def archive(version: str) -> Path:
    base = f"{APP}-{version}-{os_tag()}-{arch_tag()}"
    for stale in DIST.glob(f"{APP}-*"):
        if stale.is_file() and stale.name.endswith((".zip", ".tar.gz", ".sha256")):
            stale.unlink()
    fmt = "zip" if os_tag() == "windows" else "gztar"
    out = Path(shutil.make_archive(str(DIST / base), fmt, root_dir=DIST, base_dir=APP))
    digest = hashlib.sha256()
    with out.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    sidecar = out.with_name(out.name + ".sha256")
    sidecar.write_text(f"{digest.hexdigest()}  {out.name}\n")
    log(f"sha256: {digest.hexdigest()}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="build baumer-calib executable bundle")
    ap.add_argument(
        "--version",
        default=os.environ.get("BUILD_VERSION") or "",
        help="version tag (default: $BUILD_VERSION or pyproject)",
    )
    args = ap.parse_args()
    version = args.version or default_version()

    log(
        f"building {APP} {version} for {os_tag()}/{arch_tag()} "
        f"python {platform.python_version()}"
    )
    shutil.rmtree(DIST, ignore_errors=True)
    has_neoapi = ensure_neoapi()
    ensure_pyinstaller()
    exe = build(has_neoapi)
    smoke_test(exe)
    out = archive(version)
    log(f"OK -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
