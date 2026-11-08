#!/usr/bin/env bash
# Manutenzione del mese in un comando, anche da casa (VPN di manutenzione: scripts/accesso_remoto.sh).
# Gli aggiornamenti di sicurezza di Ubuntu (sistema e Docker) si installano da soli ogni giorno: lo script controlla
# che sia così e aggiorna il resto, cioè i contenitori (PostgreSQL, Redis, Caddy, Python) e, se c'è, la nuova
# versione del FASAS. Prima di toccare qualunque cosa fa un backup; alla fine controlla che il FASAS risponda.
#
#   sudo ./scripts/aggiorna_fasas.sh --controlla        cosa c'è da fare (non cambia nulla)
#   sudo ./scripts/aggiorna_fasas.sh                    backup, contenitori aggiornati, nuova versione se c'è
#   sudo ./scripts/aggiorna_fasas.sh --solo-sicurezza   backup e contenitori aggiornati, versione del FASAS invariata
#   sudo ./scripts/aggiorna_fasas.sh --riavvia          come sopra e, se un aggiornamento lo chiede, riavvio del server
#   sudo ./scripts/aggiorna_fasas.sh --versione REF     porta il FASAS a una versione precisa (commit, tag o ramo
#                                                       di GitHub): la usa la pubblicazione da GitHub Actions
#
# Se dopo l'aggiornamento il FASAS non risponde, si torna da soli alla versione e all'immagine di prima (il backup
# fatto all'inizio resta disponibile per i casi in cui serve anche il database di prima).
#
# Ogni esecuzione è annotata in /var/log/fasas-aggiornamenti.log (registro della manutenzione).
# Guida: docs/INSTALLAZIONE_IN_STRUTTURA.md, passo 18.
set -euo pipefail

cd "${FASAS_ROOT_DIR:-$(dirname "$0")/..}"
ROOT_DIR=$(pwd)
# la nuova versione può cambiare anche questo script, e bash legge i file man mano: si esegue una copia
if [ -z "${FASAS_AGGIORNA_COPIA:-}" ]; then
  COPY=$(mktemp /tmp/fasas-aggiorna.XXXXXX)
  cp "$ROOT_DIR/scripts/aggiorna_fasas.sh" "$COPY"
  FASAS_AGGIORNA_COPIA="$COPY" FASAS_ROOT_DIR="$ROOT_DIR" exec bash "$COPY" "$@"
fi
trap 'rm -f "$FASAS_AGGIORNA_COPIA"' EXIT
LOG=/var/log/fasas-aggiornamenti.log
MODE=aggiorna
CODE=1
REBOOT=""
TARGET=""

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die() { printf '\n\033[31mERRORE:\033[0m %s\n' "$*" >&2; log "ERRORE: $*"; exit 1; }
log() { printf '%s %s\n' "$(date -Iseconds)" "$*" >> "$LOG" 2>/dev/null || true; }

while [ $# -gt 0 ]; do
  case "$1" in
    --controlla) MODE=controlla ;;
    --solo-sicurezza) CODE="" ;;
    --riavvia) REBOOT=1 ;;
    --versione) shift; TARGET=${1:-}; [[ "$TARGET" =~ ^[A-Za-z0-9._/-]+$ ]] || die "versione non valida: $TARGET" ;;
    *) die "argomento sconosciuto: $1 (vedere le istruzioni in cima allo script)" ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "eseguire con sudo"
[ -f .env ] || die "file .env non trovato: il FASAS non è installato in $ROOT_DIR (scripts/prepara_server.sh)"
git() { GIT_TERMINAL_PROMPT=0 command git -c safe.directory="$ROOT_DIR" "$@"; }

# al riavvio il disco cifrato si apre da solo (TPM) oppure chiede la frase alla tastiera del server?
needs_passphrase() {
  [ -f /etc/crypttab ] || return 1
  grep -Ev '^\s*(#|$)' /etc/crypttab | grep -qv 'tpm2-device'
}

web_ok() {
  docker compose exec -T web python -c \
    "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/salute/', timeout=8)" > /dev/null 2>&1
}

