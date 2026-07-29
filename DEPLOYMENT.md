# Deployment Guide — Hostinger VPS

This is the source of truth for build, environment, VPS, and Nginx setup —
[FOUNDING_ENGINEER_PLAYBOOK.md](FOUNDING_ENGINEER_PLAYBOOK.md) §10 points here rather than
duplicating these steps. For frontend architecture and UI decisions during a
deploy-related change, see [PRODUCT_DESIGN_SYSTEM.md](PRODUCT_DESIGN_SYSTEM.md).

> **This doc previously described a setup that was never actually deployed
> this way** (npm instead of Yarn, Nginx pointing directly at the repo's
> `frontend/build`, a `courtbazaar-backend` service name) — it caused a real
> incident where following it produced a broken build. It's been rewritten
> to match what's actually running in production. If you change how
> deployment works, update this file in the same commit — a deploy doc that
> drifts from reality is worse than no doc.

Before running through this guide, confirm these backend security items are
already in place — there is no separate production security audit document,
so this checklist is the record of them:
- JWT secret is freshly generated for production, not the local-dev value (§2, `JWT_SECRET`)
- Any seeded/test accounts from local development are removed or disabled
- OTP delivery is wired to a real SMS provider, not left in mock/log mode (§6, `SMS_PROVIDER`)
- File storage points at real R2/S3 credentials, not a local/mock path (§6, `S3_*`)

## 0. Package manager: Yarn, not npm

This project is Yarn-canonical — see the `packageManager` field in
`frontend/package.json`. There is no `package-lock.json`; only
`frontend/yarn.lock` is checked in, and a `preinstall` script
(`npx only-allow yarn`) hard-fails if `npm install`/`npm ci` is run by
mistake, rather than silently producing a broken or divergent install.
**Never run `npm install`, `npm ci`, or delete `yarn.lock`.**

## 1. Server prerequisites

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo corepack enable   # provides the exact Yarn version pinned in packageManager
# MongoDB: either install locally (see MongoDB's official Debian/Ubuntu repo
# instructions) or point MONGO_URL at a managed instance (Atlas free tier
# works fine for this scale).
```

Create a dedicated non-root user to run the app:

```bash
sudo useradd -m -s /bin/bash courtbazaar
sudo mkdir -p /var/www/courtbazaar
sudo chown courtbazaar:courtbazaar /var/www/courtbazaar
```

## 2. Get the code onto the server

```bash
sudo -u courtbazaar git clone <your-repo-url> /var/www/courtbazaar
cd /var/www/courtbazaar
```

> **Unverified — confirm on your VPS.** This guide assumes the repo lives at
> `/var/www/courtbazaar` (matching `WorkingDirectory` in
> `deploy/courtbazaar.service` below). If your actual checkout is somewhere
> else (e.g. a home directory), either move it here or update every path in
> this file and in `deploy/courtbazaar.service` to match — don't let the doc
> and the real path silently diverge again.

## 3. Backend setup

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt        # production deps only
cp .env.example .env
nano .env                              # fill in every value — see checklist below
deactivate
```

Bootstrap the first admin account (only once, interactively — never scripted
with a hardcoded password):

```bash
source venv/bin/activate
python scripts/create_admin.py
deactivate
```

Install the systemd unit:

```bash
sudo cp deploy/courtbazaar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now courtbazaar
sudo systemctl status courtbazaar   # confirm it's running
curl http://127.0.0.1:8000/api/     # should return the API version JSON
```

## 4. Frontend build

```bash
cd ../frontend
cp .env.example .env
nano .env                              # set REACT_APP_BACKEND_URL to the real API domain
yarn install --frozen-lockfile
yarn build
```

`yarn build` also writes `build/version.json` (the current git commit) as a
`prebuild` step — this is how you verify a deployment actually shipped what
you think it shipped (see §7).

Nginx does **not** point at this `frontend/build` folder directly — the
built files are copied into Nginx's actual document root, `/var/www/html`
(see §5). No Node process runs in production for the frontend either way.

```bash
rsync -a --delete --exclude='.well-known' build/ /var/www/html/
```

`--exclude='.well-known'` preserves anything ACME/certbot has placed there
for TLS certificate validation — don't drop that flag.

## 5. Nginx

Document root is `/var/www/html`, not the repo. Install once:

