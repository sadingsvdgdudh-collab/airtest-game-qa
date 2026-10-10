#!/usr/bin/env bash
# Shardy（井字棋）本地服务：后端 3000（WebSocket）、项目展示客户端 3001（HTTP）。
# 机器相关的 node 路径不要写进仓库 —— 放到工作区的 local.env（GAMEQA_NODE=…）。
if [ -n "${ZSH_VERSION:-}" ]; then
  GAMEQA_SHARDY_DIR="$(cd "$(dirname "${(%):-%N}")" && pwd)"
else
  GAMEQA_SHARDY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
export GAMEQA_SHARDY_REPO="$(cd "$GAMEQA_SHARDY_DIR/../.." && pwd)"
GAMEQA_ROOT="${GAMEQA_WORK_DIR:-$GAMEQA_SHARDY_DIR/../../../../work}"
export SHARDY_WORK="${SHARDY_WORK:-$GAMEQA_ROOT/shardy}"
export SHARDY_VENDOR="${SHARDY_VENDOR:-$SHARDY_WORK/vendor/shardy-tictactoe}"
export SHARDY_LOGS="${SHARDY_LOGS:-$SHARDY_WORK/logs}"
export SHARDY_PORT="${SHARDY_PORT:-3000}"
export SHARDY_CLIENT_PORT="${SHARDY_CLIENT_PORT:-3001}"

# 依次找：环境里指定的 → 工作区自带的 → PATH 上的
shardy_node() {
  for candidate in "${GAMEQA_NODE:-}" "${SHARDY_NODE:-}" "$GAMEQA_ROOT/tools/node/bin/node"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then printf '%s' "$candidate"; return 0; fi
  done
  if command -v node >/dev/null 2>&1; then command -v node; return 0; fi
  return 1
}
