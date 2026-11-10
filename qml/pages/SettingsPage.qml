import QtQuick
import "../components"

Flickable {
    id: page
    contentHeight: col.height + 64
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    readonly property var cfg: ember.settings

    Column {
        id: col
        x: 40; y: 36
        width: Math.min(page.width - 80, 900)
        spacing: 16
        Label { text: "Settings"; role: "displayS"; emphasized: true }

        Card {
            width: parent.width; height: ap.height + 48
            Column {
                id: ap
                x: 24; y: 24; width: parent.width - 48
                spacing: 16
                CardTitle { icon: "palette"; text: "Appearance" }
                ButtonGroup {
                    width: 320; itemHeight: 44
                    model: [{ key: "dark", label: "Dark", icon: "moon" }, { key: "light", label: "Light", icon: "light" }]
                    current: page.cfg.theme
                    onPicked: (k) => ember.setSetting("theme", k)
                }
                Row {
                    spacing: 12
                    Repeater {
                        model: ember.accents
                        delegate: Column {
                            required property var modelData
                            spacing: 6
                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: 48; height: 48
                                radius: page.cfg.accent === modelData.name ? 16 : 24
                                Behavior on radius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
                                color: modelData.color
                                Icon { anchors.centerIn: parent; name: "check"; size: 24; color: "white"
                                       visible: page.cfg.accent === modelData.name }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: ember.setSetting("accent", modelData.name) }
                            }
                            Label { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.name; role: "labelS"; color: Theme.inkVariant }
                        }
                    }
                }
            }
        }
        Card {
            width: parent.width; height: bh.height + 48
            Column {
                id: bh
                x: 24; y: 24; width: parent.width - 48
                spacing: 8
                CardTitle { icon: "settings"; text: "Behaviour"; bottomPadding: 8 }
                SwitchRow { width: parent.width; icon: "power"; title: "Start with the desktop"
                            subtitle: "Opens hidden in the tray so profiles are one right-click away. Tuning itself never needs the app open."
                            checked: !!page.cfg.autostart; onToggled: (on) => ember.setSetting("autostart", on) }
                SwitchRow { width: parent.width; icon: "game"; title: "Notify when a game starts"
                            subtitle: "A desktop notification with the profile Ember is using for that game."
                            checked: page.cfg.notify_games !== false; onToggled: (on) => ember.setSetting("notify_games", on) }
                SwitchRow { width: parent.width; icon: "sparkle"; title: "In-game “Ember active” banner"
                            subtitle: "A small bar at the top of the game for its first seconds, listing your profile and features (games launched with ember-run)."
                            checked: ember.globalGraphics.banner !== false
                            onToggled: (on) => { var g = JSON.parse(JSON.stringify(ember.globalGraphics)); g.banner = on; ember.setGraphics("", g) } }
                SwitchRow { width: parent.width; icon: "close"; title: "Close to tray"
                            subtitle: "Closing the window keeps Ember in the system tray."
                            checked: page.cfg.close_to_tray !== false; onToggled: (on) => ember.setSetting("close_to_tray", on) }
                LabeledSlider {
                    width: parent.width; label: "Sensor refresh"
                    hint: "How often the app reads sensors while open. Faster costs a little CPU."
                    from: 250; to: 2000; stepSize: 250; value: page.cfg.interval_ms
                    format: function(v) { return Math.round(v) + " ms" }
                    onMoved: (v) => ember.setSetting("interval_ms", Math.round(v))
                }
            }
        }
        Card {
            width: parent.width; height: sv.height + 48
            Column {
                id: sv
                x: 24; y: 24; width: parent.width - 48
                spacing: 8
                CardTitle { icon: "shield"; text: "Ember service"; bottomPadding: 8 }
                InfoRow { label: "Status"; value: ember.daemon.connected ? "Running" : "Not running" }
                InfoRow { label: "Permission"; value: ember.daemon.connected ? (ember.daemon.authorized ? "Can change settings" : "Read-only") : "—" }
                InfoRow { label: "Socket"; value: "/run/ember/emberd.sock"; mono: true }
                Row {
                    topPadding: 12; spacing: 8
                    Btn { text: ember.daemon.connected ? "Reinstall service" : "Install service"; icon: "download"
                          variant: ember.daemon.connected ? "outlined" : "filled"; onClicked: ember.installService() }
                    Btn { text: "Refresh"; icon: "refresh"; variant: "text"; onClicked: ember.refreshDaemon() }
                }
            }
        }
        Card {
            width: parent.width; height: up.height + 48
            readonly property var u: ember.updateInfo
            Column {
                id: up
                x: 24; y: 24; width: parent.width - 48
                spacing: 8
                readonly property var u: parent.u
                Item {
                    width: parent.width; height: 40
                    Row { spacing: 12; anchors.verticalCenter: parent.verticalCenter
                        CardTitle { icon: "download"; text: "Updates" } }
                    Row {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                        Btn { text: up.u.checking ? "Checking…" : "Check now"; icon: "refresh"; variant: "text"
                              enabled: !up.u.checking; onClicked: ember.checkUpdates() }
                        Btn { visible: up.u.restart_needed; text: "Restart Ember"; icon: "refresh"
                              onClicked: ember.restartNow() }
                        Btn { visible: up.u.available && up.u.kind === "local" && !up.u.restart_needed
                              text: up.u.busy ? "Updating…" : "Update to " + up.u.latest; icon: "download"
                              enabled: !up.u.busy; onClicked: ember.installUpdate() }
                    }
                }
                InfoRow { label: "This version"; value: up.u.current }
                InfoRow { label: "Latest release"; value: up.u.latest || (up.u.error ? "Couldn’t check" : "…") }
                InfoRow {
                    label: "Last checked"
                    value: {
                        var t = up.u.last_checked
                        if (!t) return "Not yet"
                        var d = Math.max(0, Date.now() / 1000 - t)
                        return d < 90 ? "Just now" : d < 3600 ? Math.round(d / 60) + " min ago"
                             : d < 86400 ? Math.round(d / 3600) + " h ago" : new Date(t * 1000).toLocaleString()
                    }
                }
                InfoRow { label: "Status"
                          value: up.u.rolled_back ? "Version " + up.u.rolled_back + " did not work here and was rolled back"
                               : up.u.restart_needed ? "Version " + up.u.installed + " installed. Restart to use it"
                               : up.u.busy ? (up.u.status === "downloading" ? "Downloading" : up.u.status === "installing" ? "Installing" : "Checking")
                               : up.u.status_error ? "Last update failed: " + up.u.status_error
                               : up.u.available ? "Update available"
                               : up.u.latest ? "Up to date" : "" }
                SwitchRow {
                    visible: up.u.kind === "local"
                    width: parent.width; icon: "download"
                    title: "Install updates automatically"
                    subtitle: "Every download must carry a valid signature from Ember’s release key before anything is installed. The service restarts on its own, and the app restarts the next time it’s in the tray."
                    checked: !!up.u.auto; enabled: ember.daemon.authorized
                    onToggled: (on) => ember.setAutoUpdate(on)
                }
                Item {
                    visible: up.u.kind === "local"
                    width: parent.width; height: 56
                    opacity: ember.daemon.authorized ? 1 : 0.4
                    IconBadge { id: ivb; icon: "timer"; anchors.verticalCenter: parent.verticalCenter }
                    Column {
                        anchors.left: ivb.right; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter
                        Label { text: "Check for updates"; role: "titleM" }
                        Label { text: "How often Ember looks for a new release."; role: "bodyS"; color: Theme.inkVariant }
                    }
                    Row {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                        Repeater {
                            model: [["daily", "Daily"], ["weekly", "Weekly"], ["monthly", "Monthly"]]
                            delegate: Chip { required property var modelData; text: modelData[1]
                                             selected: (up.u.interval || "daily") === modelData[0]
                                             enabled: ember.daemon.authorized
                                             onClicked: ember.setUpdateInterval(modelData[0]) }
                        }
                    }
                }
                Label {
                    visible: up.u.kind !== "local"; width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                    text: up.u.kind === "package" ? "Ember was installed by your package manager, which keeps it up to date."
                                                  : "Running from a source checkout: update with git pull, then run install.sh."
                }
                Item {
                    visible: up.u.kind === "local" && !!up.u.previous && up.u.previous !== up.u.installed
                    width: parent.width; height: 56
                    opacity: ember.daemon.authorized ? 1 : 0.4
                    IconBadge { id: rbb; icon: "reset"; anchors.verticalCenter: parent.verticalCenter }
                    Column {
                        anchors.left: rbb.right; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter
                        anchors.right: rbBtn.left; anchors.rightMargin: 16
                        Label { text: "Previous version kept: " + (up.u.previous || ""); role: "titleM" }
                        Label { width: parent.width; elide: Text.ElideRight; role: "bodyS"; color: Theme.inkVariant
                                text: "If an update breaks the service or the app, Ember goes back to it on its own. You can also go back by hand." }
                    }
                    Btn { id: rbBtn; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                          text: "Roll back"; icon: "reset"; variant: "outlined"; enabled: ember.daemon.authorized
                          onClicked: ember.rollbackUpdate() }
                }
                Btn { text: "Release notes"; variant: "text"; icon: "link"; onClicked: ember.openUrl(up.u.url) }
            }
        }
        Card {
            width: parent.width; height: ab.height + 48
            Column {
                id: ab
                x: 24; y: 24; width: parent.width - 48
                spacing: 6
                CardTitle { icon: "info"; text: "About Ember" }
                Label { width: parent.width; wrapMode: Text.WordWrap; role: "body"; color: Theme.inkVariant
                        text: "An open-source GPU control center for AMD Radeon on Linux. Ember talks to the amdgpu kernel driver through its documented sysfs interface and to Mesa’s Vulkan layers - the same open stack AMD and the community maintain. Not affiliated with AMD." }
            }
        }
    }
}
