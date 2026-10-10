#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
# 默认无窗口（无人值守）；GAMEQA_EMULATOR_WINDOW=1 时开窗口，便于人工看着跑。
# 开窗口时改用软件渲染：host GPU 路径下 Chrome 会反复崩溃（"Chrome keeps stopping" 弹窗会盖住页面，
# 界面模板就匹配不到），swiftshader 慢但稳。
WINDOW_FLAG="-no-window"
GPU="auto"
if [ "${GAMEQA_EMULATOR_WINDOW:-0}" = "1" ]; then
  WINDOW_FLAG=""
  GPU="${GAMEQA_EMULATOR_GPU:-swiftshader_indirect}"
fi

exec emulator -avd airtest_api34_arm64 -port 5554 -memory 1536 -cores 2 \
  -gpu "$GPU" $WINDOW_FLAG -no-audio -no-snapshot -camera-back none -camera-front none "$@"
