#!/usr/bin/env python3
"""Fetch the checksum-pinned Python SDK and install its runtime in an app."""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

IOS = Path(__file__).resolve().parents[1]
LOCK = json.loads((IOS / "upstream.json").read_text())


def download(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "python.tar.gz"
        urllib.request.urlretrieve(LOCK["python_url"], archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != LOCK["python_sha256"]:
            raise RuntimeError("Python archive checksum mismatch")
        # Explicitly reject paths and symlinks escaping the archive root.
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                path = (destination / member.name).resolve()
                if not path.is_relative_to(destination.resolve()):
                    raise RuntimeError("Unsafe path in Python support archive")
                if member.issym() and not (path.parent / member.linkname).resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError("Unsafe symlink in Python support archive")
                if member.isdev() or member.isfifo():
                    raise RuntimeError("Unexpected special file in Python support archive")
            tar.extractall(destination, filter="data")
    return destination / "Python.xcframework"


def install(app, framework, platform="device", sign=True):
    app, framework = Path(app).resolve(), Path(framework).resolve()
    slice_name = "ios-arm64" if platform == "device" else "ios-arm64_x86_64-simulator"
    architecture = "arm64" if platform == "device" else os.uname().machine
    slice_path = framework / slice_name
    if not slice_path.is_dir():
        raise RuntimeError("Missing Python slice: " + str(slice_path))
    root = app / "ExteraPython"
    root.mkdir(exist_ok=True)
    stdlib = root / "stdlib"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "test", "tests", "tkinter", "idlelib", "ensurepip")
    shutil.copytree(framework / "lib/python3.13", stdlib, dirs_exist_ok=True, ignore=ignore)
    architecture_lib = slice_path / ("lib-" + architecture) / "python3.13"
    for file in architecture_lib.glob("*.py"):
        shutil.copyfile(file, stdlib / file.name)
    shutil.copytree(IOS / "python", root / "sdk", dirs_exist_ok=True, ignore=ignore)
    dynload = root / "lib-dynload"
    dynload.mkdir(exist_ok=True)
    frameworks = app / "Frameworks"
    frameworks.mkdir(exist_ok=True)
    shutil.copytree(slice_path / "Python.framework", frameworks / "Python.framework", dirs_exist_ok=True)
    for file in (architecture_lib / "lib-dynload").glob("*.so"):
        name = file.name.split(".")[0]
        if name.startswith(("_test", "xx", "_xx")):
            continue
        directory = frameworks / (name + ".framework")
        directory.mkdir(exist_ok=True)
        shutil.copy2(file, directory / name)
        info = {
            "CFBundleExecutable": name,
            "CFBundleIdentifier": "app.exteragram.python." + name.replace("_", "-"),
            "CFBundleName": name,
            "CFBundlePackageType": "FMWK",
            "CFBundleVersion": "1",
            "CFBundleShortVersionString": "1.0",
            "MinimumOSVersion": "15.0",
            "CFBundleSupportedPlatforms": ["iPhoneOS" if platform == "device" else "iPhoneSimulator"],
        }
        (directory / "Info.plist").write_bytes(plistlib.dumps(info))
        marker = dynload / (file.name[:-3] + ".fwork")
        marker.write_text(str((directory / name).relative_to(app)) + "\n")
        (directory / (name + ".origin")).write_text(str(marker.relative_to(app)) + "\n")
    if sign:
        for directory in frameworks.glob("*.framework"):
            subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(directory)], check=True)
    if not (stdlib / "encodings/__init__.py").exists() or not list(dynload.glob("*.fwork")):
        raise RuntimeError("Incomplete Python resource bundle")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="op", required=True)
    fetch = sub.add_parser("download")
    fetch.add_argument("destination", type=Path)
    add = sub.add_parser("install")
    add.add_argument("app", type=Path)
    add.add_argument("framework", type=Path)
    add.add_argument("--platform", choices=["device", "simulator"], default="device")
    add.add_argument("--no-sign", action="store_true")
    args = parser.parse_args()
    if args.op == "download":
        print(download(args.destination))
    else:
        install(args.app, args.framework, args.platform, sign=not args.no_sign)
