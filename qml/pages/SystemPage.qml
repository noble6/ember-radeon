import QtQuick
import "../components"
import "Fmt.js" as F

Flickable {
    id: page
    WheelScroll { view: page }
    contentHeight: col.height + 64
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    readonly property var g: ember.gpu
    readonly property var sy: ember.system
    readonly property var caps: g.caps || {}
    readonly property var layers: sy.layers || {}

    component Feature: Item {
        property string label
        property bool on
        property string note: ""
        width: parent ? parent.width : 300; height: 44
        Rectangle { id: dot; width: 24; height: 24; radius: 12; anchors.verticalCenter: parent.verticalCenter
                    color: parent.on ? Theme.alpha(Theme.good, 0.18) : Theme.surfaceContainerHighest
                    Icon { anchors.centerIn: parent; size: 16; name: parent.parent.on ? "check" : "close"
                           color: parent.parent.on ? Theme.good : Theme.inkVariant } }
        Label { anchors.left: dot.right; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                text: parent.label; role: "body" }
        Label { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                text: parent.note; role: "bodyS"; color: Theme.inkVariant }
    }

    Column {
        id: col
        x: 40; y: 36
        width: page.width - 80
        spacing: 16
        Item {
            width: parent.width; height: 64
            Column {
                Label { text: "System"; role: "displayS"; emphasized: true }
                Label { text: "Hardware, driver stack and what this machine supports."; role: "body"; color: Theme.inkVariant }
            }
            Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                  text: "Copy report"; icon: "copy"; variant: "tonal"; onClicked: ember.copy(ember.report()) }
        }
        Banner {
            width: parent.width
            visible: (page.sy.legacy_radeon || []).length > 0
            tone: "warn"; icon: "warning"
            title: "A Radeon card is using the old ‘radeon’ driver"
            text: "GCN 1/2 cards (HD 7000, R7/R9 200) can run on amdgpu for Vulkan and all of Ember’s controls. Add <b>radeon.si_support=0 amdgpu.si_support=1 radeon.cik_support=0 amdgpu.cik_support=1</b> to your kernel command line and reboot."
        }
        Row {
            width: parent.width; spacing: 16
            Card {
                width: (parent.width - 16) / 2; height: hw.height + 48
                Column {
                    id: hw
                    x: 24; y: 24; width: parent.width - 48
                    CardTitle { icon: "chip"; text: "Graphics card"; bottomPadding: 8 }
                    InfoRow { label: "Name"; value: page.g.name }
                    InfoRow { label: "Chip"; value: page.g.chip }
                    InfoRow { label: "Architecture"; value: page.g.arch }
                    InfoRow { label: "Board partner"; value: page.g.board }
                    InfoRow { label: "Device / revision"; value: (page.g.device_id || "") + " / " + (page.g.revision || ""); mono: true }
                    InfoRow { label: "Subsystem"; value: page.g.subsystem; mono: true }
                    InfoRow { label: "VBIOS"; value: page.g.vbios; mono: true }
                    InfoRow { label: "Video memory"; value: F.gib(page.g.vram_total) + " GB " + (page.g.vram_vendor || "") }
                    InfoRow { label: "Smart Access Memory (ReBAR)"; value: page.g.rebar ? "Enabled" : "Disabled - enable Above 4G decoding + ReBAR in BIOS" }
                    InfoRow { label: "PCIe link (now / max)"; value: (ember.snap.pcie || "?") + "  /  " + (page.g.pcie_max || "?") }
                    InfoRow { label: "PCI slot"; value: page.g.pci; mono: true }
                }
            }
            Card {
                width: (parent.width - 16) / 2; height: sw.height + 48
                Column {
                    id: sw
                    x: 24; y: 24; width: parent.width - 48
                    CardTitle { icon: "apps"; text: "Software"; bottomPadding: 8 }
                    InfoRow { label: "Operating system"; value: page.sy.os }
                    InfoRow { label: "Kernel"; value: page.sy.kernel }
                    InfoRow { label: "Session"; value: page.sy.session }
                    InfoRow { label: "Mesa"; value: page.sy.mesa }
                    InfoRow { label: "Vulkan"; value: page.sy.vk_api ? page.sy.vk_api + " · " + (page.sy.vk_driver || "").toUpperCase() : "" }
                    InfoRow { label: "OpenGL"; value: page.sy.gl_version }
                    InfoRow { label: "amdgpu DRM"; value: page.sy.drm }
                    InfoRow { label: "ppfeaturemask"; value: page.sy.ppfeaturemask; mono: true }
                    InfoRow { label: "Processor"; value: page.sy.cpu }
                    InfoRow { label: "Memory"; value: F.gib(page.sy.ram) + " GB" }
                }
            }
        }
        Row {
            width: parent.width; spacing: 16
            Card {
                width: (parent.width - 16) / 2; height: cp.height + 48
                Column {
                    id: cp
                    x: 24; y: 24; width: parent.width - 48
                    CardTitle { icon: "tune"; text: "Driver controls"; bottomPadding: 8 }
                    Feature { label: "Performance levels"; on: !!page.caps.perf_level }
                    Feature { label: "Workload profiles"; on: !!page.caps.power_profile }
                    Feature { label: "Power limit"; on: !!page.caps.power_cap }
                    Feature { label: "Fan control"; on: !!page.caps.fan_pwm || !!page.caps.fan_curve_fw
                              note: page.caps.fan_curve_fw ? "firmware curve" : page.caps.fan_pwm ? "PWM" : "" }
                    Feature { label: "Overclock & undervolt"; on: !!page.caps.overdrive
                              note: page.caps.overdrive ? "" : (page.sy.overdrive_kernel ? "unsupported" : "ppfeaturemask") }
                    Feature { label: "Detailed metrics (gpu_metrics)"; on: !!page.caps.gpu_metrics }
                    Feature { label: "Ember service"; on: !!ember.daemon.connected; note: ember.daemon.connected ? "" : "not installed" }
                }
            }
            Card {
                width: (parent.width - 16) / 2; height: ly.height + 48
                Column {
                    id: ly
                    x: 24; y: 24; width: parent.width - 48
                    CardTitle { icon: "game"; text: "Gaming layers"; bottomPadding: 8 }
                    Feature { label: "Anti-Lag (VK_LAYER_MESA_anti_lag)"; on: !!page.layers.antilag }
                    Feature { label: "Sharpening (vkBasalt)"; on: !!page.layers.vkbasalt; note: page.layers.vkbasalt ? "" : "pacman -S vkbasalt" }
                    Feature { label: "Overlay & FPS cap (MangoHud)"; on: !!page.layers.mangohud; note: page.layers.mangohud ? "" : "pacman -S mangohud" }
                    Feature { label: "FSR 1 (Proton-GE family)"; on: !!page.layers.proton_fsr; note: page.layers.proton_fsr ? "" : "install via ProtonUp-Qt" }
                    Feature { label: "Super Resolution (gamescope)"; on: !!page.layers.gamescope; note: page.layers.gamescope ? "" : "pacman -S gamescope" }
                    Feature { label: "FSR 4 auto-upgrade (proton-cachyos)"; on: !!page.layers.proton_cachyos
                              note: page.layers.proton_cachyos ? "" : "pacman -S proton-cachyos-slr" }
                    Feature { label: "Recording (gpu-screen-recorder)"; on: !!page.layers.gpu_screen_recorder
                              note: page.layers.gpu_screen_recorder ? "" : "optional" }
                    Label { width: parent.width; topPadding: 8; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                            text: "Proton versions found: " + ((page.sy.protons || []).join(", ") || "none besides Valve Proton") }
                }
            }
        }
        Card {
            width: parent.width; height: cc.height + 48
            Column {
                id: cc
                x: 24; y: 24; width: parent.width - 48
                spacing: 4
                Item {
                    width: parent.width; height: 40
                    CardTitle { icon: "memory"; text: "Shader caches"; anchors.verticalCenter: parent.verticalCenter }
                    Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "Rescan"; icon: "refresh"
                          variant: "text"; onClicked: ember.refreshCaches() }
                }
                Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant; bottomPadding: 8
                        text: "Clearing fixes stutter or glitches after driver updates. Shaders rebuild the next time each game runs, so expect a slower first launch." }
                Item {
                    width: parent.width; height: 48
                    Label { text: "Mesa driver cache (all games and apps)"; role: "body"; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                        Label { text: ((ember.caches.mesa || 0) / 1048576).toFixed(0) + " MB"; role: "body"; emphasized: true
                                anchors.verticalCenter: parent.verticalCenter }
                        Btn { text: "Clear"; icon: "delete"; variant: "tonal"; size: 36; onClicked: ember.clearCache("mesa") }
                    }
                }
                Repeater {
                    model: ember.caches.games || []
                    delegate: Item {
                        required property var modelData
                        width: parent.width; height: 48
                        Label { text: modelData.name + " (Steam)"; role: "body"; anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 220; elide: Text.ElideRight }
                        Row {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                            Label { text: (modelData.bytes / 1048576).toFixed(0) + " MB"; role: "body"; emphasized: true
                                    anchors.verticalCenter: parent.verticalCenter }
                            Btn { text: "Clear"; icon: "delete"; variant: "tonal"; size: 36; onClicked: ember.clearCache(modelData.id) }
                        }
                    }
                }
            }
        }
    }
}
