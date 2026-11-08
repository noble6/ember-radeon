pragma Singleton
import QtQuick

// Material 3 roles from one seed, tuned for a vivid "performance" accent on graphite.
QtObject {
    id: t
    property color seed: ember ? ember.accent : "#E0243C"
    property bool dark: ember ? ember.dark : true
    readonly property real h: seed.hslHue < 0 ? 0.97 : seed.hslHue
    readonly property real s: Math.max(0.55, seed.hslSaturation)
    readonly property string font: fontFamily
    readonly property string mono: "monospace"

    function tone(hue, sat, l) { return Qt.hsla(((hue % 1) + 1) % 1, sat, l / 100, 1) }
    function pick(d, l) { return dark ? d : l }

    // accent roles
    readonly property color primary: pick(tone(h, s * 0.95, 56), tone(h, s * 0.9, 44))
    readonly property color inkPrimary: pick("#FFFFFF", tone(h, s, 99))
    readonly property color primaryContainer: pick(tone(h, s * 0.7, 22), tone(h, s, 90))
    readonly property color inkPrimaryContainer: pick(tone(h, s, 92), tone(h, s, 12))
    readonly property color secondary: pick(tone(h, 0.28, 78), tone(h, 0.25, 40))
    readonly property color secondaryContainer: pick(tone(h, 0.22, 24), tone(h, 0.35, 88))
    readonly property color inkSecondaryContainer: pick(tone(h, 0.3, 90), tone(h, 0.3, 12))
    readonly property color tertiary: pick(tone(h + 0.17, s * 0.9, 76), tone(h + 0.17, s * 0.8, 40))
    readonly property color tertiaryContainer: pick(tone(h + 0.17, s * 0.6, 28), tone(h + 0.17, s, 88))
    readonly property color inkTertiaryContainer: pick(tone(h + 0.17, s, 92), tone(h + 0.17, s, 12))
    readonly property color error: pick("#FFB4AB", "#BA1A1A")

    // tinted neutrals
    readonly property color surface: pick(tone(h, 0.06, 5), tone(h, 0.12, 97))
    readonly property color surfaceDim: pick(tone(h, 0.06, 3.5), tone(h, 0.1, 90))
    readonly property color surfaceContainerLowest: pick(tone(h, 0.05, 7), tone(h, 0.1, 100))
    readonly property color surfaceContainerLow: pick(tone(h, 0.05, 9.5), tone(h, 0.12, 96))
    readonly property color surfaceContainer: pick(tone(h, 0.05, 12), tone(h, 0.12, 94))
    readonly property color surfaceContainerHigh: pick(tone(h, 0.05, 15.5), tone(h, 0.1, 91.5))
    readonly property color surfaceContainerHighest: pick(tone(h, 0.05, 20), tone(h, 0.1, 88))
    readonly property color ink: pick(tone(h, 0.06, 93), tone(h, 0.1, 10))
    readonly property color inkVariant: pick(tone(h, 0.05, 68), tone(h, 0.06, 34))
    readonly property color outline: pick(tone(h, 0.04, 46), tone(h, 0.05, 55))
    readonly property color outlineVariant: pick(tone(h, 0.04, 23), tone(h, 0.06, 82))
    // status colours for telemetry
    readonly property color good: pick("#3DDC97", "#0E8A5F")
    readonly property color warn: pick("#FFB547", "#B26A00")
    readonly property color hot: pick("#FF5470", "#C4122F")
    function heat(temp) { return temp >= 90 ? hot : temp >= 75 ? warn : good }
    readonly property color inverseSurface: pick(tone(h, 0.12, 90), tone(h, 0.12, 20))
    readonly property color inverseOnSurface: pick(tone(h, 0.12, 15), tone(h, 0.12, 95))

    // motion (M3 expressive springs, approximated)
    readonly property int fast: 200
    readonly property int medium: 380
    readonly property int slow: 560
    readonly property var spatial: Easing.OutBack
    readonly property real overshoot: 1.25

    function alpha(c, a) { c = Qt.lighter(c, 1.0); return Qt.rgba(c.r, c.g, c.b, a) }
    function mix(a, b, k) { a = Qt.lighter(a, 1.0); b = Qt.lighter(b, 1.0); return Qt.rgba(a.r + (b.r - a.r) * k, a.g + (b.g - a.g) * k, a.b + (b.b - a.b) * k, 1) }
}
