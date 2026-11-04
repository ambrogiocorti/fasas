#!/usr/bin/env bash
# Gruppo di continuità (UPS) collegato al server con il cavo USB, gestito con NUT (Network UPS Tools).
# - quando manca la corrente il FASAS avvisa coordinatori e amministratori (preparare la modalità senza rete);
# - prima che la batteria finisca il FASAS si ferma in modo ordinato e il server si spegne da solo;
# - al ritorno della corrente il gruppo riaccende le prese e il server riparte (BIOS: «Power On» dopo mancanza
#   di corrente, guida passo 2).
#
#   sudo ./scripts/gruppo_continuita.sh --elenca                cerca il gruppo collegato via USB
#   sudo ./scripts/gruppo_continuita.sh --configura             installa e configura (spegnimento al 40% di carica)
#   sudo ./scripts/gruppo_continuita.sh --configura --soglia 50 spegnimento con più margine
#   sudo ./scripts/gruppo_continuita.sh --stato                 corrente o batteria, carica, autonomia stimata
#
# Guida: docs/INSTALLAZIONE_IN_STRUTTURA.md, passo 15b. --simulato (solo per le prove automatiche) usa un gruppo
# finto e al posto dello spegnimento scrive /run/fasas-spegnimento-simulato.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT_DIR=$(pwd)
UPS=fasas-ups
STATE_DIR=${FASAS_UPS_STATE_DIR:-/srv/fasas-ups}
THRESHOLD=40
MODE=""
SIMULATED=""

die() { printf '\n\033[31mERRORE:\033[0m %s\n' "$*" >&2; exit 1; }
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }

set_env() {  # set_env NOME VALORE nel file .env del FASAS (se c'è)
  [ -f .env ] || return 0
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --elenca) MODE=elenca ;;
    --configura) MODE=configura ;;
    --stato) MODE=stato ;;
    --soglia) shift; THRESHOLD=${1:-}; [[ "$THRESHOLD" =~ ^[1-9][0-9]$ ]] || die "--soglia vuole una percentuale (es. --soglia 50)" ;;
    --simulato) SIMULATED=1 ;;
    *) die "argomento sconosciuto: $1 (vedere le istruzioni in cima allo script)" ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "eseguire con sudo"

install_nut() {
  command -v upsmon > /dev/null && command -v upsd > /dev/null && return 0
  echo "  installo NUT (Network UPS Tools)..."
  DEBIAN_FRONTEND=noninteractive timeout 900 apt-get -o DPkg::Lock::Timeout=300 install -y -q nut > /dev/null \
    || die "installazione di NUT non riuscita: riprovare più tardi (aggiornamenti in corso?)"
}

case "$MODE" in
  elenca)
    install_nut
    nut-scanner -U -q 2>/dev/null || true
    echo "Se non compare nulla: il cavo USB del gruppo è collegato al server? Provare un'altra porta USB."
    ;;

  configura)
    install_nut
    if [ -n "$SIMULATED" ]; then
      printf 'battery.charge: 100\nbattery.runtime: 1800\nups.status: OL\n' > /etc/nut/fasas-prova.dev  # stato per ultimo
      DEVICE='	driver = "dummy-ups"
	port = "fasas-prova.dev"
	mode = "dummy-once"'
      SHUTDOWN_CMD="touch /run/fasas-spegnimento-simulato"
    else
      FOUND=$(nut-scanner -U -q 2>/dev/null | awk 'NR > 1 && /^\[/ {exit} NR > 1 && /=/ {print}')
      [ -n "$FOUND" ] || die "nessun gruppo di continuità trovato via USB: collegare il cavo USB al server e riprovare."
      DEVICE=$(printf '%s\n' "$FOUND" | grep -E '^\s*(driver|port|vendorid|productid|bus|serial) =' || true)
      SHUTDOWN_CMD="/usr/local/sbin/fasas-spegni"
    fi
    install -d -o root -g nut -m 750 /etc/nut
    cat > /etc/nut/ups.conf <<EOF
# Gruppo di continuità del server FASAS (scripts/gruppo_continuita.sh)
[$UPS]
$DEVICE
	desc = "Gruppo di continuità del server FASAS"
	# spegnimento con margine: batteria sotto il ${THRESHOLD}% o meno di 3 minuti di autonomia stimata
	ignorelb
	override.battery.charge.low = $THRESHOLD
	override.battery.runtime.low = 180
EOF
    echo "MODE=standalone" > /etc/nut/nut.conf
    printf 'LISTEN 127.0.0.1 3493\n' > /etc/nut/upsd.conf
    PASSWORD=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
    cat > /etc/nut/upsd.users <<EOF
[fasas-monitor]
	password = $PASSWORD
	upsmon primary
EOF
    cat > /etc/nut/upsmon.conf <<EOF
