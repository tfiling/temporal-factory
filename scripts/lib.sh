# Shared helpers for scripts/*.sh. Source it; works from any directory.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"

die() { echo "error: $*" >&2; exit 1; }

require_env() { [ -f .env ] || die "no .env: cp .env.example .env and fill it in"; }

# Version of what the image is built from: commit, plus a hash of uncommitted changes to the files the
# Dockerfile copies (so further edits to a dirty tree show up, and vault-only edits don't).
source_version() {
  local paths=(Dockerfile pyproject.toml checks.sh entrypoint.sh factory tests) version changes
  version="$(git rev-parse --short HEAD)"
  if [ -n "$(git status --porcelain -- "${paths[@]}")" ]; then
    changes="$(git diff HEAD --binary -- "${paths[@]}"
      git ls-files -z --others --exclude-standard -- "${paths[@]}" | xargs -0 shasum)"
    version+="-dirty-$(shasum <<<"$changes" | cut -c1-8)"
  fi
  echo "$version"
}

# Baked into the image by any compose build run from these scripts (see docker-compose.yml).
FACTORY_VERSION="$(source_version)"
export FACTORY_VERSION

# Start the stack only if the worker is down, so a running worker is never recreated mid-job.
ensure_worker() {
  require_env
  local running
  running="$(docker compose ps --status running --services)"
  grep -qx worker <<<"$running" || docker compose up -d worker
}

# Warn only: rebuilding would restart the worker and interrupt running jobs.
warn_if_stale() {
  local worker image
  worker="$(docker compose exec -T worker printenv FACTORY_VERSION </dev/null)" || worker=unknown
  # The CLI runs the image, which is newer than the worker after a build without a restart.
  image="$(docker compose run --rm -T --no-deps --entrypoint printenv worker FACTORY_VERSION </dev/null 2>/dev/null)" ||
    image=unknown
  [ "$worker" = "$FACTORY_VERSION" ] ||
    echo "warning: worker runs $worker, tree is $FACTORY_VERSION; run scripts/up.sh to rebuild" >&2
  [ "$image" = "$worker" ] || echo "warning: CLI runs $image, worker runs $worker; run scripts/up.sh" >&2
}

# factory.cli in a one-off container. -T keeps piped stdin working (feedback, reject).
factory_cli() {
  ensure_worker
  warn_if_stale
  docker compose run --rm -T -e PYTHONUNBUFFERED=1 worker python -m factory.cli "$@"
}
