import QtQuick

// Inline problem message with an icon (never colour alone).
Rectangle {
    id: root

    property string text: ""

    visible: text !== ""
    width: parent ? parent.width : 300
    height: visible ? message.implicitHeight + Theme.space.sm * 2 : 0
    radius: Theme.radius.sm
    color: Theme.colors.dangerBg
    border.width: 1
    border.color: Theme.colors.dangerBorder
    Accessible.role: Accessible.AlertMessage
    Accessible.name: text

    Row {
        x: Theme.space.sm
        y: Theme.space.sm
        spacing: Theme.space.xs
        Icon { name: "alert"; size: 16; color: Theme.colors.dangerText }
        Txt {
            id: message
            width: root.width - Theme.space.sm * 2 - 24
            text: root.text
            color: Theme.colors.dangerText
            wrapMode: Text.WordWrap
        }
    }
}
