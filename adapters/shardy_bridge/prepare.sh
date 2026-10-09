#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
shardy_work="${SHARDY_WORK:-$(cd "$here/../../../.." && pwd)/work/shardy}"
shardy_vendor="$shardy_work/vendor/shardy-tictactoe"
shardy_node="${SHARDY_NODE:-node}"
shardy_pnpm="${SHARDY_PNPM:-pnpm}"
shardy_commit='ed8e978917cbe5aba79009928e8c3b92a34b81cc'
mkdir -p "$shardy_work/vendor" "$shardy_work/logs" "$shardy_work/pnpm-store"
if [ ! -d "$shardy_vendor/.git" ]; then
  git clone https://github.com/mopsicus/shardy-tictactoe.git "$shardy_vendor"
  git -C "$shardy_vendor" checkout --detach "$shardy_commit"
fi
if [ "$(git -C "$shardy_vendor" rev-parse HEAD)" != "$shardy_commit" ]; then
  echo 'Existing vendor revision differs from the pinned commit; choose another SHARDY_WORK directory.' >&2
  exit 1
fi
if [ -f "$shardy_vendor/pnpm-lock.yaml" ] && ! cmp -s "$here/pnpm-lock.yaml" "$shardy_vendor/pnpm-lock.yaml"; then
  echo 'Existing dependency lock differs; choose another SHARDY_WORK directory.' >&2
  exit 1
fi
cp "$here/pnpm-lock.yaml" "$shardy_vendor/pnpm-lock.yaml"
export PATH="$(dirname "$shardy_node"):$PATH"
cd "$shardy_vendor"
"$shardy_pnpm" install --frozen-lockfile --ignore-scripts --store-dir "$shardy_work/pnpm-store"
"$shardy_node" node_modules/typescript/bin/tsc
printf 'Prepared official Shardy backend: %s\n' "$shardy_vendor"
