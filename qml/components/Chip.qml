import QtQuick

// M3 filter chip: outlined at rest, tonal with a check when selected.
Rectangle {
    id: root
    property string text
    property bool selected: false
    property string icon: ""
    signal clicked()
    height: 36
    width: row.implicitWidth + 32
    radius: selected ? height / 2 : 10
    color: selected ? Theme.secondaryContainer : "transparent"
    border.width: selected ? 0 : 1
    border.color: Theme.outline
    opacity: enabled ? 1 : 0.38
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Behavior on radius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
    scale: ma.pressed ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast } }
    StateLayer { id: sl; radius: root.radius; tint: root.selected ? Theme.inkSecondaryContainer : Theme.ink
                 hovered: ma.containsMouse; pressed: ma.pressed }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Icon { name: root.selected ? "check" : root.icon; size: 18; visible: root.selected || root.icon !== ""
               color: root.selected ? Theme.inkSecondaryContainer : Theme.primary; anchors.verticalCenter: parent.verticalCenter }
        Text { text: root.text; color: root.selected ? Theme.inkSecondaryContainer : Theme.ink
               font.family: Theme.font; font.pixelSize: 14; font.weight: Font.DemiBold; font.letterSpacing: 0.1
               anchors.verticalCenter: parent.verticalCenter }
    }
    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onPressed: (m) => sl.ripple(m.x, m.y); onClicked: root.clicked() }
}
