#!/bin/bash

# Jednorázová synchronizace exportů z analyzátoru Vanta.
# Skript je určený pro opakované spouštění pomocí systemd.

REMOTE="//192.168.1.152/Vanta"
REMOTE_DIR="exports"
DEST="/home/pilat/vanta_exports"
AUTH="/etc/vanta-sync/credentials"
LOG="/var/log/vanta-sync.log"
LOCK="$DEST/.vanta-sync.lock"

mkdir -p "$DEST"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG"
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

LIST=$(
    smbclient "$REMOTE" \
        -A "$AUTH" \
        -c "cd $REMOTE_DIR; ls" \
        2>/dev/null
)
RC=$?

# Vypnutá nebo nedostupná Vanta je běžný stav, proto jej nelogujeme.
if [ "$RC" -ne 0 ]; then
    exit 0
fi

mapfile -t FILES < <(extract_filenames "$LIST")

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

exit 0
