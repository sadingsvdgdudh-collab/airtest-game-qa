#!/usr/bin/env bash
# 启动 Shardy 后端（3000）与项目展示客户端（3001）。可重复执行：已在跑就跳过。
# 对应 docs/环境部署.md 第 5 节的手工命令；日志与 pid 与手工方式一致。
set -euo pipefail
. "$(dirname -- "$0")/env.sh"

NODE="$(shardy_node)" || {
  printf '找不到 node：请在工作区 local.env 里设置 GAMEQA_NODE=/绝对路径/node\n' >&2; exit 1; }
[ -d "$SHARDY_VENDOR" ] || {
  printf '缺少 Shardy 依赖：%s\n先按 docs/环境部署.md 第 5 节跑一次 prepare.sh\n' "$SHARDY_VENDOR" >&2; exit 1; }
mkdir -p "$SHARDY_LOGS"

start_one() {                     # 名字 脚本 端口 日志
  local name="$1" script="$2" port="$3" log="$4" pidfile="$SHARDY_WORK/$1.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    printf '%s 已在运行（PID %s）\n' "$name" "$(cat "$pidfile")"; return 0
  fi
  ( cd "$GAMEQA_SHARDY_REPO" && nohup "$NODE" "$script" >>"$log" 2>&1 & printf '%s\n' "$!" >"$pidfile" )
  printf '%s 启动中（PID %s，端口 %s，日志 %s）\n' "$name" "$(cat "$pidfile")" "$port" "$log"
}

start_one backend adapters/shardy_bridge/start_backend.mjs "$SHARDY_PORT"        "$SHARDY_LOGS/backend.log"
start_one client  integrations/shardy_client/server.mjs     "$SHARDY_CLIENT_PORT" "$SHARDY_LOGS/client.log"

for _ in $(seq 1 30); do
  ready=1
  for port in "$SHARDY_PORT" "$SHARDY_CLIENT_PORT"; do
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || ready=0
  done
  if [ "$ready" = 1 ]; then
    printf 'Shardy 就绪：后端 %s、展示客户端 http://127.0.0.1:%s/（%s）\n' \
      "$SHARDY_PORT" "$SHARDY_CLIENT_PORT" "$NODE"
    exit 0
  fi
  sleep 0.5
done
printf 'Shardy 起不来，看 %s/backend.log 与 client.log\n' "$SHARDY_LOGS" >&2
exit 1
