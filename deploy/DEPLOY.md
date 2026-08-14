# Deploying Crypto Swing-Trader to trade.mad-apps.co.za

> 🚫 **Not for the mad-apps server.** This Docker/Caddy kit assumes a *fresh,
> empty* server and binds ports 80/443 itself — on vs.mad-apps.co.za that
> collides head-on with the VirtualSchool nginx already using those ports.
> For that server use **[RUNBOOK-crypto.md](RUNBOOK-crypto.md)** (native
> systemd + the existing nginx/MySQL/certbot), which is built to co-exist.
> Keep this file only if you ever move the app to a server of its own.


A self-contained Docker stack: **Caddy** (auto-HTTPS + serves the React app +
proxies `/api`), **backend** (FastAPI + scheduler), **MySQL 8**. You run this on
the server — I can't SSH in from the dev session.

> **Read first — this app was built as a personal, local, dev-mode tool.**
> Before exposing it to the internet you MUST: (1) enable the TOTP login,
> (2) use strong DB passwords, (3) let Caddy give you HTTPS. Steps below do all
> three. The app still does **not** place trades and is decision-support only.

---

## 0. Prerequisites on the server (vs.mad-apps.co.za)
- **Docker Engine + Compose plugin** installed (`docker --version`, `docker compose version`).
- **Ports 80 and 443 reachable** from the internet (open the firewall/security group).
- **DNS:** create an **A record** `trade.mad-apps.co.za` → the server's public IP.
  Verify it resolves (`dig +short trade.mad-apps.co.za`) **before** step 3, or
  Caddy can't obtain a TLS certificate.

> ⚠️ **If the server already runs nginx/Apache on 80/443** (likely, if it hosts
> other mad-apps sites), Caddy can't also bind them — see "Behind an existing
> proxy" at the bottom.

## 1. Get the code onto the server
```bash
git clone <your repo>  crypto-trader     # or scp/rsync the project folder
cd crypto-trader/deploy
cp .env.production.example .env
```

## 2. Configure secrets — edit `deploy/.env`
- Set strong `MYSQL_PASSWORD` and `MYSQL_ROOT_PASSWORD`, and make `DATABASE_URL`
  use the **same** user/password/db.
- Set a long random `AUTH_SECRET_KEY`.
- Leave `TOTP_SECRET` blank for now (enabled in step 4).

## 3. Build & start
```bash
docker compose up -d --build
docker compose logs -f caddy      # watch it obtain the TLS cert (first run ~30s)
```
Visit **https://trade.mad-apps.co.za** — you should see the app (login not yet on).

## 4. Turn ON the login (do this before real use)
```bash
docker compose exec backend python -m app.auth_setup    # prints a QR + secret
```
Scan the QR with Google Authenticator (or "Enter a setup key" with the secret).
Then put that secret into `deploy/.env`:
```
TOTP_SECRET=<the secret it printed>
```
Restart the backend so the gate turns on:
```bash
docker compose up -d backend
```
Reload the site — it now asks for the 6-digit code.

## 5. Load initial data (one-off; the scheduler keeps it fresh after)
```bash
docker compose exec backend python -m app.ingestion.seed_securities        # seed crypto assets
docker compose exec backend python - <<'PY'
from app.db.session import SessionLocal
from app.repositories import securities as s
from app.ingestion.jobs import ingest_daily_prices, ingest_macro, compute_indicators
db = SessionLocal(); tickers = [x.ticker for x in s.list_securities(db, limit=1000)[0]]; db.close()
for t in tickers:
    ingest_daily_prices(tickers=[t], lookback_days=1825)
print(ingest_macro()); print(compute_indicators())
PY
```

## Operations
- **Update after code changes:** `git pull && docker compose up -d --build`
- **Logs:** `docker compose logs -f backend`
- **DB backup:** `docker compose exec db mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" crypto_trader > backup.sql`
- **Stop:** `docker compose down` (data persists in named volumes)
- Migrations run automatically on every backend start.

## Notes / caveats (honest)
- **Single worker on purpose** — the price/signal scheduler runs in-process, so
  running multiple web workers would duplicate every job. Keep `--workers 1`
  (already set). This is plenty for one user.
- **Binance/alternative.me must be reachable from the server.** Some hosts geo-block
  Binance; `data-api.binance.vision` is usually fine, but verify from the server:
  `docker compose exec backend python -c "import httpx;print(httpx.get('https://data-api.binance.vision/api/v3/ping').status_code)"`
- **This stack has NOT been build-tested from the dev machine** (no Docker there,
  and images are Linux). If `docker compose build` errors, it'll be a
  dependency/version detail — send me the log and I'll fix it.
- Single-factor TOTP + HTTPS is appropriate for a personal single-user tool, not
  a hardened multi-tenant service.

## Behind an existing reverse proxy (if 80/443 are taken)
Don't let Caddy own 80/443. Instead:
1. In `deploy/Caddyfile`, change the first line `trade.mad-apps.co.za {` to `:8080 {`
   (plain HTTP, no TLS — your front proxy terminates TLS).
2. In `deploy/docker-compose.yml`, change caddy `ports:` to `- "127.0.0.1:8080:8080"`.
3. `docker compose up -d --build`.
4. Add a server block to your existing nginx and reload it:
```nginx
server {
    server_name trade.mad-apps.co.za;
    location / { proxy_pass http://127.0.0.1:8080; proxy_set_header Host $host;
                 proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-For $remote_addr; }
    listen 443 ssl;   # use your existing certbot/Let's Encrypt cert for this domain
}
```
(Run `certbot --nginx -d trade.mad-apps.co.za` if you manage certs with certbot.)
