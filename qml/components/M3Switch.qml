import QtQuick

Item {
    id: root
    property bool checked: false
    signal toggled(bool on)
    implicitWidth: 52; implicitHeight: 32
    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.checked ? Theme.primary : Theme.surfaceContainerHighest
        border.width: root.checked ? 0 : 2
        border.color: Theme.outline
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
    Rectangle {
        id: knob
        readonly property real d: ma.pressed ? 28 : (root.checked ? 24 : 16)
        width: d; height: d; radius: d / 2
        anchors.verticalCenter: parent.verticalCenter
        x: root.checked ? root.width - 4 - d : (ma.pressed ? 2 : 8)
        color: root.checked ? Theme.inkPrimary : Theme.outline
        Behavior on x { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
        Behavior on width { NumberAnimation { duration: Theme.fast } }
        Behavior on height { NumberAnimation { duration: Theme.fast } }
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Icon {
            anchors.centerIn: parent
            name: "check"; size: 16
            color: Theme.inkPrimaryContainer
            opacity: root.checked ? 1 : 0
            scale: root.checked ? 1 : 0.3
            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
            Behavior on scale { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
        }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        anchors.margins: -6
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
