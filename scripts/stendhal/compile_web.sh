#!/bin/sh
set -eu
. "$(dirname -- "$0")/env.sh"
BASE="$STENDHAL_BASE"
JAVA="$JAVA_BIN"
NODE=${STENDHAL_NODE:-node}
cd "$BASE/source"
"$NODE" "$BASE/typescript/package/bin/tsc" -p src/js/stendhal/tsconfig.json
mkdir -p build/js
unzip -qo "$BASE/runtime/libs/marauroa.jar" 'js/*' -d build
cat > build/js/build.js <<'JS'
var stendhal = window.stendhal = window.stendhal || {};
stendhal.data = stendhal.data || {};
stendhal.data.build = {version: '1.49', build: 'local-qa-cbe0825', dist: 'webclient'};
JS
"$JAVA" -Xmx512m -jar buildtools/closure-compiler/compiler.jar --language_in=ECMASCRIPT_2020 --language_out=STABLE --compilation_level ADVANCED --debug --formatting=PRETTY_PRINT --process_common_js_modules --module_resolution=node --jscomp_off=checkVars --js_output_file=src/js/stendhal-compiled.js src/js/stendhal/license.js build/js/marauroa.js build/js/client-framework.js build/js/message-factory.js build/js/perception.js build/js/rpfactory.js build/js/inflate.js build/js/deserializer.js build/js/build.js src/js/jsxgraph-util.js src/js/stendhal/data/sha3.js 'build/ts/*.js' 'build/ts/**/*.js' > "$BASE/compile_web.log" 2>&1
mkdir -p "$BASE/runtime/js"
cp src/js/stendhal.html src/js/stendhal-compiled.js src/js/LICENSE.html src/js/favicon.ico "$BASE/runtime/js/"
cp -R src/js/css "$BASE/runtime/js/"
printf 'Web client built; compiler diagnostics: %s\n' "$BASE/compile_web.log"
