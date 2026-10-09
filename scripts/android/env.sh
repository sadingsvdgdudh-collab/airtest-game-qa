#!/usr/bin/env bash
if [ -n "${ZSH_VERSION:-}" ]; then
  GAMEQA_ANDROID_SCRIPT_DIR="$(cd "$(dirname "${(%):-%N}")" && pwd)"
else
  GAMEQA_ANDROID_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
GAMEQA_ANDROID_ROOT="${GAMEQA_WORK_DIR:-$GAMEQA_ANDROID_SCRIPT_DIR/../../../../work}/android"
export ANDROID_HOME="${ANDROID_HOME:-$GAMEQA_ANDROID_ROOT/sdk}"
export ANDROID_USER_HOME="$GAMEQA_ANDROID_ROOT/user"
export ANDROID_EMULATOR_HOME="$GAMEQA_ANDROID_ROOT/user"
export ANDROID_AVD_HOME="$GAMEQA_ANDROID_ROOT/avd"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
