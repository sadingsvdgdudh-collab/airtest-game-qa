#!/bin/sh
set -eu
. "$(dirname -- "$0")/env.sh"
[ -d "$RUNTIME" ] || { printf 'Run setup.py (and build_fault.py for fault) first\n' >&2; exit 1; }
cd "$RUNTIME"
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
  printf 'Stendhal %s already running (PID %s)\n' "$MODE" "$(cat server.pid)"
  exit 0
fi
mkdir -p home tmp
"$JAVA_BIN" -Xmx512m -Duser.home="$RUNTIME/home" -Djava.io.tmpdir="$RUNTIME/tmp" -cp "$EXTRA_CP$STENDHAL_BASE/patches/classes:.:stendhal-server-1.49.jar:stendhal-maps-1.49.jar:stendhal-xmlconf-1.49.jar:$STENDHAL_BASE/client/lib/stendhal-data.jar:$STENDHAL_BASE/client/lib/stendhal-sound-data.jar:libs/*" games.stendhal.server.StendhalServer > console.log 2>&1 &
printf '%s\n' "$!" > server.pid
printf 'Stendhal %s starting (PID %s), log %s\n' "$MODE" "$!" "$RUNTIME/console.log"
wait "$(cat server.pid)"
