import QtQuick

// Keyboard focus indicator: drawn just outside its parent, fades in and out.
Rectangle {
    id: root

    property bool show: false
    property real baseRadius: Theme.radius.sm

    anchors.fill: parent
    anchors.margins: -3
    radius: baseRadius + 3
    color: "transparent"
    border.width: 2
    border.color: Theme.colors.focusRing
    opacity: show ? 1 : 0
    visible: opacity > 0

    Behavior on opacity {
        NumberAnimation { duration: Theme.motion.micro }
    }
}
