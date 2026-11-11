import QtQuick
import "../components"
import "Fmt.js" as F

Flickable {
    id: page
    WheelScroll { view: page }
    contentHeight: col.height + 64
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    readonly property var s: ember.snap
    readonly property var h: ember.history
    readonly property color c2: Theme.mix(Theme.primary, "#FF8A00", 0.6)
    readonly property color c3: Theme.mix(Theme.primary, "#00B8D4", 0.8)

    Column {
        id: col
        x: 40; y: 36
        width: page.width - 80
        spacing: 16
        Item {
            width: parent.width; height: 64
            Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                  text: ember.logPath ? "Stop recording" : "Record to CSV"; icon: ember.logPath ? "close" : "save"
                  variant: ember.logPath ? "filled" : "outlined"; onClicked: ember.toggleLogging() }
            Column {
                Label { text: "Metrics"; role: "displayS"; emphasized: true }
                Label { text: "Last " + Math.round(120 * ember.settings.interval_ms / 1000) + " seconds · sampled every "
                              + ember.settings.interval_ms + " ms"; role: "body"; color: Theme.inkVariant }
            }
        }
        Grid {
            width: parent.width
            columns: 2; spacing: 16
            readonly property real cw: (width - spacing) / 2
            ChartCard {
                width: parent.cw; title: "Clocks"
                value: (page.s.gfx_mhz || 0) < 1 ? "Idle" : F.num(page.s.gfx_mhz); unit: (page.s.gfx_mhz || 0) < 1 ? "" : "MHz"
                autoFloor: 1000
                series: [{ data: page.h.gfx_mhz, color: Theme.primary, label: "GPU", now: F.num(page.s.gfx_mhz) + " MHz" },
                         { data: page.h.mem_mhz, color: page.c2, label: "Memory", now: F.num(page.s.mem_mhz) + " MHz" }]
            }
            ChartCard {
                width: parent.cw; title: "Temperatures"
                value: F.num(page.s.temp_junction); unit: "°C"
                minY: 20; maxY: 110
                series: [{ data: page.h.temp_junction, color: Theme.heat(page.s.temp_junction || 0), label: "Hotspot", now: F.num(page.s.temp_junction) + "°" },
                         { data: page.h.temp_edge, color: page.c3, label: "Edge", now: F.num(page.s.temp_edge) + "°" },
                         { data: page.h.temp_mem, color: page.c2, label: "Memory", now: F.num(page.s.temp_mem) + "°" }]
            }
            ChartCard {
                width: parent.cw; title: "Board power"
                value: F.num(page.s.power_w); unit: "W"
                minY: 0; maxY: Math.max(10, (page.s.power_cap_w || 100) * 1.05)
                series: [{ data: page.h.power_w, color: Theme.primary, label: "Draw", now: F.num(page.s.power_w) + " W" },
                         { data: page.h.power_cap_w, color: Theme.outline, label: "Limit", now: F.num(page.s.power_cap_w) + " W" }]
            }
            ChartCard {
                width: parent.cw; title: "Activity"
                value: F.num(page.s.busy); unit: "%"
                minY: 0; maxY: 100
                series: [{ data: page.h.busy, color: Theme.primary, label: "Graphics", now: F.num(page.s.busy) + "%" },
                         { data: page.h.mem_busy, color: page.c2, label: "Memory controller", now: F.num(page.s.mem_busy) + "%" },
                         { data: page.h.vram_pct, color: page.c3, label: "VRAM used", now: F.gib(page.s.vram_used) + " GB" }]
            }
            ChartCard {
                width: parent.cw; title: "Fan"
                value: F.num(page.s.fan_rpm); unit: "RPM"
                minY: 0; maxY: page.s.fan_max_rpm || NaN
                series: [{ data: page.h.fan_rpm, color: page.c3, label: "Speed" }]
            }
            Card {
                width: parent.cw; height: 260; radius: 28
                Column {
                    anchors.fill: parent; anchors.margins: 24
                    spacing: 0
                    Label { text: "Sensors"; role: "titleM"; emphasized: true; bottomPadding: 6 }
                    InfoRow { label: "Core voltage"; value: F.num(page.s.vddgfx_mv) + " mV" }
                    InfoRow { label: "VR (GFX) temperature"; value: page.s.temp_vrgfx !== null && page.s.temp_vrgfx !== undefined ? F.num(page.s.temp_vrgfx) + " °C" : "—" }
                    InfoRow { label: "PCIe link"; value: page.s.pcie }
                    InfoRow { label: "Performance level"; value: page.s.perf_level }
                    InfoRow { label: "Throttling"; value: page.s.throttle && page.s.throttle.length ? page.s.throttle.join(", ") : "None" }
                }
            }
        }
        // per-app usage
        Card {
            width: parent.width; height: apps.height + 48; radius: 28
            Column {
                id: apps
                x: 24; y: 24; width: parent.width - 48
                spacing: 4
                Item {
                    width: parent.width; height: 32
                    Label { text: "Apps using the GPU"; role: "titleM"; emphasized: true; anchors.verticalCenter: parent.verticalCenter }
                    Label { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            text: "from DRM fdinfo · your own processes"; role: "bodyS"; color: Theme.inkVariant }
                }
                Repeater {
                    model: ember.processes
                    delegate: Item {
                        required property var modelData
                        width: parent.width; height: 40
                        Label { text: modelData.name; role: "body"; emphasized: true; width: parent.width * 0.3; elide: Text.ElideRight
                                anchors.verticalCenter: parent.verticalCenter }
                        Rectangle {
                            x: parent.width * 0.32; width: parent.width * 0.36; height: 8; radius: 4
                            anchors.verticalCenter: parent.verticalCenter
                            color: Theme.surfaceContainerHighest
                            Rectangle { width: parent.width * Math.min(1, (modelData.gpu_pct || 0) / 100); height: 8; radius: 4; color: Theme.primary
                                        Behavior on width { NumberAnimation { duration: 400 } } }
                        }
                        Label { x: parent.width * 0.70; width: parent.width * 0.1; horizontalAlignment: Text.AlignRight
                                text: modelData.gpu_pct === null || modelData.gpu_pct === undefined ? "…" : modelData.gpu_pct.toFixed(1) + "%"
                                role: "body"; anchors.verticalCenter: parent.verticalCenter; font.features: { "tnum": 1 } }
                        Label { anchors.right: parent.right; width: parent.width * 0.18; horizontalAlignment: Text.AlignRight
                                text: Math.round(modelData.vram_mb) + " MB" + (modelData.media ? "  ·  video" : "")
                                role: "body"; color: Theme.inkVariant; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
                Label { visible: ember.processes.length === 0; text: "Nothing is using the GPU right now."; role: "body"; color: Theme.inkVariant }
            }
        }

        // DPM states
        Card {
            width: parent.width; height: dpm.height + 48; radius: 28
            Column {
                id: dpm
                x: 24; y: 24; width: parent.width - 48
                spacing: 12
                Label { text: "Power states"; role: "titleM"; emphasized: true }
                Repeater {
                    model: [{ name: "GPU", levels: ember.tuning.sclk_levels || [] },
                            { name: "Memory", levels: ember.tuning.mclk_levels || [] }]
                    delegate: Row {
                        required property var modelData
                        spacing: 8
                        Label { text: modelData.name; role: "labelL"; color: Theme.inkVariant; width: 80; anchors.verticalCenter: parent.verticalCenter }
                        Repeater {
                            model: modelData.levels
                            delegate: Rectangle {
                                required property var modelData
                                height: 32; radius: 16; width: lt.implicitWidth + 24
                                color: modelData.active ? Theme.primary : Theme.surfaceContainerHighest
                                Label { id: lt; anchors.centerIn: parent; text: modelData.label; role: "labelL"
                                        color: modelData.active ? Theme.inkPrimary : Theme.inkVariant }
                            }
                        }
                    }
                }
                Label { text: "Snapshot from when the page last refreshed - states change hundreds of times a second."
                        role: "bodyS"; color: Theme.inkVariant }
            }
        }
    }
}