check() {
  say "Sistema operativo (Ubuntu)"
  local last pending
  last=$(tail -n 1 /var/log/unattended-upgrades/unattended-upgrades.log 2>/dev/null | cut -c1-10 || true)
  if [ -n "$last" ]; then ok "aggiornamenti di sicurezza automatici: ultimo controllo il $(date -d "$last" '+%d/%m/%Y' 2>/dev/null || echo "$last")"
  else warn "aggiornamenti automatici mai eseguiti: rilanciare scripts/prepara_server.sh (passo 15)"; fi
  pending=$(apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null | grep -c '^Inst .*-security' || true)
  if [ "${pending:-0}" -gt 0 ]; then warn "$pending aggiornamenti di sicurezza in attesa (di solito si installano entro domani)"
  else ok "nessun aggiornamento di sicurezza in attesa"; fi
  if [ -f /var/run/reboot-required ]; then
    if needs_passphrase; then warn "serve un riavvio: farlo IN STRUTTURA (al riavvio il disco chiede la frase alla tastiera)"
    else warn "serve un riavvio (sudo scripts/aggiorna_fasas.sh --riavvia, oppure di notte alle 05:15 se attivo)"; fi
  else ok "nessun riavvio necessario"; fi
  local free
  free=$(df --output=pcent / | tail -n 1 | tr -dc '0-9')
  if [ "${free:-0}" -ge 90 ]; then warn "disco del server pieno al $free%"; else ok "disco del server usato al $free%"; fi

  say "FASAS"
  if GIT_TERMINAL_PROMPT=0 timeout 60 git -c safe.directory="$ROOT_DIR" fetch -q 2>/dev/null && git rev-parse -q --verify '@{u}' > /dev/null; then
    local behind
    behind=$(git rev-list --count 'HEAD..@{u}')
    if [ "$behind" -gt 0 ]; then
      warn "nuova versione disponibile ($behind modifiche): leggere CHANGELOG.md prima di aggiornare"
      git log --oneline -n 10 'HEAD..@{u}' | sed 's/^/      /'
    else ok "versione aggiornata ($(git rev-parse --short HEAD))"; fi
  else
    warn "nuova versione non controllabile (internet o ramo di riferimento assenti)"
  fi
  local image created days
  for image in $(docker compose config --images 2>/dev/null | sort -u); do
    created=$(docker image inspect -f '{{.Created}}' "$image" 2>/dev/null | cut -c1-10 || true)
    [ -n "$created" ] || continue
    days=$(( ($(date +%s) - $(date -d "$created" +%s)) / 86400 ))
    if [ "$days" -gt 35 ]; then warn "contenitore $image di $days giorni fa: da aggiornare"
    else ok "contenitore $image di $days giorni fa"; fi
  done
  if web_ok; then ok "il FASAS risponde"; else warn "il FASAS non risponde: sudo docker compose ps"; fi
}

check
[ "$MODE" = aggiorna ] || exit 0

log "inizio aggiornamento (${CODE:+versione e }contenitori)"
say "1. Backup prima di aggiornare"
web_ok || die "il FASAS non risponde: sistemare prima il problema (sudo docker compose ps, guida «Problemi frequenti»)"
docker compose exec -T web python manage.py backup_create || die "backup non riuscito: nessun aggiornamento fatto"
ok "backup fatto e verificato (in caso di problemi si ripristina dalla pagina Backup)"

BEFORE=$(git rev-parse HEAD)
BEFORE_BRANCH=$(git symbolic-ref -q --short HEAD || true)
IMAGE=$(docker compose config --images 2>/dev/null | grep '^fasas-digitale:' | head -n 1 || true)
# immagine in funzione conservata per tornare indietro senza ricostruirla
if [ -n "$IMAGE" ] && docker image inspect "$IMAGE" > /dev/null 2>&1; then
  docker tag "$IMAGE" fasas-digitale:precedente
fi
if [ -n "$TARGET" ]; then
  say "2. Versione $TARGET del FASAS"
  git status --porcelain --untracked-files=no | grep -q . \
    && die "ci sono modifiche locali in $ROOT_DIR (git status): nessun aggiornamento fatto"
  timeout 120 git fetch -q --tags origin || die "versione non scaricata da GitHub (internet?): nessun aggiornamento fatto"
  RESOLVED=$(git rev-parse -q --verify "origin/$TARGET^{commit}" 2>/dev/null || git rev-parse -q --verify "$TARGET^{commit}" 2>/dev/null) \
    || die "versione $TARGET non trovata: nessun aggiornamento fatto"
  git checkout -q --detach "$RESOLVED"
  ok "versione $(git rev-parse --short "$BEFORE") → $(git rev-parse --short HEAD)"
  log "versione $(git rev-parse --short "$BEFORE") -> $(git rev-parse --short HEAD) ($TARGET)"
