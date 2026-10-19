#!/bin/bash
# One-command stock-rebuild eval for a GBA agbcc project, from a target file.
#   audit/agbcc/eval.sh audit/targets/<name>.env
# Needs git, Docker and python3. Clones into repos/ (blobless), rebuilds in a throwaway container,
# writes out/<name>/ and audit/labels/<name>.csv, and prints the comparison.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd); cd "$ROOT"
source "$1"
[ "$FAMILY" = agbcc ] || { echo "$1 is a $FAMILY target, not agbcc"; exit 1; }
FORK_DIR=agbcc-$NAME
clone() {  # url dir commit
  [ -d "repos/$2" ] || git clone -q --filter=blob:none "$1" "repos/$2"
  git -C "repos/$2" -c advice.detachedHead=false checkout -q "$3"
}
clone "$REPO" "$NAME" "$PIN"
clone "$FORK_REPO" "$FORK_DIR" "$FORK_SHA"
clone https://github.com/pret/agbcc agbcc-pret da598c1d918402c42c0c0d7128ba14567f3175e9
rm -rf "out/$NAME" && mkdir -p "out/$NAME"
docker run --rm --name "eval-$NAME" --cpus 3 --memory 3g \
  -v "$ROOT/repos:/src:ro" -v "$ROOT/out/$NAME:/mnt" -v "$ROOT/audit/agbcc:/a:ro" \
  -e PROJ="$NAME" -e FORK="$FORK_DIR" -e FORK_SHA="$FORK_SHA" -e PREPROC="${PREPROC:-0}" \
  -e CFLAGS="$CFLAGS" -e OVERRIDES="${OVERRIDES:-}" \
  debian:bookworm-slim bash -c 'mkdir -p /out && bash /a/run.sh > /out/log.txt 2>&1; cp -a /out/. /mnt/'
grep -E "^(FAIL|CPPFAIL)" "out/$NAME/log.txt" || true
C=audit/klonoa/compare.py
python3 $C "out/$NAME" project
python3 $C "out/$NAME" --labels "$NAME" "$PIN" "${SDK_RE:-}" > "audit/labels/$NAME.csv"
python3 audit/scorecard.py | grep -E "^\| ($NAME|Project) "
