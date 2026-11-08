import QtQuick
import QtQuick.Shapes

// 270° arc gauge with a big readout in the middle.
Item {
    id: root
    property real value: 0
    property real from: 0
    property real to: 100
    property string label
    property string unit
    property string text: isNaN(value) ? "—" : Math.round(value).toString()
    property string sub: ""
    property color color: Theme.primary
    property real thickness: 14
    readonly property real frac: isNaN(value) ? 0 : Math.max(0, Math.min(1, (value - from) / (to - from)))
    property real shown: frac
    Behavior on shown { NumberAnimation { duration: 450; easing.type: Easing.OutCubic } }
    implicitWidth: 180; implicitHeight: 180

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: Theme.surfaceContainerHighest; strokeWidth: root.thickness
            fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc { centerX: root.width / 2; centerY: root.height / 2
                           radiusX: root.width / 2 - root.thickness; radiusY: radiusX
                           startAngle: 135; sweepAngle: 270 }
        }
        ShapePath {
            strokeColor: root.shown > 0.004 ? root.color : "transparent"; strokeWidth: root.thickness
            fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc { centerX: root.width / 2; centerY: root.height / 2
                           radiusX: root.width / 2 - root.thickness; radiusY: radiusX
                           startAngle: 135; sweepAngle: Math.max(0.5, 270 * root.shown) }
        }
    }
    Column {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: 4
        spacing: 0
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 3
            Label { text: root.text; role: root.width > 160 ? "displayS" : "headlineM"; emphasized: true
                    font.features: { "tnum": 1 } }
            Label { text: root.unit; role: "titleS"; color: Theme.inkVariant; anchors.baseline: parent.children[0].baseline }
        }
        Label { anchors.horizontalCenter: parent.horizontalCenter; text: root.label; role: "labelL"; color: Theme.inkVariant }
        Label { visible: root.sub !== ""; anchors.horizontalCenter: parent.horizontalCenter; text: root.sub
                role: "labelS"; color: Theme.inkVariant }
    }
}
