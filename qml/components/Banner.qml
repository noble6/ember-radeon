import QtQuick

Rectangle {
    id: root
    property string icon: "info"
    property string title
    property string text
    property string action: ""
    property string tone: "info"   // info | warn | error
    signal triggered()
    radius: 20
    implicitHeight: Math.max(72, col.implicitHeight + 32)
    color: tone === "error" ? Theme.alpha(Theme.hot, 0.14) : tone === "warn" ? Theme.alpha(Theme.warn, 0.12)
                            : Theme.surfaceContainerHigh
    Icon { id: ic; name: root.icon; size: 24; anchors.left: parent.left; anchors.leftMargin: 20
           anchors.verticalCenter: parent.verticalCenter
           color: root.tone === "error" ? Theme.hot : root.tone === "warn" ? Theme.warn : Theme.primary }
    Column {
        id: col
        anchors.left: ic.right; anchors.leftMargin: 16
        anchors.right: btn.visible ? btn.left : parent.right; anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Label { text: root.title; role: "titleS"; emphasized: true; width: parent.width; elide: Text.ElideRight }
        Label { text: root.text; role: "bodyS"; color: Theme.inkVariant; width: parent.width; wrapMode: Text.WordWrap
                lineHeightMode: Text.ProportionalHeight; lineHeight: 1.15; textFormat: Text.StyledText }
    }
    Btn { id: btn; visible: root.action !== ""; text: root.action; variant: "tonal"
          anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter
          onClicked: root.triggered() }
}
