import QtQuick
import QtQuick.Effects

// An image clipped to a rounded rectangle (plain `clip` only clips to the bounding box).
Item {
    id: root
    property alias source: img.source
    property alias status: img.status
    property alias sourceSize: img.sourceSize
    property real radius: 16
    property int fillMode: Image.PreserveAspectCrop
    Image {
        id: img
        anchors.fill: parent
        visible: false
        fillMode: root.fillMode
        asynchronous: true; smooth: true; mipmap: true
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: root.radius
        visible: false
        antialiasing: true
        layer.enabled: true
        layer.smooth: true
    }
    // Software rendering (VMs, offscreen) has no shader effects: show the plain image instead.
    readonly property bool shaders: GraphicsInfo.api !== GraphicsInfo.Software && GraphicsInfo.api !== GraphicsInfo.Unknown
    Image {
        anchors.fill: parent
        visible: !root.shaders
        source: img.source; fillMode: root.fillMode; asynchronous: true; smooth: true
    }
    MultiEffect {
        anchors.fill: parent
        visible: root.shaders && img.status === Image.Ready
        source: img
        maskEnabled: true
        maskSource: mask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }
}
