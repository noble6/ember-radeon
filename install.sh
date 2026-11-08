#!/bin/bash
# Ember installer. Installs the app + root service system-wide under /usr/local.
#   ./install.sh            (asks for your password via sudo)
#   ./install.sh --uninstall
#   ./install.sh --unattended   (used by ember-update.service; already root)
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX=/usr/local
LIB=$PREFIX/lib/ember

TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}}"
for a in "$@"; do case $a in --user=*) TARGET_USER="${a#--user=}";; esac; done

if [[ $EUID -ne 0 ]]; then
  exec sudo "$0" "$@" --user="$(id -un)"
fi

if [[ " $* " == *" --uninstall "* ]]; then
  systemctl disable --now emberd.service ember-update.timer 2>/dev/null || true
  rm -f /etc/systemd/system/emberd.service /etc/systemd/system/ember-update.service \
        /etc/systemd/system/ember-update-now.service /etc/systemd/system/ember-update.timer \
        /etc/polkit-1/rules.d/50-ember-update.rules
  systemctl daemon-reload
  rm -rf "$LIB" "$PREFIX/bin/ember" "$PREFIX/bin/ember-run" \
         "$PREFIX/share/applications/ember.desktop" "$PREFIX/share/icons/hicolor/scalable/apps/ember.svg"
  echo "Ember removed. Kept /etc/ember, /var/lib/ember and /etc/modprobe.d/ember-overdrive.conf (if any)."
  exit 0
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -c 'import PySide6' 2>/dev/null || echo "note: PySide6 not found; the service works, the app needs pyside6 (pacman -S pyside6)"

# Everything the root service imports must be root-owned and not user-writable.
rm -rf "$LIB.new"
install -d -m 755 "$LIB.new"
cp -r "$SRC/ember" "$SRC/qml" "$SRC/fonts" "$SRC/icons" "$SRC/packaging" "$LIB.new/"
install -m 755 "$SRC/main.py" "$SRC/emberd.py" "$SRC/ember-update.py" "$SRC/install.sh" "$LIB.new/"
install -d -m 755 "$LIB.new/bin"
install -m 755 "$SRC/bin/ember-run" "$LIB.new/bin/ember-run"
find "$LIB.new" -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root "$LIB.new"
chmod -R go-w "$LIB.new"
rm -rf "$LIB"
mv "$LIB.new" "$LIB"
chmod 755 "$LIB/packaging/ember-overdrive"

cat > "$PREFIX/bin/ember" <<EOS
#!/bin/sh
exec /usr/bin/python3 $LIB/main.py "\$@"
EOS
chmod 755 "$PREFIX/bin/ember"
ln -sf "$LIB/bin/ember-run" "$PREFIX/bin/ember-run"
ln -sf "$LIB/packaging/ember-overdrive" "$LIB/ember-overdrive"

install -D -m 644 "$SRC/packaging/ember.desktop" "$PREFIX/share/applications/ember.desktop"
install -D -m 644 "$SRC/icons/ember.svg" "$PREFIX/share/icons/hicolor/scalable/apps/ember.svg"
gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true

install -d -m 755 /etc/ember
if [[ ! -f /etc/ember/emberd.conf ]]; then
  {
    echo "# Who may change GPU settings through emberd (comma separated)."
    echo "groups = wheel"
    echo "users = ${TARGET_USER:-}"
  } > /etc/ember/emberd.conf
fi

install -m 644 "$SRC/packaging/emberd.service" /etc/systemd/system/emberd.service
install -m 644 "$SRC/packaging/ember-update.service" /etc/systemd/system/ember-update.service
install -m 644 "$SRC/packaging/ember-update-now.service" /etc/systemd/system/ember-update-now.service
install -m 644 "$SRC/packaging/ember-update.timer" /etc/systemd/system/ember-update.timer
if [[ -d /etc/polkit-1/rules.d ]]; then
  install -m 644 "$SRC/packaging/50-ember-update.rules" /etc/polkit-1/rules.d/50-ember-update.rules
fi
systemctl daemon-reload
systemctl enable emberd.service >/dev/null 2>&1
systemctl enable --now ember-update.timer >/dev/null 2>&1 || true
systemctl restart emberd.service
sleep 0.5
systemctl --no-pager --lines=0 status emberd.service | head -3 || true
echo "Ember installed. Launch it from your app menu or run: ember"
