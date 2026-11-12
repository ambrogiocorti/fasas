#!/bin/sh
# Scarica CieSDK di PagoPA (licenza MIT) al commit esaminato, applica la patch per la firma e genera il progetto Xcode.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
COMMIT=63d2195750742dde104b5b352c7ca9cb32638e3d
rm -rf "$HERE/vendor/cie-sdk-ios"
mkdir -p "$HERE/vendor"
git clone --quiet --filter=blob:none --no-checkout https://github.com/pagopa/cie-sdk-ios.git "$HERE/vendor/cie-sdk-ios"
git -C "$HERE/vendor/cie-sdk-ios" checkout --quiet "$COMMIT"
git -C "$HERE/vendor/cie-sdk-ios" apply "$HERE/patches/cie-sdk-ios-63d2195-performSignature.patch"
cd "$HERE" && xcodegen generate
echo "Progetto pronto: apri FasasSigner.xcodeproj con Xcode."
