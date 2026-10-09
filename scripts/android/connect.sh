#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
adb -s emulator-5554 wait-for-device
if [ "$(adb -s emulator-5554 shell getprop sys.boot_completed | tr -d '\r')" != 1 ]; then
  echo 'Wait until Android finishes booting, then run this command again.' >&2
  exit 1
fi
for port in 8080 3000 3001; do
  adb -s emulator-5554 reverse "tcp:$port" "tcp:$port"
done
adb -s emulator-5554 shell wm size 720x1280
adb -s emulator-5554 shell wm density 320
