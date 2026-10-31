#!/usr/bin/env bash
# Prepara il server FASAS installato in struttura (Ubuntu Server 24.04 con Docker).
#
#   sudo ./scripts/prepara_server.sh
#
# Cosa fa, chiedendo conferma: crea il file .env con chiavi nuove (solo se non esiste già), installa
# l'aggiornamento automatico dell'indirizzo DuckDNS, attiva firewall e riavvio automatico dopo gli
# aggiornamenti di sicurezza, costruisce e avvia i container, controlla che il sito risponda in HTTPS.
# Si può rilanciare: non rigenera mai le chiavi esistenti. Guida completa: docs/INSTALLAZIONE_IN_STRUTTURA.md
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT_DIR=$(pwd)
ENV_FILE="$ROOT_DIR/.env"
DUCKDNS_CONF=/etc/fasas-duckdns.conf
DUCKDNS_BIN=/usr/local/sbin/fasas-duckdns

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die() { printf '\n\033[31mERRORE:\033[0m %s\n' "$*" >&2; exit 1; }

ask() {  # ask "domanda" "valore predefinito" → risposta su stdout
  local answer
  if [ -n "${2:-}" ]; then
    read -r -p "  $1 [$2]: " answer </dev/tty
  else
    read -r -p "  $1: " answer </dev/tty
  fi
  printf '%s' "${answer:-${2:-}}"
}

ask_secret() {
  local answer
  read -r -s -p "  $1: " answer </dev/tty
  echo >/dev/tty
  printf '%s' "$answer"
}

yes_no() {  # yes_no "domanda" s|n → 0 se sì
  local default=$2 answer
  read -r -p "  $1 [$([ "$default" = s ] && echo S/n || echo s/N)]: " answer </dev/tty
  answer=${answer:-$default}
  case "$answer" in s|S|si|sì|SI|y|Y) return 0 ;; *) return 1 ;; esac
}

env_value() {  # legge una variabile dal .env
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2-
}

# --- 0. Controlli -------------------------------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || die "eseguire con sudo:  sudo ./scripts/prepara_server.sh"
[ -f docker-compose.yml ] || die "docker-compose.yml non trovato: lanciare lo script dalla cartella del FASAS."
for cmd in docker curl python3 ip; do
  command -v "$cmd" >/dev/null || die "manca il comando «$cmd». Installare con: sudo apt install docker.io docker-compose-v2 curl"
done
docker compose version >/dev/null 2>&1 || die "manca Docker Compose. Installare con: sudo apt install docker-compose-v2"
systemctl is-active --quiet docker || systemctl enable --now docker

say "FASAS Digitale – preparazione del server in struttura"
echo "  Cartella: $ROOT_DIR"

