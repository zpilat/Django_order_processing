#!/bin/bash

# Jednorázová synchronizace exportů z analyzátoru Vanta.
# Skript je určený pro opakované spouštění pomocí systemd.

REMOTE="//192.168.1.152/Vanta"
REMOTE_DIR="exports"
DEST="/home/pilat/vanta_exports"
AUTH="/root/.vanta-smb"
LOG="/var/log/vanta-sync.log"
STATUS="$DEST/.vanta-sync-status.json"
LOCK="$DEST/.vanta-sync.lock"

mkdir -p "$DEST"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG"
}

json_number_or_null() {
    if [ -n "$1" ]; then
        printf '%s' "$1"
    else
        printf 'null'
    fi
}

write_status() {
    local available="$1"
    local running="$2"
    local remote_files="$3"
    local downloaded_files="$4"
    local remaining_files="$5"
    local error="$6"
    local checked_at
    local error_json="null"
    local status_tmp="$STATUS.tmp.$$"

    checked_at="$(date --iso-8601=seconds)"
    if [ -n "$error" ]; then
        error_json="\"$error\""
    fi

    printf '{\n  "checked_at": "%s",\n  "available": %s,\n  "running": %s,\n  "remote_files": %s,\n  "downloaded_files": %s,\n  "remaining_files": %s,\n  "error": %s\n}\n' \
        "$checked_at" \
        "$available" \
        "$running" \
        "$(json_number_or_null "$remote_files")" \
        "$(json_number_or_null "$downloaded_files")" \
        "$(json_number_or_null "$remaining_files")" \
        "$error_json" \
        > "$status_tmp"

    chmod 0644 "$status_tmp"
    mv -- "$status_tmp" "$STATUS"
}

extract_filenames() {
    local listing="$1"
    local line
    local filename

    while IFS= read -r line; do
        filename=""

        # Vezmeme pouze název zakončený .csv nebo .json.
        # Všechny SMB atributy za názvem souboru se zahodí.
        if [[ "$line" =~ ^[[:space:]]*(.*\.(csv|json))[[:space:]]+[A-Z]+[[:space:]]+[0-9]+ ]]; then
            filename="${BASH_REMATCH[1]}"
        fi

        [ -n "$filename" ] && printf '%s\n' "$filename"
    done <<< "$listing"
}

# Dvě souběžná spuštění nesmějí pracovat se stejnými soubory.
exec 9>"$LOCK"
if ! flock -n 9; then
    exit 0
fi

write_status "null" "true" "" "0" "" ""

LIST=$(
    smbclient "$REMOTE" \
        -A "$AUTH" \
        -c "cd $REMOTE_DIR; ls" \
        2>/dev/null
)
RC=$?

if [ "$RC" -ne 0 ]; then
    write_status "false" "false" "" "0" "" "nelze načíst adresář exports"
    exit 0
fi

mapfile -t FILES < <(extract_filenames "$LIST")
REMOTE_COUNT="${#FILES[@]}"
DOWNLOADED_COUNT=0

write_status "true" "true" "$REMOTE_COUNT" "0" "$REMOTE_COUNT" ""

for filename in "${FILES[@]}"; do
    [ -z "$filename" ] && continue

    log "Nový soubor: $filename"

    rm -f -- "$DEST/$filename.tmp"

    smbclient "$REMOTE" \
        -A "$AUTH" \
        -c "lcd \"$DEST\"; cd \"$REMOTE_DIR\"; get \"$filename\" \"$filename.tmp\"" \
        >> "$LOG" 2>&1

    RC=$?

    if [ "$RC" -ne 0 ] || [ ! -f "$DEST/$filename.tmp" ]; then
        rm -f -- "$DEST/$filename.tmp"
        log "CHYBA při stahování: $filename"
        continue
    fi

    chmod 0644 "$DEST/$filename.tmp"

    if [ -f "$DEST/$filename" ]; then
        if cmp -s -- "$DEST/$filename.tmp" "$DEST/$filename"; then
            rm -f -- "$DEST/$filename.tmp"
        else
            rm -f -- "$DEST/$filename.tmp"
            log "KONFLIKT: lokální soubor se stejným názvem má jiný obsah: $filename"
            continue
        fi
    else
        mv -- "$DEST/$filename.tmp" "$DEST/$filename"
        DOWNLOADED_COUNT=$((DOWNLOADED_COUNT + 1))
        log "Stažen: $filename"
    fi

    # Vzdálený soubor mažeme až poté, co je kompletní lokální kopie na finálním místě.
    smbclient "$REMOTE" \
        -A "$AUTH" \
        -c "cd \"$REMOTE_DIR\"; del \"$filename\"" \
        >> "$LOG" 2>&1

    if [ "$?" -ne 0 ]; then
        log "CHYBA při mazání z Vanty: $filename"
    fi
done

# Druhý výpis určí, zda na Vantě ještě skutečně něco čeká.
FINAL_LIST=$(
    smbclient "$REMOTE" \
        -A "$AUTH" \
        -c "cd $REMOTE_DIR; ls" \
        2>/dev/null
)
RC=$?

if [ "$RC" -ne 0 ]; then
    write_status "false" "false" "" "$DOWNLOADED_COUNT" "" "Kontrola po stažení selhala"
    exit 0
fi

mapfile -t REMAINING_FILES < <(extract_filenames "$FINAL_LIST")
REMAINING_COUNT="${#REMAINING_FILES[@]}"

write_status \
    "true" \
    "false" \
    "$REMOTE_COUNT" \
    "$DOWNLOADED_COUNT" \
    "$REMAINING_COUNT" \
    ""

exit 0
