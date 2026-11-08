import QtQuick

Rectangle {
    id: root
    property alias text: input.text
    property string placeholder: ""
    signal accepted()
    implicitHeight: 48; implicitWidth: 220
    radius: 14
    color: Theme.surfaceContainerHighest
    border.width: input.activeFocus ? 2 : 0
    border.color: Theme.primary
    TextInput {
        id: input
        anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16
        verticalAlignment: TextInput.AlignVCenter
        color: Theme.ink; selectionColor: Theme.primary; selectedTextColor: Theme.inkPrimary
        font.family: Theme.font; font.pixelSize: 15
        clip: true
        onAccepted: root.accepted()
        Text { visible: !input.text && !input.activeFocus; text: root.placeholder; color: Theme.inkVariant
               font: input.font; anchors.verticalCenter: parent.verticalCenter }
    }
}
