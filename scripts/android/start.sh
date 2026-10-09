#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
exec emulator -avd airtest_api34_arm64 -port 5554 -memory 1536 -cores 2 \
  -gpu auto -no-window -no-audio -no-snapshot -camera-back none -camera-front none "$@"
