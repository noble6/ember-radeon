import QtQuick

// An icon in a tonal container: the one way Ember shows an icon next to a title.
Rectangle {
    id: root
    property string icon: "info"
    property int size: 40
    property bool active: true              // false = neutral container (e.g. a switch that is off)
    property color accent: Theme.primary    // tint for both the container and the icon
    property bool round: false
    width: size; height: size
    radius: round ? size / 2 : Math.round(size * 0.3)
    color: active ? Theme.alpha(accent, Theme.dark ? 0.18 : 0.14) : Theme.surfaceContainerHighest
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Icon { anchors.centerIn: parent; name: root.icon; size: Math.round(root.size * 0.55)
           color: root.active ? root.accent : Theme.inkVariant }
}
