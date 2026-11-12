#!/bin/sh
# Scarica la libreria IAS (protocollo della CIE su NFC) di PagoPA/IPZS, licenza MIT, a una versione FISSATA,
# nel modulo app. Il logger originale non viene copiato: lo sostituisce lo stub del FASAS (nessun APDU nei log).
set -eu
REPO=https://github.com/pagopa/io-cie-android-sdk.git
COMMIT=9f70a324ba41fe50099d3b8b5653870bcc875292
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST="$HERE/app/src/main/java/it/ipzs/cieidsdk"
TMP=$(mktemp -d)
git clone --quiet --filter=blob:none --no-checkout "$REPO" "$TMP/sdk"
git -C "$TMP/sdk" checkout --quiet "$COMMIT"
SRC="$TMP/sdk/android/src/main/java/it/ipzs/cieidsdk"
mkdir -p "$DEST"
cp -R "$SRC/nfc" "$SRC/exceptions" "$DEST/"
cp "$TMP/sdk/package.json" "$HERE/app/THIRD_PARTY_io-cie-android-sdk_package.json"
cat > "$HERE/app/THIRD_PARTY_NOTICE.md" <<NOTE
Il codice in app/src/main/java/it/ipzs/cieidsdk/{nfc,exceptions} proviene da
$REPO (commit $COMMIT), licenza MIT (vedi package.json del progetto), © PagoPA S.p.A. / IPZS.
Scaricato da scripts/fetch_ias.sh; non è incluso nel repository del FASAS.
NOTE
rm -rf "$TMP"
echo "Libreria IAS copiata in $DEST (commit $COMMIT)."
