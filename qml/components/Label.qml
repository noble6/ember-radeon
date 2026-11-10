import QtQuick

// Typography roles: display, headline, title, body, label (+ emphasized)
Text {
    property string role: "body"
    property bool emphasized: false
    readonly property var spec: ({
        "displayL": [57, 64], "displayM": [45, 52], "displayS": [36, 44],
        "headlineL": [32, 40], "headlineM": [28, 36], "headlineS": [24, 32],
        "titleL": [22, 28], "titleM": [16, 24], "titleS": [14, 20],
        "bodyL": [16, 24], "body": [14, 20], "bodyS": [12, 16],
        "labelL": [14, 20], "label": [12, 16], "labelS": [11, 16]
    })
    color: Theme.ink
    font.family: Theme.font
    font.pixelSize: spec[role][0]
    lineHeight: spec[role][1]
    lineHeightMode: Text.FixedHeight
    font.weight: emphasized ? (role.startsWith("display") || role.startsWith("headline") ? Font.ExtraBold : Font.Bold)
                            : (role.startsWith("title") || role.startsWith("label") ? Font.DemiBold : Font.Normal)
    font.letterSpacing: role.startsWith("display") ? -0.6 : role.startsWith("headline") ? -0.25 : role.startsWith("title") ? 0 : 0.1
    verticalAlignment: Text.AlignVCenter
}