```bash
sudo cp ../deploy/nginx.conf /etc/nginx/sites-available/courtbazaar
sudo ln -s /etc/nginx/sites-available/courtbazaar /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Then add TLS (do this before announcing the domain publicly):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d courtbazaar.in -d www.courtbazaar.in
```

## 6. Environment variable checklist

Every var below must be set on the server before real traffic hits it —
cross-reference `backend/.env.example` for the full list with inline notes.

- [ ] `MONGO_URL`, `DB_NAME` — reachable from this VPS
- [ ] `JWT_SECRET` — freshly generated, not the local-dev value
- [ ] `CORS_ORIGINS` — the real frontend domain, not `*`
- [ ] `S3_ENDPOINT_URL` / `S3_BUCKET` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` — real Cloudflare R2 (or AWS S3) credentials
- [ ] `EMAIL_PROVIDER` + `BREVO_API_KEY` (or `RESEND_API_KEY`) — real key, or lead/status emails silently no-op
- [ ] `SMS_PROVIDER` + `FAST2SMS_API_KEY` (or `MSG91_AUTH_KEY`) — real key, or OTP login can't actually deliver codes
- [ ] `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` — production (not test) keys
- [ ] `REACT_APP_BACKEND_URL` (frontend `.env`, baked in at build time) — the real API domain

## 7. Redeploying after a change

Use `deploy/deploy.sh` — it runs every step below in order and, critically,
**fails loudly instead of finishing silently wrong** if the live site's
`version.json` doesn't match the commit it just deployed:

```bash
cd /var/www/courtbazaar
./deploy/deploy.sh
```

Equivalent by hand, if you need to run a step in isolation:

```bash
cd /var/www/courtbazaar
git fetch origin
git pull origin main

cd backend
source venv/bin/activate && pip install -r requirements.txt && deactivate
sudo systemctl restart courtbazaar

cd ../frontend
yarn install --frozen-lockfile
yarn build
rsync -a --delete --exclude='.well-known' build/ /var/www/html/

sudo nginx -t && sudo systemctl reload nginx

# Verify: does the live site match what you just pushed?
curl -s https://courtbazaar.in/version.json
git rev-parse HEAD
# The "commit" field above must equal this HEAD hash.
```

If `npm ci`/`npm install` ever gets run here by habit, it will hard-fail
immediately (`preinstall` guard) instead of quietly building against a stale
or wrong dependency tree — that failure is correct behavior, not a bug to
work around. Fix the command, not the guard.

## 8. Rollback

Stop the service, `git checkout` the previous known-good commit, reinstall/rebuild
both sides, restart, and re-check `/api/` plus the main user flows before
considering the incident closed. A rollback should be fast, simple, and
low-drama — don't stack fixes on top of a broken deploy; roll back first,
investigate after.

## 9. Docker / CI-CD / versioning

Docker is not used. Docker only appears in local development, for running
MongoDB (see the Playbook §5) — production runs the backend and frontend
directly on the VPS via systemd/Nginx as described above, with no container
runtime.

CI/CD: `.github/workflows/deploy.yml` deploys automatically on every push to
`main`. It SSHes into the VPS as `root` and runs `deploy/deploy.sh` — the
same script described in §7, unchanged. The workflow does not reimplement
any deploy steps itself; it only triggers the existing script, so §7 remains
the source of truth for what a deploy actually does. It can also be run
manually from the Actions tab (`workflow_dispatch`) without a new push.

Required GitHub Actions secrets (Settings → Secrets and variables → Actions):

- `VPS_HOST` — the VPS IP or hostname
- `VPS_SSH_KEY` — private key for a `root`-capable SSH keypair; the matching
  public key must be in `root`'s `~/.ssh/authorized_keys` on the VPS
- `VPS_PORT` — optional, defaults to `22` if unset

### Branch model

```
feature/* → PR → develop → (QA/testing) → PR → main → auto-deploy
```

- `develop` is an integration/QA branch. Merging into it does **not**
  deploy anything — it exists purely so multiple in-flight features can be
  tested together before going to production.
- `main` is production. Every push to `main` (i.e. every merged PR) deploys
  automatically via the workflow above — treat a merge to `main` as
  equivalent to running `deploy/deploy.sh` yourself.
- Branch protection on `main` (and ideally `develop`) should require PR
  review and passing checks before merge — configure this under Settings →
  Branches, since it isn't something a workflow file can enforce on its own.
