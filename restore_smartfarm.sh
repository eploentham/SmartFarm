#!/usr/bin/env bash
#
# restore_smartfarm.sh   (companion to dump_smartfarm.sh)
# ------------------------------------------------------------------------
# Restore a smartfarm dump (.sql.gz) into the LOCAL MariaDB on this machine.
#
#   * verifies the gzip file is not corrupt
#   * strips DEFINER=`user`@`host` clauses  -> views won't fail with
#     "definer does not exist" after moving to a new server
#   * asks for confirmation  (restore OVERWRITES the smartfarm database:
#     the dump contains DROP TABLE / CREATE DATABASE)
#   * verifies tables + views afterward
#
# Usage:
#   ./restore_smartfarm.sh <path-to-dump.sql.gz>
#   ./restore_smartfarm.sh latest        # restore the newest dump in BACKUP_DIR
#   ./restore_smartfarm.sh               # list available dumps
# ------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${HOME}/db_backups"
DB_NAME="smartfarm"

# ---- 1. Pick the dump file ----------------------------------------------
DUMP="${1:-}"

if [[ -z "$DUMP" ]]; then
  echo "Available dumps in $BACKUP_DIR:"
  ls -1t "$BACKUP_DIR"/${DB_NAME}_*.sql.gz 2>/dev/null | nl || echo "  (none found)"
  echo
  echo "Usage: $0 <path-to-dump.sql.gz>   |   $0 latest"
  exit 1
fi

if [[ "$DUMP" == "latest" ]]; then
  DUMP="$(ls -1t "$BACKUP_DIR"/${DB_NAME}_*.sql.gz 2>/dev/null | head -1)"
  [[ -n "$DUMP" ]] || { echo "No dumps found in $BACKUP_DIR"; exit 1; }
fi

[[ -f "$DUMP" ]] || { echo "ERROR: file not found: $DUMP"; exit 1; }

# ---- 2. Verify gzip integrity -------------------------------------------
echo "[*] Checking gzip integrity: $DUMP"
gunzip -t "$DUMP" || { echo "ERROR: corrupt gzip file -- do NOT restore this one"; exit 1; }
SIZE=$(du -h "$DUMP" | cut -f1)

# ---- 3. Confirm (DESTRUCTIVE) -------------------------------------------
echo
echo "  ==========================================================="
echo "   This will OVERWRITE the '$DB_NAME' database on THIS machine."
echo "   The dump includes DROP TABLE / CREATE DATABASE statements."
echo "   Source : $DUMP  ($SIZE)"
echo "   Target : local MariaDB (via sudo)"
echo "  ==========================================================="
echo
read -r -p "Type YES to proceed: " ANS
[[ "$ANS" == "YES" ]] || { echo "Aborted."; exit 1; }

# ---- 4. Restore, stripping DEFINER clauses ------------------------------
echo "[*] Restoring (DEFINER clauses stripped so views load cleanly) ..."
gunzip -c "$DUMP" \
  | sed -E 's/DEFINER=`[^`]+`@`[^`]+`//g' \
  | sudo mariadb
sudo mariadb -e "FLUSH PRIVILEGES;"

# ---- 5. Verify ----------------------------------------------------------
echo "[*] Verifying restored objects ..."
sudo mariadb "$DB_NAME" -e "
  SELECT COUNT(*) AS base_tables
    FROM information_schema.tables
   WHERE table_schema='$DB_NAME' AND table_type='BASE TABLE';
  SELECT COUNT(*) AS views
    FROM information_schema.views
   WHERE table_schema='$DB_NAME';"

echo "[*] Test view query (v_pump_health -- checks the definer fix):"
if sudo mariadb "$DB_NAME" -e "SELECT COUNT(*) AS v_pump_health_ok FROM v_pump_health;"; then
  echo "    -> view is queryable, no definer error."
else
  echo "    -> WARNING: view query failed; check the log above."
fi

echo "[*] Restore complete."