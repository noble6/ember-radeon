import QtQuick
import "../components"

Flickable {
    id: page
    contentHeight: col.height + 64
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    Column {
        id: col
        x: 40; y: 36
        width: page.width - 80
        spacing: 16
        Item {
            width: parent.width; height: 64
            Column {
                Label { text: "Display"; role: "displayS"; emphasized: true }
                Label { text: "FreeSync, refresh rate, HDR and colour - applied live by the compositor."; role: "body"; color: Theme.inkVariant }
            }
            Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                  text: "Refresh"; icon: "refresh"; variant: "outlined"; onClicked: ember.refreshDisplays() }
        }
        Banner {
            width: parent.width
            visible: !ember.displayControl
            icon: "info"
            title: "Display control needs KDE Plasma"
            text: "On Wayland the compositor owns display settings. Ember drives KDE’s kscreen-doctor; on GNOME use Settings → Displays (VRR lives under ‘Variable Refresh Rate’)."
        }
        Repeater {
            model: ember.displays
            delegate: Card {
                id: dc
                required property var modelData
                readonly property var o: modelData
                readonly property var cur: o.current || {}
                readonly property var rates: o.modes.filter(function(m) { return m.w === dc.cur.w && m.h === dc.cur.h })
                readonly property var sizes: {
                    var seen = {}, out = []
                    for (var i = 0; i < o.modes.length; i++) {
                        var k = o.modes[i].w + "x" + o.modes[i].h
                        if (!seen[k]) { seen[k] = true; out.push(o.modes[i]) }
                    }
                    return out.slice(0, 8)
                }
                width: col.width; height: dcol.height + 48
                function bestRate(w, h) {
                    var best = null
                    for (var i = 0; i < o.modes.length; i++) {
                        var m = o.modes[i]
                        if (m.w === w && m.h === h && (!best || m.hz > best.hz)) best = m
                    }
                    return best
                }
                Column {
                    id: dcol
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 6
                    Item {
                        width: parent.width; height: 56
                        Row {
                            spacing: 14; anchors.verticalCenter: parent.verticalCenter
                            Rectangle { width: 48; height: 48; radius: 14; color: Theme.primaryContainer
                                        Icon { anchors.centerIn: parent; name: "monitor"; size: 26; color: Theme.primary } }
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                Label { text: dc.o.model; role: "titleL"; emphasized: true }
                                Label { text: dc.o.name + "  ·  " + dc.cur.w + "×" + dc.cur.h + " @ " + Math.round(dc.cur.hz) + " Hz"
                                              + (dc.o.vrange ? "  ·  FreeSync range " + dc.o.vrange[0] + "–" + dc.o.vrange[1] + " Hz" : "")
                                        role: "body"; color: Theme.inkVariant }
                            }
                        }
                    }
                    Item {
                        width: parent.width; height: 72
                        Rectangle { id: ic; width: 40; height: 40; radius: 12; anchors.verticalCenter: parent.verticalCenter
                                    color: dc.o.vrr !== "never" ? Theme.primaryContainer : Theme.surfaceContainerHighest
                                    Icon { anchors.centerIn: parent; name: "sync"; size: 22; color: dc.o.vrr !== "never" ? Theme.primary : Theme.inkVariant } }
                        Column {
                            anchors.left: ic.right; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 520
                            Label { text: "FreeSync (variable refresh rate)"; role: "titleM" }
                            Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                                    text: dc.o.vrr === "never" ? (dc.o.vrange ? "Off - your monitor supports " + dc.o.vrange[0] + "–" + dc.o.vrange[1] + " Hz. Turn it on for tear-free, low-latency games."
                                                                              : "Off.")
                                          : dc.o.vrr === "automatic" ? "On for fullscreen games - the recommended setting." : "Always on, desktop included." }
                        }
                        ButtonGroup {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: 420; itemHeight: 40
                            model: [{ key: "never", label: "Off" }, { key: "automatic", label: "Games" }, { key: "always", label: "Always" }]
                            current: dc.o.vrr
                            onPicked: (k) => ember.setDisplay(dc.o.name, "vrrpolicy", k)
                        }
                    }
                    Label { text: "Refresh rate"; role: "titleS"; color: Theme.inkVariant; topPadding: 8 }
                    Flow {
                        width: parent.width; spacing: 8
                        Repeater {
                            model: dc.rates
                            delegate: Chip { required property var modelData; text: Math.round(modelData.hz * 100) / 100 + " Hz"
                                             selected: modelData.id === dc.cur.id
                                             onClicked: ember.setDisplay(dc.o.name, "mode", modelData.id) }
                        }
                    }
                    Label { text: "Resolution"; role: "titleS"; color: Theme.inkVariant; topPadding: 8 }
                    Flow {
                        width: parent.width; spacing: 8
                        Repeater {
                            model: dc.sizes
                            delegate: Chip { required property var modelData; text: modelData.w + "×" + modelData.h
                                             selected: modelData.w === dc.cur.w && modelData.h === dc.cur.h
                                             onClicked: { var b = dc.bestRate(modelData.w, modelData.h); if (b) ember.setDisplay(dc.o.name, "mode", b.id) } }
                        }
                    }
                    Item { width: 1; height: 8 }
                    SwitchRow { width: parent.width; icon: "light"; title: "HDR"
                                subtitle: "High dynamic range output. Needs an HDR-capable monitor; games also need HDR enabled per game."
                                checked: dc.o.hdr; onToggled: (on) => ember.setDisplay(dc.o.name, "hdr", on ? "enable" : "disable") }
                    SwitchRow { width: parent.width; icon: "palette"; title: "Wide colour gamut"
                                subtitle: "Use the panel’s full colour space instead of sRGB."
                                checked: dc.o.wcg; onToggled: (on) => ember.setDisplay(dc.o.name, "wcg", on ? "enable" : "disable") }
                    Item {
                        width: parent.width; height: 64
                        Label { text: "Colour depth"; role: "titleM"; anchors.verticalCenter: parent.verticalCenter; x: 56 }
                        ButtonGroup {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: 360; itemHeight: 36
                            model: [{ key: "0", label: "Auto" }, { key: "8", label: "8 bpc" }, { key: "10", label: "10 bpc" }, { key: "12", label: "12 bpc" }]
                            current: String(dc.o.max_bpc)
                            onPicked: (k) => ember.setDisplay(dc.o.name, "maxbpc", k)
                        }
                    }
                    Item {
                        width: parent.width; height: 64
                        Label { text: "RGB range"; role: "titleM"; anchors.verticalCenter: parent.verticalCenter; x: 56 }
                        ButtonGroup {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: 360; itemHeight: 36
                            model: [{ key: "automatic", label: "Auto" }, { key: "full", label: "Full" }, { key: "limited", label: "Limited" }]
                            current: dc.o.rgb
                            onPicked: (k) => ember.setDisplay(dc.o.name, "rgbrange", k)
                        }
                    }
                    LabeledSlider {
                        visible: dc.o.ddc && !dc.o.hdr
                        width: parent.width; label: "Monitor brightness"
                        hint: "Sets the monitor’s own backlight over DDC/CI."
                        from: 0; to: 100; stepSize: 5; value: brightTimer.running ? brightTimer.v : dc.o.brightness
                        format: function(v) { return Math.round(v) + "%" }
                        onMoved: (v) => brightTimer.restartWith(Math.round(v))
                        Timer { id: brightTimer; interval: 250; property int v: 0
                                function restartWith(x) { v = x; restart() }
                                onTriggered: ember.setDisplay(dc.o.name, "brightness", String(v)) }
                    }
                }
            }
        }
    }
}
