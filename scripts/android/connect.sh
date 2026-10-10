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

# 输入法（必须）：默认用 Airtest 自带的注入 IME，并清掉 Gboard 的中文数据。
# 否则 text() 会被中文拼音吞进候选区（候选条上显示 "q a player"），用户名根本落不进输入框，
# UI 用例会在登录步骤失败。Gboard 的中文是内建语言包，删不掉，只能让它不参与输入。
LATIN=com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME
YOSEMITE=com.netease.nie.yosemite/.ime.ImeService
adb -s emulator-5554 shell pm clear com.google.android.inputmethod.latin >/dev/null 2>&1 || true
adb -s emulator-5554 shell ime enable "$LATIN" >/dev/null 2>&1 || true
adb -s emulator-5554 shell ime enable "$YOSEMITE" >/dev/null 2>&1 || true
adb -s emulator-5554 shell ime set "$YOSEMITE" >/dev/null 2>&1 || true
