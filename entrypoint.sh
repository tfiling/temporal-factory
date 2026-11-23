#!/usr/bin/env bash
set -e
gh auth setup-git 2>/dev/null || true
git config --global user.name "${GIT_AUTHOR_NAME:-factory}"
git config --global user.email "${GIT_AUTHOR_EMAIL:-factory@localhost}"
exec "$@"
