#!/usr/bin/env bash
# Disco di continuità: SSD esterno USB SEMPRE collegato al server. Il FASAS ci copia ogni 5 minuti il database
# (cifrato) e i file nuovi: se il disco interno si guasta si perdono al massimo pochi minuti di registrazioni.
#
#   sudo ./scripts/disco_continuita.sh --elenca              mostra i dischi USB collegati
#   sudo ./scripts/disco_continuita.sh --prepara /dev/sdc    CANCELLA il disco e lo prepara (una volta sola)
#   sudo ./scripts/disco_continuita.sh --stato               disco collegato? ultima copia? spazio libero?
#   sudo ./scripts/disco_continuita.sh --rimonta             dopo averlo ricollegato: lo rimonta e riavvia il FASAS
#
# È un disco diverso da quello della copia mensile (che resta scollegato in un altro luogo): questo resta attaccato.
# Guida: docs/INSTALLAZIONE_IN_STRUTTURA.md, passo 14b.
set -euo pipefail

cd "$(dirname "$0")/.."
MOUNT=${FASAS_CONTINUITA_MOUNT:-/srv/fasas-continuita}
LABEL=FASAS-CONTINUA
APP_UID=10001  # utente dell'applicazione nel container (Dockerfile)
MARKER=.fasas-continuita
MODE=""
DEVICE=""
YES=""

die() { printf '\n\033[31mERRORE:\033[0m %s\n' "$*" >&2; exit 1; }
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }

set_env() {  # set_env NOME VALORE: aggiunge o sostituisce la riga nel file .env del FASAS
  [ -f .env ] || die "file .env non trovato: eseguire prima scripts/prepara_server.sh"
  if grep -q "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --elenca) MODE=elenca ;;
    --prepara) MODE=prepara; shift; DEVICE=${1:-} ;;
    --stato) MODE=stato ;;
    --rimonta) MODE=rimonta ;;
    --si) YES=1 ;;  # solo per le prove automatiche: salta la conferma scritta
    *) die "argomento sconosciuto: $1 (vedere le istruzioni in cima allo script)" ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "eseguire con sudo"

case "$MODE" in
  elenca)
    DISKS=$(lsblk -dnpo NAME,TRAN | awk '$2 == "usb" {print $1}')
    [ -n "$DISKS" ] || { echo "Nessun disco USB collegato."; exit 0; }
    for disk in $DISKS; do lsblk -po NAME,SIZE,MODEL,FSTYPE,LABEL,MOUNTPOINTS "$disk"; done
    echo "Per prepararlo usare il nome del DISCO intero (es. /dev/sdc), non della partizione."
    ;;

  prepara)
    [ -n "$DEVICE" ] || die "indicare il disco, es. --prepara /dev/sdc (elenco: sudo $0 --elenca)"
    [ -b "$DEVICE" ] || die "$DEVICE non esiste: controllare con sudo $0 --elenca"
    [ "$(lsblk -dno TYPE "$DEVICE")" != part ] || die "$DEVICE è una partizione: indicare il disco intero (es. /dev/sdc)"
    TRAN=$(lsblk -dno TRAN "$DEVICE" 2>/dev/null || true)
    [ "$TRAN" = usb ] || [[ "$DEVICE" == /dev/loop* ]] || die "$DEVICE non è un disco USB: per sicurezza non lo tocco."
    if lsblk -nro MOUNTPOINTS "$DEVICE" | grep -q .; then
      die "$DEVICE ha partizioni in uso (montate): non è il disco giusto oppure va prima smontato."
    fi
    echo
    lsblk -po NAME,SIZE,MODEL,FSTYPE,LABEL "$DEVICE"
    echo
    echo "TUTTO il contenuto di $DEVICE verrà CANCELLATO."
    if [ -z "$YES" ]; then
      read -r -p "Per continuare scrivere CANCELLA e premere Invio: " ANSWER
      [ "$ANSWER" = CANCELLA ] || die "annullato: il disco non è stato toccato."
    fi
    wipefs -a "$DEVICE" > /dev/null
    mkfs.ext4 -q -F -L "$LABEL" "$DEVICE"
    UUID=$(blkid -s UUID -o value "$DEVICE")
    [ -n "$UUID" ] || die "formattazione non riuscita"
    ok "disco formattato (ext4, etichetta $LABEL)"
    mkdir -p "$MOUNT"
    sed -i "\|[[:space:]]${MOUNT}[[:space:]]|d" /etc/fstab
    # nofail: se il disco manca il server si avvia lo stesso, e il FASAS segnala che la copia continua è ferma
    echo "UUID=$UUID $MOUNT ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2" >> /etc/fstab
    systemctl daemon-reload 2>/dev/null || true
    mount "$MOUNT"
    echo "Disco di continuità FASAS – preparato il $(date '+%d/%m/%Y %H:%M')" > "$MOUNT/$MARKER"
    chown -R "$APP_UID:$APP_UID" "$MOUNT"
    chmod 700 "$MOUNT"
    ok "montato in $MOUNT, anche a ogni riavvio"
    set_env FASAS_CONTINUITY_HOST_DIR "$MOUNT"
    set_env FASAS_CONTINUITY_DIR /continuita
    chmod 600 .env
    ok "FASAS configurato: copia ogni 5 minuti"
    echo
    echo "Ora riavviare il FASAS:  cd $(pwd) && sudo docker compose up -d"
    ;;

  stato)
    if ! findmnt -n "$MOUNT" > /dev/null; then
      die "il disco di continuità NON è montato in $MOUNT: è collegato? Poi: sudo $0 --rimonta"
    fi
    [ -f "$MOUNT/$MARKER" ] || die "in $MOUNT c'è un disco non preparato dal FASAS"
    ok "disco collegato in $MOUNT"
    df -h "$MOUNT" | tail -n 1 | awk '{print "  spazio libero: " $4 " su " $2}'
    if [ -f "$MOUNT/ultima-copia.json" ]; then
      echo "  ultima copia: $(sed -n 's/.*"at": "\([^"]*\)".*/\1/p' "$MOUNT/ultima-copia.json")"
    else
      echo "  nessuna copia ancora: la prima arriva entro 5 minuti dal riavvio del FASAS"
    fi
    echo "  copie del database presenti: $(find "$MOUNT/database" -name 'fasas-continua-*.fbk' 2>/dev/null | wc -l)"
    ;;

  rimonta)
    findmnt -n "$MOUNT" > /dev/null || mount "$MOUNT" || die "il disco non si monta: è collegato? (sudo $0 --elenca)"
    [ -f "$MOUNT/$MARKER" ] || die "in $MOUNT c'è un disco non preparato dal FASAS"
    ok "disco montato in $MOUNT"
    docker compose restart worker web > /dev/null
    ok "FASAS riavviato: la copia riprende entro 5 minuti"
    ;;

  *) die "indicare --elenca, --prepara /dev/sdX, --stato oppure --rimonta (istruzioni in cima allo script)" ;;
esac
