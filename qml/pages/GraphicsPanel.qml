import QtQuick
import "../components"

// Adrenalin-style graphics features, mapped to the open Linux stack.
Column {
    id: root
    property var gfx: ({})
    property bool locked: false
    signal changed(var gfx)
    readonly property var layers: ember.system.layers || {}
    readonly property string arch: ember.gpu.arch_key || ""
    readonly property bool fsr4Gpu: arch === "rdna2" || arch === "rdna3" || arch === "rdna4"
    spacing: 4
    function set(k, v) { var g = JSON.parse(JSON.stringify(gfx)); g[k] = v; changed(g) }

    component Group: Label { role: "labelL"; color: Theme.primary; topPadding: 14; bottomPadding: 2; emphasized: true }
    component Choice: Item {
        id: ch
        property string icon
        property string title
        property string badge: ""
        property var options: []
        property string current
        property bool active: current !== (options.length ? options[0].key : "")
        signal picked(string key)
        width: parent ? parent.width : 400; height: 64; opacity: root.locked ? 0.4 : 1
        Rectangle { id: ic; width: 40; height: 40; radius: 12; anchors.verticalCenter: parent.verticalCenter
                    color: ch.active ? Theme.primaryContainer : Theme.surfaceContainerHighest
                    Icon { anchors.centerIn: parent; name: ch.icon; size: 22; color: ch.active ? Theme.primary : Theme.inkVariant } }
        Column {
            anchors.left: ic.right; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter
            anchors.right: bg.left; anchors.rightMargin: 12
            Label { text: ch.title; role: "titleM"; width: parent.width; elide: Text.ElideRight }
            Label { visible: ch.badge !== ""; text: ch.badge; role: "labelS"; color: Theme.inkVariant
                    width: parent.width; elide: Text.ElideRight }
        }
        ButtonGroup {
            id: bg
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            width: Math.min(400, 92 * ch.options.length); itemHeight: 36; enabled: !root.locked
            model: ch.options; current: ch.current
            onPicked: (k) => ch.picked(k)
        }
    }

    // ---------------------------------------------------------------- one-click presets
    readonly property string preset: ember.graphicsPresetOf(gfx)
    Group { text: "ONE-CLICK PRESETS"; topPadding: 4 }
    Row {
        width: parent.width; spacing: 8
        opacity: root.locked ? 0.4 : 1
        Repeater {
            model: ember.graphicsPresets
            delegate: Rectangle {
                id: pt
                required property var modelData
                readonly property bool sel: root.preset === modelData.key
                width: (root.width - 3 * 8) / 4; height: 100
                radius: sel ? 24 : 16
                Behavior on radius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
                color: sel ? Theme.secondaryContainer : Theme.surfaceContainerHigh
                border.width: 1; border.color: sel ? Theme.alpha(Theme.primary, 0.5) : Theme.alpha(Theme.outlineVariant, 0.6)
                Behavior on color { ColorAnimation { duration: Theme.fast } }
                scale: pm.pressed ? 0.98 : 1
                Behavior on scale { NumberAnimation { duration: Theme.fast } }
                StateLayer { id: psl; radius: pt.radius; hovered: pm.containsMouse; pressed: pm.pressed }
                IconBadge { id: pi; x: 12; y: 12; size: 32; icon: pt.sel ? "check" : pt.modelData.icon; round: pt.sel }
                Label { anchors.left: pi.right; anchors.leftMargin: 10; anchors.verticalCenter: pi.verticalCenter
                        text: pt.modelData.label; role: "titleS"; emphasized: true
                        width: parent.width - 66; elide: Text.ElideRight }
                Label { x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; width: parent.width - 24
                        text: pt.modelData.blurb; role: "labelS"; color: Theme.inkVariant; elide: Text.ElideRight
                        wrapMode: Text.WordWrap; maximumLineCount: 2 }
                MouseArea { id: pm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            enabled: !root.locked
                            onPressed: (m) => psl.ripple(m.x, m.y)
                            onClicked: root.changed(ember.withGraphicsPreset(root.gfx, pt.modelData.key)) }
            }
        }
    }

    // ---------------------------------------------------------------- latency
    Group { text: "LATENCY & FRAME PACING" }
    SwitchRow {
        width: parent.width; icon: "timer"; enabled: !root.locked
        title: "Anti-Lag"; badge: root.layers.antilag ? "Mesa layer" : "not installed"
        subtitle: "Paces the CPU so frames aren’t queued ahead of the GPU - less input latency in GPU-bound Vulkan / DXVK games."
        checked: !!root.gfx.antilag; onToggled: (on) => root.set("antilag", on)
    }
    SwitchRow {
        width: parent.width; icon: "speed"; enabled: !root.locked
        title: "Frame rate target"; badge: "MangoHud"
        subtitle: "Caps FPS to cut power, heat and fan noise - like Radeon Chill’s ceiling."
        checked: (root.gfx.fps_cap || 0) > 0; onToggled: (on) => root.set("fps_cap", on ? 60 : 0)
    }
    LabeledSlider {
        visible: (root.gfx.fps_cap || 0) > 0
        width: parent.width - 56; x: 56; enabled: !root.locked
        label: "Target"; from: 30; to: 240; stepSize: 1; value: root.gfx.fps_cap || 60
        format: function(v) { return Math.round(v) + " FPS" }
        onMoved: (v) => root.set("fps_cap", Math.round(v))
    }
    Choice {
        icon: "sync"; title: "Vertical sync"; badge: "Enhanced = mailbox: no tearing, low latency"
        options: [{ key: "default", label: "App" }, { key: "fifo", label: "On" }, { key: "mailbox", label: "Enhanced" }, { key: "immediate", label: "Off" }]
        current: root.gfx.present_mode || "default"; onPicked: (k) => root.set("present_mode", k)
    }

    // ---------------------------------------------------------------- upscaling
    Group { text: "UPSCALING & FRAME GENERATION" }
    SwitchRow {
        width: parent.width; icon: "sparkle"; enabled: !root.locked && root.fsr4Gpu
        title: "FSR 4 (ML upscaling)"
        badge: !root.fsr4Gpu ? "needs RDNA 2 or newer" : "experimental · " + (root.layers.proton_fsr ? "Proton-GE / CachyOS" : "needs proton-cachyos or Proton-GE")
        subtitle: (root.arch === "rdna2" ? "Upgrades FSR 3.1 games to FSR 4. RX 6000 runs AMD’s INT8 model - sharper than FSR 3, roughly 10–20% slower."
                                         : "Upgrades games that ship FSR 3.1 to FSR 4’s machine-learning upscaler.")
                  + " Experimental: some games may crash, flicker or refuse to start - turn it off for that game if so."
        checked: !!root.gfx.fsr4; onToggled: (on) => root.set("fsr4", on)
    }
    SwitchRow {
        visible: !!root.gfx.fsr4
        width: parent.width - 56; x: 56; enabled: !root.locked
        title: "Show FSR 4 indicator"; subtitle: "Small watermark so you can confirm it’s really active."
        checked: !!root.gfx.fsr4_indicator; onToggled: (on) => root.set("fsr4_indicator", on)
    }
    SwitchRow {
        width: parent.width; icon: "upscale"; enabled: !root.locked
        title: "FSR 3 in any game"; badge: "experimental · " + (root.layers.proton_cachyos ? "OptiScaler · proton-cachyos" : "needs proton-cachyos (or GE-Proton 11)")
        subtitle: "Replaces DLSS or XeSS with FSR 3.1 - or FSR 4 when that’s on too - in games that never shipped FSR. Works on every Radeon. Experimental: injection can break some games or anti-cheat; never use it online with anti-cheat."
        checked: !!root.gfx.optiscaler; onToggled: (on) => root.set("optiscaler", on)
    }
    SwitchRow {
        width: parent.width - 56; x: 56; enabled: !root.locked
        title: "FSR 3 frame generation"; badge: "experimental · OptiScaler"
        subtitle: "Doubles the presented frame rate. Best above ~60 FPS base; pair it with Anti-Lag and VSync Off or FreeSync. Can add artifacts or stutter in some games."
        checked: !!root.gfx.opti_fg; onToggled: (on) => root.set("opti_fg", on)
    }
    SwitchRow {
        width: parent.width; icon: "rocket"; enabled: !root.locked && root.fsr4Gpu
        title: "FSR frame generation (Redstone)"; badge: "experimental · custom Proton"
        subtitle: "Swaps a game’s FSR 3.1 frame generation for the ML ‘Redstone’ model. Needs FSR 4 on and a game with FSR frame generation. Very new - expect issues in some games."
        checked: !!root.gfx.mlfg; onToggled: (on) => root.set("mlfg", on)
    }
    SwitchRow {
        width: parent.width; icon: "upscale"; enabled: !root.locked
        title: "Super Resolution for any game"; badge: root.layers.gamescope ? "gamescope" : "install gamescope"
        subtitle: "Like Radeon Super Resolution: the game renders at a lower resolution and gamescope upscales to your display. Above 100% = Virtual Super Resolution."
        checked: !!root.gfx.gamescope; onToggled: (on) => root.set("gamescope", on)
    }
    Column {
        visible: !!root.gfx.gamescope
        width: parent.width - 56; x: 56; spacing: 10
        Flow {
            width: parent.width; spacing: 8
            Repeater {
                model: [{ v: 50, l: "Performance 50%" }, { v: 59, l: "Balanced 59%" }, { v: 67, l: "Quality 67%" },
                        { v: 77, l: "Ultra Quality 77%" }, { v: 100, l: "Native" }, { v: 150, l: "VSR 150%" }, { v: 200, l: "VSR 200%" }]
                delegate: Chip { required property var modelData; text: modelData.l
                                 selected: (root.gfx.gs_scale || 77) === modelData.v; onClicked: root.set("gs_scale", modelData.v) }
            }
        }
        Flow {
            width: parent.width; spacing: 8
            Repeater {
                model: [{ k: "fsr", l: "FSR 1" }, { k: "nis", l: "NIS" }, { k: "integer", l: "Integer scaling" },
                        { k: "linear", l: "Bilinear" }, { k: "nearest", l: "Nearest" }]
                delegate: Chip { required property var modelData; text: modelData.l
                                 selected: (root.gfx.gs_filter || "fsr") === modelData.k; onClicked: root.set("gs_filter", modelData.k) }
            }
        }
        LabeledSlider {
            visible: root.gfx.gs_filter === "fsr" || root.gfx.gs_filter === "nis" || !root.gfx.gs_filter
            width: parent.width; label: "Upscaler sharpness"
            from: 0; to: 20; stepSize: 1; value: 20 - (root.gfx.gs_sharpness === undefined ? 2 : root.gfx.gs_sharpness)
            format: function(v) { return Math.round(v) + " / 20" }
            onMoved: (v) => root.set("gs_sharpness", 20 - Math.round(v))
        }
    }
    SwitchRow {
        width: parent.width; icon: "upscale"; enabled: !root.locked
        title: "FSR 1 in Proton"; badge: root.layers.proton_fsr ? "Proton-GE" : "needs Proton-GE"
        subtitle: "Pick a lower in-game fullscreen resolution and Wine upscales it with FSR 1. Lighter than gamescope, Proton-GE only."
        checked: !!root.gfx.fsr; onToggled: (on) => root.set("fsr", on)
    }
    LabeledSlider {
        visible: !!root.gfx.fsr
        width: parent.width - 56; x: 56; enabled: !root.locked
        label: "FSR sharpness"; from: 0; to: 5; stepSize: 1; value: 5 - (root.gfx.fsr_strength === undefined ? 2 : root.gfx.fsr_strength)
        format: function(v) { return Math.round(v) + " / 5" }
        onMoved: (v) => root.set("fsr_strength", 5 - Math.round(v))
    }

    // ---------------------------------------------------------------- image quality
    Group { text: "IMAGE QUALITY" }
    SwitchRow {
        width: parent.width; icon: "sparkle"; enabled: !root.locked
        title: "Image sharpening"; badge: root.layers.vkbasalt ? "FidelityFX CAS · vkBasalt" : "vkBasalt not installed"
        subtitle: "Contrast-adaptive sharpening on the final image. Toggle in-game with the Home key."
        checked: (root.gfx.sharpen || 0) > 0; onToggled: (on) => root.set("sharpen", on ? 50 : 0)
    }
    LabeledSlider {
        visible: (root.gfx.sharpen || 0) > 0
        width: parent.width - 56; x: 56; enabled: !root.locked
        label: "Sharpness"; from: 1; to: 100; value: root.gfx.sharpen || 0
        format: function(v) { return Math.round(v) + "%" }
        onMoved: (v) => root.set("sharpen", Math.round(v))
    }
    Choice {
        icon: "eye"; title: "Morphological anti-aliasing"; badge: "vkBasalt post-process"
        options: [{ key: "off", label: "Off" }, { key: "fxaa", label: "FXAA" }, { key: "smaa", label: "SMAA" }]
        current: root.gfx.aa || "off"; onPicked: (k) => root.set("aa", k)
    }
    Choice {
        icon: "tune"; title: "Anisotropic filtering"; badge: "Vulkan (RADV) override"
        options: [{ key: "0", label: "App" }, { key: "4", label: "4×" }, { key: "8", label: "8×" }, { key: "16", label: "16×" }]
        current: String(root.gfx.aniso || 0); onPicked: (k) => root.set("aniso", parseInt(k))
    }

    // ---------------------------------------------------------------- display & overlay
    Group { text: "DISPLAY & OVERLAY" }
    SwitchRow {
        width: parent.width; icon: "light"; enabled: !root.locked
        title: "HDR"; badge: "experimental"
        subtitle: root.gfx.gamescope ? "gamescope outputs HDR directly. Enable HDR for your display on the Display page."
                                     : "Runs Proton on its native Wayland driver with HDR output. Needs Proton 10+ and HDR on in Display."
        checked: !!root.gfx.hdr; onToggled: (on) => root.set("hdr", on)
    }
    Choice {
        icon: "chart"; title: "Performance overlay"; badge: "MangoHud · Shift+F12 toggles in game"
        options: [{ key: "off", label: "Off" }, { key: "minimal", label: "FPS" }, { key: "standard", label: "Standard" }, { key: "detailed", label: "Detailed" }]
        current: root.gfx.overlay || "off"; onPicked: (k) => root.set("overlay", k)
    }
}
