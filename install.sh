#!/bin/bash
# Ember installer. Installs the app + root service system-wide under /usr/local.
#   ./install.sh               (asks for your password via sudo)
#   ./install.sh --uninstall
#   ./install.sh --unattended  (used by ember-update.service; already root)
#   ./install.sh --rollback    (put the previous version back; used by ember-rollback.service)
#
# Fail-safe: the version being replaced is kept in /usr/local/lib/ember.prev. When an
# unattended update leaves the service unable to run, the previous version is restored
# automatically and the script exits with status 3.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX=/usr/local
LIB=$PREFIX/lib/ember
PREV=$LIB.prev
STATE=/var/lib/ember

TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}}"
for a in "$@"; do case $a in --user=*) TARGET_USER="${a#--user=}";; esac; done

if [[ $EUID -ne 0 ]]; then
  exec sudo "$0" "$@" --user="$(id -un)"
fi

has_flag() { [[ " $ARGS " == *" $1 "* ]]; }
ARGS="$*"

version_of() {   # version_of <tree>
  sed -n 's/^__version__ = "\(.*\)"/\1/p' "$1/ember/__init__.py" 2>/dev/null | head -1
}

# Everything outside $LIB that belongs to a version: launchers, units, policy. Taken from
# the tree given, so it can put back an older version's files as well as install new ones.
install_system_files() {   # install_system_files <tree>
  local t="$1" u
  cat > "$PREFIX/bin/ember" <<EOS
#!/bin/sh
exec /usr/bin/python3 $LIB/main.py "\$@"
EOS
  chmod 755 "$PREFIX/bin/ember"
  ln -sf "$LIB/bin/ember-run" "$PREFIX/bin/ember-run"
  ln -sf "$LIB/packaging/ember-overdrive" "$LIB/ember-overdrive"
  chmod 755 "$LIB/packaging/ember-overdrive"
  install -D -m 644 "$t/packaging/ember.desktop" "$PREFIX/share/applications/ember.desktop"
  install -D -m 644 "$t/icons/ember.svg" "$PREFIX/share/icons/hicolor/scalable/apps/ember.svg"
  gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true
  for u in emberd.service ember-update.service ember-update-now.service ember-update.timer ember-rollback.service; do
    if [[ -f "$t/packaging/$u" ]]; then
      install -m 644 "$t/packaging/$u" "/etc/systemd/system/$u"
    else
      rm -f "/etc/systemd/system/$u"      # the version being restored did not have this unit
    fi
  done
  if [[ -d /etc/polkit-1/rules.d && -f "$t/packaging/50-ember-update.rules" ]]; then
    install -m 644 "$t/packaging/50-ember-update.rules" /etc/polkit-1/rules.d/50-ember-update.rules
  fi
  systemctl daemon-reload
}

# The service counts as healthy when it is still running a few seconds after its start.
service_healthy() {
  local i
  for i in 1 2 3; do
    sleep 2
    systemctl is-active --quiet emberd.service || return 1
  done
  [[ -S /run/ember/emberd.sock ]]
}

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\n\r\t'; }

# Swap the previous version back in. $1 = why (shown in Settings > Updates).
restore_previous() {
  local why="$1" bad prev
  [[ -f "$PREV/main.py" ]] || { echo "no previous version to go back to" >&2; return 1; }
  bad=$(version_of "$LIB"); prev=$(version_of "$PREV")
  rm -rf "$LIB.failed"
  if [[ -e "$LIB" ]]; then mv "$LIB" "$LIB.failed"; fi
  mv "$PREV" "$LIB"
  install_system_files "$LIB"
  systemctl restart emberd.service || true
  rm -rf "$LIB.failed"
  install -d -m 755 "$STATE"
  # Remember the version that failed so the daily check does not install it again,
  # and tell the app what happened.
  printf '{"version": "%s"}\n' "$(json_escape "$bad")" > "$STATE/update-skip.json"
  printf '{"state": "rolled-back", "time": %s, "current": "%s", "failed": "%s", "error": "%s"}\n' \
    "$(date +%s)" "$(json_escape "$prev")" "$(json_escape "$bad")" "$(json_escape "$why")" > "$STATE/update-status.json"
  chmod 644 "$STATE/update-skip.json" "$STATE/update-status.json"
  echo "Ember $bad was rolled back to $prev: $why"
}

if has_flag --uninstall; then
  systemctl disable --now emberd.service ember-update.timer 2>/dev/null || true
  rm -f /etc/systemd/system/emberd.service /etc/systemd/system/ember-update.service \
        /etc/systemd/system/ember-update-now.service /etc/systemd/system/ember-update.timer \
        /etc/systemd/system/ember-rollback.service /etc/polkit-1/rules.d/50-ember-update.rules
  systemctl daemon-reload
  rm -rf "$LIB" "$LIB.new" "$LIB.old" "$LIB.failed" "$PREV" "$PREFIX/bin/ember" "$PREFIX/bin/ember-run" \
         "$PREFIX/share/applications/ember.desktop" "$PREFIX/share/icons/hicolor/scalable/apps/ember.svg"
  echo "Ember removed. Kept /etc/ember, /var/lib/ember and /etc/modprobe.d/ember-overdrive.conf (if any)."
  exit 0
fi

if has_flag --rollback; then
  restore_previous "rolled back on request"
  exit 0
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -c 'import PySide6' 2>/dev/null || echo "note: PySide6 not found; the service works, the app needs pyside6 (pacman -S pyside6)"

WAS_HEALTHY=0
if systemctl is-active --quiet emberd.service 2>/dev/null; then WAS_HEALTHY=1; fi

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

# Swap with renames, so there is no moment in which Ember is missing. The version being
# replaced stays in $PREV until the next update, as the thing to fall back to.
rm -rf "$LIB.old" "$LIB.failed"
if [[ -e "$LIB" ]]; then
  if [[ "$SRC" != "$PREV" ]]; then rm -rf "$PREV"; mv "$LIB" "$PREV"; else mv "$LIB" "$LIB.old"; fi
fi
mv "$LIB.new" "$LIB"
rm -rf "$LIB.old"

install -d -m 755 /etc/ember
if [[ ! -f /etc/ember/emberd.conf ]]; then
  {
    echo "# Who may change GPU settings through emberd (comma separated)."
    echo "groups = wheel"
    echo "users = ${TARGET_USER:-}"
  } > /etc/ember/emberd.conf
fi

install_system_files "$LIB"
systemctl enable emberd.service >/dev/null 2>&1
systemctl enable --now ember-update.timer >/dev/null 2>&1 || true
systemctl restart emberd.service || true

# Fail-safe for automatic updates: a service that ran before must run after.
if has_flag --unattended && [[ $WAS_HEALTHY -eq 1 && -z "${EMBER_NO_ROLLBACK:-}" ]]; then
  if ! service_healthy; then
    echo "the Ember service does not start with this version; restoring the previous one" >&2
    if restore_previous "the service did not start after the update"; then
      exit 3
    fi
    exit 1
  fi
else
  sleep 0.5
fi
systemctl --no-pager --lines=0 status emberd.service | head -3 || true
echo "Ember installed. Launch it from your app menu or run: ember"
