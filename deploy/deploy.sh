#!/usr/bin/env bash
# CourtBazaar production deploy — the single source of truth for how a
# deploy actually happens. See DEPLOYMENT.md §7.
#
# This exists because manual copy-pasted deploy steps (or a stale doc) is
# how npm got run against this Yarn-only project and how a build silently
# went out that didn't match the intended commit. Every step below either
# succeeds correctly or the script stops — nothing here "probably worked."

set -euo pipefail

REPO_DIR="/root/courtbazaar"
WEB_ROOT="/var/www/html"
BACKEND_SERVICE="courtbazaar"
DOMAIN="https://courtbazaar.com"

cd "$REPO_DIR"

# Deliberately does NOT `git pull` here. This file is executed as
# `bash deploy/deploy.sh` — the running process holds THIS file open by
# inode from the moment it starts. `git pull`'s checkout replaces a tracked
# file via unlink+create (a new inode), which an already-open file
# descriptor never sees; a process reading its own script never notices,
# and keeps executing the OLD content for the rest of that same run. So a
# pull done from inside this script — the bug this replaces — silently ran
# every following line (including the DOMAIN check below) against
# whatever this file said BEFORE the pull, on any deploy that changed
# deploy.sh itself, even though the checkout on disk was already correct
# for the next run. The caller (deploy.yml's SSH step / DEPLOYMENT.md §7's
# manual instructions) pulls first, in a separate command, before this
# script is ever invoked — by the time this line runs, the repo is
# guaranteed already up to date.
TARGET_COMMIT="$(git rev-parse HEAD)"
echo "    target commit: $TARGET_COMMIT"

echo "==> Backend: installing deps and restarting service"
cd "$REPO_DIR/backend"
source venv/bin/activate
pip install -r requirements.txt
deactivate
sudo systemctl restart "$BACKEND_SERVICE"
sudo systemctl is-active --quiet "$BACKEND_SERVICE" || {
  echo "!! $BACKEND_SERVICE failed to start — check: sudo journalctl -u $BACKEND_SERVICE -n 50"
  exit 1
}
echo "==> Waiting for backend to come up"
BACKEND_UP=0
for i in $(seq 1 15); do
  if curl -sf http://127.0.0.1:8000/api/ > /dev/null; then
    BACKEND_UP=1
    break
  fi
  sleep 1
done
if [ "$BACKEND_UP" -ne 1 ]; then
  echo "!! backend did not respond on 127.0.0.1:8000/api/ after 15s"
  exit 1
fi

echo "==> Frontend: installing deps (Yarn only — see package.json packageManager)"
cd "$REPO_DIR/frontend"
yarn install --frozen-lockfile

echo "==> Frontend: building (also stamps build/version.json with $TARGET_COMMIT)"
yarn build

echo "==> Publishing build to $WEB_ROOT"
rsync -a --delete --exclude='.well-known' build/ "$WEB_ROOT/"

echo "==> Reloading Nginx"
sudo nginx -t
sudo systemctl reload nginx

echo "==> Verifying the live site actually matches what we just deployed"
sleep 1
LIVE_COMMIT="$(curl -sf "$DOMAIN/version.json" | grep -o '"commit": *"[a-f0-9]*"' | grep -o '[a-f0-9]\{40\}' || true)"

if [ -z "$LIVE_COMMIT" ]; then
  echo "!! could not read $DOMAIN/version.json — deploy may not be live. Check Nginx and DNS."
  exit 1
fi

if [ "$LIVE_COMMIT" != "$TARGET_COMMIT" ]; then
  echo "!! MISMATCH: live commit ($LIVE_COMMIT) != deployed commit ($TARGET_COMMIT)"
  echo "!! Do not assume this deploy shipped — investigate before moving on."
  exit 1
fi

echo "==> Verified: $DOMAIN is now serving commit $TARGET_COMMIT"
echo "==> Deploy complete."
