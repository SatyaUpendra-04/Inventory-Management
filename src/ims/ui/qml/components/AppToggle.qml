import QtQuick
import QtQuick.Controls.Basic

// On/off switch with a sliding knob.
Switch {
    id: control

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    spacing: Theme.space.sm
    opacity: enabled ? 1 : 0.45
    font.family: Theme.type.family
    font.pixelSize: Theme.type.body

    indicator: Rectangle {
        id: track
        implicitWidth: 38
        implicitHeight: 22
        x: control.leftPadding
        anchors.verticalCenter: parent.verticalCenter
        radius: height / 2
        color: control.checked ? Theme.colors.accent
             : control.hovered ? Theme.colors.elementActive : Theme.colors.elementHover
        border.width: control.checked ? 0 : 1
        border.color: Theme.colors.controlBorder
        Behavior on color { ColorAnimation { duration: Theme.motion.standard } }

        Rectangle {
            width: 18
            height: 18
            radius: 9
            anchors.verticalCenter: parent.verticalCenter
            x: control.checked ? parent.width - width - 2 : 2
            color: "#ffffff"
            border.width: 1
            border.color: Qt.rgba(0, 0, 0, 0.08)
            Behavior on x {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: Theme.motion.standard; easing.type: Easing.OutBack; easing.overshoot: 1.2 }
            }
        }

        FocusRing { show: control.visualFocus; baseRadius: track.radius }
    }

    contentItem: Txt {
        text: control.text
        leftPadding: control.indicator.width + control.spacing
    }
}
