#!/usr/bin/env bash
#
# Nightly backup of the crypto_trader database. Installed as a cron job.
#
# Prices are re-fetchable from Binance, but paper trades, the watchlist and
# generated signals are not — this protects them. Keeps 14 days.

set -euo pipefail

APP_DIR="/srv/cryptotrader"
ENV="$APP_DIR/backend/.env"
BACKUP_DIR="/var/backups/cryptotrader"
KEEP_DAYS=14
STAMP="$(date +%Y%m%d-%H%M%S)"

[[ -f "$ENV" ]] || { echo "$(date -Is) no .env at $ENV, aborting" >&2; exit 1; }

# Credentials live in one place: parse the SQLAlchemy DATABASE_URL, e.g.
#   mysql+pymysql://crypto_user:PASSWORD@127.0.0.1:3306/crypto_trader
DB_URL="$(grep -E '^DATABASE_URL=' "$ENV" | head -1 | cut -d= -f2-)"
rest="${DB_URL#*://}"                 # user:pass@host:port/db
creds="${rest%@*}"                    # user:pass
hostpart="${rest#*@}"                 # host:port/db
DB_USER="${creds%%:*}"
DB_PASSWORD="${creds#*:}"
hostport="${hostpart%%/*}"            # host:port
DB_NAME="${hostpart##*/}"; DB_NAME="${DB_NAME%%\?*}"
DB_HOST="${hostport%%:*}"

mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
echo "$(date -Is) starting backup of $DB_NAME"

SQL_FILE="$BACKUP_DIR/db-$STAMP.sql.gz"
# --single-transaction = consistent snapshot without locking the app out.
# MYSQL_PWD keeps the password out of the process list.
MYSQL_PWD="$DB_PASSWORD" mysqldump \
  --host="$DB_HOST" --user="$DB_USER" \
  --single-transaction --quick --routines --no-tablespaces \
  "$DB_NAME" | gzip -9 > "$SQL_FILE"
chmod 600 "$SQL_FILE"
echo "$(date -Is) database -> $SQL_FILE ($(du -h "$SQL_FILE" | cut -f1))"

# rotate
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'db-*.sql.gz' \
  -mtime +"$KEEP_DAYS" -print -delete | wc -l)"
echo "$(date -Is) rotated out $DELETED file(s) older than $KEEP_DAYS days"

# verify: a backup never tested is a guess. Confirm valid gzip + a known table.
gzip -t "$SQL_FILE" 2>/dev/null || { echo "$(date -Is) WARNING: $SQL_FILE not valid gzip" >&2; exit 1; }
zgrep -q "CREATE TABLE \`securities\`" "$SQL_FILE" || {
  echo "$(date -Is) WARNING: $SQL_FILE has no securities table — dump may be incomplete" >&2; exit 1; }

echo "$(date -Is) backup verified, $(ls -1 "$BACKUP_DIR" | wc -l) file(s) retained"
echo "$(date -Is) NOTE: these stay on this machine — copy them off-site if the data matters."
