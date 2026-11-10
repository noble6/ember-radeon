#!/bin/bash
# Build the release tarball, checksum and signature that ember-update.service installs.
#   packaging/make-release.sh            -> dist/ember-radeon-<version>.tar.gz(.sha256)(.sig)
# The signature is made with the Ed25519 release key, which stays on the maintainer's
# machine (default ~/.config/ember-release/signing-key.pem, or $EMBER_SIGNING_KEY).
# Installed copies of Ember refuse updates that are not signed with it.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(python3 -c 'import re;print(re.search(r"__version__ = \"([^\"]+)\"", open("ember/__init__.py").read()).group(1))')
NAME="ember-radeon-$VERSION"
mkdir -p dist
git archive --format=tar.gz --prefix="$NAME/" -o "dist/$NAME.tar.gz" HEAD
(cd dist && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
KEY="${EMBER_SIGNING_KEY:-$HOME/.config/ember-release/signing-key.pem}"
if [[ ! -f "$KEY" ]]; then
  echo "signing key not found at $KEY: an unsigned release would be rejected by every install" >&2
  exit 1
fi
openssl pkeyutl -sign -inkey "$KEY" -rawin -in "dist/$NAME.tar.gz" -out "dist/$NAME.tar.gz.sig"
# Check our own work against the key that ships in the code.
python3 -c 'import sys; from ember.core import update as U; U.verify_signature(open(sys.argv[1],"rb").read(), open(sys.argv[1]+".sig","rb").read()); print("signature ok")' "dist/$NAME.tar.gz"
echo "dist/$NAME.tar.gz"
cat "dist/$NAME.tar.gz.sha256"
