# Deployment Guide — Hostinger VPS

This is the source of truth for build, environment, VPS, and Nginx setup —
[FOUNDING_ENGINEER_PLAYBOOK.md](FOUNDING_ENGINEER_PLAYBOOK.md) §10 points here rather than
duplicating these steps. For frontend architecture and UI decisions during a
deploy-related change, see [PRODUCT_DESIGN_SYSTEM.md](PRODUCT_DESIGN_SYSTEM.md).

Before running through this guide, confirm these backend security items are
already in place — there is no separate production security audit document,
so this checklist is the record of them:
- JWT secret is freshly generated for production, not the local-dev value (§2, `JWT_SECRET`)
- Any seeded/test accounts from local development are removed or disabled
- OTP delivery is wired to a real SMS provider, not left in mock/log mode (§6, `SMS_PROVIDER`)
- File storage points at real R2/S3 credentials, not a local/mock path (§6, `S3_*`)

## 1. Server prerequisites

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
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
sudo cp deploy/courtbazaar-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now courtbazaar-backend
sudo systemctl status courtbazaar-backend   # confirm it's running
curl http://127.0.0.1:8000/api/             # should return the API version JSON
```

## 4. Frontend build

```bash
cd ../frontend
cp .env.example .env
nano .env                              # set REACT_APP_BACKEND_URL to the real API domain
npm ci
npm run build
```

The `build/` folder is what Nginx serves — no Node process runs in production
for the frontend.

## 5. Nginx

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

```bash
cd /var/www/courtbazaar
git pull origin main

cd backend
source venv/bin/activate && pip install -r requirements.txt && deactivate
sudo systemctl restart courtbazaar-backend

cd ../frontend
npm ci && npm run build
sudo systemctl reload nginx   # not strictly required, but harmless
```

## 8. Rollback

Stop the service, `git checkout` the previous known-good commit, reinstall/rebuild
both sides, restart, and re-check `/api/` plus the main user flows before
considering the incident closed. A rollback should be fast, simple, and
low-drama — don't stack fixes on top of a broken deploy; roll back first,
investigate after.

## 9. Docker / CI-CD / versioning

Not currently used. Docker only appears in local development, for running
MongoDB (see the Playbook §5) — production runs the backend and frontend
directly on the VPS via systemd/Nginx as described above, with no container
runtime and no CI/CD pipeline. If either is introduced later, this is the
document to update.