IFACE=$(ip -4 route show default | awk '{for (i = 1; i <= NF; i++) if ($i == "dev") {print $(i + 1); exit}}')
SERVER_CIDR=$(ip -4 -o addr show dev "${IFACE:-lo}" scope global 2>/dev/null | awk '{print $4; exit}')
SERVER_IP=${SERVER_CIDR%/*}
[ -n "$SERVER_IP" ] || die "il server non ha un indirizzo di rete: collegare il cavo di rete e riprovare."
ok "Indirizzo del server nella rete della struttura: $SERVER_IP (scheda $IFACE)"

# --- 1. File .env con le chiavi --------------------------------------------------------------------------
if [ -f "$ENV_FILE" ]; then
  say "1. File .env"
  ok "esiste già: lo lascio com'è (le chiavi non si rigenerano: documenti e backup diventerebbero illeggibili)"
  DOMAIN=$(env_value FASAS_DOMAIN)
  LAN=$(env_value FASAS_2FA_TRUSTED_NETWORKS)
  [ -n "$DOMAIN" ] || die "nel .env manca FASAS_DOMAIN."
else
  say "1. Indirizzo, rete e chiavi"
  while true; do
    DOMAIN=$(ask "Indirizzo del FASAS (es. casarosa.duckdns.org)" "")
    DOMAIN=$(printf '%s' "$DOMAIN" | tr '[:upper:]' '[:lower:]' | sed -e 's#^https\?://##' -e 's#/.*$##')
    if [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]]; then break; fi
    warn "indirizzo non valido, riprovare (solo lettere, numeri, trattini e punti)"
  done

  SUGGESTED=$(python3 -c 'import ipaddress, sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$SERVER_CIDR")
  echo "  Rete della struttura: da qui si entra con la sola password; da fuori serve sempre il codice"
  echo "  della verifica in due passaggi. Di solito è quella proposta."
  while true; do
    LAN=$(ask "Rete della struttura" "$SUGGESTED")
    if LAN=$(python3 - "$LAN" <<'PY'
import ipaddress, sys
try:
    net = ipaddress.ip_network(sys.argv[1].strip(), strict=False)
except ValueError:
    sys.exit(1)
# le reti interne di Docker (172.17–172.31) non vanno mai considerate «rete della struttura»
if net.version != 4 or not net.is_private or net.prefixlen < 16:
    sys.exit(1)
docker = ipaddress.ip_network("172.16.0.0/12")
if net.overlaps(docker) and not net.subnet_of(ipaddress.ip_network("172.16.0.0/16")):
    sys.exit(1)
print(net)
PY
    ); then break; fi
    warn "rete non valida: serve una rete privata come 192.168.1.0/24 (non le reti interne di Docker)"
  done

  while true; do
    EMAIL=$(ask "Email dell'amministrazione (per il servizio delle notifiche push)" "")
    if [[ "$EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then break; fi
    warn "email non valida"
  done

  OFFSITE_ENDPOINT="" OFFSITE_REGION="" OFFSITE_BUCKET="" OFFSITE_KEY="" OFFSITE_SECRET=""
  echo
  echo "  Copia fuori sede dei backup su Backblaze B2 (guida, passo 13). Si può configurare anche dopo."
  if yes_no "Hai già creato il bucket B2 con Object Lock e la chiave d'accesso?" n; then
    while true; do
      OFFSITE_ENDPOINT=$(ask "Endpoint del bucket (es. s3.eu-central-003.backblazeb2.com)" "")
      OFFSITE_ENDPOINT=${OFFSITE_ENDPOINT#https://}
      OFFSITE_ENDPOINT=${OFFSITE_ENDPOINT%/}
      if [[ "$OFFSITE_ENDPOINT" =~ ^s3\.([a-z0-9-]+)\.backblazeb2\.com$ ]]; then
        OFFSITE_REGION=${BASH_REMATCH[1]}
        OFFSITE_ENDPOINT="https://$OFFSITE_ENDPOINT"
        break
      fi
      warn "l'endpoint ha la forma s3.<regione>.backblazeb2.com: copiarlo dalla pagina del bucket"
    done
    [[ "$OFFSITE_REGION" == eu-* ]] || warn "la regione $OFFSITE_REGION non è in Europa: per i dati sanitari serve una regione UE"
    while true; do
      OFFSITE_BUCKET=$(ask "Nome del bucket" "")
      [[ "$OFFSITE_BUCKET" =~ ^[a-zA-Z0-9-]{6,63}$ ]] && break
      warn "nome non valido"
    done
    OFFSITE_KEY=$(ask "keyID della chiave d'accesso" "")
    OFFSITE_SECRET=$(ask_secret "applicationKey (non viene mostrata mentre la scrivi)")
    [[ "$OFFSITE_KEY" =~ ^[A-Za-z0-9]+$ && -n "$OFFSITE_SECRET" && "$OFFSITE_SECRET" != *[[:space:]\$\'\"\\]* ]] \
      || die "keyID o applicationKey non validi: ricopiarli dalla pagina Application Keys di Backblaze."
  fi

  umask 077
  FASAS_DOMAIN="$DOMAIN" FASAS_LAN="$LAN" FASAS_EMAIL="$EMAIL" \
  OFFSITE_ENDPOINT="$OFFSITE_ENDPOINT" OFFSITE_REGION="$OFFSITE_REGION" OFFSITE_BUCKET="$OFFSITE_BUCKET" \
  OFFSITE_KEY="$OFFSITE_KEY" OFFSITE_SECRET="$OFFSITE_SECRET" python3 - "$ENV_FILE" <<'PY'
import base64, datetime, os, secrets, sys

e = os.environ
key32 = lambda: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
text = f"""\
# FASAS Digitale in struttura – creato da scripts/prepara_server.sh il {datetime.date.today():%d/%m/%Y}.
# NON rigenerare né perdere le chiavi: senza quelle originali documenti e backup non si aprono più.
# Copia di sicurezza: busta di custodia (guida, passo 11). Dopo una modifica: sudo docker compose up -d
DJANGO_DEBUG=0
DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}
FASAS_DOMAIN={e["FASAS_DOMAIN"]}
POSTGRES_PASSWORD={secrets.token_urlsafe(32)}

# Cifratura dei documenti e dei backup
FASAS_ENCRYPTION_KEYS={key32()}
FASAS_BACKUP_KEY={key32()}

# Verifica in due passaggi: obbligatoria per questi ruoli; da fuori dalla rete della struttura per tutti
FASAS_2FA_REQUIRED_ROLES=admin,coordinator,doctor
FASAS_2FA_TRUSTED_NETWORKS={e["FASAS_LAN"]}
FASAS_LOGIN_MAX_FAILURES=5
FASAS_LOGIN_LOCKOUT_MINUTES=15

# Monitoraggio: token per il dettaglio di /salute/ (docs/MONITORAGGIO.md)
FASAS_HEALTH_TOKEN={secrets.token_urlsafe(32)}
FASAS_HEALTH_MIN_FREE_GB=5

# Notifiche push (la chiave la aggiunge lo script al primo avvio)
FASAS_VAPID_SUBJECT=mailto:{e["FASAS_EMAIL"]}
FASAS_VAPID_PRIVATE_KEY=
FASAS_PUSH_SHOW_DETAILS=0

# Regole cliniche e firma con CIE (docs/DISPOSITIVO_MEDICO.md, docs/FIRMA_CIE.md)
FASAS_PROTOCOLS_REQUIRE_VALIDATION=1
FASAS_FEA_REQUIRE_ACCEPTANCE=1
FASAS_AUDIT_TIMESTAMP=1

# Copia fuori sede dei backup su Backblaze B2 (piano gratuito 10 GB: conservazione ridotta, guida passo 13)
FASAS_OFFSITE_ENDPOINT={e["OFFSITE_ENDPOINT"]}
FASAS_OFFSITE_REGION={e["OFFSITE_REGION"]}
FASAS_OFFSITE_BUCKET={e["OFFSITE_BUCKET"]}
FASAS_OFFSITE_ACCESS_KEY={e["OFFSITE_KEY"]}
FASAS_OFFSITE_SECRET_KEY={e["OFFSITE_SECRET"]}
FASAS_OFFSITE_LOCK_DAYS=14
FASAS_OFFSITE_KEEP_DAILY=7
FASAS_OFFSITE_KEEP_MONTHLY=3
"""
with open(sys.argv[1], "x", encoding="utf-8") as handle:
    handle.write(text)
PY
  chmod 600 "$ENV_FILE"
  ok "creato $ENV_FILE (leggibile solo dall'amministratore del server)"
fi

# --- 2. Indirizzo DuckDNS ----------------------------------------------------------------------------
say "2. Aggiornamento automatico dell'indirizzo"
if [[ "$DOMAIN" == *.duckdns.org ]]; then
  NAME=${DOMAIN%.duckdns.org}
  NAME=${NAME##*.}
  if [ ! -f "$DUCKDNS_CONF" ]; then
    TOKEN=$(ask_secret "Token di DuckDNS (in alto nella pagina di duckdns.org dopo l'accesso)")
    [[ "$TOKEN" =~ ^[0-9a-fA-F-]{30,40}$ ]] || die "token DuckDNS non valido: ricopiarlo da duckdns.org"
    (umask 077; printf 'DUCKDNS_NOME=%s\nDUCKDNS_TOKEN=%s\n' "$NAME" "$TOKEN" >"$DUCKDNS_CONF")
  fi
  cat >"$DUCKDNS_BIN" <<'SH'
#!/bin/sh
# Aggiorna l'indirizzo DuckDNS con l'IP pubblico attuale della struttura (installato da prepara_server.sh).
. /etc/fasas-duckdns.conf
# il token passa a curl da stdin, così non compare nell'elenco dei processi
risposta=$(printf 'url = "https://www.duckdns.org/update?domains=%s&token=%s&ip="\n' "$DUCKDNS_NOME" "$DUCKDNS_TOKEN" \
  | curl -4 -fsS -m 30 --retry 3 -K -) || { logger -t fasas-duckdns "DuckDNS non raggiungibile"; exit 1; }
[ "$risposta" = "OK" ] || { logger -t fasas-duckdns "aggiornamento rifiutato ($risposta): controllare nome e token"; exit 1; }
SH
  chmod 755 "$DUCKDNS_BIN"
  printf '%s\n' "# Aggiorna l'indirizzo DuckDNS del FASAS (scripts/prepara_server.sh)" \
    "*/5 * * * * root $DUCKDNS_BIN >/dev/null 2>&1" \
    "@reboot root sleep 60 && $DUCKDNS_BIN >/dev/null 2>&1" >/etc/cron.d/fasas-duckdns
  chmod 644 /etc/cron.d/fasas-duckdns
  if "$DUCKDNS_BIN"; then
    ok "DuckDNS aggiornato: $DOMAIN punta all'IP pubblico della struttura (controllo ogni 5 minuti)"
  else
    die "DuckDNS ha rifiutato l'aggiornamento: controllare nome e token (sudo rm $DUCKDNS_CONF e rilanciare)."
  fi
else
  warn "$DOMAIN non è un indirizzo DuckDNS: l'aggiornamento dell'IP va configurato presso il proprio fornitore"
fi

# --- 3. Firewall e aggiornamenti -----------------------------------------------------------------------
say "3. Firewall e aggiornamenti di sicurezza"
install_missing() {  # installa i pacchetti indicati solo se mancano; mai attese senza limite
  local missing=() package
  for package in "$@"; do dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package"); done
  [ ${#missing[@]} -eq 0 ] && return 0
  echo "  installo ${missing[*]} (qualche minuto; se è in corso un aggiornamento automatico, lo aspetto)…"
  # fino a 5 minuti di attesa se un altro aggiornamento tiene occupato apt, 15 minuti al massimo per comando
  timeout 900 apt-get -o DPkg::Lock::Timeout=300 update -qq \
    && DEBIAN_FRONTEND=noninteractive timeout 900 apt-get -o DPkg::Lock::Timeout=300 install -y -qq \
      "${missing[@]}" >/dev/null
}
if yes_no "Attivo il firewall (da fuori solo le porte 80 e 443, accesso SSH solo dalla rete $LAN)?" s; then
  install_missing ufw || die "installazione del firewall non riuscita: riprovare tra qualche minuto (forse era in corso un aggiornamento)."
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow from "$LAN" to any port 22 proto tcp comment "SSH dalla rete della struttura" >/dev/null
  ufw allow 80/tcp comment "FASAS: certificato HTTPS" >/dev/null
  ufw allow 443/tcp comment "FASAS" >/dev/null
  ufw --force enable >/dev/null
  systemctl restart docker  # le regole di Docker per le porte 80 e 443 tornano sopra quelle del firewall
  ok "firewall attivo: da fuori solo le porte 80 e 443, SSH solo da $LAN"
else
  warn "firewall non modificato da questo script (guida, passo 15)"
fi

UPDATES_OK=1
install_missing unattended-upgrades || UPDATES_OK=""
if [ ! -f /etc/apt/apt.conf.d/20auto-upgrades ]; then
  printf '%s\n' 'APT::Periodic::Update-Package-Lists "1";' 'APT::Periodic::Unattended-Upgrade "1";' \
    >/etc/apt/apt.conf.d/20auto-upgrades
fi
# i file di configurazione modificati in locale (es. password di GRUB, passo 5) non bloccano gli aggiornamenti
printf '%s\n' '// FASAS: aggiornamenti di sicurezza anche dei pacchetti con configurazione modificata in locale' \
  'Dpkg::Options { "--force-confdef"; "--force-confold"; };' >/etc/apt/apt.conf.d/51fasas-configurazione
timedatectl set-timezone Europe/Rome 2>/dev/null || true
if [ -n "$UPDATES_OK" ]; then
  ok "aggiornamenti di sicurezza automatici ogni giorno, fuso orario Europe/Rome"
else
  warn "aggiornamenti automatici non installati ora (apt occupato o non raggiungibile): rilanciare lo script più tardi"
fi
echo "  Se il disco chiede la frase di cifratura a ogni accensione (guida, passo 5), rispondere n."
if yes_no "Riavvio automatico alle 05:15 quando un aggiornamento lo richiede?" s; then
  printf '%s\n' '// FASAS: riavvio automatico dopo gli aggiornamenti che lo richiedono, fuori dai job notturni' \
    'Unattended-Upgrade::Automatic-Reboot "true";' 'Unattended-Upgrade::Automatic-Reboot-Time "05:15";' \
    >/etc/apt/apt.conf.d/52fasas-riavvio
  ok "riavvio automatico alle 05:15 quando serve; il FASAS riparte da solo"
else
  rm -f /etc/apt/apt.conf.d/52fasas-riavvio
  warn "riavvio automatico non attivo: dopo gli aggiornamenti del kernel riavviare a mano (sudo reboot)"
fi
# accessi degli amministratori (SSH, sudo) conservati circa 7 mesi invece di 4 settimane
if [ -f /etc/logrotate.d/rsyslog ] && grep -qE '^\s*rotate 4$' /etc/logrotate.d/rsyslog; then
  sed -i -E 's/^(\s*)rotate 4$/\1rotate 30/' /etc/logrotate.d/rsyslog
fi
if grep -qE '^\s*rotate 30$' /etc/logrotate.d/rsyslog 2>/dev/null; then
  ok "registro degli accessi al server (/var/log/auth.log) conservato circa 7 mesi"
fi

# --- 4. Avvio --------------------------------------------------------------------------------------------
say "4. Costruzione e avvio del FASAS (la prima volta servono alcuni minuti)"
docker compose build --pull
if [ -z "$(env_value FASAS_VAPID_PRIVATE_KEY)" ]; then
  LINE=$(docker compose run --rm --no-deps -T web python manage.py fasas_vapid_keys | grep '^FASAS_VAPID_PRIVATE_KEY=' || true)
  [ -n "$LINE" ] || die "chiave per le notifiche push non generata."
  sed -i "s|^FASAS_VAPID_PRIVATE_KEY=.*|$LINE|" "$ENV_FILE"
  ok "chiave delle notifiche push aggiunta al .env"
fi
docker compose up -d

printf '  attendo che il sito sia pronto'
STATE=""
for _ in $(seq 1 60); do
  WEB=$(docker compose ps -q web)
  STATE=$(docker inspect --format '{{.State.Health.Status}}' "$WEB" 2>/dev/null || true)
  [ "$STATE" = healthy ] && break
  printf '.'
  sleep 5
done
echo
[ "$STATE" = healthy ] || die "il sito non è partito. Vedere: sudo docker compose logs --tail 50 web"
ok "sito avviato"

# Le connessioni che Docker inoltra (es. IPv6) arrivano dall'indirizzo della sua rete interna: non deve
# rientrare nella rete della struttura, altrimenti da fuori si entrerebbe senza il secondo passaggio.
NETWORK=$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' "$WEB" | awk '{print $1}')
GATEWAY=$(docker network inspect --format '{{range .IPAM.Config}}{{.Gateway}} {{end}}' "$NETWORK" 2>/dev/null | awk '{print $1}')
if [ -n "$GATEWAY" ] && python3 -c 'import ipaddress, sys; sys.exit(0 if any(ipaddress.ip_address(sys.argv[1]) in ipaddress.ip_network(n.strip(), strict=False) for n in sys.argv[2].split(",") if n.strip()) else 1)' "$GATEWAY" "$LAN"; then
  docker compose stop web worker
  die "la rete della struttura ($LAN) contiene la rete interna di Docker ($GATEWAY): correggere FASAS_2FA_TRUSTED_NETWORKS nel .env e rilanciare."
fi

printf '  controllo HTTPS e certificato per %s' "$DOMAIN"
HTTPS_OK=""
for _ in $(seq 1 24); do
  if curl -fsS -m 10 --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/salute/" >/dev/null 2>&1; then
    HTTPS_OK=1
    break
  fi
  printf '.'
  sleep 5
done
echo
if [ -n "$HTTPS_OK" ]; then
  ok "HTTPS funzionante con certificato valido: https://$DOMAIN"
else
  warn "certificato HTTPS non ancora ottenuto. Di solito vuol dire che dall'esterno le porte 80 e 443"
  warn "non arrivano a questo server: controllare l'inoltro delle porte nel router verso $SERVER_IP"
  warn "(guida, passo 6) e i messaggi con: sudo docker compose logs --tail 30 proxy"
fi

say "Fatto. Prossimi passi (guida, passi 10–11):"
cat <<EOF
  1) Primo amministratore:
       sudo docker compose exec web python manage.py createsuperuser
  2) Accedere da https://$DOMAIN e attivare la verifica in due passaggi.
  3) Busta di custodia delle chiavi, poi copiarla su una chiavetta da tenere in cassaforte:
       sudo docker compose exec web python manage.py fasas_chiavi busta /data/busta-chiavi.fkey
       sudo ./scripts/copia_backup_usb.sh /dev/sdX1 --busta
EOF
