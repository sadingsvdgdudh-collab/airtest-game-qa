#!/usr/bin/env bash
# 停止 Shardy 前后端：先按 pid 文件，再按端口兜底清残留。
set -uo pipefail
. "$(dirname -- "$0")/env.sh"

for name in client backend; do
  pidfile="$SHARDY_WORK/$name.pid"
  if [ ! -f "$pidfile" ]; then printf '%s 没有 pid 文件\n' "$name"; continue; fi
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    printf '%s 已停止（PID %s）\n' "$name" "$pid"
  else
    printf '%s 的 pid 文件是旧的（进程已不在）\n' "$name"
  fi
  rm -f "$pidfile"
done

for port in "$SHARDY_CLIENT_PORT" "$SHARDY_PORT"; do
  leftover="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [ -n "$leftover" ]; then
    kill $leftover 2>/dev/null || true
    printf '端口 %s 上仍有残留进程 %s，已停止\n' "$port" "$leftover"
  fi
done
exit 0
