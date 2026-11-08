import QtQuick

// Rolling telemetry chart. `series`: [{data: [..], color, label}], NaNs are gaps.
Item {
    id: root
    property var series: []
    property real minY: 0
    property real maxY: NaN          // NaN = autoscale
    property real autoFloor: 1
    property int capacity: 120
    property bool grid: true
    property bool fill: true
    property real lineWidth: 2.5
    readonly property real topY: {
        if (!isNaN(maxY)) return maxY
        var m = autoFloor
        for (var i = 0; i < series.length; i++) {
            var d = series[i].data || []
            for (var j = 0; j < d.length; j++) if (d[j] > m) m = d[j]
        }
        return m * 1.12
    }
    onSeriesChanged: cv.requestPaint()
    onWidthChanged: cv.requestPaint()
    onHeightChanged: cv.requestPaint()
    Connections { target: Theme; function onPrimaryChanged() { cv.requestPaint() } function onDarkChanged() { cv.requestPaint() } }

    Canvas {
        id: cv
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var w = width, h = height
            var span = Math.max(1e-6, root.topY - root.minY)
            if (root.grid) {
                ctx.strokeStyle = Theme.alpha(Theme.ink, 0.07)
                ctx.lineWidth = 1
                for (var g = 1; g < 4; g++) {
                    var gy = Math.round(h * g / 4) + 0.5
                    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke()
                }
            }
            for (var s = 0; s < root.series.length; s++) {
                var ser = root.series[s]
                var d = ser.data || []
                if (d.length < 2) continue
                var step = w / (root.capacity - 1)
                var x0 = w - (d.length - 1) * step
                var pts = []
                for (var i = 0; i < d.length; i++) {
                    var v = d[i]
                    if (v !== v) { pts.push(null); continue }
                    pts.push([x0 + i * step, h - 3 - (Math.min(v, root.topY) - root.minY) / span * (h - 6)])
                }
                // fill
                if (root.fill && s === 0) {
                    var grad = ctx.createLinearGradient(0, 0, 0, h)
                    grad.addColorStop(0, Theme.alpha(ser.color, 0.32))
                    grad.addColorStop(1, Theme.alpha(ser.color, 0.0))
                    ctx.fillStyle = grad
                    ctx.beginPath()
                    var started = false, lastX = 0
                    for (var k = 0; k < pts.length; k++) {
                        if (!pts[k]) continue
                        if (!started) { ctx.moveTo(pts[k][0], h); ctx.lineTo(pts[k][0], pts[k][1]); started = true }
                        else ctx.lineTo(pts[k][0], pts[k][1])
                        lastX = pts[k][0]
                    }
                    if (started) { ctx.lineTo(lastX, h); ctx.closePath(); ctx.fill() }
                }
                ctx.strokeStyle = ser.color
                ctx.lineWidth = root.lineWidth
                ctx.lineJoin = "round"; ctx.lineCap = "round"
                ctx.beginPath()
                var pen = false
                for (var q = 0; q < pts.length; q++) {
                    if (!pts[q]) { pen = false; continue }
                    if (!pen) { ctx.moveTo(pts[q][0], pts[q][1]); pen = true } else ctx.lineTo(pts[q][0], pts[q][1])
                }
                ctx.stroke()
                // live dot
                var last = pts[pts.length - 1]
                if (last) {
                    ctx.fillStyle = ser.color
                    ctx.beginPath(); ctx.arc(last[0] - 3, last[1], 4, 0, Math.PI * 2); ctx.fill()
                }
            }
        }
    }
}
