#!/usr/bin/env bash
#
# Run the comprehensive framework-execution test suite inside the
# Dockerfile.validation image, which has every external compiler
# pre-installed (protoc, kotlinc, javac, tsc, cargo, plus Jackson +
# kotlinx-serialization + Bean Validation runtime jars).
#
# Locally this gives the same coverage as CI's "External Compiler
# Validation" job — no test skips for missing toolchains.
#
# Usage:
#   scripts/validate-in-docker.sh                # build (if needed) + run
#   scripts/validate-in-docker.sh --rebuild      # force rebuild before run
#
# The image is tagged ``schema-gen-validation:local`` and reused on
# subsequent invocations. Rebuilds are only needed after editing
# Dockerfile.validation; the test code itself is bind-mounted so source
# edits take effect without rebuilding.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="schema-gen-validation:local"
DOCKERFILE="${REPO_ROOT}/Dockerfile.validation"

# --- Pre-flight: docker daemon ----------------------------------------

if ! command -v docker >/dev/null 2>&1; then
  cat >&2 <<EOF
docker not found on PATH. Install Docker to run the comprehensive local
validation (https://docs.docker.com/get-docker/).

The pre-commit fast hook still runs Python-framework correctness on every
commit; only the external-compiler layer (Protobuf / Rust / Zod / Kotlin /
Jackson) needs Docker to run locally. CI's "External Compiler Validation"
job covers them on every PR regardless.
EOF
  exit 2
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon not running — start Docker and retry." >&2
  exit 2
fi

# --- Always run docker build (cached layers make it a no-op when -----
# nothing has changed, and any Dockerfile edit is picked up
# automatically). ``--rebuild`` adds ``--no-cache`` to force a clean
# build from scratch. -------------------------------------------------

REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
  esac
done

BUILD_ARGS=()
if [[ "$REBUILD" == 1 ]]; then
  BUILD_ARGS+=(--no-cache)
  echo "==> Forcing clean rebuild of $IMAGE_TAG (no-cache)..."
elif docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  echo "==> Refreshing $IMAGE_TAG from $DOCKERFILE (cached, fast if unchanged)..."
else
  echo "==> Building $IMAGE_TAG from $DOCKERFILE (one-time, ~10 min)..."
fi
DOCKER_BUILDKIT=1 docker build -f "$DOCKERFILE" -t "$IMAGE_TAG" "${BUILD_ARGS[@]}" "$REPO_ROOT"

# --- Run the framework-execution suite inside the container -----------
#
# Bind-mount the source tree so test edits don't require a rebuild.
# Use a per-image cache directory for ``uv`` and pip so repeated runs
# don't re-download the world.

CACHE_VOL="schema-gen-validation-cache"
docker volume inspect "$CACHE_VOL" >/dev/null 2>&1 \
  || docker volume create "$CACHE_VOL" >/dev/null

echo "==> Running framework-execution tests inside $IMAGE_TAG ..."
exec docker run --rm \
  --workdir /app \
  -v "$REPO_ROOT":/app \
  -v "$CACHE_VOL":/root/.cache \
  -e UV_LINK_MODE=copy \
  "$IMAGE_TAG" \
  bash -c '
    set -euo pipefail
    # Install schema-gen + dev deps (fastavro, etc.) into the container.
    pip install --quiet --no-cache-dir -e ".[dev,sqlalchemy,pathway,jsonschema,graphql,avro]" fastavro
    # Run the three suites that constitute the comprehensive correctness
    # gate: snapshot stability, AST-level invariants, and full
    # framework-execution (every external compiler runs unconditionally).
    pytest -q \
      tests/test_generator_output_stability.py \
      tests/test_generator_correctness_invariants.py \
      tests/test_generator_framework_execution.py
  '
