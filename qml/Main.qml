import QtQuick
import QtQuick.Window
import "components"
import "pages"

Window {
    id: win
    width: 1380; height: 900
    minimumWidth: 1100; minimumHeight: 720
    title: "Ember"
    color: Theme.surface
    property int page: 0
    property bool closeToTray: false
    Behavior on color { ColorAnimation { duration: Theme.medium } }

    onClosing: (close) => { if (closeToTray) { close.accepted = false; win.hide() } }

    NavRail {
        id: rail
        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        current: win.page
        items: [{ icon: "home", label: "Home" }, { icon: "chart", label: "Metrics" },
                { icon: "tune", label: "Tuning" }, { icon: "game", label: "Gaming" }, { icon: "videocam", label: "Record" }, { icon: "monitor", label: "Display" },
                { icon: "chip", label: "System" }, { icon: "settings", label: "Settings" }]
        onPicked: (i) => win.page = i
    }

    Rectangle {
        id: stage
        anchors.left: rail.right; anchors.right: parent.right
        anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.margins: 8; anchors.leftMargin: 0
        radius: 32
        color: Theme.surfaceContainerLowest
        clip: true
        layer.enabled: true
        layer.samples: 4
        layer.smooth: true

        component PageSlot: Item {
            id: slot
            property int index
            default property alias content: holder.data
            readonly property bool shown: win.page === index
            anchors.fill: parent
            visible: opacity > 0.01
            opacity: shown ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: shown ? 320 : 120; easing.type: Easing.OutCubic } }
            Item {
                id: holder
                visible: slot.opacity > 0.01
                width: parent.width; height: parent.height
                y: slot.shown ? 0 : 36
                Behavior on y { NumberAnimation { duration: 460; easing.type: Easing.OutBack; easing.overshoot: 1.1 } }
            }
        }
        PageSlot { index: 0; HomePage { anchors.fill: parent; onNavigate: (p) => win.page = p } }
        PageSlot { index: 1; MetricsPage { anchors.fill: parent } }
        PageSlot { index: 2; TuningPage { anchors.fill: parent } }
        PageSlot { index: 3; GamingPage { anchors.fill: parent } }
        PageSlot { index: 4; RecordPage { anchors.fill: parent } }
        PageSlot { index: 5; DisplayPage { anchors.fill: parent } }
        PageSlot { index: 6; SystemPage { anchors.fill: parent } }
        PageSlot { index: 7; SettingsPage { anchors.fill: parent } }
    }

    // busy indicator
    Rectangle {
        anchors.top: stage.top; anchors.horizontalCenter: stage.horizontalCenter
        anchors.topMargin: ember.busy ? 12 : -40
        Behavior on anchors.topMargin { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
        width: 120; height: 32; radius: 16
        color: Theme.inverseSurface
        Row {
            anchors.centerIn: parent; spacing: 8
            MorphShape { width: 16; height: 16; shape: "cookie9"; color: Theme.primary; spinning: true; spinDuration: 900
                         anchors.verticalCenter: parent.verticalCenter }
            Text { text: "Applying"; color: Theme.inverseOnSurface; font.family: Theme.font; font.pixelSize: 13
                   font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
        }
    }

    // snackbar
    Rectangle {
        id: snack
        property string text
        property bool shown: false
        anchors.horizontalCenter: stage.horizontalCenter
        y: shown ? parent.height - height - 32 : parent.height + 20
        Behavior on y { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
        height: Math.max(52, snackText.implicitHeight + 24); radius: 16
        width: Math.min(stage.width - 64, snackText.implicitWidth + 48)
        color: Theme.inverseSurface
        Label { id: snackText; anchors.centerIn: parent; width: Math.min(implicitWidth, snack.width - 48)
                text: snack.text; role: "bodyL"; color: Theme.inverseOnSurface; wrapMode: Text.WordWrap
                lineHeightMode: Text.ProportionalHeight; lineHeight: 1.1 }
        Timer { id: snackTimer; interval: 4500; onTriggered: snack.shown = false }
        Connections { target: ember; function onToast(msg) { snack.text = msg; snack.shown = true; snackTimer.restart() } }
    }

    Shortcut { sequence: "Ctrl+1"; onActivated: win.page = 0 }
    Shortcut { sequence: "Ctrl+2"; onActivated: win.page = 1 }
    Shortcut { sequence: "Ctrl+3"; onActivated: win.page = 2 }
    Shortcut { sequence: "Ctrl+4"; onActivated: win.page = 3 }
    Shortcut { sequence: "Ctrl+5"; onActivated: win.page = 4 }
    Shortcut { sequence: "Ctrl+6"; onActivated: win.page = 5 }
    Shortcut { sequence: "Ctrl+7"; onActivated: win.page = 6 }
    Shortcut { sequence: "Ctrl+8"; onActivated: win.page = 7 }
}
