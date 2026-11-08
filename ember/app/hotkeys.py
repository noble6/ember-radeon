"""Global hotkeys through KDE's KGlobalAccel (works while a fullscreen game has focus).

Ember registers its actions like any KDE app, so they show up (and can be
rebound) in System Settings > Keyboard > Shortcuts > Ember. Other desktops can
bind a custom shortcut to `ember --rec <action>` instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from PySide6.QtCore import QObject, Signal, Slot, SLOT
from PySide6.QtDBus import QDBusConnection

COMPONENT = "ember"
FRIENDLY = "Ember"
_ALT, _SHIFT = 0x08000000, 0x02000000
_F9, _F10, _F11 = 0x01000038, 0x01000039, 0x0100003A

# action id -> (label, default Qt key combination)
ACTIONS = {
    "toggle-recording": ("Start / stop recording", _ALT | _F9),
    "save-replay": ("Save Instant Replay", _ALT | _F10),
    "toggle-replay": ("Turn Instant Replay on / off", _ALT | _SHIFT | _F10),
    "screenshot": ("Take screenshot", _ALT | _F11),
}
_BASE = ["dbus-send", "--session", "--print-reply", "--dest=org.kde.kglobalaccel", "/kglobalaccel"]


def kde_available() -> bool:
    if not shutil.which("dbus-send"):
        return False
    try:
        r = subprocess.run(["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.DBus", "/",
                            "org.freedesktop.DBus.NameHasOwner", "string:org.kde.kglobalaccel"],
                           capture_output=True, text=True, timeout=3)
        return "boolean true" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def _aid(action: str) -> str:
    return f"array:string:{COMPONENT},{action},{FRIENDLY},{ACTIONS[action][0]}"


def _call(*args: str) -> str:
    try:
        return subprocess.run(_BASE + list(args), capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


class Hotkeys(QObject):
    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self.enabled = False
        self.keys: dict[str, int] = {}

    def register_keys(self) -> bool:
        """Blocking D-Bus calls (run off the GUI thread). Call listen() afterwards on the GUI thread."""
        if not kde_available():
            return False
        for action, (_label, key) in ACTIONS.items():
            _call("org.kde.KGlobalAccel.doRegister", _aid(action))
            # 1 = IsDefault: declare the default. 2 = SetPresent without NoAutoloading:
            # KDE keeps a key the user already chose in System Settings.
            _call("org.kde.KGlobalAccel.setShortcut", _aid(action), f"array:int32:{key}", "uint32:1")
            out = _call("org.kde.KGlobalAccel.setShortcut", _aid(action), f"array:int32:{key}", "uint32:2")
            nums = [int(x) for x in out.split() if x.lstrip("-").isdigit()]
            self.keys[action] = nums[0] if nums else 0
        return True

    def listen(self) -> bool:
        self.enabled = QDBusConnection.sessionBus().connect(
            "org.kde.kglobalaccel", f"/component/{COMPONENT}", "org.kde.kglobalaccel.Component",
            "globalShortcutPressed", self, SLOT("_pressed(QString,QString,qlonglong)"))
        return self.enabled

    @Slot(str, str, "qlonglong")
    def _pressed(self, component, action, _ts):
        if component == COMPONENT and action in ACTIONS:
            self.triggered.emit(action)

    def describe(self) -> list[dict]:
        from PySide6.QtGui import QKeySequence
        out = []
        for action, (label, default) in ACTIONS.items():
            key = self.keys.get(action, default if not self.enabled else 0)
            text = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText) if key else "Not set"
            out.append({"id": action, "label": label, "keys": text})
        return out


def open_shortcut_settings() -> None:
    for cmd in (["systemsettings", "kcm_keys"], ["kcmshell6", "kcm_keys"]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                             env={k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"})
            return
