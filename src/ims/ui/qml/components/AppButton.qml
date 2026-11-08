import QtQuick
import QtQuick.Controls.Basic

// Push button. variant: primary | secondary | ghost | danger
Button {
    id: control

    property string variant: "secondary"
    property string iconName: ""
    property bool compact: false

    readonly property bool _primary: variant === "primary"
    readonly property bool _danger: variant === "danger"
    readonly property color _fg: !enabled ? Theme.colors.textDisabled
                               : _primary ? Theme.colors.onAccent
                               : _danger ? Theme.colors.dangerOnSolid
                               : Theme.colors.text
    readonly property color _fill: {
        if (!enabled) return variant === "ghost" ? "transparent" : Theme.colors.element
        if (_primary) return control.hovered && enabled ? Theme.colors.accentHover : Theme.colors.accent
        if (_danger) return control.hovered && enabled ? Qt.darker(Theme.colors.dangerSolid, 1.08)
                                                       : Theme.colors.dangerSolid
        if (control.down) return Theme.colors.elementActive
        if (control.hovered && enabled) return variant === "ghost" ? Theme.colors.element
                                                                   : Theme.colors.elementHover
        return variant === "ghost" ? "transparent" : Theme.colors.surface
    }

    implicitHeight: compact ? 28 : 34
    implicitWidth: Math.max(compact ? 28 : 34, implicitContentWidth + leftPadding + rightPadding)
    leftPadding: text ? (compact ? Theme.space.sm : Theme.space.md) : 0
    rightPadding: leftPadding
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    font.family: Theme.type.family
    font.pixelSize: compact ? Theme.type.caption : Theme.type.body
    font.weight: Theme.type.medium

    scale: down ? Theme.motion.pressScale : 1.0
    Behavior on scale { NumberAnimation { duration: Theme.motion.micro; easing.type: Easing.OutCubic } }

    transform: Translate {
        y: control.hovered && !control.down && control.enabled ? -Theme.motion.hoverLift : 0
        Behavior on y { NumberAnimation { duration: Theme.motion.micro; easing.type: Easing.OutCubic } }
    }

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: Theme.space.xs - 2
            Icon {
                visible: control.iconName !== ""
                name: control.iconName
                size: control.compact ? 14 : 16
                color: control._fg
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                visible: control.text !== ""
                text: control.text
                font: control.font
                color: control._fg
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    background: Rectangle {
        radius: Theme.radius.sm
        color: control._fill
        border.width: control.variant === "secondary" || (!control.enabled && control.variant !== "ghost") ? 1 : 0
        border.color: control.enabled ? Theme.colors.controlBorder : Theme.colors.divider
        Behavior on color { ColorAnimation { duration: Theme.motion.micro } }

        FocusRing { show: control.visualFocus; baseRadius: Theme.radius.sm }
    }
}
