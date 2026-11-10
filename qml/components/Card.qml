import QtQuick

Rectangle {
    property int pad: 24
    radius: 28
    color: Theme.surfaceContainer
    border.width: 1
    border.color: Theme.alpha(Theme.outlineVariant, Theme.dark ? 0.55 : 0.9)
    Behavior on color { ColorAnimation { duration: Theme.medium } }
}
