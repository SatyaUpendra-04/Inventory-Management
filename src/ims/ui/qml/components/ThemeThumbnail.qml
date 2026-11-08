import QtQuick

// Miniature window used to preview Light, Dark and Automatic appearance.
Rectangle {
    id: root

    property string mode: "light"  // light | dark | system
    property bool chosen: false
    property bool hovered: false

    readonly property var _light: ({ window: "#f4f5f7", side: "#eceef1", card: "#ffffff", line: "#d6d9de", text: "#c7cbd2" })
    readonly property var _dark: ({ window: "#17191c", side: "#1d2024", card: "#24272c", line: "#363a40", text: "#4a4f57" })

    radius: Theme.radius.md
    color: "transparent"
    border.width: chosen ? 2 : 1
    border.color: chosen ? Theme.colors.accent : (hovered ? Theme.colors.textMuted : Theme.colors.border)
    Behavior on border.color { ColorAnimation { duration: Theme.motion.micro } }

    component Mini: Item {
        property var c
        Rectangle { anchors.fill: parent; color: c.window }
        Rectangle { width: parent.width * 0.3; height: parent.height; color: c.side }
        Rectangle { x: 6; y: 8; width: parent.width * 0.3 - 12; height: 5; radius: 2; color: Theme.colors.accent }
        Repeater {
            model: 3
            Rectangle { x: 6; y: 20 + index * 9; width: parent.width * 0.3 - 16; height: 4; radius: 2; color: c.text }
        }
        Rectangle {
            x: parent.width * 0.3 + 8; y: 10
            width: parent.width * 0.7 - 16; height: parent.height - 20
            radius: 4; color: c.card; border.width: 1; border.color: c.line
            Rectangle { x: 8; y: 8; width: parent.width * 0.55; height: 5; radius: 2; color: c.text }
            Rectangle { x: 8; y: 18; width: parent.width * 0.75; height: 4; radius: 2; color: c.line }
            Rectangle { x: 8; y: parent.height - 16; width: 28; height: 9; radius: 3; color: Theme.colors.accent }
        }
    }

    Item {
        anchors.fill: parent
        anchors.margins: root.chosen ? 3 : 2
        clip: true

        Mini { anchors.fill: parent; c: root.mode === "dark" ? root._dark : root._light }
        Item {
            visible: root.mode === "system"
            x: parent.width / 2
            width: parent.width / 2
            height: parent.height
            clip: true
            Mini { x: -parent.x; width: parent.parent.width; height: parent.height; c: root._dark }
        }
    }
}
