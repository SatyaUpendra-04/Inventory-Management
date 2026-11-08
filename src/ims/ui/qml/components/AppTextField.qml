import QtQuick
import QtQuick.Controls.Basic

// Labelled text field with optional icon, password reveal, helper text and error message.
Column {
    id: root

    property alias text: field.text
    property alias field: field
    property string label: ""
    property string placeholder: ""
    property string helper: ""
    property string error: ""
    property string iconName: ""
    property bool password: false
    property bool revealed: false

    signal accepted()

    width: 280
    spacing: 6

    Txt {
        visible: root.label !== ""
        text: root.label
        variant: "caption"
        font.weight: Theme.type.medium
    }

    TextField {
        id: field

        width: parent.width
        height: 34
        leftPadding: root.iconName ? 34 : Theme.space.sm
        rightPadding: root.password ? 38 : Theme.space.sm
        echoMode: root.password && !root.revealed ? TextInput.Password : TextInput.Normal
        placeholderText: root.placeholder
        placeholderTextColor: Theme.colors.textMuted
        color: Theme.colors.text
        selectionColor: Theme.colors.accentSubtleHover
        selectedTextColor: Theme.colors.text
        font.family: Theme.type.family
        font.pixelSize: Theme.type.body
        hoverEnabled: true
        Accessible.name: root.label || root.placeholder
        onAccepted: root.accepted()

        background: Rectangle {
            radius: Theme.radius.sm
            color: Theme.colors.surface
            border.width: 1
            border.color: root.error ? Theme.colors.dangerSolid
                        : field.hovered && !field.activeFocus ? Theme.colors.textMuted
                        : Theme.colors.controlBorder
            Behavior on border.color { ColorAnimation { duration: Theme.motion.micro } }
            FocusRing { show: field.activeFocus }
        }

        Icon {
            visible: root.iconName !== ""
            name: root.iconName
            size: 16
            color: Theme.colors.textMuted
            anchors.left: parent.left
            anchors.leftMargin: Theme.space.sm
            anchors.verticalCenter: parent.verticalCenter
        }

        IconButton {
            visible: root.password
            iconName: root.revealed ? "eye-off" : "eye"
            iconSize: 16
            tip: root.revealed ? qsTr("Hide password") : qsTr("Show password")
            width: 28
            height: 28
            anchors.right: parent.right
            anchors.rightMargin: 3
            anchors.verticalCenter: parent.verticalCenter
            onClicked: root.revealed = !root.revealed
        }
    }

    Row {
        visible: root.error !== "" || root.helper !== ""
        spacing: 4
        Icon {
            visible: root.error !== ""
            name: "alert"
            size: 14
            color: Theme.colors.dangerText
            anchors.verticalCenter: parent.verticalCenter
        }
        Txt {
            text: root.error || root.helper
            variant: "caption"
            color: root.error ? Theme.colors.dangerText : Theme.colors.textMuted
            width: root.width - 20
            wrapMode: Text.WordWrap
        }
    }
}
