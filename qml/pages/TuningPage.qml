import QtQuick
import "../components"
import "Fmt.js" as F

Item {
    id: page
    readonly property var s: ember.snap
    readonly property var t: ember.tuning
    readonly property var st: ember.gpuState
    readonly property var profiles: st.profiles || {}
    readonly property bool can: ember.daemon.authorized
    readonly property var odControls: t.od_controls || []
    property string editing: ""
    property var draft: ember.defaultSettings()
    property bool dirty: false
    property bool naming: false

    function pickInitial() {
        var names = ember.profileNames
        if (editing && profiles[editing]) return
        var rt = ember.runtime
        editing = rt && rt.applied && profiles[rt.applied] ? rt.applied : (names.length ? names[0] : "")
    }
    function load(name) {
        editing = name
        draft = profiles[name] ? F.clone(profiles[name]) : ember.defaultSettings()
        dirty = false
    }
    function edit(fn) { var d = F.clone(draft); fn(d); draft = d; dirty = true }
    onProfilesChanged: { pickInitial(); if (!dirty) load(editing) }
    Component.onCompleted: { pickInitial(); load(editing) }

    Flickable {
        id: fl
        anchors.fill: parent
        contentHeight: col.height + 140
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
                    Label { text: "Tuning"; role: "displayS"; emphasized: true }
                    Label { text: "Edit a profile, save it, and it’s applied immediately if it’s the active one."
                            role: "body"; color: Theme.inkVariant }
                }
                Row {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    Btn { text: "Restore built-ins"; icon: "reset"; variant: "text"; enabled: page.can
                          onClicked: ember.resetPresets() }
                    Btn { text: "Stock"; icon: "chip"; variant: "outlined"; enabled: page.can
                          onClicked: ember.resetStock() }
                }
            }

            ServiceBanner { width: parent.width }

            // profile picker
            Flow {
                width: parent.width
                spacing: 8
                Repeater {
                    model: ember.profileNames
                    delegate: Chip {
                        required property string modelData
                        text: modelData + (ember.runtime.applied === modelData ? "  ●" : "")
                        icon: F.profileIcon(modelData)
                        selected: page.editing === modelData
                        onClicked: page.load(modelData)
                    }
                }
                Chip { text: "New profile"; icon: "add"; visible: !page.naming; enabled: page.can
                       onClicked: { page.naming = true; nameBox.text = ""; nameBox.forceActiveFocus() } }
                Row {
                    visible: page.naming
                    spacing: 8
                    TextBox { id: nameBox; width: 220; height: 36; placeholder: "Profile name"
                              onAccepted: createBtn.clicked() }
                    Btn { id: createBtn; text: "Create"; size: 36
                          onClicked: {
                              var n = nameBox.text.trim()
                              if (!n) return
                              ember.saveProfile(n, page.draft, false)
                              page.editing = n; page.dirty = false; page.naming = false
                          } }
                    Btn { text: "Cancel"; variant: "text"; size: 36; onClicked: page.naming = false }
                }
            }

            // -------- performance
            Card {
                width: parent.width; height: perf.height + 48
                Column {
                    id: perf
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 16
                    Row { spacing: 12
                        CardTitle { icon: "speed"; text: "Performance" } }
                    Label { text: "Clock behaviour"; role: "titleS"; color: Theme.inkVariant }
                    ButtonGroup {
                        width: Math.min(parent.width, 640); itemHeight: 44
                        model: [{ key: "auto", label: "Auto" }, { key: "low", label: "Lowest clocks" },
                                { key: "high", label: "Highest clocks" }, { key: "manual", label: "Manual" }]
                        current: page.draft.perf_level
                        onPicked: (k) => page.edit(function(d) { d.perf_level = k })
                    }
                    Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                            text: page.draft.perf_level === "high" ? "Pins the GPU at its top power state - lowest latency, highest idle power."
                                : page.draft.perf_level === "low" ? "Pins the GPU at its lowest state. Good for battery-like quiet; games will crawl."
                                : page.draft.perf_level === "manual" ? "Lets the workload profile below fully steer the power management firmware."
                                : "The driver picks clocks on demand. Best for almost everyone." }
                    Label { text: "Workload profile"; role: "titleS"; color: Theme.inkVariant }
                    Flow {
                        width: parent.width; spacing: 8
                        Repeater {
                            model: page.t.power_profiles || []
                            delegate: Chip {
                                required property var modelData
                                text: F.profileLabel(modelData.name)
                                selected: (page.draft.power_profile === null || page.draft.power_profile === undefined)
                                          ? modelData.name === "BOOTUP_DEFAULT" : page.draft.power_profile === modelData.index
                                onClicked: page.edit(function(d) { d.power_profile = modelData.name === "BOOTUP_DEFAULT" ? null : modelData.index })
                            }
                        }
                    }
                }
            }

            // -------- power
            Card {
                width: parent.width; height: pw.height + 48
                visible: !!ember.gpu.caps && ember.gpu.caps.power_cap
                Column {
                    id: pw
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 12
                    SwitchRow {
                        width: parent.width; icon: "bolt"
                        title: "Custom power limit"
                        subtitle: "Board allows " + F.num(page.t.power_cap.min) + "–" + F.num(page.t.power_cap.max)
                                  + " W (default " + F.num(page.t.power_cap.default) + " W). Lower = cooler and quieter; higher = more sustained boost."
                        checked: page.draft.power_cap_w !== null && page.draft.power_cap_w !== undefined
                        onToggled: (on) => page.edit(function(d) { d.power_cap_w = on ? page.t.power_cap.default : null })
                    }
                    LabeledSlider {
                        width: parent.width
                        visible: page.draft.power_cap_w !== null && page.draft.power_cap_w !== undefined
                        label: "Power limit"
                        from: page.t.power_cap.min || 0; to: page.t.power_cap.max || 100; stepSize: 1
                        stockValue: page.t.power_cap.default || NaN
                        value: page.draft.power_cap_w || 0
                        format: function(v) { return Math.round(v) + " W" }
                        onMoved: (v) => page.edit(function(d) { d.power_cap_w = v })
                    }
                }
            }

            // -------- fan
            Card {
                width: parent.width; height: fan.height + 48
                visible: !!ember.gpu.caps && (ember.gpu.caps.fan_pwm || ember.gpu.caps.fan_curve_fw)
                Column {
                    id: fan
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 16
                    Item {
                        width: parent.width; height: 32
                        Row { spacing: 12
                            CardTitle { icon: "fan"; text: "Fan" } }
                        Label { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                text: "Now " + F.num(page.s.fan_rpm) + " RPM · " + F.num(page.s.fan_pct) + "%"
                                role: "labelL"; color: Theme.inkVariant }
                    }
                    ButtonGroup {
                        width: Math.min(parent.width, 520); itemHeight: 44
                        model: [{ key: "auto", label: "Firmware" }, { key: "curve", label: "Custom curve" }, { key: "fixed", label: "Fixed speed" }]
                        current: page.draft.fan.mode
                        onPicked: (k) => page.edit(function(d) { d.fan.mode = k })
                    }
                    Label { visible: page.draft.fan.mode === "auto"; width: parent.width; wrapMode: Text.WordWrap
                            role: "bodyS"; color: Theme.inkVariant
                            text: "The card’s own fan table, including zero-RPM at idle. Ember doesn’t touch the fan." }
                    LabeledSlider {
                        visible: page.draft.fan.mode === "fixed"
                        width: parent.width; label: "Fan speed"
                        from: 0; to: 100; value: page.draft.fan.fixed_pct
                        format: function(v) { return Math.round(v) + "%" }
                        onMoved: (v) => page.edit(function(d) { d.fan.fixed_pct = Math.round(v) })
                    }
                    FanCurve {
                        visible: page.draft.fan.mode === "curve"
                        width: parent.width; height: 300
                        curve: page.draft.fan.curve
                        currentTemp: page.s["temp_" + page.draft.fan.sensor] || NaN
                        currentPct: page.s.fan_pct === null || page.s.fan_pct === undefined ? NaN : page.s.fan_pct
                        onEdited: (c) => page.edit(function(d) { d.fan.curve = c })
                    }
                    Item {
                        visible: page.draft.fan.mode === "curve"
                        width: parent.width; height: 40
                        Row {
                            spacing: 8; anchors.verticalCenter: parent.verticalCenter
                            Label { text: "Follow"; role: "labelL"; color: Theme.inkVariant; anchors.verticalCenter: parent.verticalCenter }
                            Repeater {
                                model: [{ k: "junction", l: "Hotspot" }, { k: "edge", l: "Edge" }, { k: "mem", l: "Memory" }]
                                delegate: Chip { required property var modelData; text: modelData.l
                                                 selected: page.draft.fan.sensor === modelData.k
                                                 onClicked: page.edit(function(d) { d.fan.sensor = modelData.k }) }
                            }
                        }
                        Label { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                text: "Drag points · double-click to add · right-click to remove"; role: "bodyS"; color: Theme.inkVariant }
                    }
                    LabeledSlider {
                        visible: page.draft.fan.mode === "curve"
                        width: Math.min(parent.width, 420); label: "Spin-down hysteresis"
                        hint: "Fans only slow down after the temperature drops this much, so they don’t pump up and down."
                        from: 0; to: 10; value: page.draft.fan.hysteresis
                        format: function(v) { return Math.round(v) + " °C" }
                        onMoved: (v) => page.edit(function(d) { d.fan.hysteresis = Math.round(v) })
                    }
                    Label { visible: page.draft.fan.mode !== "auto"; width: parent.width; wrapMode: Text.WordWrap
                            role: "bodyS"; color: Theme.inkVariant
                            text: "Safety: fans go to 100% within 5 °C of the hotspot limit whatever the curve says, and return to firmware control if the service stops." }
                }
            }

            // -------- overdrive
            Card {
                width: parent.width; height: od.height + 48
                Column {
                    id: od
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 16
                    Row { spacing: 12
                        CardTitle { icon: "rocket"; text: "Clocks & voltage" } }
                    Banner {
                        width: parent.width
                        visible: !page.t.od
                        icon: "lock"; tone: "info"
                        title: ember.system.overdrive_kernel ? "Overdrive is on in the kernel but not exposed for this GPU"
                                                             : "Overclocking and undervolting are locked by the kernel"
                        text: ember.system.overdrive_kernel ? "This GPU generation may not support pp_od_clk_voltage."
                              : "amdgpu hides clock and voltage controls unless <b>ppfeaturemask</b> has the overdrive bit. Ember can set it for you (adds a modprobe option and rebuilds the initramfs); it takes effect after a reboot. The kernel marks itself <i>tainted</i> while overdrive is on, which only matters when reporting kernel bugs."
                        action: ember.system.overdrive_kernel ? "" : "Enable overdrive…"
                        onTriggered: ember.enableOverdrive()
                    }
                    SwitchRow {
                        visible: page.odControls.length > 0
                        width: parent.width; icon: "tune"
                        title: "Custom clocks & voltage"
                        subtitle: (ember.gpu.arch || "") + " · Off = factory clocks. Start small: undervolting in 25 mV steps is the classic first move."
                        checked: !!page.draft.od
                        onToggled: (on) => page.edit(function(d) {
                            if (!on) { d.od = null; return }
                            d.od = {}
                            for (var i = 0; i < page.odControls.length; i++) d.od[page.odControls[i].key] = page.odControls[i].stock
                        })
                    }
                    Column {
                        visible: page.odControls.length > 0 && !!page.draft.od
                        width: parent.width; spacing: 20
                        Repeater {
                            model: page.odControls
                            delegate: LabeledSlider {
                                required property var modelData
                                width: parent.width
                                label: modelData.label; hint: modelData.hint
                                from: modelData.from; to: modelData.to; stepSize: modelData.step
                                stockValue: modelData.stock
                                value: page.draft.od && page.draft.od[modelData.key] !== undefined && page.draft.od[modelData.key] !== null
                                       ? page.draft.od[modelData.key] : modelData.stock
                                format: function(v) { return (modelData.key === "sclk_offset" && v > 0 ? "+" : "") + Math.round(v) + " " + modelData.unit }
                                onMoved: (v) => page.edit(function(d) { d.od[modelData.key] = Math.round(v) })
                            }
                        }
                    }
                }
            }

            // -------- firmware fan options (RDNA3+)
            Card {
                width: parent.width; height: fwc.height + 48
                visible: (page.t.fan_ctrl_info || []).length > 0
                Column {
                    id: fwc
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 16
                    Row { spacing: 12
                        CardTitle { icon: "fan"; text: "Fan firmware options" } }
                    Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                            text: "Settings the card’s own fan controller understands (RDNA3 and newer). They act when the fan is on Firmware mode." }
                    Repeater {
                        model: page.t.fan_ctrl_info || []
                        delegate: Item {
                            id: fo
                            required property var modelData
                            readonly property var cur: page.draft.fan.fw && page.draft.fan.fw[modelData.key] !== undefined
                                                       ? page.draft.fan.fw[modelData.key] : modelData.value
                            width: parent.width
                            height: modelData.key === "zero_rpm" ? zr.height : sl.height
                            function setv(v) { page.edit(function(d) { if (!d.fan.fw) d.fan.fw = {}; d.fan.fw[fo.modelData.key] = v }) }
                            SwitchRow { id: zr; visible: fo.modelData.key === "zero_rpm"; width: parent.width; icon: "moon"
                                        title: "Zero RPM"; subtitle: "Let the fans stop completely at low temperatures."
                                        checked: !!fo.cur; onToggled: (on) => fo.setv(on ? 1 : 0) }
                            LabeledSlider { id: sl; visible: fo.modelData.key !== "zero_rpm"; width: parent.width
                                            label: fo.modelData.label
                                            from: fo.modelData.range ? fo.modelData.range[0] : 0
                                            to: fo.modelData.range ? fo.modelData.range[1] : 100
                                            value: fo.cur; stockValue: fo.modelData.value
                                            format: function(v) { return Math.round(v) + (fo.modelData.key.indexOf("temp") >= 0 ? " °C"
                                                                   : fo.modelData.key === "min_pwm" ? " %" : " RPM") }
                                            onMoved: (v) => fo.setv(Math.round(v)) }
                        }
                    }
                }
            }

            // -------- startup
            Card {
                width: parent.width; height: boot.height + 32
                SwitchRow {
                    id: boot
                    x: 24; y: 16; width: parent.width - 48
                    icon: "power"
                    title: "Apply the active profile at boot"
                    subtitle: "If a boot with custom clocks doesn’t survive 90 seconds, the next boot skips them automatically."
                    checked: !!page.st.apply_on_boot
                    enabled: page.can
                    onToggled: (on) => ember.setApplyOnBoot(on)
                }
            }
        }
    }

    // sticky action bar
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: page.editing ? 24 : -100
        Behavior on anchors.bottomMargin { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
        width: bar.implicitWidth + 32; height: 72; radius: 36
        color: Theme.surfaceContainerHighest
        border.width: page.dirty ? 2 : 0; border.color: Theme.primary
        Row {
            id: bar
            anchors.centerIn: parent
            spacing: 10
            Column {
                anchors.verticalCenter: parent.verticalCenter
                leftPadding: 12; rightPadding: 12
                Label { text: page.editing; role: "titleM"; emphasized: true }
                Label { text: page.dirty ? "Unsaved changes" : (ember.runtime.applied === page.editing ? "Active" : "Saved")
                        role: "labelS"; color: page.dirty ? Theme.primary : Theme.inkVariant }
            }
            Btn { text: "Delete"; icon: "delete"; variant: "text"; enabled: page.can
                  anchors.verticalCenter: parent.verticalCenter
                  onClicked: { ember.deleteProfile(page.editing); page.editing = "" } }
            Btn { text: "Discard"; variant: "outlined"; visible: page.dirty; anchors.verticalCenter: parent.verticalCenter
                  onClicked: page.load(page.editing) }
            Btn { text: "Save"; variant: "tonal"; enabled: page.can && page.dirty; anchors.verticalCenter: parent.verticalCenter
                  onClicked: { ember.saveProfile(page.editing, page.draft, false); page.dirty = false } }
            Btn { text: ember.runtime.applied === page.editing ? "Save & apply" : "Save & activate"; icon: "check"
                  enabled: page.can && (page.dirty || ember.runtime.applied !== page.editing)
                  anchors.verticalCenter: parent.verticalCenter
                  onClicked: { ember.saveProfile(page.editing, page.draft, true); page.dirty = false } }
        }
    }
}
