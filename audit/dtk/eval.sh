#!/bin/bash
# One-command stock-rebuild eval for a dtk (GameCube/Wii Metrowerks) project, from a target file.
#   audit/dtk/eval.sh audit/targets/<name>.env
# Needs git, Docker and python3; build the images once with audit/images.sh.
# The compiler bundle, its patches and the unit list all come from the project's own configure.py,
# evaluated only inside the container. Writes out/eval/<name>/ and audit/labels/<name>.csv.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd); cd "$ROOT"
source "$1"
[ "$FAMILY" = dtk ] || { echo "$1 is a $FAMILY target, not dtk"; exit 1; }
A=audit
[ -d "repos/$NAME" ] || git clone -q --filter=blob:none "$REPO" "repos/$NAME"
git -C "repos/$NAME" -c advice.detachedHead=false checkout -q "$PIN"
if [ -z "${LABELS_ONLY:-}" ]; then  # LABELS_ONLY=1: re-score an existing out/eval/<name>/ without recompiling
rm -rf "out/eval/$NAME" && mkdir -p "out/eval/$NAME"
docker run --rm --name "eval-$NAME" --platform linux/arm64 --cpus "${CPUS:-8}" --memory 6g \
  -v "$ROOT/repos/$NAME:/src:ro" -v "$ROOT/$A:/audit:ro" -v "$ROOT/out/eval/$NAME:/mnt" \
  -e VERSIONS="$VERSIONS" -e JOBS="${CPUS:-8}" \
  reveval-gc:arm64 bash -c 'bash /audit/dtk/run.sh > /tmp/log.txt 2>&1; cp /tmp/log.txt /mnt/log.txt'
fi
grep -E "STEPFAIL|failed" "out/eval/$NAME/log.txt" || true
rm -f "out/eval/$NAME/labels.csv"
docker run --rm --platform linux/amd64 -v "$ROOT:/r" -w /r -e REPO="repos/$NAME" -e NAME="$NAME" -e PIN="$PIN" \
  -e VERSIONS="$VERSIONS" -e GAME_PREFIX="${GAME_PREFIX:-}" -e SDK_RE="${SDK_RE:-}" reveval-ppc:amd64 bash -c '
  set -e; n=$(wc -w <<<"$VERSIONS"); first=1
  for v in $VERSIONS; do
    p=$NAME; [ "$n" -gt 1 ] && p=$NAME-$v
    python3 audit/community/tier.py labels out/eval/$NAME/$v out/eval/$NAME/$v/base $p ${PIN:0:8} $GAME_PREFIX \
      2> out/eval/$NAME/$v/labels.log | { [ $first = 1 ] && cat || tail -n +2; } >> out/eval/$NAME/labels.csv
    first=0; cat out/eval/$NAME/$v/labels.log
  done'
cp "out/eval/$NAME/labels.csv" "$A/labels/$NAME.csv"
python3 $A/scorecard.py | grep -E "^\| ($NAME|Project) "
