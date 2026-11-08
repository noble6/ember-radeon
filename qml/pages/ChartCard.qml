import QtQuick
import "../components"

Card {
    id: root
    property string title
    property string value
    property string unit
    property var series: []
    property real minY: 0
    property real maxY: NaN
    property real autoFloor: 1
    radius: 28
    implicitHeight: 260
    Label { id: t; x: 24; y: 20; text: root.title; role: "titleM"; emphasized: true }
    Row {
        anchors.right: parent.right; anchors.rightMargin: 24; y: 14
        spacing: 4
        Label { id: v; text: root.value; role: "headlineM"; emphasized: true; font.features: { "tnum": 1 } }
        Label { text: root.unit; role: "titleS"; color: Theme.inkVariant; anchors.baseline: v.baseline }
    }
    Row {
        x: 24; anchors.top: t.bottom; anchors.topMargin: 6
        spacing: 16
        Repeater {
            model: root.series.length > 1 ? root.series : []
            delegate: Row {
                required property var modelData
                spacing: 6
                Rectangle { width: 10; height: 10; radius: 5; color: modelData.color; anchors.verticalCenter: parent.verticalCenter }
                Label { text: modelData.label + (modelData.now !== undefined ? "  " + modelData.now : "")
                        role: "labelL"; color: Theme.inkVariant }
            }
        }
    }
    LineChart {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.top: parent.top; anchors.topMargin: 76
        anchors.margins: 16; anchors.bottomMargin: 18
        series: root.series; minY: root.minY; maxY: root.maxY; autoFloor: root.autoFloor
    }
}
