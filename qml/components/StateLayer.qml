import QtQuick
import QtQuick.Effects

// Material state layer: hover and press tint, plus a ripple that spreads from the
// pointer and is clipped to the control's rounded shape.
Item {
    id: root
    property real radius: 0
    property color tint: Theme.ink
    property bool hovered: false
    property bool pressed: false
    anchors.fill: parent
    // Shader effects are needed to clip the ripple; without them only the tint is shown.
    readonly property bool shaders: GraphicsInfo.api !== GraphicsInfo.Software && GraphicsInfo.api !== GraphicsInfo.Unknown

    function ripple(px, py) {
        if (!shaders || width <= 0) return
        dot.cx = px; dot.cy = py
        dot.reach = Math.sqrt(width * width + height * height)
        anim.restart()
    }

    Rectangle {
        anchors.fill: parent; radius: root.radius; color: root.tint
        opacity: root.pressed ? 0.10 : root.hovered ? 0.08 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
    }
    Item {
        anchors.fill: parent
        visible: anim.running
        layer.enabled: anim.running
        layer.effect: MultiEffect { maskEnabled: true; maskSource: mask; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }
        Rectangle {
            id: dot
            property real cx: 0
            property real cy: 0
            property real r: 0
            property real reach: 100
            x: cx - r; y: cy - r; width: 2 * r; height: 2 * r; radius: r
            color: root.tint; opacity: 0
        }
    }
    Rectangle { id: mask; anchors.fill: parent; radius: root.radius; visible: false; antialiasing: true
                layer.enabled: anim.running; layer.smooth: true }
    ParallelAnimation {
        id: anim
        NumberAnimation { target: dot; property: "r"; from: 6; to: dot.reach; duration: 480; easing.type: Easing.OutCubic }
        SequentialAnimation {
            NumberAnimation { target: dot; property: "opacity"; from: 0.18; to: 0.14; duration: 160 }
            NumberAnimation { target: dot; property: "opacity"; to: 0; duration: 320; easing.type: Easing.OutQuad }
        }
    }
}
