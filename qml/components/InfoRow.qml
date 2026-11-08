import QtQuick

Item {
    property string label
    property var value
    property bool ok: true
    property bool mono: false
    implicitHeight: 40
    width: parent ? parent.width : 300
    Label { text: parent.label; role: "body"; color: Theme.inkVariant; anchors.verticalCenter: parent.verticalCenter }
    Label { text: (parent.value === undefined || parent.value === null || parent.value === "") ? "—" : String(parent.value); role: "body"; emphasized: true
            color: parent.ok ? Theme.ink : Theme.inkVariant
            font.family: parent.mono ? Theme.mono : Theme.font
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, parent.width * 0.62); horizontalAlignment: Text.AlignRight; elide: Text.ElideMiddle }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.outlineVariant; opacity: 0.6 }
}
