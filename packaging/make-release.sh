#!/bin/bash
# Build the release tarball and checksum that ember-update.service installs.
#   packaging/make-release.sh            -> dist/ember-radeon-<version>.tar.gz(.sha256)
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(python3 -c 'import re;print(re.search(r"__version__ = \"([^\"]+)\"", open("ember/__init__.py").read()).group(1))')
NAME="ember-radeon-$VERSION"
mkdir -p dist
git archive --format=tar.gz --prefix="$NAME/" -o "dist/$NAME.tar.gz" HEAD
(cd dist && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
echo "dist/$NAME.tar.gz"
cat "dist/$NAME.tar.gz.sha256"
