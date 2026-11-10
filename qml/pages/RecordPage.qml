import QtQuick
import "../components"

Flickable {
    id: page
    contentHeight: col.height + 64
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    readonly property var st: ember.recState
    readonly property var cfg: ember.recConfig
    readonly property var caps: ember.recCaps
    readonly property bool ok: !!caps.available
    property real now: Date.now() / 1000
    Timer { interval: 500; running: page.visible && ember.uiVisible && (page.st.recording || page.st.mode === "replay"); repeat: true
            onTriggered: page.now = Date.now() / 1000 }

    function clock(since) {
        var s = Math.max(0, Math.floor(page.now - since))
        var m = Math.floor(s / 60), h = Math.floor(m / 60)
        var mm = (m % 60 < 10 && h ? "0" : "") + (m % 60), ss = (s % 60 < 10 ? "0" : "") + (s % 60)
        return (h ? h + ":" : "") + mm + ":" + ss
    }
    function size(b) { return b > 1073741824 ? (b / 1073741824).toFixed(1) + " GB" : Math.max(1, Math.round(b / 1048576)) + " MB" }
    function ago(t) {
        var d = page.now - t
        if (d < 60) return "just now"
        if (d < 3600) return Math.floor(d / 60) + " min ago"
        if (d < 86400) return Math.floor(d / 3600) + " h ago"
        return new Date(t * 1000).toLocaleDateString()
    }
    function keyFor(id) {
        var l = (ember.hotkeys.list || [])
        for (var i = 0; i < l.length; i++) if (l[i].id === id) return l[i].keys
        return ""
    }
    readonly property var bitrate: ({ "medium": 12000, "high": 20000, "very_high": 35000, "ultra": 60000 })

    Column {
        id: col
        x: 40; y: 36
        width: page.width - 80
        spacing: 16

        Item {
            width: parent.width; height: 64
            Column {
                Label { text: "Record"; role: "displayS"; emphasized: true }
                Label { text: "Recording and Instant Replay with your GPU’s hardware encoder, so games barely lose any FPS."
                        role: "body"; color: Theme.inkVariant }
            }
            Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                  text: "Open folder"; icon: "folder"; variant: "outlined"; onClicked: ember.openPath(page.cfg.output_dir) }
        }

        Banner {
            width: parent.width
            visible: !page.ok
            tone: "warn"; icon: "videocam"
            title: "Recording needs gpu-screen-recorder"
            text: "Install it with <b>sudo pacman -S gpu-screen-recorder</b> (or your distro’s package), then restart Ember."
        }

        // ------------------------------------------------------------ controls
        Row {
            width: parent.width; spacing: 16
            enabled: page.ok
            opacity: page.ok ? 1 : 0.7

            Card {
                id: recCard
                width: (parent.width - 16) / 2; height: 236; radius: 32
                color: page.st.recording ? Theme.alpha(Theme.hot, 0.12) : Theme.surfaceContainer
                Rectangle {
                    id: bigBtn
                    x: 28; anchors.verticalCenter: parent.verticalCenter
                    width: 120; height: 120; radius: page.st.recording ? 32 : 60
                    Behavior on radius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
                    color: Theme.hot
                    scale: bma.pressed ? 0.94 : 1
                    Behavior on scale { NumberAnimation { duration: Theme.fast } }
                    Icon { anchors.centerIn: parent; name: page.st.recording ? "stop" : "videocam"; size: 52; color: "white" }
                    SequentialAnimation on opacity { running: !!page.st.recording && ember.uiVisible; loops: Animation.Infinite
                        NumberAnimation { to: 0.75; duration: 700 } NumberAnimation { to: 1; duration: 700 }
                        onRunningChanged: if (!running) bigBtn.opacity = 1 }
                    MouseArea { id: bma; anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                enabled: !page.st.busy; onClicked: ember.recAction("toggle-recording") }
                }
                Column {
                    anchors.left: bigBtn.right; anchors.leftMargin: 28; anchors.right: parent.right; anchors.rightMargin: 24
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Label { text: page.st.recording ? "● RECORDING" : "Recording"; role: "labelL"; emphasized: true
                            color: page.st.recording ? Theme.hot : Theme.inkVariant }
                    Label { text: page.st.recording ? page.clock(page.st.recording_since) : "Ready"; role: "displayS"; emphasized: true
                            font.features: { "tnum": 1 } }
                    Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                            text: page.st.recording ? "Click or press " + page.keyFor("toggle-recording") + " to stop and save."
                                                    : "Click or press " + page.keyFor("toggle-recording") + " to start. Works in fullscreen games." }
                    Btn { text: "Screenshot  " + page.keyFor("screenshot"); icon: "camera"; variant: "tonal"; size: 36
                          enabled: !page.st.busy; onClicked: ember.recAction("screenshot") }
                }
            }

            Card {
                width: (parent.width - 16) / 2; height: 236; radius: 32
                color: page.st.mode === "replay" ? Theme.alpha(Theme.good, 0.10) : Theme.surfaceContainer
                Column {
                    anchors.fill: parent; anchors.margins: 24
                    spacing: 10
                    Item {
                        width: parent.width; height: 40
                        Row {
                            spacing: 12; anchors.verticalCenter: parent.verticalCenter
                            CardTitle { icon: "replay"; text: "Instant Replay" }
                        }
                        M3Switch { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                   checked: page.st.mode === "replay"; enabled: !page.st.busy
                                   onToggled: ember.recAction("toggle-replay") }
                    }
                    Label { width: parent.width; wrapMode: Text.WordWrap; role: "body"; color: Theme.inkVariant
                            text: page.st.mode === "replay"
                                  ? "Keeping the last " + page.cfg.replay_seconds + " s in memory for " + page.clock(page.st.since)
                                    + ". Press " + page.keyFor("save-replay") + " after a great moment."
                                  : "Always-on buffer of the last " + page.cfg.replay_seconds + " s (about "
                                    + Math.round(page.bitrate[page.cfg.quality] * page.cfg.replay_seconds / 8000) + " MB of RAM). Turn on with "
                                    + page.keyFor("toggle-replay") + "." }
                    Row {
                        spacing: 8
                        enabled: page.st.mode === "replay" && !page.st.busy
                        opacity: 1
                        Btn { text: "Save replay"; icon: "save"; onClicked: ember.recAction("save-replay") }
                        Repeater {
                            model: [15, 30, 60].filter(function(s) { return s < page.cfg.replay_seconds })
                            delegate: Btn { required property int modelData; text: "Last " + modelData + " s"; variant: "outlined"
                                            onClicked: ember.saveReplaySeconds(modelData) }
                        }
                    }
                    SwitchRow { width: parent.width; title: "Start with games"
                                subtitle: "Turn Instant Replay on when a game starts and off when it closes."
                                checked: !!page.cfg.auto_replay; onToggled: (on) => ember.setRecSetting("auto_replay", on) }
                }
            }
        }

        // ------------------------------------------------------------ live stream
        Card {
            id: live
            readonly property bool on: page.st.mode === "stream"
            width: parent.width; height: ls.height + 48
            enabled: page.ok; opacity: page.ok ? 1 : 0.7
            color: on ? Theme.alpha(Theme.hot, 0.10) : Theme.surfaceContainer
            Column {
                id: ls
                x: 24; y: 24; width: parent.width - 48
                spacing: 14
                Item {
                    width: parent.width; height: 40
                    CardTitle { icon: "upload"; text: "Live stream"
                                sub: live.on ? "On air for " + page.clock(page.st.since) : "Broadcast your screen with the GPU encoder" }
                    Row {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                        Rectangle {
                            visible: live.on; anchors.verticalCenter: parent.verticalCenter
                            height: 28; radius: 14; width: lv.implicitWidth + 34; color: Theme.hot
                            Rectangle { x: 10; width: 8; height: 8; radius: 4; color: "white"; anchors.verticalCenter: parent.verticalCenter
                                        SequentialAnimation on opacity { running: live.on && ember.uiVisible; loops: Animation.Infinite
                                            NumberAnimation { to: 0.2; duration: 600 } NumberAnimation { to: 1; duration: 600 } } }
                            Label { id: lv; x: 24; anchors.verticalCenter: parent.verticalCenter; text: "LIVE"; role: "labelL"
                                    emphasized: true; color: "white" }
                        }
                        Btn { text: live.on ? "End stream" : "Go live"; icon: live.on ? "stop" : "upload"
                              variant: live.on ? "outlined" : "filled"
                              enabled: !page.st.busy && (live.on || !page.st.mode)
                              onClicked: ember.recAction("toggle-stream") }
                    }
                }
                Row {
                    spacing: 8
                    Label { text: "Service"; role: "titleS"; color: Theme.inkVariant; width: 172; anchors.verticalCenter: parent.verticalCenter }
                    Repeater {
                        model: ember.streamServices
                        delegate: Chip { required property var modelData; text: modelData.label
                                         selected: page.cfg.stream_service === modelData.key; enabled: !live.on
                                         onClicked: ember.setRecSetting("stream_service", modelData.key) }
                    }
                }
                Row {
                    visible: page.cfg.stream_service === "custom"
                    spacing: 8
                    Label { text: "Server"; role: "titleS"; color: Theme.inkVariant; width: 172; anchors.verticalCenter: parent.verticalCenter }
                    TextBox { width: 440; placeholder: "rtmp://your.server/app"; text: page.cfg.stream_url || ""; enabled: !live.on
                              onEdited: ember.setRecSetting("stream_url", text.trim()) }
                }
                Row {
                    spacing: 8
                    Label { text: "Stream key"; role: "titleS"; color: Theme.inkVariant; width: 172; anchors.verticalCenter: parent.verticalCenter }
                    TextBox { width: 440; password: true; placeholder: "Paste the key from your channel settings"
                              text: page.cfg.stream_key || ""; enabled: !live.on
                              onEdited: ember.setRecSetting("stream_key", text.trim()) }
                }
                Row {
                    spacing: 8
                    Label { text: "Bitrate"; role: "titleS"; color: Theme.inkVariant; width: 172; anchors.verticalCenter: parent.verticalCenter }
                    Repeater {
                        model: [3000, 4500, 6000, 8000, 12000]
                        delegate: Chip { required property int modelData; text: (modelData / 1000) + " Mbps"
                                         selected: (page.cfg.stream_kbps || 6000) === modelData; enabled: !live.on
                                         onClicked: ember.setRecSetting("stream_kbps", modelData) }
                    }
                }
                Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                        text: "Streams in H.264 with your capture, frame rate and audio settings below. The key is stored only on this PC and never shown in messages. Recording and Instant Replay are paused while you are live." }
            }
        }

        // ------------------------------------------------------------ settings
        Card {
            width: parent.width; height: qs.height + 48
            enabled: page.ok; opacity: page.ok ? 1 : 0.7
            Column {
                id: qs
                x: 24; y: 24; width: parent.width - 48
                spacing: 10
                CardTitle { icon: "eq"; text: "Quality" }
                component Pick: Item {
                    id: pk
                    property string label
                    property var options: []      // [{v, l}]
                    property var current
                    signal picked(var v)
                    width: parent ? parent.width : 400; height: Math.max(44, fl.height)
                    Label { text: pk.label; role: "titleS"; color: Theme.inkVariant; width: 170; anchors.verticalCenter: parent.verticalCenter }
                    Flow {
                        id: fl
                        x: 180; width: parent.width - 180; spacing: 8
                        anchors.verticalCenter: parent.verticalCenter
                        Repeater {
                            model: pk.options
                            delegate: Chip { required property var modelData; text: modelData.l
                                             selected: String(pk.current) === String(modelData.v)
                                             onClicked: pk.picked(modelData.v) }
                        }
                    }
                }
                Pick {
                    label: "Capture"
                    options: (page.caps.captures || []).filter(function(c) { return c.name !== "region" })
                             .map(function(c) { return { v: c.name, l: c.name === "portal" ? "Choose (portal)" : c.name + (c.resolution ? "  " + c.resolution : "") } })
                    current: page.cfg.capture || ((page.caps.captures || []).length ? page.caps.captures[0].name : "")
                    onPicked: (v) => ember.setRecSetting("capture", v)
                }
                Pick {
                    label: "Frame rate"
                    options: [30, 60, 120, 144, 165].map(function(f) { return { v: f, l: f + " FPS" } })
                    current: page.cfg.fps; onPicked: (v) => ember.setRecSetting("fps", v)
                }
                Pick {
                    label: "Video codec"
                    options: [{ v: "auto", l: "Auto" }].concat((page.caps.codecs || []).map(function(c) {
                                 return { v: c, l: c === "hevc" ? "HEVC (H.265)" : c === "h264" ? "H.264 (most compatible)" : "AV1" } }))
                    current: page.cfg.codec; onPicked: (v) => ember.setRecSetting("codec", v)
                }
                Pick {
                    label: "Quality"
                    options: [{ v: "medium", l: "Medium" }, { v: "high", l: "High" }, { v: "very_high", l: "Very high" }, { v: "ultra", l: "Ultra" }]
                    current: page.cfg.quality; onPicked: (v) => ember.setRecSetting("quality", v)
                }
                Pick {
                    label: "Replay length"
                    options: [15, 30, 60, 120, 300, 600].map(function(s) { return { v: s, l: s < 60 ? s + " s" : (s / 60) + " min" } })
                    current: page.cfg.replay_seconds; onPicked: (v) => ember.setRecSetting("replay_seconds", v)
                }
                Pick {
                    label: "File format"
                    options: [{ v: "mp4", l: "MP4" }, { v: "mkv", l: "MKV (safe if the PC crashes)" }]
                    current: page.cfg.container; onPicked: (v) => ember.setRecSetting("container", v)
                }
                Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant; topPadding: 4
                        text: "Encoders on this GPU: " + ((page.caps.codecs || []).join(", ").toUpperCase() || "checking…")
                              + ((page.caps.codecs || []).indexOf("av1") < 0 && (page.caps.codecs || []).length ? ". AV1 recording needs an RX 7000 or newer." : "") }
            }
        }

        Row {
            width: parent.width; spacing: 16
            enabled: page.ok; opacity: page.ok ? 1 : 0.7
            Card {
                width: (parent.width - 16) / 2; height: au.height + 48
                Column {
                    id: au
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 4
                    CardTitle { icon: "folder"; text: "Audio & files"; bottomPadding: 6 }
                    SwitchRow { width: parent.width; icon: "volume"; title: "Desktop and game audio"
                                checked: page.cfg.desktop_audio !== false; onToggled: (on) => ember.setRecSetting("desktop_audio", on) }
                    SwitchRow { width: parent.width; icon: "mic"; title: "Microphone"
                                checked: !!page.cfg.mic; onToggled: (on) => ember.setRecSetting("mic", on) }
                    SwitchRow { visible: !!page.cfg.mic; width: parent.width; title: "Microphone on its own track"
                                subtitle: "Easier to edit; some players only play the first track."
                                checked: page.cfg.mic_separate !== false; onToggled: (on) => ember.setRecSetting("mic_separate", on) }
                    SwitchRow { width: parent.width; icon: "eye"; title: "Show mouse cursor"
                                checked: page.cfg.cursor !== false; onToggled: (on) => ember.setRecSetting("cursor", on) }
                    SwitchRow { width: parent.width; icon: "folder"; title: "A folder per game"
                                checked: page.cfg.per_game_folders !== false; onToggled: (on) => ember.setRecSetting("per_game_folders", on) }
                    Label { text: "Save to"; role: "titleS"; color: Theme.inkVariant; topPadding: 8 }
                    TextBox { width: parent.width; text: page.cfg.output_dir
                              onAccepted: { ember.setRecSetting("output_dir", text); ember.refreshClips() } }
                }
            }
            Card {
                width: (parent.width - 16) / 2; height: hk.height + 48
                Column {
                    id: hk
                    x: 24; y: 24; width: parent.width - 48
                    spacing: 4
                    Item {
                        width: parent.width; height: 40
                        Row { spacing: 12; anchors.verticalCenter: parent.verticalCenter
                            CardTitle { icon: "keyboard"; text: "Hotkeys" } }
                        Btn { visible: !!ember.hotkeys.kde; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                              text: "Change"; variant: "text"; onClicked: ember.openShortcutSettings() }
                    }
                    Repeater {
                        model: ember.hotkeys.list || []
                        delegate: Item {
                            required property var modelData
                            width: parent.width; height: 44
                            Label { text: modelData.label; role: "body"; anchors.verticalCenter: parent.verticalCenter }
                            Rectangle {
                                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                height: 30; radius: 8; width: kt.implicitWidth + 20
                                color: Theme.surfaceContainerHighest; border.width: 1; border.color: Theme.outlineVariant
                                Label { id: kt; anchors.centerIn: parent; text: modelData.keys; role: "labelL"; font.family: Theme.mono }
                            }
                        }
                    }
                    Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant; topPadding: 8
                            textFormat: Text.StyledText
                            text: ember.hotkeys.kde ? "Registered with KDE, so they work inside fullscreen games. Rebind them in System Settings → Shortcuts → Ember."
                                  : "Not on KDE: bind these commands to shortcuts in your desktop’s settings:<br><b>ember --rec toggle-recording</b>, <b>ember --rec save-replay</b>, <b>ember --rec toggle-replay</b>, <b>ember --rec screenshot</b>" }
                }
            }
        }

        // ------------------------------------------------------------ clips
        Card {
            width: parent.width; height: cl.height + 48
            Column {
                id: cl
                x: 24; y: 24; width: parent.width - 48
                spacing: 2
                Item {
                    width: parent.width; height: 40
                    CardTitle { icon: "movie"; text: "Recent clips"; anchors.verticalCenter: parent.verticalCenter }
                    Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "Refresh"; icon: "refresh"
                          variant: "text"; onClicked: ember.refreshClips() }
                }
                Repeater {
                    model: ember.clips
                    delegate: Item {
                        id: clip
                        required property var modelData
                        width: parent.width; height: 56
                        Rectangle { anchors.fill: parent; radius: 14; color: Theme.ink; opacity: cma.containsMouse ? 0.05 : 0 }
                        MouseArea { id: cma; anchors.fill: parent; hoverEnabled: true; onDoubleClicked: ember.openPath(clip.modelData.path) }
                        Rectangle { id: ci; x: 8; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; radius: 12
                                    color: Theme.primaryContainer
                                    Icon { anchors.centerIn: parent; size: 22; color: Theme.primary
                                           name: clip.modelData.kind === "screenshot" ? "camera" : clip.modelData.kind === "replay" ? "replay" : "videocam" } }
                        Column {
                            anchors.left: ci.right; anchors.leftMargin: 14; anchors.right: acts.left; anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            Label { text: clip.modelData.name; role: "body"; emphasized: true; width: parent.width; elide: Text.ElideRight }
                            Label { text: (clip.modelData.game ? clip.modelData.game + "  ·  " : "") + page.size(clip.modelData.bytes) + "  ·  " + page.ago(clip.modelData.time)
                                    role: "bodyS"; color: Theme.inkVariant; width: parent.width; elide: Text.ElideRight }
                        }
                        Row {
                            id: acts
                            anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            Btn { icon: "play"; variant: "text"; size: 36; onClicked: ember.openPath(clip.modelData.path) }
                            Btn { icon: "folder"; variant: "text"; size: 36; onClicked: ember.showInFolder(clip.modelData.path) }
                            Btn { icon: "delete"; variant: "text"; size: 36; onClicked: ember.deleteClip(clip.modelData.path) }
                        }
                    }
                }
                Label { visible: ember.clips.length === 0; text: "No clips yet. Press " + page.keyFor("toggle-recording")
                                  + " to record or turn on Instant Replay."; role: "body"; color: Theme.inkVariant; topPadding: 4 }
            }
        }
    }
}
