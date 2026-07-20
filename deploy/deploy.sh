#!/usr/bin/env bash
# CourtBazaar production deploy — the single source of truth for how a
# deploy actually happens. See DEPLOYMENT.md §7.
#
# This exists because manual copy-pasted deploy steps (or a stale doc) is
# how npm got run against this Yarn-only project and how a build silently
# went out that didn't match the intended commit. Every step below either
# succeeds correctly or the script stops — nothing here "probably worked."

set -euo pipefail

REPO_DIR="/var/www/courtbazaar"
WEB_ROOT="/var/www/html"
BACKEND_SERVICE="courtbazaar"
DOMAIN="https://courtbazaar.in"

cd "$REPO_DIR"

echo "==> Fetching latest code"
git fetch origin
git pull origin main
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
curl -sf http://127.0.0.1:8000/api/ > /dev/null || {
  echo "!! backend is not responding on 127.0.0.1:8000/api/"
  exit 1
}

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
