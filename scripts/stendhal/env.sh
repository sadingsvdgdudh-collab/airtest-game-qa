#!/bin/sh
# Shared paths. GAMEQA_WORK_DIR isolates every runtime file from user home.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
WORK_DIR=${GAMEQA_WORK_DIR:-"$PROJECT_DIR/../../work"}
WORK_DIR=$(CDPATH= cd -- "$WORK_DIR" && pwd)
STENDHAL_BASE="$WORK_DIR/stendhal"
JAVA_BIN=${STENDHAL_JAVA:-"$WORK_DIR/tools/zulu21.40.17-ca-jdk21.0.6-macosx_aarch64/zulu-21.jdk/Contents/Home/bin/java"}
JAVAC_BIN=${STENDHAL_JAVAC:-"$(dirname -- "$JAVA_BIN")/javac"}
MODE=${1:-main}
case "$MODE" in
  main) RUNTIME="$STENDHAL_BASE/runtime"; EXTRA_CP="" ;;
  fault) RUNTIME="$STENDHAL_BASE/runtime-fault"; EXTRA_CP="$STENDHAL_BASE/fault/classes:" ;;
  *) printf 'Mode must be main or fault\n' >&2; exit 2 ;;
esac
