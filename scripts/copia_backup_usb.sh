#!/usr/bin/env bash
# Copia l'ultimo backup cifrato del FASAS (verificato) su un disco o una chiavetta USB.
#
#   sudo ./scripts/copia_backup_usb.sh --elenca              mostra i dischi USB collegati
#   sudo ./scripts/copia_backup_usb.sh /dev/sdb1             copia l'ultimo backup e controlla la copia
#   sudo ./scripts/copia_backup_usb.sh /dev/sdb1 --tieni 6   come sopra, tenendo sul disco solo gli ultimi 6
#   sudo ./scripts/copia_backup_usb.sh /dev/sdc1 --busta     copia la busta di custodia delle chiavi
#
# I backup sono cifrati: senza FASAS_BACKUP_KEY (busta di custodia + frase segreta) non si aprono.
# Con ogni backup copia anche il registro degli accessi al server (/var/log/auth.log*), con le impronte SHA-256.
# Tenere il disco dei backup e la chiavetta della busta in due posti diversi. Guida: docs/INSTALLAZIONE_IN_STRUTTURA.md
set -euo pipefail

cd "$(dirname "$0")/.."
VOLUME=fasas_fasas-data
KEEP=12
MODE=backup
DEVICE=""

die() { printf '\n\033[31mERRORE:\033[0m %s\n' "$*" >&2; exit 1; }
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --elenca)
      DISKS=$(lsblk -dnpo NAME,TRAN | awk '$2 == "usb" {print $1}')
      [ -n "$DISKS" ] || { echo "Nessun disco USB collegato."; exit 0; }
      for disk in $DISKS; do lsblk -po NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS "$disk"; done
      echo "Usare il nome della partizione (es. /dev/sdb1)."
      exit 0 ;;
    --busta) MODE=busta ;;
    --tieni) shift; KEEP=${1:-}; [[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || die "--tieni vuole un numero (es. --tieni 6)" ;;
    /dev/*) DEVICE=$1 ;;
    *) die "argomento sconosciuto: $1 (vedere le istruzioni in cima allo script)" ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "eseguire con sudo"
[ -n "$DEVICE" ] || die "indicare la partizione del disco USB, es. /dev/sdb1 (elenco: sudo $0 --elenca)"
[ -b "$DEVICE" ] || die "$DEVICE non esiste: controllare con sudo $0 --elenca"
PARENT=$(lsblk -no PKNAME "$DEVICE" | head -n 1)
[ "$(lsblk -dno TRAN "/dev/${PARENT:-${DEVICE#/dev/}}" 2>/dev/null)" = usb ] || die "$DEVICE non è un disco USB: per sicurezza non lo uso."

DATA=$(docker volume inspect "$VOLUME" --format '{{.Mountpoint}}' 2>/dev/null) || die "volume $VOLUME non trovato: il FASAS è installato con docker compose?"

MOUNTED_HERE=""
MOUNTPOINT=$(findmnt -nro TARGET -S "$DEVICE" | head -n 1 || true)
if [ -z "$MOUNTPOINT" ]; then
  MOUNTPOINT=/mnt/fasas-usb
  mkdir -p "$MOUNTPOINT"
  FSTYPE=$(lsblk -no FSTYPE "$DEVICE")
  case "$FSTYPE" in
    ntfs) mount -t ntfs3 "$DEVICE" "$MOUNTPOINT" ;;
    "") die "$DEVICE non è formattato: formattarlo in exFAT (da un PC) e riprovare." ;;
    *) mount "$DEVICE" "$MOUNTPOINT" ;;
  esac
  MOUNTED_HERE=1
fi
cleanup() { if [ -n "$MOUNTED_HERE" ]; then sync; umount "$MOUNTPOINT" && echo "  Disco smontato: si può scollegare."; fi; }
trap cleanup EXIT

copy_checked() {  # copy_checked origine destinazione → copia e confronta l'impronta SHA-256
  local src=$1 dst=$2 a b
  cp "$src" "$dst.parziale"
  sync
  a=$(sha256sum "$src" | cut -d' ' -f1)
  b=$(sha256sum "$dst.parziale" | cut -d' ' -f1)
  [ "$a" = "$b" ] || { rm -f "$dst.parziale"; die "la copia di $(basename "$src") non coincide con l'originale: disco difettoso?"; }
  mv "$dst.parziale" "$dst"
  ok "copiato e controllato: $(basename "$dst") (SHA-256 ${a:0:16}…)"
}

shopt -s nullglob
if [ "$MODE" = busta ]; then
  ENVELOPES=("$DATA"/*.fkey)
  [ ${#ENVELOPES[@]} -gt 0 ] || die "nessuna busta trovata. Crearla prima con: sudo docker compose exec web python manage.py fasas_chiavi busta /data/busta-chiavi.fkey"
  mkdir -p "$MOUNTPOINT/FASAS-busta-chiavi"
  for envelope in "${ENVELOPES[@]}"; do
    copy_checked "$envelope" "$MOUNTPOINT/FASAS-busta-chiavi/$(basename "$envelope")"
  done
  echo "  Conservare questa chiavetta in cassaforte, lontano dal server e dal disco dei backup."
  echo "  La frase segreta va custodita separatamente (es. gestore di password della direzione)."
  exit 0
fi

echo "  Verifico l'ultimo backup (decifratura e impronta)…"
RESULT=$(docker compose exec -T web python manage.py backup_verify 2>&1) || die "verifica non riuscita: $RESULT"
NAME=$(printf '%s\n' "$RESULT" | sed -n 's/^Backup \(fasas-backup-[^:]*\.fbk\): integrità verificata\.$/\1/p' | tail -n 1)
[ -n "$NAME" ] || die "risposta inattesa dalla verifica: $RESULT"
SOURCE="$DATA/backups/$NAME"
[ -f "$SOURCE" ] || die "file $SOURCE non trovato"
ok "backup verificato: $NAME"

TARGET="$MOUNTPOINT/FASAS-backup"
mkdir -p "$TARGET"
if [ -f "$TARGET/$NAME" ] && [ "$(sha256sum "$TARGET/$NAME" | cut -d' ' -f1)" = "$(sha256sum "$SOURCE" | cut -d' ' -f1)" ]; then
  ok "già presente sul disco e identico"
else
  FREE=$(df --output=avail -B1 "$TARGET" | tail -n 1)
  [ "$FREE" -gt "$(stat -c %s "$SOURCE")" ] || die "spazio insufficiente sul disco USB"
  copy_checked "$SOURCE" "$TARGET/$NAME"
fi

# sul disco restano solo gli ultimi $KEEP backup (i nomi contengono data e ora, quindi l'ordine è cronologico)
mapfile -t OLD < <(find "$TARGET" -maxdepth 1 -name 'fasas-backup-*.fbk' -printf '%f\n' | sort | head -n -"$KEEP")
for old in "${OLD[@]}"; do
  rm -f "$TARGET/$old"
  echo "  tolto il backup più vecchio: $old"
done
cat >"$TARGET/LEGGIMI.txt" <<'EOF'
Backup cifrati del FASAS Digitale (AES-256-GCM). Per aprirli servono la chiave FASAS_BACKUP_KEY, che si
recupera dalla busta di custodia con la sua frase segreta, e la procedura «Ripristino vero» di docs/BACKUP.md.
Non contengono dati leggibili senza la chiave. Conservare il disco in un luogo chiuso, lontano dal server.
EOF
echo "  Sul disco: $(find "$TARGET" -maxdepth 1 -name 'fasas-backup-*.fbk' | wc -l) backup, $(du -sh "$TARGET" | cut -f1)."

# Registro degli accessi al server (SSH, sudo): copia mensile fuori dal server, con impronte per verificarne
# l'integrità (amministratori di sistema, provvedimento del Garante 27/11/2008). Contiene nomi utente e indirizzi
# IP degli amministratori, nessun dato degli ospiti. Le copie mensili restano tutte (pochi kB ciascuna).
LOGS=("${AUTH_LOG_DIR:-/var/log}"/auth.log*)
if [ ${#LOGS[@]} -gt 0 ]; then
  MONTH_DIR="$MOUNTPOINT/FASAS-registro-accessi-server/$(date +%Y-%m-%d)"
  mkdir -p "$MONTH_DIR"
  cp --preserve=timestamps "${LOGS[@]}" "$MONTH_DIR/"  # exFAT non conserva proprietario e permessi
  (cd "$MONTH_DIR" && sha256sum -- auth.log* >SHA256SUMS && sha256sum -c --quiet SHA256SUMS) \
    || die "copia del registro degli accessi non riuscita"
  ok "registro degli accessi al server copiato in $(basename "$MONTH_DIR") (impronte in SHA256SUMS)"
fi