# Sorveglianza del gruppo di continuità del server FASAS (scripts/gruppo_continuita.sh)
MONITOR $UPS@localhost 1 fasas-monitor $PASSWORD primary
MINSUPPLIES 1
SHUTDOWNCMD "$SHUTDOWN_CMD"
NOTIFYCMD /usr/local/sbin/fasas-ups-avviso
NOTIFYFLAG ONLINE SYSLOG+EXEC
NOTIFYFLAG ONBATT SYSLOG+WALL+EXEC
NOTIFYFLAG LOWBATT SYSLOG+WALL+EXEC
NOTIFYFLAG FSD SYSLOG+WALL+EXEC
NOTIFYFLAG COMMOK SYSLOG+EXEC
NOTIFYFLAG COMMBAD SYSLOG+EXEC
NOTIFYFLAG NOCOMM SYSLOG+EXEC
NOTIFYFLAG REPLBATT SYSLOG+EXEC
POLLFREQ 5
POLLFREQALERT 5
DEADTIME 15
POWERDOWNFLAG /etc/killpower
FINALDELAY 5
EOF
    chown root:nut /etc/nut/*.conf /etc/nut/upsd.users
    chmod 640 /etc/nut/*.conf /etc/nut/upsd.users

    # Gli eventi vanno in un file che il FASAS legge ogni minuto (upsmon gira come utente «nut»: niente docker)
    install -d -o nut -g nut -m 755 "$STATE_DIR"
    cat > /usr/local/sbin/fasas-ups-avviso <<EOF
#!/bin/sh
# Chiamato da upsmon a ogni evento del gruppo di continuità: lo scrive per il FASAS (job «ups»).
TMP="$STATE_DIR/.stato.\$\$"
printf '{"evento": "%s", "quando": "%s"}\n' "\${NOTIFYTYPE:-SCONOSCIUTO}" "\$(date -Iseconds)" > "\$TMP" && chmod 644 "\$TMP" && mv "\$TMP" "$STATE_DIR/stato.json"
EOF
    chmod 755 /usr/local/sbin/fasas-ups-avviso
    # Spegnimento: prima si ferma il FASAS (database chiuso in modo ordinato), poi il server
    cat > /usr/local/sbin/fasas-spegni <<EOF
#!/bin/sh
# Batteria del gruppo quasi scarica: FASAS fermato in modo ordinato, poi spegnimento del server.
cd "$ROOT_DIR" && timeout 120 docker compose stop
/sbin/shutdown -h +0
EOF
    chmod 755 /usr/local/sbin/fasas-spegni
    NOTIFYTYPE=ONLINE /usr/local/sbin/fasas-ups-avviso
    chown nut:nut "$STATE_DIR/stato.json"

    if [ -d /run/systemd/system ]; then
      systemctl enable nut-server nut-monitor > /dev/null 2>&1 || true
      systemctl restart nut-driver-enumerator > /dev/null 2>&1 || true
      upsdrvctl stop > /dev/null 2>&1 || true
      systemctl restart "nut-driver@$UPS" > /dev/null 2>&1 || upsdrvctl start
      systemctl restart nut-server nut-monitor
    fi
    ok "gruppo di continuità configurato: spegnimento ordinato sotto il $THRESHOLD% di carica"
    set_env FASAS_UPS_HOST_DIR "$STATE_DIR"
    set_env FASAS_UPS_STATUS_FILE /ups/stato.json
    [ ! -f .env ] || chmod 600 .env
    ok "FASAS configurato: avvisi a coordinatori e amministratori quando manca la corrente"
    echo
    echo "Ora riavviare il FASAS:  cd $ROOT_DIR && sudo docker compose up -d"
    echo "Poi la prova vera (guida, passo 15b): staccare la spina del gruppo e controllare l'avviso nel FASAS."
    ;;

  stato)
    command -v upsc > /dev/null || die "NUT non è installato: sudo $0 --configura"
    STATUS=$(upsc "$UPS@localhost" ups.status 2>/dev/null) || die "il gruppo non risponde: cavo USB collegato? (sudo $0 --elenca)"
    case "$STATUS" in
      *OB*) echo "  A BATTERIA (corrente assente)" ;;
      *OL*) ok "alimentato dalla rete elettrica" ;;
      *) echo "  stato: $STATUS" ;;
    esac
    echo "  carica: $(upsc "$UPS@localhost" battery.charge 2>/dev/null || echo '?')%"
    RUNTIME=$(upsc "$UPS@localhost" battery.runtime 2>/dev/null || echo "")
    [ -z "$RUNTIME" ] || echo "  autonomia stimata: $((RUNTIME / 60)) minuti"
    [ ! -f "$STATE_DIR/stato.json" ] || echo "  ultimo evento: $(cat "$STATE_DIR/stato.json")"
    ;;

  *) die "indicare --elenca, --configura oppure --stato (istruzioni in cima allo script)" ;;
esac
