import QtQuick

Rectangle {
    id: root
    property alias text: input.text
    property string placeholder: ""
    property bool password: false
    signal accepted()
    signal edited()
    implicitHeight: 48; implicitWidth: 220
    radius: height / 2
    color: Theme.surfaceContainerHighest
    border.width: input.activeFocus ? 2 : 1
    border.color: input.activeFocus ? Theme.primary : Theme.alpha(Theme.outlineVariant, 0.6)
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }
    TextInput {
        id: input
        anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20
        verticalAlignment: TextInput.AlignVCenter
        color: Theme.ink; selectionColor: Theme.primary; selectedTextColor: Theme.inkPrimary
        font.family: Theme.font; font.pixelSize: 15
        clip: true
        echoMode: root.password ? TextInput.Password : TextInput.Normal
        onAccepted: root.accepted()
        onEditingFinished: root.edited()
        Text { visible: !input.text && !input.activeFocus; text: root.placeholder; color: Theme.inkVariant
               font: input.font; anchors.verticalCenter: parent.verticalCenter }
    }
}
