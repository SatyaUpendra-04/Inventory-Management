import QtQuick
import QtQuick.Controls.Basic

// Square icon-only button with a tooltip (the tooltip doubles as its accessible name).
AbstractButton {
    id: control

    property string iconName: ""
    property string tip: ""
    property bool selected: false
    property int iconSize: 18

    implicitWidth: 32
    implicitHeight: 32
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.45
    Accessible.name: tip

    ToolTip.visible: hovered && tip !== ""
    ToolTip.delay: 600
    ToolTip.text: tip

    scale: down ? Theme.motion.pressScale : 1.0
    Behavior on scale { NumberAnimation { duration: Theme.motion.micro } }

    contentItem: Item {
        Icon {
            anchors.centerIn: parent
            name: control.iconName
            size: control.iconSize
            color: control.selected ? Theme.colors.accentText : Theme.colors.textMuted
        }
    }

    background: Rectangle {
        radius: Theme.radius.sm
        color: control.selected ? Theme.colors.accentSubtle
             : control.down ? Theme.colors.elementActive
             : control.hovered ? Theme.colors.element : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
        FocusRing { show: control.visualFocus }
    }
}
