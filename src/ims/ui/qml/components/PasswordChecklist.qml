import QtQuick

// Live list of password rules; each turns green with a tick as it is met.
Column {
    id: root

    property string password: ""
    property string username: ""
    readonly property var items: Session.passwordChecklist(password, username)
    readonly property bool allMet: {
        for (var i = 0; i < items.length; ++i) if (!items[i].met) return false
        return items.length > 0
    }

    spacing: 4

    Repeater {
        model: root.items
        delegate: Row {
            required property var modelData
            spacing: 6
            Icon {
                name: modelData.met ? "circle-check" : "circle-minus"
                size: 15
                color: modelData.met ? Theme.colors.successText : Theme.colors.textMuted
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
            }
            Txt {
                text: modelData.label
                variant: "caption"
                color: modelData.met ? Theme.colors.successText : Theme.colors.textMuted
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
