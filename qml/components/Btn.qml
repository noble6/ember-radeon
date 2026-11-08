import QtQuick

// M3 Expressive button: round at rest, squircles when pressed or selected.
Rectangle {
    id: root
    property string text: ""
    property string icon: ""
    property string variant: "filled"   // filled | tonal | outlined | text | elevated
    property bool selected: false
    property bool toggle: false
    property int size: 40                // 32 (xs) / 40 (s) / 56 (m) / 96 (l)
    signal clicked()
    signal pressedChanged2(bool down)

    readonly property bool down: ma.pressed
    readonly property color fg: variant === "filled" ? Theme.inkPrimary
                              : variant === "tonal" ? Theme.inkSecondaryContainer
                              : Theme.primary
    implicitHeight: size
    implicitWidth: row.implicitWidth + (text ? (size >= 56 ? 48 : 32) : (size - row.implicitWidth))
    radius: down ? Math.min(height / 2, size >= 56 ? 16 : 10) : (toggle && selected ? Math.min(height / 2, 16) : height / 2)
    Behavior on radius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
    color: variant === "filled" ? Theme.primary
         : variant === "tonal" ? (toggle && selected ? Theme.primary : Theme.secondaryContainer)
         : variant === "elevated" ? Theme.surfaceContainerLow : "transparent"
    border.width: variant === "outlined" ? 1 : 0
    border.color: Theme.outlineVariant
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    scale: down ? 0.96 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast } }

    Rectangle { anchors.fill: parent; radius: parent.radius; color: root.fg; opacity: ma.pressed ? 0.14 : ma.containsMouse ? 0.08 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } } }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Icon { visible: root.icon !== ""; name: root.icon; size: root.size >= 56 ? 24 : 20
               color: root.variant === "tonal" && root.toggle && root.selected ? Theme.inkPrimary : root.fg
               anchors.verticalCenter: parent.verticalCenter }
        Text {
            visible: root.text !== ""
            text: root.text
            color: root.variant === "tonal" && root.toggle && root.selected ? Theme.inkPrimary : root.fg
            font.family: Theme.font; font.pixelSize: root.size >= 56 ? 16 : 14; font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
        onPressedChanged: root.pressedChanged2(pressed)
    }
}