elif [ -n "$CODE" ] && git rev-parse -q --verify '@{u}' > /dev/null && [ "$(git rev-list --count 'HEAD..@{u}')" -gt 0 ]; then
  say "2. Nuova versione del FASAS"
  git pull -q --ff-only || die "nuova versione non scaricata: ci sono modifiche locali in $ROOT_DIR (git status)"
  ok "versione $(git rev-parse --short "$BEFORE") → $(git rev-parse --short HEAD)"
  log "versione $(git rev-parse --short "$BEFORE") -> $(git rev-parse --short HEAD)"
fi

rollback() {  # torna a codice e immagine di prima; il database resta quello attuale
  warn "$1: ritorno alla versione di prima ($(git rev-parse --short "$BEFORE"))"
  log "ritorno alla versione precedente: $1"
  if [ "$(git rev-parse HEAD)" != "$BEFORE" ]; then
    if [ -n "$BEFORE_BRANCH" ]; then git checkout -q "$BEFORE_BRANCH" && git reset -q --keep "$BEFORE"
    else git checkout -q --detach "$BEFORE"; fi
  fi
  if [ -n "$IMAGE" ] && docker image inspect fasas-digitale:precedente > /dev/null 2>&1; then
    docker tag fasas-digitale:precedente "$IMAGE"
    docker compose up -d --no-build --remove-orphans || true
  else
    docker compose up -d --build --remove-orphans || true
  fi
  for _ in $(seq 1 90); do web_ok && break; sleep 2; done
  if web_ok; then
    log "tornati alla versione precedente"
    die "aggiornamento annullato, il FASAS funziona con la versione di prima. Se la nuova versione aveva modificato il database e qualcosa non va, ripristinare il backup fatto all'inizio (guida «Ripristino»)."
  fi
  die "il FASAS non risponde nemmeno con la versione di prima: ripristinare il backup fatto all'inizio (guida «Ripristino») — sudo docker compose logs --tail 100 web"
}

say "3. Contenitori aggiornati"
docker compose pull -q --ignore-buildable 2>/dev/null || docker compose pull -q --ignore-pull-failures \
  || warn "immagini non scaricate (internet?): si riparte con quelle attuali"
if ! docker compose build -q --pull; then
  [ "$(git rev-parse HEAD)" = "$BEFORE" ] || rollback "costruzione della nuova versione non riuscita"
  die "costruzione del FASAS non riuscita: il FASAS attuale resta in funzione"
fi
# «up» fallisce anche quando il sito nuovo non diventa sano (il worker lo aspetta): si decide con il controllo
docker compose up -d --remove-orphans || warn "i contenitori della nuova versione non sono partiti tutti"
for _ in $(seq 1 90); do web_ok && break; sleep 2; done
web_ok || rollback "dopo l'aggiornamento il FASAS non risponde"
ok "FASAS ripartito e funzionante ($(git rev-parse --short HEAD))"
docker image prune -f > /dev/null 2>&1 || true
log "aggiornamento completato"

if [ -f /var/run/reboot-required ]; then
  if [ -z "$REBOOT" ]; then
    warn "il sistema chiede un riavvio: sudo scripts/aggiorna_fasas.sh --riavvia (o di notte alle 05:15, se attivo)"
  elif needs_passphrase; then
    warn "riavvio NON fatto: il disco chiederebbe la frase alla tastiera del server. Riavviare in struttura."
  else
    log "riavvio del server"
    ok "riavvio tra 1 minuto: il FASAS riparte da solo (2-3 minuti)"
    shutdown -r +1 "FASAS: riavvio per aggiornamenti di sicurezza" > /dev/null 2>&1
  fi
fi
echo
echo "Fatto. Entrare nel FASAS e controllare Impostazioni › Stato del sistema."
