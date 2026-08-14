# Deploying Crypto Swing-Trader next to VirtualSchool

This deploys **trade.mad-apps.co.za** onto the **same server** that already runs
VirtualSchool, reusing its nginx, MySQL and certbot instead of fighting them.
It never touches the `virtual_school` database or the school's site.

Same shape as the school's runbook: you run these from **Git Bash on your Windows
machine** and over **SSH on the server**. I can't SSH in — I only write the kit.

You log in as **`johannvdwalt`** (a sudo user) with the `id_mad_apps` key. Your
`~/.ssh/config` maps `trade.mad-apps.co.za` to that user + key, so `ssh
trade.mad-apps.co.za` needs no `-i` or username. The deploy scripts need root, so
they're run with **`sudo`**.

> ⚠️ These are the scripts to use for this server. The Docker/Caddy kit
> ([DEPLOY.md](DEPLOY.md)) is only for a *fresh, empty* server — it would collide
> with the school's nginx on ports 80/443. Ignore it here.

---

## What co-exists, and how

| Shared resource | VirtualSchool | Crypto Swing-Trader | Kept apart by |
|---|---|---|---|
| nginx (80/443) | `virtualschool` site | `cryptotrader` site | different `server_name` |
| MySQL | `virtual_school` db | `crypto_trader` db + `crypto_user` | separate db + user/grants |
| Backend port | `127.0.0.1:8000` | `127.0.0.1:8001` | different port |
| systemd | `virtualschool.service` | `cryptotrader.service` | different unit |
| TLS | certbot (shared timer + `/var/www/certbot`) | same certbot, extra cert | one renewal timer covers both |

---

## Step 0 — create the DNS A record

`trade.mad-apps.co.za` → the server's public IP (the **same** IP the school uses).
Verify from your own machine before continuing, or certbot can't get a cert:

```bash
nslookup trade.mad-apps.co.za
```

## Step 1 — copy the code up (RUN ON YOUR WINDOWS MACHINE, in Git Bash)

`/srv` is root-owned and `johannvdwalt` can't write there directly, so rsync into
your home first, then sudo-copy it across on the server.

```bash
cd /c/Users/JohannvanderWalt/Documents/GitHub/Investor
rsync -avz --delete \
  --exclude '.venv' --exclude 'node_modules' --exclude 'dist' \
  --exclude '.env' --exclude '__pycache__' --exclude '.git' \
  ./ trade.mad-apps.co.za:~/cryptotrader-src/
```

Then on the server:
```bash
ssh trade.mad-apps.co.za
sudo mkdir -p /srv/cryptotrader
sudo rsync -a --delete ~/cryptotrader-src/ /srv/cryptotrader/
```

> `.env` is excluded on purpose — the server generates its own with its own DB
> password. Never copy your local one up.

## Step 2 — provision (ON THE SERVER)

```bash
sudo bash /srv/cryptotrader/deploy/provision-crypto.sh trade.mad-apps.co.za you@email.address
```
Creates the `crypto_trader` database + user on the existing MySQL, the service
user, `backend/.env` (with a generated DB password + `AUTH_SECRET_KEY`), the
nginx site, and the systemd unit. If the A record is already live it also gets
the TLS certificate.

## Step 3 — turn on the login

Edit `/srv/cryptotrader/backend/.env` (`sudo nano /srv/cryptotrader/backend/.env`)
and set `TOTP_SECRET`. Two choices:

- **Reuse your existing Google Authenticator entry** — paste the same base32
  secret you already scanned. The same 6-digit codes then work here too.
- **Enrol fresh** — get a new QR:
  ```bash
  cd /srv/cryptotrader/backend
  sudo -u cryptotrader .venv/bin/python -m app.auth_setup
  ```
  Scan it, then paste the printed secret into `TOTP_SECRET=`.

Leaving it blank means the app is **open to anyone** — don't, on a public URL.

## Step 4 — deploy

```bash
sudo bash /srv/cryptotrader/deploy/deploy-crypto.sh
```
Installs deps, runs migrations, seeds the asset list, **back-fills ~5 years of
prices on the first run** (a few minutes), builds the frontend, starts the
service, reloads nginx, and refuses to claim success unless `/api/health`
answers.

Then open **https://trade.mad-apps.co.za** — you should get the login.

## Step 5 — if TLS was skipped (A record wasn't ready at step 2)

```bash
sudo bash /srv/cryptotrader/deploy/enable-tls-crypto.sh trade.mad-apps.co.za you@email.address
```

---

## Everyday commands

```bash
systemctl status cryptotrader
journalctl -u cryptotrader -f                      # live logs (scheduler + API)
sudo bash /srv/cryptotrader/deploy/deploy-crypto.sh # deploy an update (won't re-ingest history)
```

To update the code later, repeat Step 1 (rsync to `~/cryptotrader-src`, then
`sudo rsync` into `/srv/cryptotrader`) before running the deploy script.

Confirm neither app disturbed the other:
```bash
systemctl is-active virtualschool cryptotrader     # both: active
ss -tlnp | grep -E ':(8000|8001)'                  # 8000 school, 8001 crypto
sudo -u cryptotrader mysql -e "SHOW DATABASES;" 2>/dev/null || \
  mysql -e "SHOW DATABASES;"                        # virtual_school AND crypto_trader
```

## Honest caveats

- **Not build-tested from the dev machine** (no Linux/Docker here). If a script
  errors, send me the output — it'll be a path/version detail.
- **Binance must be reachable from the server.** Verify:
  `curl -s -o /dev/null -w '%{http_code}\n' https://data-api.binance.vision/api/v3/ping`
- **One worker on purpose** — the scheduler runs in-process; more workers would
  duplicate every job.
- Still **decision-support only**. It does not place trades, and the backtests
  did not beat buy-and-hold over the tested window. Deploying changes neither.
- If you copied files from Windows and a script fails on line 1, strip CR:
  `sed -i 's/\r$//' /srv/cryptotrader/deploy/*.sh`
```
