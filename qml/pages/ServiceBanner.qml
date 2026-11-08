import QtQuick
import "../components"

// Shown on pages that need the privileged service.
Column {
    width: parent ? parent.width : 400
    spacing: 12
    Banner {
        width: parent.width
        visible: !ember.daemon.connected
        tone: "warn"; icon: "lock"
        title: "Ember service isn’t running"
        text: "Monitoring works without it, but changing clocks, power and fans needs the small system service (emberd). It runs as root, validates every value and hands the fan back to firmware if it stops."
        action: "Install service"
        onTriggered: ember.installService()
    }
    Banner {
        width: parent.width
        visible: ember.daemon.connected && !ember.daemon.authorized
        tone: "warn"; icon: "lock"
        title: "Not authorized"
        text: "Your account can view state but not change it. Add it to the <b>wheel</b> group or to <b>/etc/ember/emberd.conf</b>."
    }
    Banner {
        width: parent.width
        visible: !!ember.daemon.boot_skipped
        tone: "error"; icon: "warning"
        title: "Overclock skipped this boot"
        text: "The previous boot didn’t stay up long enough after applying your clocks, so Ember booted with stock clocks to be safe. Check your profile, then apply it again."
    }
    Banner {
        width: parent.width
        visible: !!(ember.runtime && ember.runtime.error)
        tone: "error"; icon: "warning"
        title: "Some settings didn’t apply"
        text: ember.runtime && ember.runtime.error ? ember.runtime.error : ""
    }
}
