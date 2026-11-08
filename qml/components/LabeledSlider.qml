import QtQuick

Column {
    id: root
    property string label
    property string hint: ""
    property alias from: s.from
    property alias to: s.to
    property alias stepSize: s.stepSize
    property alias value: s.value
    property alias stockValue: s.stockValue
    property var format: function(v) { return Math.round(v) }
    signal moved(real v)
    spacing: 4
    Item {
        width: parent.width; height: 22
        Label { text: root.label; role: "titleS"; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
        Label { text: root.format(s.value); role: "titleS"; emphasized: true; color: Theme.primary
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter }
    }
    Label { visible: root.hint !== ""; text: root.hint; role: "bodyS"; color: Theme.inkVariant
            width: parent.width; wrapMode: Text.WordWrap; lineHeightMode: Text.ProportionalHeight; lineHeight: 1.1 }
    Slider { id: s; width: parent.width; format: root.format; onMoved: (v) => root.moved(v) }
}
