import QtQuick

// M3 Expressive slider: thick track, gap around the handle, value bubble while dragging.
Item {
    id: root
    property real from: 0
    property real to: 100
    property real stepSize: 1
    property real value: 0
    property real stockValue: NaN          // optional tick for the default value
    property var format: function(v) { return Math.round(v) }
    property bool showBubble: true
    signal moved(real v)
    signal committed(real v)
    implicitHeight: 44
    implicitWidth: 240
    opacity: enabled ? 1 : 0.38

    readonly property real span: Math.max(1e-9, to - from)
    readonly property real frac: Math.max(0, Math.min(1, (value - from) / span))
    readonly property real hx: 8 + frac * (width - 16)

    function valueAt(x) {
        var f = Math.max(0, Math.min(1, (x - 8) / (width - 16)))
        var v = from + f * span
        if (stepSize > 0) v = Math.round((v - from) / stepSize) * stepSize + from
        return Math.max(from, Math.min(to, v))
    }

    Rectangle {   // active
        x: 0; anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, root.hx - 6); height: 16; radius: 8
        topRightRadius: 3; bottomRightRadius: 3
        color: Theme.primary
    }
    Rectangle {   // inactive
        x: root.hx + 6; anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, root.width - x); height: 16; radius: 8
        topLeftRadius: 3; bottomLeftRadius: 3
        color: Theme.surfaceContainerHighest
    }
    Rectangle {   // stock marker
        visible: !isNaN(root.stockValue)
        width: 4; height: 4; radius: 2
        anchors.verticalCenter: parent.verticalCenter
        x: 8 + Math.max(0, Math.min(1, (root.stockValue - root.from) / root.span)) * (root.width - 16) - 2
        color: x < root.hx ? Theme.inkPrimary : Theme.inkVariant
    }
    Rectangle {   // handle
        width: ma.pressed ? 2 : 4; height: 40; radius: 2
        x: root.hx - width / 2; anchors.verticalCenter: parent.verticalCenter
        color: Theme.primary
        Behavior on width { NumberAnimation { duration: Theme.fast } }
    }
    Rectangle {   // bubble
        visible: root.showBubble
        opacity: ma.pressed ? 1 : 0
        scale: ma.pressed ? 1 : 0.6
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        Behavior on scale { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
        transformOrigin: Item.Bottom
        width: Math.max(44, bubble.implicitWidth + 20); height: 36; radius: 18
        x: root.hx - width / 2; y: -height - 4
        color: Theme.inverseSurface
        Text { id: bubble; anchors.centerIn: parent; text: root.format(root.value); color: Theme.inverseOnSurface
               font.family: Theme.font; font.pixelSize: 14; font.weight: Font.DemiBold }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        anchors.topMargin: -6; anchors.bottomMargin: -6
        cursorShape: Qt.PointingHandCursor
        preventStealing: true
        onPressed: (m) => root.moved(root.valueAt(m.x))
        onPositionChanged: (m) => { if (pressed) root.moved(root.valueAt(m.x)) }
        onReleased: root.committed(root.value)
        // No wheel handling on purpose: a slider under the pointer must never change
        // while the page is being scrolled. Wheel events fall through to the page.
    }
}
