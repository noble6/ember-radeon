import QtQuick

// Compact live metric with a sparkline.
Card {
    id: root
    property string icon
    property string label
    property string value
    property string unit
    property string sub: ""
    property var points: []
    property color accent: Theme.primary
    property real minY: 0
    property real maxY: NaN
    radius: 24
    implicitHeight: 148
    Row {
        id: head
        x: 16; y: 14
        spacing: 10
        IconBadge { icon: root.icon; size: 32; accent: root.accent; anchors.verticalCenter: parent.verticalCenter }
        Label { text: root.label; role: "labelL"; color: Theme.inkVariant; anchors.verticalCenter: parent.verticalCenter }
    }
    Row {
        x: 20; anchors.top: head.bottom; anchors.topMargin: 6
        spacing: 4
        Label { id: big; text: root.value; role: "headlineL"; emphasized: true; font.features: { "tnum": 1 } }
        Label { text: root.unit; role: "titleS"; color: Theme.inkVariant; anchors.baseline: big.baseline }
    }
    Label { visible: root.sub !== ""; text: root.sub; role: "labelS"; color: Theme.inkVariant
            anchors.right: root.right; anchors.rightMargin: 20; y: 22 }
    LineChart {
        anchors.left: root.left; anchors.right: root.right; anchors.bottom: root.bottom
        anchors.margins: 6; anchors.bottomMargin: 10
        height: 46
        grid: false; lineWidth: 2
        minY: root.minY; maxY: root.maxY
        series: [{ data: root.points, color: root.accent }]
    }
}
