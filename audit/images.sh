#!/bin/bash
# Build the two throwaway images the dtk runner uses (Debian bookworm-slim + a few packages).
#   reveval-gc:arm64   native arm64: python3, qemu-user (runs wibo + Metrowerks), curl, unzip
#   reveval-ppc:amd64  python3 + binutils-powerpc-linux-gnu (objdump for the per-function compare)
# Apple Silicon: wibo can't run under Rosetta, hence native arm64 + qemu-i386 for compiling.
set -euo pipefail
docker build -q --platform linux/arm64 -t reveval-gc:arm64 - <<'D'
FROM debian:bookworm-slim
RUN apt-get update -qq && apt-get install -y -qq python3 curl unzip qemu-user ca-certificates jq >/dev/null
D
docker build -q --platform linux/amd64 -t reveval-ppc:amd64 - <<'D'
FROM debian:bookworm-slim
RUN apt-get update -qq && apt-get install -y -qq python3 binutils-powerpc-linux-gnu >/dev/null
D
