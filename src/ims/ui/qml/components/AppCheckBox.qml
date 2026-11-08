import QtQuick
import QtQuick.Controls.Basic

CheckBox {
    id: control

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    spacing: Theme.space.xs
    opacity: enabled ? 1 : 0.45
    font.family: Theme.type.family
    font.pixelSize: Theme.type.body

    indicator: Rectangle {
        id: box
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        anchors.verticalCenter: parent.verticalCenter
        radius: 5
        color: control.checked ? Theme.colors.accent : Theme.colors.surface
        border.width: control.checked ? 0 : 1
        border.color: control.hovered ? Theme.colors.textMuted : Theme.colors.controlBorder
        Behavior on color { ColorAnimation { duration: Theme.motion.micro } }

        Icon {
            anchors.centerIn: parent
            name: "check"
            size: 14
            color: Theme.colors.onAccent
            scale: control.checked ? 1 : 0.4
            opacity: control.checked ? 1 : 0
            Behavior on scale { NumberAnimation { duration: Theme.motion.micro; easing.type: Easing.OutBack } }
            Behavior on opacity { NumberAnimation { duration: Theme.motion.micro } }
        }

        FocusRing { show: control.visualFocus; baseRadius: 5 }
    }

    contentItem: Txt {
        text: control.text
        leftPadding: control.indicator.width + control.spacing
    }
}
