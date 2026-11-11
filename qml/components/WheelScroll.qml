import QtQuick

// Page scrolling for the mouse wheel: a fixed, generous distance per notch with a short
// glide, instead of Flickable's slow default. Touchpads keep their own 1:1 feel.
WheelHandler {
    id: h
    property Flickable view: parent as Flickable
    property real notch: 180              // pixels per wheel notch
    property real goal: 0
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    acceptedModifiers: Qt.NoModifier
    onWheel: (ev) => {
        if (!view) return
        var maxY = Math.max(0, view.contentHeight - view.height)
        var smooth = ev.pixelDelta.y !== 0 && Math.abs(ev.angleDelta.y) < 120    // touchpad
        var dy = smooth ? ev.pixelDelta.y * 1.4 : ev.angleDelta.y / 120 * notch
        var from = glide.running ? goal : view.contentY
        goal = Math.max(0, Math.min(maxY, from - dy))
        if (smooth) { glide.stop(); view.contentY = goal }
        else glide.restart()
    }
    property NumberAnimation glide: NumberAnimation {
        target: h.view; property: "contentY"; to: h.goal
        duration: 200; easing.type: Easing.OutCubic
    }
}
