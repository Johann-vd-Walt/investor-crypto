#!/usr/bin/env bash
#
# One-command update: pull the latest code from GitHub and redeploy.
#
#     sudo bash /srv/cryptotrader/deploy/update.sh
#
# The server is a deploy target, not a place to edit code — this does a hard
# reset to match GitHub exactly. Your .env, .venv, node_modules and price data
# are untracked/ignored, so they are left alone.

set -euo pipefail

APP_DIR="/srv/cryptotrader"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m!! %s\033[0m\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run with sudo: sudo bash $APP_DIR/deploy/update.sh"
cd "$APP_DIR" || fail "$APP_DIR not found"
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

say "Pulling latest from GitHub"
BEFORE="$(git rev-parse --short HEAD 2>/dev/null || echo none)"
git fetch --quiet origin main || fail "git fetch failed — check the deploy key / network."
git reset --hard --quiet origin/main || fail "git reset failed."
AFTER="$(git rev-parse --short HEAD)"
if [[ "$BEFORE" == "$AFTER" ]]; then
  echo "  already at $AFTER — no new commits"
else
  echo "  $BEFORE -> $AFTER"
  git --no-pager log --oneline "${BEFORE}..${AFTER}" 2>/dev/null | sed 's/^/    /' || true
fi

say "Deploying"
bash "$APP_DIR/deploy/deploy-crypto.sh"
