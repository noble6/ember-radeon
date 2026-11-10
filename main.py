#!/usr/bin/env python3
"""Ember - an open GPU control center for AMD Radeon on Linux."""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QSurfaceFormat, QGuiApplication  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

try:
    from ember.app.backend import Backend  # noqa: E402
except Exception as _e:   # noqa: BLE001 - a broken update must not leave the user without an app
    Backend = None
    _import_error = _e

def _server_name() -> str:
    """Single-instance socket. Lives in the user's private runtime dir when there is one:
    a name in /tmp could be squatted by another local user to keep Ember from starting."""
    rt = os.environ.get("XDG_RUNTIME_DIR")
    if rt and os.path.isdir(rt):
        d = Path(rt) / "ember"
        try:
            d.mkdir(mode=0o700, exist_ok=True)
            return str(d / "app.sock")
        except OSError:
            pass
    return f"ember-{os.getuid()}"


APP_ID = _server_name()
PAGES = ["home", "metrics", "tuning", "gaming", "record", "display", "system", "settings"]


REC_ACTIONS = ("toggle-recording", "save-replay", "toggle-replay", "screenshot")


def failsafe(reason: str) -> None:
    """The app could not start. If that follows an update, and the previous version is still
    on disk, ask the system to put it back (ember-rollback.service; no password for wheel).
    Uses only the standard library: whatever broke may be anything of ours."""
    import json
    import subprocess
    try:
        st = json.loads(Path("/var/lib/ember/update-status.json").read_text())
    except (OSError, ValueError):
        return
    import time
    if st.get("state") != "updated" or time.time() - float(st.get("time") or 0) > 14 * 86400:
        return                      # not after an update: an ordinary crash, leave things alone
    if not Path("/usr/local/lib/ember.prev/install.sh").is_file() or HERE != Path("/usr/local/lib/ember"):
        return
    print(f"ember: {reason}; going back to the previous version", file=sys.stderr)
    try:
        subprocess.run(["systemctl", "start", "--no-block", "ember-rollback.service"], timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["notify-send", "-a", "Ember", "-i", "ember", "Ember update rolled back",
                        f"Version {st.get('current')} could not start ({reason}). "
                        "The previous version is being restored; start Ember again in a moment."],
                       timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass


def already_running(msg: bytes = b"show") -> bool:
    sock = QLocalSocket()
    sock.connectToServer(APP_ID)
    if sock.waitForConnected(300):
        sock.write(msg)
        sock.waitForBytesWritten(300)
        return True
    return False


def main() -> int:
    if Backend is None:
        failsafe(f"{type(_import_error).__name__}: {_import_error}")
        raise _import_error
    hidden = "--hidden" in sys.argv
    if "--rec" in sys.argv:
        # `ember --rec save-replay` etc.: for custom shortcuts on desktops other than KDE.
        i = sys.argv.index("--rec")
        action = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        if action not in REC_ACTIONS:
            print("usage: ember --rec " + "|".join(REC_ACTIONS), file=sys.stderr)
            return 2
        from PySide6.QtCore import QCoreApplication
        QCoreApplication(sys.argv)
        if not already_running(f"rec:{action}".encode()):
            print("Ember is not running", file=sys.stderr)
            return 1
        return 0
    shot_dir = os.environ.get("EMBER_SCREENSHOT")
    QGuiApplication.setDesktopFileName("ember")
    fmt = QSurfaceFormat.defaultFormat()
    fmt.setSamples(4)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    app.setApplicationName("Ember")
    app.setOrganizationName("Ember")
    app.setWindowIcon(QIcon(str(HERE / "icons" / "ember.svg")))
    app.setQuitOnLastWindowClosed(False)

    if not shot_dir and already_running():
        return 0
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)   # only this user may connect
    QLocalServer.removeServer(APP_ID)
    server.listen(APP_ID)

    fid = QFontDatabase.addApplicationFont(str(HERE / "fonts" / "RobotoFlex.ttf"))
    family = QFontDatabase.applicationFontFamilies(fid)[0] if fid >= 0 else "sans-serif"
    font = QFont(family, 10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    QQuickWindow.setTextRenderType(QQuickWindow.TextRenderType.CurveTextRendering)

    backend = Backend()
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda ws: [print("qml:", w.toString(), file=sys.stderr) for w in ws])
    engine.rootContext().setContextProperty("ember", backend)
    engine.rootContext().setContextProperty("fontFamily", family)
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        backend.shutdown()
        failsafe("the interface failed to load")
        return 1
    win = engine.rootObjects()[0]

    def show():
        win.show()
        win.raise_()
        win.requestActivate()

    def on_conn():
        c = server.nextPendingConnection()

        def read():
            msg = bytes(c.readAll()).decode(errors="replace").strip()
            if msg.startswith("rec:"):
                backend.recAction(msg[4:])
            else:
                show()
        c.readyRead.connect(read)
        c.disconnected.connect(c.deleteLater)     # one socket object per `ember` call: don't keep them
    server.newConnection.connect(on_conn)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable() and not shot_dir:
        tray = QSystemTrayIcon(app.windowIcon())
        tray.setToolTip("Ember")
        menu = QMenu()
        menu.addAction("Open Ember", show)
        prof_menu = menu.addMenu("Profile")
        rec_menu = menu.addMenu("Record")
        a_rec = rec_menu.addAction("Start recording", lambda: backend.recAction("toggle-recording"))
        a_replay = rec_menu.addAction("Turn Instant Replay on", lambda: backend.recAction("toggle-replay"))
        a_save = rec_menu.addAction("Save Instant Replay", lambda: backend.recAction("save-replay"))
        rec_menu.addAction("Take screenshot", lambda: backend.recAction("screenshot"))

        def sync_rec():
            st = backend.recState
            a_rec.setText("Stop recording" if st.get("recording") else "Start recording")
            a_replay.setText("Turn Instant Replay off" if st.get("mode") == "replay" else "Turn Instant Replay on")
            a_save.setEnabled(st.get("mode") == "replay")
            rec_menu.setEnabled(bool(backend.recCaps.get("available")))
        backend.recChanged.connect(sync_rec)
        sync_rec()
        backend.recEvent.connect(lambda title, body: tray.showMessage(
            title, os.path.basename(body) if body.startswith("/") else body, app.windowIcon(), 5000))

        def rebuild():
            prof_menu.clear()
            active = backend.runtime.get("applied")
            for n in ["Stock"] + list((backend.gpuState.get("profiles") or {}).keys()):
                a = prof_menu.addAction(n)
                a.setCheckable(True)
                a.setChecked((n == "Stock" and not active) or n == active)
                a.setEnabled(bool(backend.daemon.get("authorized")))
                a.triggered.connect(lambda _=False, n=n: backend.activateProfile("" if n == "Stock" else n))
        menu.addSeparator()
        menu.addAction("Quit", app.quit)
        backend.daemonChanged.connect(rebuild)
        tip = {"text": ""}

        def tooltip():
            # Every tray update is a D-Bus message to the desktop shell: send one only when the text changes.
            snap = backend.snap
            text = (f"Ember · {backend.runtime.get('applied') or 'Stock'} · "
                    f"{(snap.get('temp_junction') or 0):.0f}°C · {(snap.get('power_w') or 0):.0f} W")
            if text != tip["text"]:
                tip["text"] = text
                tray.setToolTip(text)
        tip_timer = QTimer(interval=5000, timeout=tooltip)
        tip_timer.start()
        rebuild()
        backend.gameStarted.connect(lambda title, body: tray.showMessage(
            title, body, app.windowIcon(), 6000) if backend.settings.get("notify_games", True) else None)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda r: show() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
    win.setProperty("closeToTray", tray is not None and bool(backend.settings.get("close_to_tray", True)))
    backend.settingsChanged.connect(
        lambda: win.setProperty("closeToTray", tray is not None and bool(backend.settings.get("close_to_tray", True))))

    if not hidden or tray is None:
        show()
    # In the tray, the backend drops to a slow heartbeat and QML stops animating.
    win.visibleChanged.connect(backend.setUiVisible)     # the signal carries the new state
    backend.setUiVisible(win.isVisible())

    def restart_into_update(forced=False):
        """After a background update, quietly restart into the new version while the
        window is hidden and nothing is being recorded (or right away when asked)."""
        if shot_dir or not backend.restartPending or backend.recState.get("mode"):
            return
        if win.isVisible() and not forced:
            return
        target = Path("/usr/local/lib/ember/main.py")
        if not target.exists():
            return
        backend.shutdown()
        server.close()
        QLocalServer.removeServer(APP_ID)
        os.execv(sys.executable, [sys.executable, str(target)] + ([] if forced else ["--hidden"]))
    backend.restartRequested.connect(lambda: restart_into_update(forced=True))
    restart_timer = QTimer(interval=60000, timeout=restart_into_update)
    restart_timer.start()

    app.aboutToQuit.connect(backend.shutdown)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    keepalive = QTimer(interval=500, timeout=lambda: None)   # lets Python see SIGINT/SIGTERM
    keepalive.start()

    if shot_dir:
        Path(shot_dir).mkdir(parents=True, exist_ok=True)
        if os.environ.get("EMBER_SCREENSHOT_HEIGHT"):
            win.setHeight(int(os.environ["EMBER_SCREENSHOT_HEIGHT"]))
        only = os.environ.get("EMBER_SCREENSHOT_PAGES")
        order = [PAGES.index(p) for p in only.split(",")] if only else list(range(len(PAGES)))

        def snap(i=0):
            if i >= len(order):
                app.quit()
                return
            win.setProperty("page", order[i])
            QTimer.singleShot(1600, lambda: (win.grabWindow().save(f"{shot_dir}/{order[i]}_{PAGES[order[i]]}.png"),
                                             snap(i + 1)))
        QTimer.singleShot(int(os.environ.get("EMBER_SCREENSHOT_DELAY", "3500")), snap)

    rc = app.exec()
    del win
    del engine
    return rc


if __name__ == "__main__":
    sys.exit(main())
