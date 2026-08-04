#!/usr/bin/env bash
#
# dump_smartfarm.sh
# ------------------------------------------------------------------------
# Dump the "smartfarm" database from the SOURCE MariaDB (pi5camera01)
# over Tailscale into a timestamped, gzipped .sql on THIS host (PN64 .254).
#
# Works for a one-time migration AND as a repeatable backup job.
# Run ON the PN64. It connects to pi5camera01 as a network client.
# ------------------------------------------------------------------------
set -euo pipefail

# ---- Config -------------------------------------------------------------
SRC_HOST="100.74.144.57"                          # pi5camera01 Tailscale IP -- CONFIRM this
SRC_PORT="3306"
DB_NAME="smartfarm"
OUT_DIR="/home/ekapop/db_backups"                 # where dumps are stored
CRED_FILE="/home/ekapop/.mariadb_migrate.cnf"     # holds user+password (chmod 600)
KEEP_DAYS=14                                       # auto-delete dumps older than this
# ------------------------------------------------------------------------

TS="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR}/${DB_NAME}_${TS}.sql.gz"

mkdir -p "$OUT_DIR"

if [[ ! -f "$CRED_FILE" ]]; then
  echo "ERROR: credential file not found: $CRED_FILE" >&2
  echo "Create it (see setup notes) and 'chmod 600' it before running." >&2
  exit 1
fi

echo "[$(date '+%F %T')] Dumping '${DB_NAME}' from ${SRC_HOST}:${SRC_PORT} ..."

# Flag rationale:
#   --single-transaction  : consistent snapshot of InnoDB tables, no table locks
#   --routines            : include stored procedures / functions
#   --triggers            : include triggers
#   --events              : include scheduled events
#   --databases           : include CREATE DATABASE + USE, so import recreates the DB
#   --default-character-set=utf8mb4 : preserve Thai text correctly
mariadb-dump \
  --defaults-extra-file="$CRED_FILE" \
  -h "$SRC_HOST" -P "$SRC_PORT" \
  --single-transaction \
  --routines --triggers --events \
  --default-character-set=utf8mb4 \
  --databases "$DB_NAME" \
  | gzip > "$OUT_FILE"

# ---- Sanity check: dump must be non-trivially sized ---------------------
SIZE=$(stat -c%s "$OUT_FILE")
if (( SIZE < 1000 )); then
  echo "ERROR: dump is only ${SIZE} bytes -- likely failed. Check credentials/privileges." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

# ---- Retention: prune old dumps -----------------------------------------
find "$OUT_DIR" -name "${DB_NAME}_*.sql.gz" -type f -mtime +"$KEEP_DAYS" -delete

echo "[$(date '+%F %T')] OK -> ${OUT_FILE} (${SIZE} bytes)"
echo ""
echo "Import into the local PN64 MariaDB with:"
echo "  gunzip < ${OUT_FILE} | sudo mariadb"
