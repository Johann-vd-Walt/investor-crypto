#!/usr/bin/env bash
#
# Obtain a Let's Encrypt cert for trade.mad-apps.co.za and switch its nginx site
# from the HTTP bootstrap to the real TLS site. Uses the SAME webroot + certbot
# the school uses, so nothing about the school's cert or site changes.
#
#     bash enable-tls-crypto.sh trade.mad-apps.co.za you@example.com
#
# Safe to run repeatedly. On any failure it leaves the HTTP bootstrap serving, so
# nginx keeps running.

set -euo pipefail

DOMAIN="${1:-trade.mad-apps.co.za}"
CERTBOT_EMAIL="${2:-}"
APP_DIR="/srv/cryptotrader"

SITE_TLS=/etc/nginx/sites-available/cryptotrader
SITE_BOOT_LINK=/etc/nginx/sites-enabled/cryptotrader-bootstrap
SITE_TLS_LINK=/etc/nginx/sites-enabled/cryptotrader

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m !! %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m!! %s\033[0m\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run this as root."

# ----------------------------------------------------------------- 1. DNS -----
say "Checking DNS"
RESOLVED="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}')"
SERVER_IP="$(curl -s --max-time 8 https://api.ipify.org 2>/dev/null || true)"
echo "  ${DOMAIN} resolves to: ${RESOLVED:-NOTHING}"
echo "  this server is:        ${SERVER_IP:-unknown}"
[[ -n "$RESOLVED" ]] || fail "No A record for ${DOMAIN}. Add one pointing at ${SERVER_IP:-this server}, wait for propagation, then re-run."
if [[ -n "$SERVER_IP" && "$RESOLVED" != "$SERVER_IP" ]]; then
  fail "${DOMAIN} points at ${RESOLVED}, not this server (${SERVER_IP}). Fix the A record and re-run."
fi
echo "  DNS is correct"

# ------------------------------------------------- 2. ACME path reachable? -----
say "Checking the ACME challenge path"
mkdir -p /var/www/certbot/.well-known/acme-challenge
TOKEN="crypto-test-$(date +%s)"
echo "$TOKEN" > "/var/www/certbot/.well-known/acme-challenge/$TOKEN"
chown -R www-data:www-data /var/www/certbot
systemctl is-active --quiet nginx || systemctl start nginx
FETCHED="$(curl -fsS --max-time 10 "http://${DOMAIN}/.well-known/acme-challenge/${TOKEN}" 2>/dev/null || true)"
rm -f "/var/www/certbot/.well-known/acme-challenge/$TOKEN"
[[ "$FETCHED" == "$TOKEN" ]] && echo "  reachable" || warn "Could not fetch the test challenge — continuing; certbot will give its own verdict."

# ---------------------------------------------------------- 3. certificate ----
say "Obtaining the certificate (webroot — nginx keeps running)"
if [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
  echo "  already have one for ${DOMAIN}"
else
  EMAIL_ARGS=(--register-unsafely-without-email)
  [[ -n "$CERTBOT_EMAIL" ]] && EMAIL_ARGS=(--email "$CERTBOT_EMAIL")
  certbot certonly --webroot -w /var/www/certbot \
    --non-interactive --agree-tos "${EMAIL_ARGS[@]}" -d "$DOMAIN" || \
    fail "certbot failed. The HTTP site is still serving. Read certbot's message above (usually DNS or port 80)."
  echo "  certificate issued"
fi

# -------------------------------------------------------- 4. switch nginx ------
say "Switching this site to HTTPS"
[[ -f "$SITE_TLS" ]] || fail "$SITE_TLS missing. Run provision-crypto.sh first."
ln -sf "$SITE_TLS" "$SITE_TLS_LINK"
rm -f "$SITE_BOOT_LINK"
if ! nginx -t; then
  warn "TLS config failed to validate — reverting to the HTTP bootstrap."
  rm -f "$SITE_TLS_LINK"
  ln -sf /etc/nginx/sites-available/cryptotrader-bootstrap "$SITE_BOOT_LINK"
  nginx -t && systemctl reload nginx
  fail "Reverted. nginx is still running."
fi
systemctl reload nginx
echo "  nginx is serving HTTPS for ${DOMAIN}"

# Renewal is handled by the same certbot timer the school relies on; this cert
# is just another line in its renewal set. Confirm the timer exists.
systemctl list-timers 2>/dev/null | grep -q certbot && echo "  certbot renewal timer is active" || \
  warn "No certbot timer found — check the school's renewal setup (/etc/cron.d/certbot-renew)."

cat <<DONE

$(printf '\033[1;32m')HTTPS is on:$(printf '\033[0m')  https://${DOMAIN}

If the app is not deployed yet:  bash ${APP_DIR}/deploy/deploy-crypto.sh
DONE
