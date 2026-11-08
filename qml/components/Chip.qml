import QtQuick

Rectangle {
    id: root
    property string text
    property bool selected: false
    property string icon: ""
    signal clicked()
    height: 36
    width: row.implicitWidth + 28
    radius: selected ? 12 : 10
    color: selected ? Theme.secondaryContainer : "transparent"
    border.width: selected ? 0 : 1
    border.color: Theme.outlineVariant
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Behavior on radius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
    Rectangle { anchors.fill: parent; radius: parent.radius; color: Theme.ink; opacity: ma.containsMouse ? 0.07 : 0 }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 6
        Icon { name: root.selected ? "check" : root.icon; size: 18; visible: root.selected || root.icon !== ""
               color: Theme.inkSecondaryContainer; anchors.verticalCenter: parent.verticalCenter }
        Text { text: root.text; color: root.selected ? Theme.inkSecondaryContainer : Theme.inkVariant
               font.family: Theme.font; font.pixelSize: 14; font.weight: Font.Medium
               anchors.verticalCenter: parent.verticalCenter }
    }
    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.clicked() }
}
