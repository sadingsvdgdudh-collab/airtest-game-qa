#!/bin/sh
set -eu
. "$(dirname -- "$0")/env.sh"
PIDFILE="$RUNTIME/server.pid"
[ -f "$PIDFILE" ] || exit 0
PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
  CMD=$(ps -p "$PID" -o args=)
  case "$CMD" in
    *"$RUNTIME/home"*"games.stendhal.server.StendhalServer"*) ;;
    *) printf 'Refusing to stop unrelated PID %s\n' "$PID" >&2; exit 1 ;;
  esac
  # 停服前先看一眼数据库写队列：队列非空时强停会丢写（实测过一次，后果是角色再也加载不出来）。
  LOG="$RUNTIME/console.log"
  if [ -f "$LOG" ] && tail -200 "$LOG" | grep -q "DBCommandQueue has"; then
    QUEUE=$(tail -200 "$LOG" | grep -o "DBCommandQueue has [0-9]* entries" | tail -1)
    printf 'Warning: %s — 等 30 秒让它落库后再停\n' "$QUEUE" >&2
    sleep 30
  fi
  kill "$PID"
  # 最多等 90 秒：给未落库的写留出时间（原来 20 秒不够）
  i=0
  while kill -0 "$PID" 2>/dev/null && [ "$i" -lt 90 ]; do sleep 1; i=$((i + 1)); done
  if kill -0 "$PID" 2>/dev/null; then printf 'Shutdown incomplete; PID retained\n' >&2; exit 1; fi
fi
rm -f "$PIDFILE"
