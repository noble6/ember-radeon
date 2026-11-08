import QtQuick
import "../components"
import "Fmt.js" as F

Flickable {
    id: page
    signal navigate(int page)
    contentHeight: col.height + 64
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    readonly property var s: ember.snap
    readonly property var g: ember.gpu
    readonly property var st: ember.gpuState
    readonly property var rt: ember.runtime
    readonly property string applied: rt && rt.applied ? rt.applied : ""
    readonly property real sclkMax: {
        var od = ember.tuning.od
        if (od && od.ranges && od.ranges.SCLK) return od.ranges.SCLK[1]
        var lv = ember.tuning.sclk_levels || []
        return lv.length ? lv[lv.length - 1].mhz * 1.05 : 3000
    }

    Column {
        id: col
        x: 40; y: 36
        width: page.width - 80
        spacing: 24

        // header
        Item {
            width: parent.width; height: 92
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Label { text: page.g.name || "No AMD GPU found"; role: "displayS"; emphasized: true }
                Label {
                    text: [page.g.arch, page.g.board, F.gib(page.g.vram_total) + " GB " + (page.g.vram_vendor || ""),
                           page.g.rebar ? "Smart Access Memory on" : "",
                           ember.system.mesa ? "Mesa " + ember.system.mesa : ""].filter(function(x) { return x }).join("  ·  ")
                    role: "bodyL"; color: Theme.inkVariant
                }
            }
            Rectangle {
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                height: 56; radius: 28
                width: stRow.implicitWidth + 40
                color: Theme.surfaceContainerHigh
                Row {
                    id: stRow
                    anchors.centerIn: parent; spacing: 12
                    Rectangle { width: 12; height: 12; radius: 6; anchors.verticalCenter: parent.verticalCenter
                                color: page.applied ? Theme.primary : Theme.outline }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        Label { text: page.applied || "Stock"; role: "titleM"; emphasized: true }
                        Label { text: page.rt && page.rt.reason === "game" ? "Auto-switched for " + page.rt.game
                                     : page.applied ? "Active profile" : "Driver defaults"
                                role: "labelS"; color: Theme.inkVariant }
                    }
                }
            }
        }

        Row {
            visible: ember.gpus.length > 1
            spacing: 8
            Repeater {
                model: ember.gpus
                delegate: Chip { required property var modelData; text: modelData.name + (modelData.apu ? " (integrated)" : "")
                                 icon: "chip"; selected: modelData.index === ember.gpuIndex
                                 onClicked: ember.selectGpu(modelData.index) }
            }
        }

        ServiceBanner { width: parent.width }

        Banner {
            width: parent.width
            visible: !!ember.updateInfo.restart_needed
            icon: "download"; title: "Ember " + ember.updateInfo.installed + " is installed"
            text: "Restart the app to use the new version. The service is already updated."
            action: "Restart"; onTriggered: ember.restartNow()
        }
        Banner {
            width: parent.width
            visible: !!ember.updateInfo.available && !ember.updateInfo.restart_needed && !ember.updateInfo.auto
                     && ember.updateInfo.kind === "local"
            icon: "download"; title: "Ember " + ember.updateInfo.latest + " is available"
            text: "Automatic updates are off."
            action: "Update"; onTriggered: ember.installUpdate()
        }

        // now playing
        Repeater {
            model: ember.playing
            delegate: Card {
                id: npc
                required property var modelData
                width: col.width; height: 112; radius: 28
                color: Theme.alpha(Theme.good, 0.10)
                border.width: 1; border.color: Theme.alpha(Theme.good, 0.4)
                RoundedImage { id: npi; x: 16; anchors.verticalCenter: parent.verticalCenter; width: 120; height: 80; radius: 16
                               source: npc.modelData.header ? "file://" + npc.modelData.header : "" }
                Column {
                    anchors.left: npi.right; anchors.leftMargin: 20; anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right; anchors.rightMargin: 24
                    spacing: 2
                    Row {
                        spacing: 8
                        Rectangle { width: 10; height: 10; radius: 5; color: Theme.good; anchors.verticalCenter: parent.verticalCenter
                                    SequentialAnimation on opacity { loops: Animation.Infinite
                                        NumberAnimation { to: 0.25; duration: 700 } NumberAnimation { to: 1; duration: 700 } } }
                        Label { text: "NOW PLAYING · EMBER ACTIVE"; role: "labelL"; emphasized: true; color: Theme.good }
                    }
                    Label { text: npc.modelData.name; role: "titleL"; emphasized: true; width: parent.width; elide: Text.ElideRight }
                    Label {
                        width: parent.width; elide: Text.ElideRight; role: "body"; color: Theme.inkVariant
                        text: (page.applied || "Stock") + " profile"
                              + (page.rt && page.rt.reason === "game" ? " (switched automatically)" : "")
                              + (npc.modelData.wired ? " · graphics features on" : " · launch through ember-run for graphics features")
                    }
                }
            }
        }

        // gauges
        Card {
            width: parent.width; height: 300
            radius: 32
            Row {
                anchors.centerIn: parent
                spacing: (parent.width - 4 * 220) / 5
                Gauge {
                    width: 220; height: 220
                    value: page.s.gfx_mhz || 0; to: page.sclkMax
                    text: (page.s.gfx_mhz || 0) < 1 ? "Idle" : F.num(page.s.gfx_mhz)
                    unit: (page.s.gfx_mhz || 0) < 1 ? "" : "MHz"; label: "GPU clock"
                    sub: "Load " + F.num(page.s.busy) + "%"
                }
                Gauge {
                    width: 220; height: 220
                    value: page.s.temp_junction || 0; from: 20; to: 110
                    unit: "°C"; label: "Hotspot"
                    color: Theme.heat(page.s.temp_junction || 0)
                    sub: "Edge " + F.num(page.s.temp_edge) + "° · Mem " + F.num(page.s.temp_mem) + "°"
                }
                Gauge {
                    width: 220; height: 220
                    value: page.s.power_w || 0; to: page.s.power_cap_w || 200
                    unit: "W"; label: "Board power"
                    color: Theme.mix(Theme.primary, "#FF8A00", 0.5)
                    sub: "Limit " + F.num(page.s.power_cap_w) + " W"
                }
                Gauge {
                    readonly property bool hasFan: !!page.s.fan_max_rpm
                    width: 220; height: 220
                    value: hasFan ? (page.s.fan_rpm || 0) : (page.s.vram_pct || 0)
                    to: hasFan ? (page.s.fan_max_rpm || 3500) : 100
                    text: hasFan ? ((page.s.fan_rpm || 0) < 1 ? "0" : F.num(page.s.fan_rpm)) : F.num(page.s.vram_pct)
                    unit: hasFan ? "RPM" : "%"; label: hasFan ? "Fan" : "Graphics memory"
                    color: Theme.mix(Theme.primary, "#00B8D4", 0.75)
                    sub: hasFan ? ((page.s.fan_rpm || 0) < 1 ? "Zero RPM" : (page.s.fan_mode === "manual" ? "Ember curve" : "Firmware"))
                                : F.gib(page.s.vram_used) + " of " + F.gib(page.s.vram_total) + " GB"
                }
            }
        }

        // profiles
        SectionTitle { text: "Profiles"; sub: "One click. Edit them on the Tuning page; games can switch them automatically." }
        Flow {
            width: parent.width
            spacing: 12
            Repeater {
                model: ["Stock"].concat(ember.profileNames)
                delegate: Rectangle {
                    id: tile
                    required property string modelData
                    readonly property bool sel: (modelData === "Stock" && !page.applied) || modelData === page.applied
                    width: (col.width - 3 * 12) / 4; height: 104
                    radius: sel ? 28 : 20
                    Behavior on radius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
                    color: sel ? Theme.primary : Theme.surfaceContainer
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    opacity: ember.daemon.authorized ? 1 : 0.5
                    Rectangle { anchors.fill: parent; radius: parent.radius; color: Theme.ink; opacity: ma.containsMouse && !tile.sel ? 0.05 : 0 }
                    Icon { x: 20; y: 20; name: F.profileIcon(tile.modelData); size: 26
                           color: tile.sel ? Theme.inkPrimary : Theme.primary }
                    Column {
                        x: 20; anchors.bottom: parent.bottom; anchors.bottomMargin: 16
                        width: parent.width - 40
                        Label { text: tile.modelData; role: "titleM"; emphasized: true
                                color: tile.sel ? Theme.inkPrimary : Theme.ink; elide: Text.ElideRight; width: parent.width }
                        Label { text: F.profileBlurb(tile.modelData); role: "bodyS"; elide: Text.ElideRight; width: parent.width
                                color: tile.sel ? Theme.alpha(Theme.inkPrimary, 0.8) : Theme.inkVariant }
                    }
                    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                enabled: ember.daemon.authorized
                                onClicked: ember.activateProfile(tile.modelData === "Stock" ? "" : tile.modelData) }
                }
            }
        }

        // live tiles
        SectionTitle { text: "Live" }
        Grid {
            width: parent.width
            columns: 4
            spacing: 12
            readonly property real cw: (width - 3 * spacing) / 4
            StatTile { width: parent.cw; icon: "speed"; label: "GPU load"; value: F.num(page.s.busy); unit: "%"
                       points: ember.history.busy; maxY: 100 }
            StatTile { width: parent.cw; icon: "memory"; label: "VRAM"; value: F.gib(page.s.vram_used); unit: "GB"
                       sub: "of " + F.gib(page.s.vram_total) + " GB"; points: ember.history.vram_pct; maxY: 100
                       accent: Theme.mix(Theme.primary, "#7C4DFF", 0.7) }
            StatTile { width: parent.cw; icon: "bolt"; label: "Memory clock"; value: F.num(page.s.mem_mhz); unit: "MHz"
                       points: ember.history.mem_mhz; accent: Theme.mix(Theme.primary, "#FF8A00", 0.6) }
            StatTile { width: parent.cw; icon: "thermostat"; label: "Edge temp"; value: F.num(page.s.temp_edge); unit: "°C"
                       points: ember.history.temp_edge; accent: Theme.heat(page.s.temp_edge || 0); minY: 20; maxY: 110 }
        }

        Banner {
            width: parent.width
            visible: page.s.throttle && page.s.throttle.length > 0
            tone: "warn"; icon: "warning"
            title: "GPU is throttling"
            text: "Limited by: " + (page.s.throttle || []).join(", ")
        }
    }
}
