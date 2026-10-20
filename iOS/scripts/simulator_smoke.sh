#!/bin/bash
set -euo pipefail
ios=$(cd "$(dirname "$0")/.." && pwd)
work="$ios/build/simulator"
app="$work/ExteraProbe.app"
mkdir -p "$app"
python3 "$ios/scripts/python_support.py" download "$work/vendor"
framework="$work/vendor/Python.xcframework"
architecture=$(uname -m)
sdk=$(xcrun --sdk iphonesimulator --show-sdk-path)
xcrun clang -fobjc-arc -fmodules -target "$architecture-apple-ios18.0-simulator" \
  -isysroot "$sdk" -I "$ios/native" \
  -F "$framework/ios-arm64_x86_64-simulator" \
  -framework Foundation -framework UIKit -framework AVFoundation -framework UniformTypeIdentifiers -framework Python \
  -Xlinker -rpath -Xlinker @executable_path/Frameworks \
  "$ios/native/EPPluginHost.m" "$ios/native/EPPluginManagerController.m" "$ios/tests/SimulatorMain.m" \
  -o "$app/ExteraProbe"
python3 "$ios/scripts/python_support.py" install "$app" "$framework" --platform simulator
cp "$ios/tests/smoke.plugin" "$app/smoke.plugin"
python3 - "$app" <<'PY'
import math, plistlib, struct, sys, wave
from pathlib import Path
app = Path(sys.argv[1])
(app / "Info.plist").write_bytes(plistlib.dumps({
    "CFBundleIdentifier": "app.exteragram.runtime-probe", "CFBundleExecutable": "ExteraProbe",
    "CFBundleName": "ExteraProbe", "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0",
    "CFBundlePackageType": "APPL", "MinimumOSVersion": "18.0", "LSRequiresIPhoneOS": True,
    "UIDeviceFamily": [1, 2], "UILaunchScreen": {},
}))
with wave.open(str(app / "probe.wav"), "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(8000)
    audio.writeframes(b"".join(struct.pack("<h", int(1000 * math.sin(i * math.tau * 440 / 8000))) for i in range(800)))
PY
codesign --force --sign - --timestamp=none "$app"
xcrun simctl list devices available -j > "$work/devices.json"
device=$(python3 - "$work/devices.json" <<'PY'
import json, sys
devices = json.load(open(sys.argv[1]))["devices"]
phones = [d for runtime, entries in devices.items() if "iOS" in runtime for d in entries if d["isAvailable"] and "iPhone" in d["name"]]
if not phones: raise SystemExit("No available iPhone simulator runtime on this runner")
print(phones[0]["udid"])
PY
)
xcrun simctl boot "$device" || true
xcrun simctl bootstatus "$device" -b
xcrun simctl install "$device" "$app"
xcrun simctl launch "$device" app.exteragram.runtime-probe
container=$(xcrun simctl get_app_container "$device" app.exteragram.runtime-probe data)
for attempt in {1..60}; do
  if [[ -f "$container/Documents/smoke-result.json" ]]; then
    cp "$container/Documents/smoke-result.json" "$work/smoke-result.json"
    python3 - "$work/smoke-result.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1]))
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["passed"]: raise SystemExit("Native iOS runtime probe failed")
PY
    exit 0
  fi
  sleep 2
done
xcrun simctl spawn "$device" log show --last 3m --predicate 'process == "ExteraProbe"' --style compact || true
exit 1
