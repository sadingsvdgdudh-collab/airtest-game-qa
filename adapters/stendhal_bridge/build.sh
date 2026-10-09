#!/bin/sh
set -eu
bridge_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
workspace_dir=$(CDPATH= cd -- "$bridge_dir/../../../.." && pwd)
work_dir=${GAMEQA_WORK_DIR:-"$workspace_dir/work"}
runtime=${STENDHAL_RUNTIME:-"$work_dir/stendhal/runtime"}
build_dir=${BRIDGE_BUILD_DIR:-"$work_dir/protocol-bridge/classes"}
jdk=${JAVA_HOME:-"$work_dir/tools/zulu21.40.17-ca-jdk21.0.6-macosx_aarch64/zulu-21.jdk/Contents/Home"}
java_bin=${STENDHAL_JAVA:-"$jdk/bin/java"}
javac_bin="$(dirname -- "$java_bin")/javac"
if [ ! -x "$javac_bin" ]; then echo 'Set JAVA_HOME to a JDK 21 installation or STENDHAL_JAVA to its java executable.' >&2; exit 1; fi
if [ ! -f "$runtime/stendhal-server-1.49.jar" ]; then echo 'Set STENDHAL_RUNTIME to the extracted Stendhal 1.49 server directory.' >&2; exit 1; fi
mkdir -p "$build_dir"
"$javac_bin" -encoding UTF-8 -cp "$runtime/libs/*:$runtime/stendhal-server-1.49.jar" -d "$build_dir" "$bridge_dir/StendhalBridge.java" "$bridge_dir/QaProbe.java" "$bridge_dir/QaCombat.java"
if [ "${1:-}" = '--install-probe' ]; then
    mkdir -p "$runtime/data/script/games/stendhal/server/script"
    cp "$build_dir"/games/stendhal/server/script/QaProbe*.class "$runtime/data/script/games/stendhal/server/script/"
    cp "$build_dir"/games/stendhal/server/script/QaCombat*.class "$runtime/data/script/games/stendhal/server/script/"
fi
