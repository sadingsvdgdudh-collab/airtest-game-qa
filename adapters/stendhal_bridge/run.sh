#!/bin/sh
set -eu
bridge_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
workspace_dir=$(CDPATH= cd -- "$bridge_dir/../../../.." && pwd)
work_dir=${GAMEQA_WORK_DIR:-"$workspace_dir/work"}
runtime=${STENDHAL_RUNTIME:-"$work_dir/stendhal/runtime"}
build_dir=${BRIDGE_BUILD_DIR:-"$work_dir/protocol-bridge/classes"}
jdk=${JAVA_HOME:-"$work_dir/tools/zulu21.40.17-ca-jdk21.0.6-macosx_aarch64/zulu-21.jdk/Contents/Home"}
java_bin=${STENDHAL_JAVA:-"$jdk/bin/java"}
if [ ! -f "$build_dir/StendhalBridge.class" ]; then echo 'Run build.sh before starting the bridge.' >&2; exit 1; fi
exec "$java_bin" -Duser.home="$work_dir/protocol-bridge" -cp "$build_dir:$runtime/libs/*:$runtime/stendhal-server-1.49.jar" StendhalBridge
