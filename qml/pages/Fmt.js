.pragma library

function num(v, d) { return (v === null || v === undefined || v !== v) ? "—" : Number(v).toFixed(d || 0) }
function gib(b) { return b ? (b / 1073741824).toFixed(b >= 10 * 1073741824 ? 0 : 1) : "0" }
function profileLabel(n) {
    return ({ "BOOTUP_DEFAULT": "Default", "3D_FULL_SCREEN": "3D Fullscreen", "POWER_SAVING": "Power saving",
              "VIDEO": "Video", "VR": "VR", "COMPUTE": "Compute", "CUSTOM": "Custom" })[n] || n
}
function profileIcon(n) {
    return ({ "Stock": "chip", "Quiet": "moon", "Balanced": "tune", "Performance": "rocket" })[n] || "sparkle"
}
function profileBlurb(n) {
    return ({ "Stock": "Driver defaults, nothing touched",
              "Quiet": "Lower power, relaxed fan curve",
              "Balanced": "Default clocks, firmware fans",
              "Performance": "Max power limit, aggressive cooling" })[n] || "Custom profile"
}
// Local path -> file URL. Plain "file://" + path breaks on "#", "?" and "%" in folder names.
function fileUrl(p) {
    return p ? "file://" + encodeURI(p).replace(/#/g, "%23").replace(/\?/g, "%3F") : ""
}
function clone(o) { return JSON.parse(JSON.stringify(o)) }
