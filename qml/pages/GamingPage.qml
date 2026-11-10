import QtQuick
import "../components"
import "Fmt.js" as F

Flickable {
    id: page
    contentHeight: col.height + 64
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    readonly property var games: ember.games
    property string selId: ""
    property bool adding: false
    readonly property var sel: {
        for (var i = 0; i < games.length; i++) if (games[i].id === selId) return games[i]
        return null
    }
    onGamesChanged: if (!sel && games.length) selId = games[0].id

    Column {
        id: col
        x: 40; y: 36
        width: page.width - 80
        spacing: 20

        Item {
            width: parent.width; height: 64
            Column {
                Label { text: "Gaming"; role: "displayS"; emphasized: true }
                Label { text: "Per-game graphics and automatic tuning profiles."; role: "body"; color: Theme.inkVariant }
            }
            Row {
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Btn { text: "Add game"; icon: "add"; variant: "tonal"
                      onClicked: { page.adding = !page.adding; if (page.adding) { ember.loadApps(); searchBox.forceActiveFocus() } } }
                Btn { text: "Rescan"; icon: "refresh"; variant: "outlined"; onClicked: ember.refreshGames() }
            }
        }

        Card {
            id: picker
            visible: page.adding
            width: parent.width; height: pk.height + 40
            property string query: ""
            property bool allApps: false
            property bool manual: false
            property var pending: null          // app whose process name we still need
            readonly property var shown: {
                var q = query.toLowerCase(), out = []
                var list = ember.installedApps || []
                for (var i = 0; i < list.length; i++) {
                    var a = list[i]
                    if (!allApps && !a.game && !a.added) continue
                    if (q && a.name.toLowerCase().indexOf(q) < 0 && a.process.toLowerCase().indexOf(q) < 0) continue
                    out.push(a)
                }
                return out
            }
            function choose(a) {
                if (a.added) { page.selId = a.steam ? "steam:" + a.steam : (a.ember_id || "exe:" + a.process); return }
                if (!a.process && !a.steam) { pending = a; procBox.text = ""; procBox.forceActiveFocus(); return }
                var id = ember.addAppGame(a.desktop, "")
                if (id) { page.selId = id; page.adding = false }
            }
            Column {
                id: pk
                x: 24; y: 20; width: parent.width - 48
                spacing: 14
                Item {
                    width: parent.width; height: 48
                    Row {
                        spacing: 8; anchors.verticalCenter: parent.verticalCenter
                        TextBox { id: searchBox; width: 280; placeholder: "Search installed apps"
                                  onTextChanged: picker.query = text }
                        Chip { text: "Games"; selected: !picker.allApps && !picker.manual; anchors.verticalCenter: parent.verticalCenter
                               onClicked: { picker.allApps = false; picker.manual = false } }
                        Chip { text: "All apps"; selected: picker.allApps && !picker.manual; anchors.verticalCenter: parent.verticalCenter
                               onClicked: { picker.allApps = true; picker.manual = false } }
                        Chip { text: "Enter manually"; selected: picker.manual; anchors.verticalCenter: parent.verticalCenter
                               onClicked: { picker.manual = true; nameBox.forceActiveFocus() } }
                    }
                    Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                          text: "Refresh"; icon: "refresh"; variant: "text"; onClicked: ember.loadApps() }
                }

                // process name prompt for launchers whose real game process can't be read from the shortcut
                Rectangle {
                    visible: !!picker.pending && !picker.manual
                    width: parent.width; height: 72; radius: 16; color: Theme.surfaceContainerHighest
                    Row {
                        anchors.verticalCenter: parent.verticalCenter; x: 16; spacing: 12
                        Label { anchors.verticalCenter: parent.verticalCenter; width: 300; wrapMode: Text.WordWrap; role: "bodyS"
                                textFormat: Text.StyledText
                                text: picker.pending ? "<b>" + picker.pending.name + "</b> starts through a launcher. Which process is the game?" : "" }
                        TextBox { id: procBox; width: 240; placeholder: "e.g. eldenring.exe"; onAccepted: procAdd.clicked() }
                        Btn { id: procAdd; text: "Add"; anchors.verticalCenter: parent.verticalCenter
                              onClicked: { var id = ember.addAppGame(picker.pending.desktop, procBox.text)
                                           if (id) { page.selId = id; picker.pending = null; page.adding = false } } }
                        Btn { text: "Cancel"; variant: "text"; anchors.verticalCenter: parent.verticalCenter; onClicked: picker.pending = null }
                    }
                }

                Flickable {
                    visible: !picker.manual
                    width: parent.width; height: Math.min(appFlow.height, 300)
                    contentHeight: appFlow.height; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Flow {
                        id: appFlow
                        width: parent.width; spacing: 8
                        Repeater {
                            model: picker.shown
                            delegate: Rectangle {
                                id: tile
                                required property var modelData
                                width: (appFlow.width - 16) / 3; height: 64; radius: 16
                                color: tm.containsMouse ? Theme.surfaceContainerHighest : Theme.surfaceContainerHigh
                                Behavior on color { ColorAnimation { duration: Theme.fast } }
                                Image { id: ti; x: 12; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40
                                        sourceSize.width: 80; sourceSize.height: 80; fillMode: Image.PreserveAspectFit
                                        asynchronous: true; source: F.fileUrl(tile.modelData.icon)
                                        visible: status === Image.Ready }
                                Icon { visible: ti.status !== Image.Ready; x: 20; anchors.verticalCenter: parent.verticalCenter
                                       name: "game"; size: 24; color: Theme.primary }
                                Column {
                                    x: 64; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 64 - 44
                                    Label { text: tile.modelData.name; role: "labelL"; emphasized: true; width: parent.width; elide: Text.ElideRight }
                                    Label { width: parent.width; elide: Text.ElideRight; role: "bodyS"; color: Theme.inkVariant
                                            text: tile.modelData.steam ? "Steam game" : tile.modelData.launcher ? "Launcher"
                                                  : tile.modelData.process ? tile.modelData.process : "Process name needed" }
                                }
                                Icon { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                                       name: tile.modelData.added ? "check" : "add"; size: 22
                                       color: tile.modelData.added ? Theme.good : Theme.inkVariant }
                                MouseArea { id: tm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: picker.choose(tile.modelData) }
                            }
                        }
                    }
                }
                Label { visible: !picker.manual && picker.shown.length === 0; role: "body"; color: Theme.inkVariant
                        text: (ember.installedApps || []).length ? "Nothing matches. Try “All apps”, or enter the game manually." : "Loading installed apps..." }

                Row {
                    visible: picker.manual
                    spacing: 12
                    TextBox { id: nameBox; width: 260; placeholder: "Name (e.g. Elden Ring via Lutris)" }
                    TextBox { id: exeBox; width: 260; placeholder: "Process name (e.g. eldenring.exe)"; onAccepted: addBtn.clicked() }
                    Btn { id: addBtn; text: "Add"; size: 48
                          onClicked: { ember.addCustomGame(nameBox.text, exeBox.text); page.selId = "exe:" + exeBox.text.trim().split("/").pop()
                                       nameBox.text = ""; exeBox.text = ""; page.adding = false } }
                }
                Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant; textFormat: Text.StyledText
                        text: "Ember switches tuning profiles whenever the game's process is running, however you start it. For graphics features (FSR, Anti-Lag, overlay), start it through Ember's launcher." }
            }
        }

        // library carousel
        ListView {
            id: shelf
            width: parent.width; height: 290
            orientation: ListView.Horizontal

            spacing: 16
            clip: true
            model: page.games
            boundsBehavior: Flickable.StopAtBounds
            delegate: Item {
                id: cover
                required property var modelData
                readonly property bool on: page.selId === modelData.id
                width: 180; height: 286
                Item {
                    id: art
                    readonly property real r: cover.on ? 26 : 18
                    x: 6; y: 6
                    width: 168; height: 236
                    scale: cover.on ? 1 : (cm.containsMouse ? 0.98 : 0.95)
                    Behavior on scale { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutBack } }
                    Rectangle { anchors.fill: parent; radius: art.r; color: Theme.surfaceContainerHigh }
                    RoundedImage {
                        anchors.fill: parent
                        radius: art.r
                        sourceSize.height: 480        // shown at 168x236: don't keep full-size art in memory
                        source: F.fileUrl(cover.modelData.cover)
                    }
                    Column {
                        visible: !cover.modelData.cover
                        anchors.centerIn: parent; width: parent.width - 24; spacing: 12
                        Image { id: ci; visible: status === Image.Ready; width: 96; height: 96; anchors.horizontalCenter: parent.horizontalCenter
                                sourceSize.width: 192; sourceSize.height: 192; fillMode: Image.PreserveAspectFit; asynchronous: true
                                source: F.fileUrl(cover.modelData.icon) }
                        Icon { visible: ci.status !== Image.Ready; name: "game"; size: 40; color: Theme.primary; anchors.horizontalCenter: parent.horizontalCenter }
                        Label { text: cover.modelData.name; role: "titleS"; width: parent.width; horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap; maximumLineCount: 3; elide: Text.ElideRight }
                    }
                    // selection ring drawn *outside* the artwork so it never overlaps or gets covered
                    Rectangle {
                        anchors.fill: parent; anchors.margins: -5
                        radius: art.r + 5
                        color: "transparent"
                        border.width: 3; border.color: Theme.primary
                        opacity: cover.on ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                    }
                    Rectangle {   // now playing badge
                        visible: ember.playing.some(function(p) { return p.id === cover.modelData.id })
                        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 10
                        height: 26; radius: 13; width: np.implicitWidth + 30
                        color: Theme.good
                        Rectangle { width: 8; height: 8; radius: 4; color: "#0B2A1C"; x: 10; anchors.verticalCenter: parent.verticalCenter
                                    SequentialAnimation on opacity { loops: Animation.Infinite; running: parent.parent.visible && ember.uiVisible
                                        NumberAnimation { to: 0.2; duration: 600 } NumberAnimation { to: 1; duration: 600 } } }
                        Label { id: np; x: 22; anchors.verticalCenter: parent.verticalCenter; text: "Playing"; role: "labelS"
                                color: "#0B2A1C"; emphasized: true }
                    }
                    Rectangle {   // profile badge
                        visible: cover.modelData.profile !== ""
                        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 10
                        height: 28; radius: 14; width: pb.implicitWidth + 20
                        color: Theme.primary
                        Label { id: pb; anchors.centerIn: parent; text: cover.modelData.profile; role: "labelL"; color: Theme.inkPrimary }
                    }
                }
                Label { anchors.top: art.bottom; anchors.topMargin: 10; x: 6; width: 168; text: cover.modelData.name
                        role: "labelL"; elide: Text.ElideRight; color: cover.on ? Theme.ink : Theme.inkVariant
                        horizontalAlignment: Text.AlignHCenter }
                MouseArea { id: cm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: page.selId = cover.modelData.id }
            }
            Label { visible: page.games.length === 0; anchors.centerIn: parent; role: "bodyL"; color: Theme.inkVariant
                    text: "No games found. Steam libraries are scanned automatically; add others with “Add game”." }
        }

        // selected game
        Row {
            visible: !!page.sel
            width: parent.width
            spacing: 16
            Column {
                width: (parent.width - 16) * 0.42
                spacing: 16
                Card {
                    width: parent.width; height: 220; radius: 28
                    RoundedImage { anchors.fill: parent; radius: 28; opacity: 0.85; sourceSize.width: 1400
                                   source: F.fileUrl(page.sel ? page.sel.hero : "") }
                    Image { visible: !!(page.sel && !page.sel.hero && page.sel.icon)
                            source: F.fileUrl(page.sel ? page.sel.icon : "")
                            anchors.right: parent.right; anchors.rightMargin: 32; anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: -16
                            width: 120; height: 120; sourceSize.width: 240; sourceSize.height: 240
                            fillMode: Image.PreserveAspectFit; asynchronous: true }
                    Rectangle { anchors.fill: parent; radius: 28
                                gradient: Gradient { GradientStop { position: 0.3; color: "transparent" }
                                                     GradientStop { position: 1.0; color: Theme.alpha("#000000", 0.75) } } }
                    Image { visible: !!(page.sel && page.sel.logo); source: F.fileUrl(page.sel ? page.sel.logo : "")
                            x: 24; anchors.bottom: parent.bottom; anchors.bottomMargin: 20
                            width: Math.min(parent.width * 0.6, sourceSize.width); height: 70
                            fillMode: Image.PreserveAspectFit; horizontalAlignment: Image.AlignLeft; asynchronous: true }
                    Label { visible: !(page.sel && page.sel.logo); x: 24; anchors.bottom: parent.bottom; anchors.bottomMargin: 20
                            text: page.sel ? page.sel.name : ""; role: "headlineM"; emphasized: true; color: "white"
                            width: parent.width - 48; elide: Text.ElideRight }
                }
                Card {
                    width: parent.width; height: prof.height + 40
                    Column {
                        id: prof
                        x: 24; y: 20; width: parent.width - 48
                        spacing: 12
                        Label { text: "Tuning profile while running"; role: "titleM"; emphasized: true }
                        Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                                text: "Ember’s service switches to this profile when the game starts and back when it exits - no launch options needed." }
                        Flow {
                            width: parent.width; spacing: 8
                            Repeater {
                                model: [""].concat(ember.profileNames)
                                delegate: Chip {
                                    required property string modelData
                                    text: modelData === "" ? "Don’t switch" : modelData
                                    selected: page.sel && page.sel.profile === modelData
                                    enabled: ember.daemon.authorized
                                    onClicked: ember.setGameProfile(page.sel.id, page.sel.name, modelData)
                                }
                            }
                        }
                    }
                }
                Card {
                    width: parent.width; height: lo.height + 40
                    visible: !!page.sel
                    Column {
                        id: lo
                        x: 24; y: 20; width: parent.width - 48
                        spacing: 12
                        Label { text: page.sel && page.sel.source === "Steam" ? "Steam launch options" : "Launching"; role: "titleM"; emphasized: true }
                        Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                                textFormat: Text.StyledText
                                text: page.sel && page.sel.source === "Steam"
                                      ? (page.sel.wired ? "Graphics features are active: launch options contain <b>ember-run</b>."
                                                        : "Graphics features need <b>ember-run %command%</b> in this game’s launch options. Ember can add it (close Steam first) or you can paste it.")
                                      : (page.sel && page.sel.launcher_file
                                         ? "Graphics features are active when you start it from the <b>" + page.sel.name + " (Ember)</b> menu entry."
                                         : "Profiles switch automatically. For graphics features, start it with <b>ember-run --id " + (page.sel ? page.sel.id : "") + " -- "
                                           + (page.sel && page.sel.launch ? "</b>its command<b>" : "&lt;command&gt;") + "</b>"
                                           + (page.sel && page.sel.launch ? ", or let Ember create a menu entry that does it." : "")) }
                        Rectangle {
                            visible: !!(page.sel && page.sel.launch_options)
                            width: parent.width; height: 40; radius: 12; color: Theme.surfaceContainerHighest
                            Label { anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                                    text: page.sel ? page.sel.launch_options : ""; font.family: Theme.mono; role: "bodyS"; elide: Text.ElideRight }
                        }
                        Row {
                            spacing: 8
                            Btn { visible: !!(page.sel && page.sel.source === "Steam")
                                  text: page.sel && page.sel.wired ? "Remove from Steam" : "Add to Steam"
                                  icon: "link"; variant: page.sel && page.sel.wired ? "outlined" : "filled"
                                  onClicked: ember.wireSteam(page.sel.appid, !page.sel.wired) }
                            Btn { visible: !!(page.sel && page.sel.source === "Other" && page.sel.launch)
                                  text: page.sel && page.sel.launcher_file ? "Remove launcher" : "Create launcher"
                                  icon: "rocket"; variant: page.sel && page.sel.launcher_file ? "outlined" : "filled"
                                  onClicked: ember.setGameLauncher(page.sel.exe, !page.sel.launcher_file) }
                            Btn { text: "Copy"; icon: "copy"; variant: "text"
                                  onClicked: ember.copy(page.sel.source === "Steam" ? "ember-run %command%"
                                                        : "ember-run --id " + page.sel.id + " -- " + (page.sel.launch || "")) }
                            Btn { visible: !!(page.sel && page.sel.source === "Other"); text: "Remove game"; icon: "delete"; variant: "text"
                                  onClicked: { ember.removeCustomGame(page.sel.exe); page.selId = "" } }
                        }
                    }
                }
            }
            Card {
                width: (parent.width - 16) * 0.58; height: gp.height + 40
                Column {
                    id: gp
                    x: 24; y: 20; width: parent.width - 48
                    spacing: 8
                    Item {
                        width: parent.width; height: 40
                        CardTitle { icon: "sparkle"; text: "Graphics"; anchors.verticalCenter: parent.verticalCenter }
                        Row {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                            Label { text: "Use global settings"; role: "labelL"; color: Theme.inkVariant; anchors.verticalCenter: parent.verticalCenter }
                            M3Switch { checked: !!(page.sel && page.sel.use_defaults)
                                       onToggled: (on) => { var g = JSON.parse(JSON.stringify(page.sel.graphics)); g.use_defaults = on
                                                            ember.setGraphics(page.sel.id, g) } }
                        }
                    }
                    GraphicsPanel {
                        width: parent.width
                        gfx: page.sel && page.sel.use_defaults ? ember.globalGraphics : (page.sel ? page.sel.graphics : {})
                        locked: false
                        onChanged: (g) => {
                            if (page.sel.use_defaults) ember.setGraphics("", g)
                            else ember.setGraphics(page.sel.id, g)
                        }
                    }
                    Label { width: parent.width; wrapMode: Text.WordWrap; role: "bodyS"; color: Theme.inkVariant
                            text: page.sel && page.sel.use_defaults ? "Editing global settings - they apply to every game launched through ember-run that doesn’t have its own."
                                                                    : "These settings apply only to this game." }
                    Rectangle {
                        width: parent.width; height: pv.implicitHeight + 20; radius: 12; color: Theme.surfaceContainerHighest
                        Label { id: pv; x: 14; y: 10; width: parent.width - 28; wrapMode: Text.WrapAnywhere
                                font.family: Theme.mono; role: "bodyS"; color: Theme.inkVariant
                                text: ember.launchPreview(page.sel && page.sel.use_defaults ? ember.globalGraphics : (page.sel ? page.sel.graphics : {})) }
                    }
                }
            }
        }
    }
}
