#!/usr/bin/env bash
# Manutenzione del server da casa, solo per l'amministratore di sistema. Una VPN WireGuard (gratuita, nessun
# servizio esterno o abbonamento) collega il PC dell'amministratore al server con un canale cifrato; solo da lì si
# entra con SSH. La porta 22 resta chiusa verso internet e chi usa il FASAS non si accorge di nulla.
#
#   sudo ./scripts/accesso_remoto.sh --configura                una volta: prepara la VPN sul server
#   sudo ./scripts/accesso_remoto.sh --aggiungi pc-casa         accesso per un PC: file da copiare (con --qr anche
#                                                               il codice per l'app WireGuard del telefono)
#   sudo ./scripts/accesso_remoto.sh --elenca                   accessi creati e ultimo collegamento
#   sudo ./scripts/accesso_remoto.sh --rimuovi pc-casa          PC perso o rubato, persona che lascia: tolto subito
#   sudo ./scripts/accesso_remoto.sh --stato
#
# Opzioni: --porta 51820 (UDP, da inoltrare sul router), --indirizzo nome.duckdns.org (di norma FASAS_DOMAIN).
# Da casa, con la VPN accesa:  ssh amministratore@10.77.0.1      Guida: docs/INSTALLAZIONE_IN_STRUTTURA.md, passo 15c.
set -euo pipefail

cd "$(dirname "$0")/.."
IFACE=fasasvpn
CONF=/etc/wireguard/$IFACE.conf
NET=10.77.0
PORT=51820
PORT_ARG=""
HOST=""
MODE=""
NAME=""
QR=""

die() { printf '\n\033[31mERRORE:\033[0m %s\n' "$*" >&2; exit 1; }
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --configura) MODE=configura ;;
    --aggiungi) MODE=aggiungi; shift; NAME=${1:-} ;;
    --rimuovi) MODE=rimuovi; shift; NAME=${1:-} ;;
    --elenca) MODE=elenca ;;
    --stato) MODE=stato ;;
    --qr) QR=1 ;;
    --porta) shift; PORT=${1:-}; PORT_ARG=1; [[ "$PORT" =~ ^[1-9][0-9]{3,4}$ ]] && [ "$PORT" -le 65535 ] || die "--porta vuole un numero, es. --porta 51820" ;;
    --indirizzo) shift; HOST=${1:-}; [[ "$HOST" =~ ^[A-Za-z0-9.-]+$ ]] || die "--indirizzo vuole un nome o un IP, es. fasas-insieme.duckdns.org" ;;
    *) die "argomento sconosciuto: $1 (vedere le istruzioni in cima allo script)" ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "eseguire con sudo"
case "$MODE" in aggiungi|rimuovi)
  [[ "$NAME" =~ ^[a-z0-9][a-z0-9-]{0,19}$ ]] || die "nome dell'accesso: lettere minuscole, cifre e trattini, al massimo 20 (es. pc-casa-mario)" ;;
esac

env_value() { [ -f .env ] && sed -n "s/^$1=//p" .env | tail -n 1 || true; }
is_up() { wg show "$IFACE" > /dev/null 2>&1; }
reload() {  # applica gli accessi del file senza interrompere quelli già collegati
  if is_up; then wg syncconf "$IFACE" <(wg-quick strip "$IFACE"); fi
}
firewall_active() { command -v ufw > /dev/null && LC_ALL=C ufw status | grep -q '^Status: active'; }
peers() {  # nome|indirizzo|chiave pubblica, uno per riga
  awk 'BEGIN { RS = ""; FS = "\n" }
    $1 == "[Peer]" { n = ""; ip = ""; k = ""
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^# accesso: /) { n = $i; sub(/^# accesso: /, "", n); sub(/ .*/, "", n) }
        if ($i ~ /^AllowedIPs = /) { ip = $i; sub(/^AllowedIPs = /, "", ip); sub(/\/32$/, "", ip) }
        if ($i ~ /^PublicKey = /) { k = $i; sub(/^PublicKey = /, "", k) }
      }
      print n "|" ip "|" k }' "$CONF"
}
has_peer() { peers | awk -F'|' -v n="$1" '$1 == n { f = 1 } END { exit !f }'; }

