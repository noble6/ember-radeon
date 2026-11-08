import QtQuick

Item {
    id: root
    property string title
    property string subtitle: ""
    property string icon: ""
    property bool checked: false
    property string badge: ""
    signal toggled(bool on)
    implicitHeight: Math.max(56, col.implicitHeight + 16)
    opacity: enabled ? 1 : 0.4
    Rectangle {
        visible: root.icon !== ""
        id: ic
        width: 40; height: 40; radius: 12
        anchors.verticalCenter: parent.verticalCenter
        color: root.checked ? Theme.primaryContainer : Theme.surfaceContainerHighest
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Icon { anchors.centerIn: parent; name: root.icon; size: 22
               color: root.checked ? Theme.primary : Theme.inkVariant }
    }
    Column {
        id: col
        anchors.left: root.icon !== "" ? ic.right : parent.left; anchors.leftMargin: root.icon !== "" ? 16 : 0
        anchors.right: sw.left; anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Row {
            spacing: 8
            Label { text: root.title; role: "titleM" }
            Rectangle {
                visible: root.badge !== ""
                anchors.verticalCenter: parent.verticalCenter
                height: 20; radius: 10; width: bt.implicitWidth + 14
                color: Theme.surfaceContainerHighest
                Label { id: bt; anchors.centerIn: parent; text: root.badge; role: "labelS"; color: Theme.inkVariant }
            }
        }
        Label { visible: root.subtitle !== ""; text: root.subtitle; role: "bodyS"; color: Theme.inkVariant
                width: parent.width; wrapMode: Text.WordWrap; lineHeightMode: Text.ProportionalHeight; lineHeight: 1.1 }
    }
    M3Switch { id: sw; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
               checked: root.checked; onToggled: (on) => root.toggled(on) }
}
