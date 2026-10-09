#!/bin/bash

# Hourly PostgreSQL backups; schedule this script with cron (see docs/zalohy.md).
set -Eeuo pipefail
umask 077

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S%z')" "$*"
}

trap 'log "ERROR: backup or retention failed (line $LINENO)." >&2' ERR

for tool in pg_dump pg_restore flock find mktemp; do
    command -v "$tool" >/dev/null || {
        log "ERROR: required command is missing: $tool" >&2
        exit 1
    }
done

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKUP_DIR=${1:-"$SCRIPT_DIR/../../archiv"}
mkdir -p -- "$BACKUP_DIR"
BACKUP_DIR=$(cd -- "$BACKUP_DIR" && pwd)

# Keep the lock file in place: deleting it would allow overlapping processes.
exec 9>"$BACKUP_DIR/.orders_prod_auto.lock"
if ! flock -n 9; then
    log 'SKIP: another backup is running.'
    exit 0
fi

DUMP_FILE="$BACKUP_DIR/orders_prod_auto_$(date '+%Y%m%d_%H%M%S').dump"
if [[ -e "$DUMP_FILE" ]]; then
    log "ERROR: backup already exists: $DUMP_FILE" >&2
    exit 1
fi

TEMP_FILE=$(mktemp "$BACKUP_DIR/.orders_prod_auto_XXXXXX.part")
trap 'rm -f -- "$TEMP_FILE"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

log 'START: dumping orders_prod.'
pg_dump -h 127.0.0.1 -p 5432 -U orders_user -w -F c -b -v \
    -f "$TEMP_FILE" orders_prod

# Reading the table of contents catches invalid archives, but does not replace
# a test restore into a separate database.
pg_restore --list "$TEMP_FILE" >/dev/null
mv -- "$TEMP_FILE" "$DUMP_FILE"
log "SAVED: $DUMP_FILE"

# GNU find counts full minutes: +4319 means at least 4320 minutes (72 hours).
# Delete only completed automatic dumps, and only after a successful backup.
find "$BACKUP_DIR" -maxdepth 1 -regextype posix-extended -type f \
    -regex '.*/orders_prod_auto_[0-9]{8}_[0-9]{6}\.dump' \
    -mmin +4319 -print -delete
log 'DONE: backups older than 72 hours removed.'
