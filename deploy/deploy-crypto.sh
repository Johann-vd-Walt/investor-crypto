#!/usr/bin/env bash
#
# Deploy or update Crypto Swing-Trader. Run as root after provision-crypto.sh.
#
#     bash /srv/cryptotrader/deploy/deploy-crypto.sh
#
# Installs Python deps, runs migrations, seeds the crypto asset list, builds the
# frontend, restarts the service, reloads nginx, and checks /api/health.
# On first run it also back-fills price history (slow — a few minutes).

set -euo pipefail

APP_USER="cryptotrader"
APP_DIR="/srv/cryptotrader"
VENV="$APP_DIR/backend/.venv"
PY="$VENV/bin/python"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m !! %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m!! %s\033[0m\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run this as root."
[[ -d "$APP_DIR/backend" ]] || fail "$APP_DIR/backend not found. Copy the code up first."
[[ -f "$APP_DIR/backend/.env" ]] || fail "$APP_DIR/backend/.env not found. Run provision-crypto.sh first."

# ------------------------------------------------------------- permissions ----
say "Setting ownership"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/backend/.env"
mkdir -p "$APP_DIR/.cache/matplotlib"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/.cache"

# ----------------------------------------------------------------- backend ----
say "Installing Python dependencies"
[[ -d "$VENV" ]] || sudo -u "$APP_USER" python3 -m venv "$VENV"
sudo -u "$APP_USER" "$VENV/bin/pip" install --quiet --upgrade pip wheel
sudo -u "$APP_USER" "$VENV/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt"
echo "  done"

# ---------------------------------------------------------------- database ----
say "Applying database migrations"
cd "$APP_DIR/backend"
sudo -u "$APP_USER" "$VENV/bin/alembic" upgrade head | sed 's/^/  /'

say "Seeding the crypto asset list (idempotent)"
sudo -u "$APP_USER" "$PY" -m app.ingestion.seed_securities | sed 's/^/  /'

# First-run price back-fill only. Re-running deploy will NOT re-ingest years of
# data every time — the scheduler keeps prices fresh after the first load.
say "Checking whether price history needs a first-time back-fill"
NEED_BOOTSTRAP="$(sudo -u "$APP_USER" "$PY" - <<'PY'
from app.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    n = db.execute(text("SELECT COUNT(*) FROM price_bars")).scalar() or 0
finally:
    db.close()
print("yes" if n == 0 else "no")
PY
)"
if [[ "$NEED_BOOTSTRAP" == "yes" ]]; then
  warn "No prices yet — back-filling ~5 years for every asset. This takes a few minutes."
  sudo -u "$APP_USER" "$PY" - <<'PY'
from app.db.session import SessionLocal
from app.repositories import securities as s
from app.ingestion.jobs import ingest_daily_prices, ingest_macro, compute_indicators
db = SessionLocal(); tickers = [x.ticker for x in s.list_securities(db, limit=1000)[0]]; db.close()
print(f"  {len(tickers)} assets")
for t in tickers:
    ingest_daily_prices(tickers=[t], lookback_days=1825)
print("  macro:", ingest_macro())
print("  indicators:", compute_indicators())
PY
else
  echo "  prices already present — skipping back-fill"
fi

# ---------------------------------------------------------------- frontend ----
say "Building the frontend"
cd "$APP_DIR/frontend"
sudo -u "$APP_USER" HOME="$APP_DIR" npm ci --no-fund --no-audit --silent \
  || sudo -u "$APP_USER" HOME="$APP_DIR" npm install --no-fund --no-audit --silent
sudo -u "$APP_USER" HOME="$APP_DIR" npm run build
[[ -f "$APP_DIR/frontend/dist/index.html" ]] || fail "The frontend build produced no dist/index.html"
echo "  built into frontend/dist"

# nginx (www-data) must traverse the tree and read the assets.
chmod 755 "$APP_DIR"
chmod -R a+rX "$APP_DIR/frontend/dist"

# ----------------------------------------------------------------- service ----
say "Restarting the service"
cp "$APP_DIR/deploy/cryptotrader.service" /etc/systemd/system/cryptotrader.service
systemctl daemon-reload
systemctl restart cryptotrader
sleep 3
if ! systemctl is-active --quiet cryptotrader; then
  journalctl -u cryptotrader -n 40 --no-pager
  fail "The service did not start. The log above should say why."
fi
echo "  cryptotrader is active"

say "Reloading nginx"
nginx -t && systemctl reload nginx

# ------------------------------------------------------------ health check ----
say "Checking health"
for _ in $(seq 1 15); do
  BODY="$(curl -fsS --max-time 5 http://127.0.0.1:8001/api/health 2>/dev/null || true)"
  [[ -n "$BODY" ]] && { echo "  $BODY"; break; }
  sleep 2
done
[[ -n "${BODY:-}" ]] || fail "The API did not answer on 127.0.0.1:8001. Check: journalctl -u cryptotrader -n 60"

DOMAIN="$(grep -oP '(?<=FRONTEND_ORIGIN=https://)[^,]+' "$APP_DIR/backend/.env" | head -1 || true)"
cat <<DONE

$(printf '\033[1;32m')Deployed.$(printf '\033[0m')

  App      https://${DOMAIN:-trade.mad-apps.co.za}
  Service  systemctl status cryptotrader
  Logs     journalctl -u cryptotrader -f
  Update   bash ${APP_DIR}/deploy/deploy-crypto.sh

If the login still says it is disabled, set TOTP_SECRET in
${APP_DIR}/backend/.env (enrol with: cd ${APP_DIR}/backend &&
sudo -u ${APP_USER} ${PY} -m app.auth_setup) and re-run this script.
DONE
