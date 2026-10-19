#!/usr/bin/env python3
import argparse
import json
import plistlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from python_support import install


def package(source, framework, output):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(source) as archive:
            archive.extractall(root)
        apps = list((root / "Payload").glob("*.app"))
        if len(apps) != 1:
            raise RuntimeError("Expected exactly one application in the upstream IPA")
        app = apps[0]
        install(app, framework)
        info_path = app / "Info.plist"
        info = plistlib.loads(info_path.read_bytes())
        info["CFBundleDisplayName"] = "exteraGram"
        info["UIFileSharingEnabled"] = True
        info["LSSupportsOpeningDocumentsInPlace"] = True
        # Reuse the existing Android project's exteraGram artwork.
        artwork = Path(__file__).resolve().parents[1] / "app-icon.png"
        for name, size in (("ExteraIcon60@2x.png", 120), ("ExteraIcon60@3x.png", 180),
                           ("ExteraIcon76.png", 76), ("ExteraIcon76@2x.png", 152),
                           ("ExteraIcon83.5@2x.png", 167)):
            subprocess.run(["sips", "-z", str(size), str(size), str(artwork), "--out", str(app / name)],
                           check=True, stdout=subprocess.DEVNULL)
        info["CFBundleIcons"] = {"CFBundlePrimaryIcon": {"CFBundleIconFiles": ["ExteraIcon60"]}}
        info["CFBundleIcons~ipad"] = {"CFBundlePrimaryIcon": {"CFBundleIconFiles": ["ExteraIcon60", "ExteraIcon76", "ExteraIcon83.5"]}}
        info_path.write_bytes(plistlib.dumps(info))
        (app / "embedded.mobileprovision").unlink(missing_ok=True)
        # Ad-hoc signing is packaging for a jailbreak/sideload environment. It
        # does not provide an Apple provisioning profile or an APNs identity.
        entitlements = {
            "application-identifier": "EXTERA0000." + info["CFBundleIdentifier"],
            "keychain-access-groups": ["EXTERA0000." + info["CFBundleIdentifier"]],
            "com.apple.security.application-groups": ["group." + info["CFBundleIdentifier"]],
        }
        entitlement_path = root / "entitlements.plist"
        entitlement_path.write_bytes(plistlib.dumps(entitlements))
        subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", "--generate-entitlement-der",
                        "--entitlements", str(entitlement_path), str(app)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted((root / "Payload").rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(root))
        print("Created", output.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("framework", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    package(args.source, args.framework, args.output)