case "$MODE" in
  configura)
    if ! command -v wg-quick > /dev/null || ! command -v qrencode > /dev/null; then
      echo "  installo WireGuard..."
      { timeout 900 apt-get -o DPkg::Lock::Timeout=300 update -qq \
        && DEBIAN_FRONTEND=noninteractive timeout 900 apt-get -o DPkg::Lock::Timeout=300 install -y -q wireguard-tools qrencode > /dev/null; } \
        || die "installazione di WireGuard non riuscita: riprovare più tardi (aggiornamenti in corso?)"
    fi
    if [ -f "$CONF" ]; then
      [ -z "$PORT_ARG" ] || sed -i -E "s/^ListenPort = .*/ListenPort = $PORT/" "$CONF"
      [ -z "$HOST" ] || sed -i -E "s/^# indirizzo da casa: .*/# indirizzo da casa: $HOST/" "$CONF"
      PORT=$(sed -n 's/^ListenPort = //p' "$CONF")
      ok "VPN già preparata: accessi esistenti conservati"
    else
      [ -n "$HOST" ] || HOST=$(env_value FASAS_DOMAIN)
      [ -n "$HOST" ] || die "indirizzo del FASAS non trovato in .env: indicare --indirizzo nome.duckdns.org"
      install -d -m 700 /etc/wireguard
      (umask 077; cat > "$CONF" <<EOF
# VPN per la manutenzione del server da casa (scripts/accesso_remoto.sh). Ogni blocco Peer è un accesso.
# indirizzo da casa: $HOST
[Interface]
Address = $NET.1/24
ListenPort = $PORT
PrivateKey = $(wg genkey)
EOF
)
      ok "chiavi della VPN create (restano sul server, file leggibile solo dall'amministratore)"
    fi
    if firewall_active; then
      ufw allow "$PORT/udp" comment "VPN di manutenzione FASAS" > /dev/null
      ufw allow in on "$IFACE" to any port 22 proto tcp comment "SSH dalla VPN di manutenzione" > /dev/null
      ok "firewall: aperta solo la porta UDP $PORT; SSH solo dalla rete della struttura e dalla VPN"
    else
      warn "firewall non attivo (guida, passo 15): attivarlo rilanciando scripts/prepara_server.sh"
    fi
    if [ -d /run/systemd/system ]; then
      systemctl enable "wg-quick@$IFACE" > /dev/null 2>&1
      systemctl restart "wg-quick@$IFACE"
    else
      is_up && wg-quick down "$IFACE" > /dev/null 2>&1 || true
      wg-quick up "$IFACE" > /dev/null 2>&1
    fi
    is_up || die "la VPN non è partita: vedere  journalctl -u wg-quick@$IFACE"
    ok "VPN attiva (riparte da sola a ogni accensione del server)"
    echo
    echo "Ora sul router: inoltro della porta UDP $PORT verso questo server (guida, passo 15c)."
    echo "Poi:  sudo $0 --aggiungi pc-casa"
    ;;

  aggiungi)
    [ -f "$CONF" ] || die "VPN non ancora preparata: sudo $0 --configura"
    ! has_peer "$NAME" || die "esiste già un accesso «$NAME»: sceglierne un altro nome o toglierlo con --rimuovi"
    USED=" $(peers | cut -d'|' -f2 | sed "s/^$NET\.//" | tr '\n' ' ') "
    N=""
    for i in $(seq 2 254); do case "$USED" in *" $i "*) ;; *) N=$i; break ;; esac; done
    [ -n "$N" ] || die "troppi accessi: toglierne qualcuno con --rimuovi"
    [ -n "$HOST" ] || HOST=$(sed -n 's/^# indirizzo da casa: //p' "$CONF")
    SERVER_PORT=$(sed -n 's/^ListenPort = //p' "$CONF")
    SERVER_PUB=$(sed -n 's/^PrivateKey = //p' "$CONF" | wg pubkey)
    PRIV=$(wg genkey)
    PSK=$(wg genpsk)
    printf '\n[Peer]\n# accesso: %s (creato il %s)\nPublicKey = %s\nPresharedKey = %s\nAllowedIPs = %s.%s/32\n' \
      "$NAME" "$(date '+%d/%m/%Y')" "$(printf '%s' "$PRIV" | wg pubkey)" "$PSK" "$NET" "$N" >> "$CONF"
    reload
    # il file per il PC dell'amministratore: si crea una volta sola, la chiave privata non resta sul server
    OWNER=${SUDO_USER:-root}
    HOME_DIR=$(getent passwd "$OWNER" | cut -d: -f6)
    OUT="${HOME_DIR:-/root}/fasas-$NAME.conf"
    CLIENT="[Interface]
