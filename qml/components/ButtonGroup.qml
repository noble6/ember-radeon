import QtQuick

// M3 Expressive *connected* button group. Selected item becomes a full pill.
Row {
    id: root
    property var model: []          // [{key, label, icon}]
    property string current: ""
    property int itemHeight: 56
    signal picked(string key)
    spacing: 2
    Repeater {
        model: root.model
        delegate: Rectangle {
            id: seg
            required property var modelData
            required property int index
            readonly property bool sel: root.current === modelData.key
            readonly property bool first: index === 0
            readonly property bool last: index === root.model.length - 1
            readonly property real outer: height / 2
            readonly property real inner: sel ? height / 2 : (ma.pressed ? 6 : 10)
            height: root.itemHeight
            width: (root.width - root.spacing * (root.model.length - 1)) / root.model.length
            topLeftRadius: first ? outer : inner
            bottomLeftRadius: first ? outer : inner
            topRightRadius: last ? outer : inner
            bottomRightRadius: last ? outer : inner
            Behavior on topLeftRadius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
            Behavior on bottomLeftRadius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
            Behavior on topRightRadius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
            Behavior on bottomRightRadius { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
            color: sel ? Theme.primary : Theme.surfaceContainerHighest
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Rectangle { anchors.fill: parent; color: Theme.ink; opacity: ma.containsMouse && !seg.sel ? 0.06 : 0
                        topLeftRadius: seg.topLeftRadius; bottomLeftRadius: seg.bottomLeftRadius
                        topRightRadius: seg.topRightRadius; bottomRightRadius: seg.bottomRightRadius }
            Row {
                anchors.centerIn: parent
                spacing: 8
                Icon { name: seg.modelData.icon || ""; visible: !!seg.modelData.icon; size: 20
                       color: seg.sel ? Theme.inkPrimary : Theme.inkVariant; anchors.verticalCenter: parent.verticalCenter }
                Text { text: seg.modelData.label; color: seg.sel ? Theme.inkPrimary : Theme.inkVariant
                       font.family: Theme.font; font.pixelSize: 14; font.weight: Font.DemiBold
                       anchors.verticalCenter: parent.verticalCenter }
            }
            MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: root.picked(seg.modelData.key) }
        }
    }
}
