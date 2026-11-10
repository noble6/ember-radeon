import QtQuick

// Standard card heading: tonal icon, title, optional supporting line.
Item {
    id: root
    property string text
    property string sub: ""
    property string icon: ""
    property real bottomPadding: 0
    implicitHeight: Math.max(badge.visible ? 40 : 28, col.implicitHeight) + bottomPadding
    implicitWidth: (badge.visible ? 54 : 0) + col.implicitWidth
    IconBadge { id: badge; visible: root.icon !== ""; icon: root.icon || "info"; size: 40; y: 0 }
    Column {
        id: col
        x: badge.visible ? 54 : 0
        y: Math.max(0, ((badge.visible ? 40 : 28) - implicitHeight) / 2)
        Label { text: root.text; role: "titleL"; emphasized: true }
        Label { visible: root.sub !== ""; text: root.sub; role: "bodyS"; color: Theme.inkVariant }
    }
}
