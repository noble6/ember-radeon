import QtQuick

Rectangle {
    property int pad: 24
    radius: 28
    color: Theme.surfaceContainer
    Behavior on color { ColorAnimation { duration: Theme.medium } }
}
