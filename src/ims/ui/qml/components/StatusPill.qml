import QtQuick

// Status label: always icon + words + colour, never colour alone.
// kind: success | warning | danger | info | neutral
Rectangle {
    id: root

    property string kind: "neutral"
    property string text: ""

    readonly property var _icons: ({
        success: "circle-check", warning: "alert", danger: "circle-x",
        info: "info", neutral: "circle-minus"
    })
    // Unknown or empty kinds (e.g. a hidden pill with no status) fall back to neutral.
    readonly property string _kind: _icons[kind] ? kind : "neutral"
    readonly property string _icon: _icons[_kind]

    implicitWidth: row.implicitWidth + 16
    implicitHeight: 22
    radius: height / 2
    color: Theme.colors[_kind + "Bg"]
    border.width: 1
    border.color: Theme.colors[_kind + "Border"]
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 4
        Icon {
            name: root._icon
            size: 13
            color: Theme.colors[root._kind + "Text"]
            anchors.verticalCenter: parent.verticalCenter
        }
        Txt {
            text: root.text
            variant: "caption"
            font.weight: Theme.type.medium
            color: Theme.colors[root._kind + "Text"]
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
