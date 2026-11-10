import QtQuick
import QtQuick.Shapes

// M3 Expressive polar shape (cookie / flower / burst / clover…) with morphing + spin.
Item {
    id: root
    property string shape: "cookie9"
    property color color: Theme.primaryContainer
    property color color2: color
    property bool spinning: false
    property int spinDuration: 14000
    property real breathe: 0          // 0..1, audio-reactive scale
    property real strokeWidth: 0
    property color strokeColor: "transparent"

    readonly property var specs: ({
        "circle": [6, 0.0], "cookie9": [9, 0.13], "cookie12": [12, 0.085], "cookie6": [6, 0.17],
        "flower8": [8, 0.24], "burst12": [12, 0.15], "clover4": [4, 0.32], "pill": [2, 0.22],
        "moon": [3, 0.17], "sunny": [8, 0.09], "gem": [5, 0.16]
    })
    property real lobes: (specs[shape] || specs.cookie9)[0]
    property real depth: (specs[shape] || specs.cookie9)[1]
    property bool _ready: false
    Component.onCompleted: _ready = true

    onShapeChanged: if (_ready) morph.restart()
    SequentialAnimation {
        id: morph
        NumberAnimation { target: root; property: "depth"; to: 0; duration: 170; easing.type: Easing.InCubic }
        ScriptAction { script: root.lobes = (root.specs[root.shape] || root.specs.cookie9)[0] }
        NumberAnimation { target: root; property: "depth"; to: (root.specs[root.shape] || root.specs.cookie9)[1]
                          duration: 520; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
    }

    readonly property var pts: {
        const n = 144, R = Math.min(width, height) / 2 - strokeWidth / 2, cx = width / 2, cy = height / 2
        const out = []
        for (let i = 0; i <= n; i++) {
            const a = i / n * Math.PI * 2
            const r = R * (1 - depth * (1 - Math.cos(lobes * a)) / 2)
            out.push(Qt.point(cx + r * Math.cos(a), cy + r * Math.sin(a)))
        }
        return out
    }

    Shape {
        id: shp
        anchors.fill: parent
        preferredRendererType: Shape.GeometryRenderer
        scale: 1 + root.breathe * 0.08
        Behavior on scale { NumberAnimation { duration: 90 } }
        ShapePath {
            strokeWidth: root.strokeWidth > 0 ? root.strokeWidth : -1
            strokeColor: root.strokeColor
            fillGradient: LinearGradient {
                x1: 0; y1: 0; x2: root.width; y2: root.height
                GradientStop { position: 0; color: root.color }
                GradientStop { position: 1; color: root.color2 }
            }
            PathPolyline { path: root.pts }
        }
        RotationAnimator on rotation {
            from: 0; to: 360; duration: root.spinDuration
            loops: Animation.Infinite; running: root.spinning && root.visible && ember.uiVisible
        }
    }
}
