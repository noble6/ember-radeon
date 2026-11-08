import QtQuick

Item {
    property string text
    property string sub: ""
    implicitHeight: sub ? 48 : 28
    width: parent ? parent.width : 100
    Label { id: t; text: parent.text; role: "titleL"; emphasized: true }
    Label { visible: parent.sub !== ""; anchors.top: t.bottom; text: parent.sub; role: "bodyS"; color: Theme.inkVariant }
}
