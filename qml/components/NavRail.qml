import QtQuick

Item {
    id: root
    property int current: 0
    property var items: []
    signal picked(int index)
    width: 96

    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 24
        spacing: 6

        MorphShape {
            id: logo
            anchors.horizontalCenter: parent.horizontalCenter
            width: 56; height: 56
            shape: (ember.snap.busy || 0) > 30 ? "burst12" : "cookie9"
            color: Theme.primary; color2: Theme.mix(Theme.primary, "#FF8A00", 0.45)
            spinning: (ember.snap.busy || 0) > 5
            spinDuration: Math.max(1500, 12000 - (ember.snap.busy || 0) * 100)
            Icon { anchors.centerIn: parent; name: "fire"; size: 28; color: Theme.inkPrimary }
        }
        Item { width: 1; height: 22 }

        Repeater {
            model: root.items
            delegate: Item {
                id: it
                required property var modelData
                required property int index
                readonly property bool sel: root.current === index
                width: 80; height: 68
                Rectangle {
                    id: pill
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 4; height: 32
                    width: it.sel ? 64 : (ma.containsMouse ? 56 : 32)
                    radius: 16
                    // M3: the active destination sits in a tonal indicator, not a solid accent block.
                    color: it.sel ? Theme.secondaryContainer : "transparent"
                    Behavior on width { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack; easing.overshoot: 2 } }
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    StateLayer { id: sl; radius: 16; tint: it.sel ? Theme.inkSecondaryContainer : Theme.ink
                                 hovered: ma.containsMouse; pressed: ma.pressed }
                    Icon { anchors.centerIn: parent; name: it.modelData.icon; size: 22
                           color: it.sel ? Theme.primary : Theme.inkVariant
                           scale: it.sel ? 1.08 : 1
                           Behavior on scale { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } } }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: pill.bottom; anchors.topMargin: 4
                    text: it.modelData.label
                    color: it.sel ? Theme.ink : Theme.inkVariant
                    font.family: Theme.font; font.pixelSize: 12; font.letterSpacing: 0.2
                    font.weight: it.sel ? Font.Bold : Font.Medium
                }
                MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onPressed: (m) => sl.ripple(pill.width / 2, pill.height / 2)
                            onClicked: root.picked(it.index) }
            }
        }
    }
    // daemon status dot
    Column {
        anchors.bottom: parent.bottom; anchors.bottomMargin: 20
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 4
        Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 10; height: 10; radius: 5
                    color: ember.daemon.connected ? (ember.daemon.authorized ? Theme.good : Theme.warn) : Theme.hot }
        Text { anchors.horizontalCenter: parent.horizontalCenter
               text: ember.daemon.connected ? "Service" : "Offline"
               color: Theme.inkVariant; font.family: Theme.font; font.pixelSize: 10 }
    }
}
