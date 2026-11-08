import QtQuick

// Interactive fan curve: drag points, double-click to add, right-click to remove.
Item {
    id: root
    property var curve: [[40, 0], [80, 100]]
    property real currentTemp: NaN
    property real currentPct: NaN
    property bool editable: true
    property real tMin: 20
    property real tMax: 110
    property int dragging: -1
    property int hover: -1
    signal edited(var curve)

    readonly property real padL: 44
    readonly property real padB: 30
    readonly property real padT: 12
    readonly property real padR: 12
    readonly property real pw: width - padL - padR
    readonly property real ph: height - padT - padB
    function px(t) { return padL + (t - tMin) / (tMax - tMin) * pw }
    function py(p) { return padT + (1 - p / 100) * ph }
    function tAt(x) { return tMin + (x - padL) / pw * (tMax - tMin) }
    function pAt(y) { return (1 - (y - padT) / ph) * 100 }

    onCurveChanged: cv.requestPaint()
    onCurrentTempChanged: cv.requestPaint()
    onWidthChanged: cv.requestPaint()
    onHeightChanged: cv.requestPaint()
    onHoverChanged: cv.requestPaint()
    onEditableChanged: cv.requestPaint()
    Connections { target: Theme; function onPrimaryChanged() { cv.requestPaint() } function onDarkChanged() { cv.requestPaint() } }

    function nearest(x, y) {
        for (var i = 0; i < curve.length; i++)
            if (Math.abs(px(curve[i][0]) - x) < 14 && Math.abs(py(curve[i][1]) - y) < 14) return i
        return -1
    }
    function copyCurve() { return curve.map(function(p) { return [p[0], p[1]] }) }

    Canvas {
        id: cv
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            var c = root.curve
            ctx.font = "11px '" + Theme.font + "'"
            // grid + labels
            ctx.lineWidth = 1
            for (var t = 30; t <= root.tMax; t += 10) {
                var x = Math.round(root.px(t)) + 0.5
                ctx.strokeStyle = Theme.alpha(Theme.ink, t % 20 === 0 ? 0.08 : 0.04)
                ctx.beginPath(); ctx.moveTo(x, root.padT); ctx.lineTo(x, root.padT + root.ph); ctx.stroke()
                if (t % 20 === 0 || t === 30) {
                    ctx.fillStyle = Theme.inkVariant; ctx.textAlign = "center"
                    ctx.fillText(t + "°", x, root.height - 10)
                }
            }
            for (var p = 0; p <= 100; p += 25) {
                var y = Math.round(root.py(p)) + 0.5
                ctx.strokeStyle = Theme.alpha(Theme.ink, 0.07)
                ctx.beginPath(); ctx.moveTo(root.padL, y); ctx.lineTo(root.padL + root.pw, y); ctx.stroke()
                ctx.fillStyle = Theme.inkVariant; ctx.textAlign = "right"
                ctx.fillText(p + "%", root.padL - 8, y + 4)
            }
            if (!c || c.length < 1) return
            var col = root.editable ? Theme.primary : Theme.outline
            // area
            var grad = ctx.createLinearGradient(0, root.padT, 0, root.padT + root.ph)
            grad.addColorStop(0, Theme.alpha(col, 0.35)); grad.addColorStop(1, Theme.alpha(col, 0.02))
            ctx.fillStyle = grad
            ctx.beginPath()
            ctx.moveTo(root.padL, root.padT + root.ph)
            ctx.lineTo(root.padL, root.py(c[0][1]))
            for (var i = 0; i < c.length; i++) ctx.lineTo(root.px(c[i][0]), root.py(c[i][1]))
            ctx.lineTo(root.padL + root.pw, root.py(c[c.length - 1][1]))
            ctx.lineTo(root.padL + root.pw, root.padT + root.ph)
            ctx.closePath(); ctx.fill()
            // line
            ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.lineJoin = "round"
            ctx.beginPath(); ctx.moveTo(root.padL, root.py(c[0][1]))
            for (var j = 0; j < c.length; j++) ctx.lineTo(root.px(c[j][0]), root.py(c[j][1]))
            ctx.lineTo(root.padL + root.pw, root.py(c[c.length - 1][1]))
            ctx.stroke()
            // current temperature marker
            if (!isNaN(root.currentTemp)) {
                var cx = root.px(Math.max(root.tMin, Math.min(root.tMax, root.currentTemp)))
                ctx.setLineDash([4, 4]); ctx.strokeStyle = Theme.alpha(Theme.ink, 0.5); ctx.lineWidth = 1.5
                ctx.beginPath(); ctx.moveTo(cx, root.padT); ctx.lineTo(cx, root.padT + root.ph); ctx.stroke()
                ctx.setLineDash([])
                if (!isNaN(root.currentPct)) {
                    ctx.fillStyle = Theme.ink
                    ctx.beginPath(); ctx.arc(cx, root.py(root.currentPct), 5, 0, Math.PI * 2); ctx.fill()
                }
            }
            // handles
            if (root.editable) for (var k = 0; k < c.length; k++) {
                var hx = root.px(c[k][0]), hy = root.py(c[k][1])
                var big = k === root.dragging || k === root.hover
                ctx.fillStyle = Theme.surfaceContainer
                ctx.beginPath(); ctx.arc(hx, hy, big ? 10 : 8, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = col
                ctx.beginPath(); ctx.arc(hx, hy, big ? 7 : 5, 0, Math.PI * 2); ctx.fill()
                if (big) {
                    var txt = c[k][0] + "°C · " + c[k][1] + "%"
                    ctx.font = "bold 12px '" + Theme.font + "'"
                    var tw = ctx.measureText(txt).width + 16
                    var bx = Math.max(root.padL, Math.min(root.padL + root.pw - tw, hx - tw / 2))
                    var by = hy - 38 < root.padT ? hy + 16 : hy - 38
                    ctx.fillStyle = Theme.inverseSurface
                    ctx.beginPath(); ctx.roundedRect(bx, by, tw, 24, 12, 12); ctx.fill()
                    ctx.fillStyle = Theme.inverseOnSurface; ctx.textAlign = "center"
                    ctx.fillText(txt, bx + tw / 2, by + 16)
                }
            }
        }
    }
    MouseArea {
        anchors.fill: parent
        enabled: root.editable
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        preventStealing: true
        cursorShape: root.hover >= 0 || root.dragging >= 0 ? Qt.SizeAllCursor : Qt.CrossCursor
        onPressed: (m) => {
            var i = root.nearest(m.x, m.y)
            if (m.button === Qt.RightButton) {
                if (i >= 0 && root.curve.length > 2) {
                    var c = root.copyCurve(); c.splice(i, 1); root.edited(c)
                }
                return
            }
            root.dragging = i
        }
        onPositionChanged: (m) => {
            if (root.dragging < 0) { root.hover = root.nearest(m.x, m.y); return }
            var i = root.dragging
            var c = root.copyCurve()
            var lo = i > 0 ? c[i - 1][0] + 1 : root.tMin
            var hi = i < c.length - 1 ? c[i + 1][0] - 1 : root.tMax
            var plo = i > 0 ? c[i - 1][1] : 0
            var phi = i < c.length - 1 ? c[i + 1][1] : 100
            c[i] = [Math.round(Math.max(lo, Math.min(hi, root.tAt(m.x)))),
                    Math.round(Math.max(plo, Math.min(phi, root.pAt(m.y))))]
            root.edited(c)
        }
        onReleased: { root.dragging = -1; cv.requestPaint() }
        onExited: root.hover = -1
        onDoubleClicked: (m) => {
            if (root.curve.length >= 8) return
            var t = Math.round(root.tAt(m.x))
            var c = root.copyCurve()
            for (var i = 0; i < c.length; i++) if (c[i][0] === t) return
            var p = Math.round(ember.fanAt(c, t))
            c.push([t, p]); c.sort(function(a, b) { return a[0] - b[0] })
            root.edited(c)
        }
    }
}