# FASAS: manutenzione da casa ($NAME). Con la VPN accesa: ssh $OWNER@$NET.1
PrivateKey = $PRIV
Address = $NET.$N/32

[Peer]
PublicKey = $SERVER_PUB
PresharedKey = $PSK
Endpoint = $HOST:$SERVER_PORT
AllowedIPs = $NET.1/32
PersistentKeepalive = 25"
    (umask 077; printf '%s\n' "$CLIENT" > "$OUT")
    chown "$OWNER" "$OUT" 2>/dev/null || true
    ok "accesso «$NAME» creato: indirizzo nella VPN $NET.$N"
    if [ -n "$QR" ]; then
      echo "Codice per l'app WireGuard del telefono (Aggiungi › Scansiona codice QR). Contiene una chiave segreta:"
      qrencode -t ansiutf8 < "$OUT"
    fi
    echo
    echo "1. Dal PC di casa, mentre è collegato alla rete della struttura, copiare il file (poi tenerlo solo lì):"
    echo "     scp $OWNER@<indirizzo-del-server>:fasas-$NAME.conf ."
    echo "2. Toglierlo dal server:  rm $OUT"
    echo "3. Installare WireGuard sul PC (wireguard.com/install, gratuito) e «Importa tunnel da file»."
    echo "4. Da casa: attivare il tunnel, poi  ssh $OWNER@$NET.1"
    ;;

  rimuovi)
    [ -f "$CONF" ] || die "VPN non preparata: non ci sono accessi da togliere"
    has_peer "$NAME" || die "nessun accesso «$NAME» (elenco: sudo $0 --elenca)"
    TMP=$(mktemp /etc/wireguard/.rimuovi.XXXXXX)
    awk -v tag="# accesso: $NAME (" 'BEGIN { RS = ""; ORS = "\n\n" } index($0, "\n" tag) == 0 { print }' "$CONF" > "$TMP"
    chmod 600 "$TMP"
    mv "$TMP" "$CONF"
    reload
    ok "accesso «$NAME» tolto: da quel dispositivo non si entra più"
    ;;

  elenca)
    [ -f "$CONF" ] || { echo "VPN non preparata (sudo $0 --configura)."; exit 0; }
    LIST=$(peers)
    [ -n "$LIST" ] || { echo "Nessun accesso creato (sudo $0 --aggiungi pc-casa)."; exit 0; }
    HANDSHAKES=$(wg show "$IFACE" latest-handshakes 2>/dev/null || true)
    printf '%s\n' "$LIST" | while IFS='|' read -r n ip k; do
      t=$(printf '%s\n' "$HANDSHAKES" | awk -v k="$k" '$1 == k { print $2 }')
      if [ -n "$t" ] && [ "$t" != 0 ]; then last="ultimo collegamento $(date -d "@$t" '+%d/%m/%Y %H:%M')"; else last="mai collegato"; fi
      printf '  %-22s %-12s %s\n' "$n" "$ip" "$last"
    done
    ;;

  stato)
    [ -f "$CONF" ] || { echo "VPN non preparata (sudo $0 --configura)."; exit 0; }
    if is_up; then ok "VPN attiva sulla porta UDP $(sed -n 's/^ListenPort = //p' "$CONF")"; else warn "VPN ferma: sudo systemctl restart wg-quick@$IFACE"; fi
    echo "  indirizzo da casa: $(sed -n 's/^# indirizzo da casa: //p' "$CONF")"
    echo "  accessi: $(peers | grep -c . || true)"
    if firewall_active; then
      if LC_ALL=C ufw status | grep -q "on $IFACE"; then ok "firewall: SSH ammesso dalla VPN"
      else warn "firewall: manca la regola SSH per la VPN (rilanciare --configura)"; fi
    fi
    ;;

  *) die "indicare --configura, --aggiungi NOME, --elenca, --rimuovi NOME oppure --stato (istruzioni in cima allo script)" ;;
esac
